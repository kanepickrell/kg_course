"""
Natural Language Query Engine
==============================
Translates natural language questions into SPARQL queries
using the ontology schema as context for the LLM.

The LLM never sees raw data — it only sees the schema (classes,
properties, taxonomies, relationship types) and generates SPARQL.
GraphDB executes the query and returns results.

This is the core differentiator: structured, validated, relationship-rich
data that an LLM can query with precision — not vector similarity search.

Endpoint: POST /api/query/natural
"""

import os
import json
import time
import re
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


router = APIRouter(prefix="/api/query", tags=["natural-language-query"])

# Injected by init
gdb = None

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")


# ============================================================
# MODELS
# ============================================================

class NaturalQueryRequest(BaseModel):
    question: str
    show_sparql: bool = True
    max_results: int = 25


class NaturalQueryResponse(BaseModel):
    success: bool
    question: str
    sparql: Optional[str] = None
    results: List[Dict[str, Any]] = []
    result_count: int = 0
    answer: Optional[str] = None
    timing_ms: int = 0
    error: Optional[str] = None


# ============================================================
# INIT
# ============================================================

def init_query_engine(graphdb_adapter):
    global gdb
    gdb = graphdb_adapter
    print("✓ Natural language query engine initialized")


def _require_gdb():
    if gdb is None:
        raise HTTPException(status_code=503, detail="Query engine not initialized")


# ============================================================
# SCHEMA CONTEXT BUILDER
# ============================================================

def _build_schema_context() -> str:
    """
    Build a concise text description of the ontology for the LLM.
    Includes classes, properties, taxonomies, and relationship types.
    """
    lines = []

    lines.append("=== KNOWLEDGE GRAPH SCHEMA ===")
    lines.append("")
    lines.append("NAMESPACE PREFIXES (use these in SPARQL):")
    lines.append("  proto: <https://proto.atlas/ontology/>")
    lines.append("  data:  <https://proto.atlas/data/>")
    lines.append("  tax:   <https://proto.atlas/taxonomy/>")
    lines.append("  rel:   <https://proto.atlas/relationship/>")
    lines.append("  skos:  <http://www.w3.org/2004/02/skos/core#>")
    lines.append("")

    # Classes and properties
    lines.append("CLASSES AND PROPERTIES:")
    types = gdb.get_ontology_types()
    for t in types:
        props = t.get("properties", [])
        prop_strs = []
        for p in props:
            req = " (REQUIRED)" if p.get("required") else ""
            tax = f" [taxonomy: {p['taxonomy']}]" if p.get("taxonomy") else ""
            prop_strs.append(f"    - proto:{p['name']} : {p.get('type', 'string')}{req}{tax}")

        lines.append(f"  proto:{t['collection']} ({t['label']})")
        lines.append(f"    Definition: {t.get('definition', '')}")
        if prop_strs:
            lines.append("    Properties:")
            lines.extend(prop_strs)
        lines.append("")

    # Taxonomy values
    lines.append("TAXONOMY VALUES (use these exact labels in FILTER):")
    for scheme_id in ["c2-frameworks", "mitre-tactics", "risk-levels", "teams"]:
        try:
            terms = gdb.get_taxonomy_terms(scheme_id)
            if terms:
                labels = [t["label"] for t in terms]
                lines.append(f"  {scheme_id}: {', '.join(labels)}")
        except Exception:
            pass
    lines.append("")

    # Relationship types
    lines.append("RELATIONSHIP TYPES (edge predicates):")
    lines.append("  rel:LEADS_TO — sequential dependency between modules/plans (transitive)")
    lines.append("  rel:MAPS_TO_TECHNIQUE — module or plan implements a MITRE technique")
    lines.append("  rel:SUPPORTS_TECHNIQUE — range environment supports a technique")
    lines.append("  rel:REQUIRES_TECHNIQUE — scenario requires a technique to be demonstrated")
    lines.append("  rel:OWNED_BY — artifact is owned by a team (functional, inverse: rel:OWNS)")
    lines.append("  rel:OWNS — team owns an artifact")
    lines.append("  rel:BELONGS_TO — person belongs to a team")
    lines.append("  rel:RELATED_TO — general semantic relationship (symmetric)")
    lines.append("")

    # Data patterns
    lines.append("DATA URI PATTERNS:")
    lines.append("  Instances: data:{key} (e.g., data:cs-start-c2)")
    lines.append("  Taxonomy terms are linked via proto:{property} to tax:{term-id}")
    lines.append("  Taxonomy labels: use skos:prefLabel to get display label")
    lines.append("")

    lines.append("IMPORTANT SPARQL NOTES:")
    lines.append("  - String properties are plain literals (no language tag)")
    lines.append("  - Taxonomy fields link to SKOS concepts, use skos:prefLabel to get labels")
    lines.append("  - Use OPTIONAL for non-required fields")
    lines.append("  - Filter by class: ?x a proto:LibraryModule")
    lines.append("  - Filter by relationship: ?x rel:MAPS_TO_TECHNIQUE ?y")

    return "\n".join(lines)


# ============================================================
# SPARQL GENERATION
# ============================================================

def _build_prompt(question: str, schema: str) -> str:
    return f"""You are a SPARQL query generator for a cyber range knowledge graph.

{schema}

USER QUESTION: {question}

Generate a SPARQL SELECT query that answers this question.
Return ONLY the SPARQL query — no explanation, no markdown fences, no commentary.
The query must use the prefixes defined above.
Always include human-readable labels in the SELECT (use rdfs:label, skos:prefLabel, proto:name).
Limit results to 25 unless the question implies a specific count."""


async def _call_llm(prompt: str) -> str:
    """Call the Ollama-compatible LLM endpoint."""
    import httpx

    async with httpx.AsyncClient(timeout=120.0) as client:
        res = await client.post(
            f"{OLLAMA_HOST}/v1/chat/completions",
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
            },
        )

    if res.status_code != 200:
        raise Exception(f"LLM returned {res.status_code}: {res.text[:200]}")

    data = res.json()
    content = data["choices"][0]["message"]["content"].strip()

    # Strip markdown fences if present
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

    # Remove any "sparql" language tag
    if content.lower().startswith("sparql"):
        content = content[6:].strip()

    return content


def _extract_sparql(raw: str) -> str:
    """Extract a clean SPARQL query from LLM output."""
    # Try to find SELECT...} pattern
    match = re.search(r'(SELECT\s.+)', raw, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return raw.strip()


async def _generate_answer(question: str, results: List[Dict], sparql: str) -> str:
    """Use LLM to generate a natural language answer from SPARQL results."""
    if not results:
        return "No results found for your query."

    # Format results as a concise table
    result_text = json.dumps(results[:10], indent=2, default=str)

    prompt = f"""Given this question and the query results, provide a clear, concise answer.
Do not mention SPARQL or databases. Just answer the question naturally.

Question: {question}

Results ({len(results)} total):
{result_text}

Answer in 2-3 sentences. Be specific — cite names, counts, and key details from the results."""

    try:
        return await _call_llm(prompt)
    except Exception:
        # Fallback: just describe what was found
        return f"Found {len(results)} results."


# ============================================================
# ENDPOINT
# ============================================================

@router.post("/natural", response_model=NaturalQueryResponse)
async def natural_language_query(request: NaturalQueryRequest):
    """
    Translate a natural language question into SPARQL, execute it,
    and return structured results with a natural language answer.

    Falls back to pattern-matched SPARQL when LLM is unavailable.
    """
    _require_gdb()

    start = time.time()
    question = request.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    sparql = None
    llm_available = True

    try:
        # 1. Try LLM-generated SPARQL
        schema = _build_schema_context()
        prompt = _build_prompt(question, schema)
        raw_sparql = await _call_llm(prompt)
        sparql = _extract_sparql(raw_sparql)
    except Exception as llm_err:
        # 2. LLM unavailable — fall back to pattern matching
        llm_available = False
        sparql = _pattern_match_sparql(question)
        if not sparql:
            elapsed = int((time.time() - start) * 1000)
            return NaturalQueryResponse(
                success=False,
                question=question,
                error=f"LLM unavailable and no pattern match for this question. LLM error: {str(llm_err)[:100]}",
                timing_ms=elapsed,
            )

    try:
        # 3. Execute SPARQL against GraphDB
        try:
            results = gdb.sparql_query(sparql)
        except Exception as e:
            if llm_available:
                # Try LLM fix
                fix_prompt = f"SPARQL query failed: {str(e)[:200]}\n\nQuery:\n{sparql}\n\nFix it. Return ONLY corrected SPARQL."
                fixed_raw = await _call_llm(fix_prompt)
                sparql = _extract_sparql(fixed_raw)
                results = gdb.sparql_query(sparql)
            else:
                raise

        # 4. Trim results
        results = results[:request.max_results]

        # 5. Generate answer
        if llm_available:
            answer = await _generate_answer(question, results, sparql)
        else:
            answer = _generate_mock_answer(question, results)

        elapsed = int((time.time() - start) * 1000)

        return NaturalQueryResponse(
            success=True,
            question=question,
            sparql=sparql if request.show_sparql else None,
            results=results,
            result_count=len(results),
            answer=answer,
            timing_ms=elapsed,
        )

    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        return NaturalQueryResponse(
            success=False,
            question=question,
            sparql=sparql,
            error=str(e),
            timing_ms=elapsed,
        )


# ============================================================
# PATTERN MATCHING (LLM fallback)
# ============================================================

def _pattern_match_sparql(question: str) -> Optional[str]:
    """
    Match common question patterns to pre-built SPARQL queries.
    Used when LLM is unavailable.
    """
    q = question.lower().strip().rstrip("?")

    # --- Library Modules ---
    if any(kw in q for kw in ["library module", "modules", "what modules"]):
        if any(kw in q for kw in ["credential", "cred"]):
            return """SELECT ?name ?description ?tactic ?riskLevel WHERE {
    ?m a proto:LibraryModule ;
       proto:name ?name ;
       proto:tactic "Credential Access" .
    OPTIONAL { ?m proto:description ?description }
    OPTIONAL { ?m proto:riskLevel ?rl . ?rl skos:prefLabel ?riskLevel }
} ORDER BY ?name"""

        if any(kw in q for kw in ["cobalt", "c2", "framework"]):
            return """SELECT ?name ?description ?tactic WHERE {
    ?m a proto:LibraryModule ;
       proto:name ?name .
    ?m proto:category ?cat .
    ?cat skos:prefLabel ?framework .
    FILTER(CONTAINS(LCASE(?framework), "cobalt"))
    OPTIONAL { ?m proto:description ?description }
    OPTIONAL { ?m proto:tactic ?tactic }
} ORDER BY ?name"""

        if any(kw in q for kw in ["high risk", "high-risk", "dangerous"]):
            return """SELECT ?name ?tactic ?riskLevel WHERE {
    ?m a proto:LibraryModule ;
       proto:name ?name .
    ?m proto:riskLevel ?rl .
    ?rl skos:prefLabel ?riskLevel .
    FILTER(?riskLevel = "High" || ?riskLevel = "Critical")
    OPTIONAL { ?m proto:tactic ?tactic }
} ORDER BY ?name"""

        if "opfor" in q:
            return """SELECT ?name ?tactic ?riskLevel WHERE {
    ?m a proto:LibraryModule ;
       proto:name ?name .
    ?m proto:owner ?team .
    ?team skos:prefLabel "OPFOR" .
    OPTIONAL { ?m proto:tactic ?tactic }
    OPTIONAL { ?m proto:riskLevel ?rl . ?rl skos:prefLabel ?riskLevel }
} ORDER BY ?name"""

        # Generic: list all modules
        return """SELECT ?name ?tactic ?category ?riskLevel ?owner WHERE {
    ?m a proto:LibraryModule ;
       proto:name ?name .
    OPTIONAL { ?m proto:tactic ?tactic }
    OPTIONAL { ?m proto:category ?cat . ?cat skos:prefLabel ?category }
    OPTIONAL { ?m proto:riskLevel ?rl . ?rl skos:prefLabel ?riskLevel }
    OPTIONAL { ?m proto:owner ?ow . ?ow skos:prefLabel ?owner }
} ORDER BY ?name"""

    # --- TTPs ---
    if any(kw in q for kw in ["ttp", "technique", "mitre", "att&ck", "attack"]):
        return """SELECT ?name ?mitreId ?description WHERE {
    ?t a proto:TTP ;
       proto:name ?name .
    OPTIONAL { ?t proto:mitreId ?mitreId }
    OPTIONAL { ?t proto:description ?description }
} ORDER BY ?name"""

    # --- Teams ---
    if any(kw in q for kw in ["team", "teams", "who owns", "ownership"]):
        return """SELECT ?teamName (COUNT(?m) AS ?moduleCount) WHERE {
    ?team a proto:Team ;
          proto:name ?teamName .
    OPTIONAL {
        ?m a proto:LibraryModule .
        ?m proto:owner ?team .
    }
} GROUP BY ?teamName ORDER BY DESC(?moduleCount)"""

    # --- Relationships ---
    if any(kw in q for kw in ["related", "connected", "linked", "relationship"]):
        if "kerberoast" in q:
            return """SELECT ?fromName ?relType ?toName WHERE {
    {
        data:kerberoast ?rel ?to .
        FILTER(STRSTARTS(STR(?rel), "https://proto.atlas/relationship/"))
        data:kerberoast proto:name ?fromName .
        ?to proto:name ?toName .
        BIND(STRAFTER(STR(?rel), "https://proto.atlas/relationship/") AS ?relType)
    } UNION {
        ?from ?rel data:kerberoast .
        FILTER(STRSTARTS(STR(?rel), "https://proto.atlas/relationship/"))
        ?from proto:name ?fromName .
        data:kerberoast proto:name ?toName .
        BIND(STRAFTER(STR(?rel), "https://proto.atlas/relationship/") AS ?relType)
    }
}"""
        # Generic: all edges
        return """SELECT ?fromName ?relType ?toName WHERE {
    ?from ?rel ?to .
    FILTER(STRSTARTS(STR(?rel), "https://proto.atlas/relationship/"))
    FILTER(STRSTARTS(STR(?from), "https://proto.atlas/data/"))
    FILTER(STRSTARTS(STR(?to), "https://proto.atlas/data/"))
    ?from proto:name ?fromName .
    ?to proto:name ?toName .
    BIND(STRAFTER(STR(?rel), "https://proto.atlas/relationship/") AS ?relType)
} LIMIT 25"""

    # --- Attack chains ---
    if any(kw in q for kw in ["chain", "path", "leads to", "attack flow", "execution"]):
        return """SELECT ?fromName ?toName WHERE {
    ?from rel:LEADS_TO ?to .
    ?from proto:name ?fromName .
    ?to proto:name ?toName .
} ORDER BY ?fromName"""

    # --- Coverage / gaps ---
    if any(kw in q for kw in ["coverage", "missing", "gap", "which tactic"]):
        return """SELECT ?tacticLabel (COUNT(?m) AS ?moduleCount) WHERE {
    ?tactic a skos:Concept ;
            skos:inScheme ?scheme ;
            skos:prefLabel ?tacticLabel .
    FILTER(CONTAINS(STR(?scheme), "mitre-tactics"))
    OPTIONAL {
        ?m a proto:LibraryModule ;
           proto:tactic ?tacticLabel .
    }
} GROUP BY ?tacticLabel ORDER BY ?moduleCount"""

    # --- Count queries ---
    if any(kw in q for kw in ["how many", "count", "total"]):
        if "module" in q:
            return """SELECT (COUNT(?m) AS ?count) WHERE { ?m a proto:LibraryModule }"""
        if "ttp" in q:
            return """SELECT (COUNT(?t) AS ?count) WHERE { ?t a proto:TTP }"""
        if "team" in q:
            return """SELECT (COUNT(?t) AS ?count) WHERE { ?t a proto:Team }"""
        # Generic count
        return """SELECT ?type (COUNT(?x) AS ?count) WHERE {
    ?x a ?type .
    FILTER(STRSTARTS(STR(?x), "https://proto.atlas/data/"))
    FILTER(STRSTARTS(STR(?type), "https://proto.atlas/ontology/"))
} GROUP BY ?type ORDER BY DESC(?count)"""

    # --- Fallback: full graph summary ---
    if any(kw in q for kw in ["everything", "all", "summary", "overview", "graph"]):
        return """SELECT ?type (COUNT(?x) AS ?count) WHERE {
    ?x a ?type .
    FILTER(STRSTARTS(STR(?x), "https://proto.atlas/data/"))
    FILTER(STRSTARTS(STR(?type), "https://proto.atlas/ontology/"))
} GROUP BY ?type ORDER BY DESC(?count)"""

    return None


def _generate_mock_answer(question: str, results: List[Dict]) -> str:
    """Generate a simple answer from results without LLM."""
    if not results:
        return "No results found for your query."

    count = len(results)
    keys = list(results[0].keys())

    # Try to build a meaningful summary
    if count == 1 and "count" in results[0]:
        return f"The count is {results[0]['count']}."

    # If results have a 'name' column, list them
    name_key = next((k for k in keys if k.lower() in ("name", "teamname", "fromname", "tacticlabel")), None)
    if name_key:
        names = [str(r.get(name_key, "")) for r in results[:8]]
        listed = ", ".join(names)
        suffix = f" (and {count - 8} more)" if count > 8 else ""
        return f"Found {count} results: {listed}{suffix}."

    return f"Query returned {count} results across {len(keys)} columns: {', '.join(keys)}."


# ============================================================
# SCHEMA INTROSPECTION ENDPOINT
# ============================================================

@router.get("/schema")
async def get_query_schema():
    """Return the schema context that the LLM uses for query generation."""
    _require_gdb()
    return {
        "schema": _build_schema_context(),
        "model": OLLAMA_MODEL,
        "host": OLLAMA_HOST,
    }


# ============================================================
# EXAMPLE QUERIES
# ============================================================

@router.get("/examples")
async def get_example_queries():
    """Return example natural language queries for the demo UI."""
    return {
        "examples": [
            {
                "category": "Inventory",
                "questions": [
                    "What library modules do we have?",
                    "Show me all TTPs in the graph",
                    "List all scenarios and their difficulty level",
                ],
            },
            {
                "category": "Technique Coverage",
                "questions": [
                    "What techniques does the Neon Saguaro scenario require?",
                    "Which techniques does the Exchange Lab v2 support?",
                    "What technique does the Dump Credentials module map to?",
                ],
            },
            {
                "category": "Gap Analysis",
                "questions": [
                    "Which required techniques have no library module mapping?",
                    "What techniques are required by Neon Saguaro but not covered by any execution plan?",
                    "Show me techniques that are fully covered by all three teams",
                ],
            },
            {
                "category": "Operational",
                "questions": [
                    "Which modules are mapped to Credential Access techniques?",
                    "What range environments support the T1190 technique?",
                    "Is the Neon Saguaro scenario mission ready?",
                ],
            },
        ]
    }


@router.post("/subgraph")
async def get_result_subgraph(request: dict):
    """
    Given SPARQL results, extract node URIs and return a visualization subgraph.
    Fetches the nodes and all edges between them.

    Body: { "results": [...], "node_keys": ["cs-start-c2", "kerberoast"] }
    Either provide raw SPARQL results (will extract data: URIs) or explicit node_keys.
    """
    _require_gdb()

    node_keys = set()

    # Extract from explicit keys
    for key in request.get("node_keys", []):
        node_keys.add(key)

    # Extract from SPARQL results — find any data: URIs
    node_names = set()
    for row in request.get("results", []):
        for field, val in row.items():
            val_str = str(val)
            if val_str.startswith("https://proto.atlas/data/"):
                key = val_str.replace("https://proto.atlas/data/", "")
                node_keys.add(key)
            # Collect name-like fields for fallback lookup
            elif field.lower() in ("name", "fromname", "toname", "teamname", "modulename", "ttpname"):
                if val_str and val_str != "None":
                    node_names.add(val_str)

    # If no URIs found, resolve names to keys via SPARQL
    if not node_keys and node_names:
        name_filters = " || ".join(f'(?name = "{n}")' for n in node_names)
        resolve_query = f"""
        SELECT ?node ?name WHERE {{
            ?node proto:name ?name .
            FILTER(STRSTARTS(STR(?node), "https://proto.atlas/data/"))
            FILTER({name_filters})
        }}
        """
        try:
            resolved = gdb.sparql_query(resolve_query)
            for row in resolved:
                uri = row.get("node", "")
                if uri.startswith("https://proto.atlas/data/"):
                    node_keys.add(uri.replace("https://proto.atlas/data/", ""))
        except Exception as e:
            print(f"⚠️ Subgraph name resolution failed: {e}")

    if not node_keys:
        return {"nodes": [], "edges": [], "count": 0}

    # Build SPARQL to get node details and edges between them
    uri_values = " ".join(f"data:{k}" for k in node_keys)

    # Get node details
    node_query = f"""
    SELECT ?node ?name ?type ?typeLabel WHERE {{
        VALUES ?node {{ {uri_values} }}
        ?node proto:name ?name .
        ?node a ?type .
        FILTER(STRSTARTS(STR(?type), "https://proto.atlas/ontology/"))
        ?type rdfs:label ?typeLabel .
    }}
    """

    # Get edges between these nodes
    edge_query = f"""
    SELECT ?from ?rel ?to ?relLabel WHERE {{
        VALUES ?from {{ {uri_values} }}
        VALUES ?to {{ {uri_values} }}
        ?from ?rel ?to .
        FILTER(STRSTARTS(STR(?rel), "https://proto.atlas/relationship/"))
        BIND(STRAFTER(STR(?rel), "https://proto.atlas/relationship/") AS ?relLabel)
    }}
    """

    # Also get edges FROM these nodes to any neighbor (1 hop out)
    neighbor_edge_query = f"""
    SELECT ?from ?rel ?to ?toName ?toType WHERE {{
        VALUES ?from {{ {uri_values} }}
        ?from ?rel ?to .
        FILTER(STRSTARTS(STR(?rel), "https://proto.atlas/relationship/"))
        FILTER(STRSTARTS(STR(?to), "https://proto.atlas/data/"))
        ?to proto:name ?toName .
        OPTIONAL {{ ?to a ?toType . FILTER(STRSTARTS(STR(?toType), "https://proto.atlas/ontology/")) }}
    }}
    """

    try:
        node_rows = gdb.sparql_query(node_query)
        edge_rows = gdb.sparql_query(edge_query)
        neighbor_rows = gdb.sparql_query(neighbor_edge_query)
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    # Build node map
    TYPE_COLORS = {
        "LibraryModule": "#6EBE46",
        "TTP": "#E84855",
        "Team": "#4DA8DA",
        "Person": "#FFA552",
        "ExecutionPlan": "#9B5DE5",
        "Scenario": "#F15BB5",
        "DevelopmentStory": "#FFD166",
        "RobotLog": "#06D6A0",
        "RangeEnvironment": "#118AB2",
    }

    nodes = {}
    for row in node_rows:
        node_uri = row.get("node", "")
        key = node_uri.replace("https://proto.atlas/data/", "")
        type_label = row.get("typeLabel", "Unknown")
        nodes[key] = {
            "id": key,
            "label": row.get("name", key),
            "type": type_label,
            "cluster": type_label,
            "importance": 1.0,
            "size": 8,
            "color": TYPE_COLORS.get(type_label, "#888"),
            "highlighted": True,  # These are the query-matched nodes
        }

    # Add neighbor nodes
    for row in neighbor_rows:
        to_uri = row.get("to", "")
        to_key = to_uri.replace("https://proto.atlas/data/", "")
        if to_key not in nodes:
            to_type = (row.get("toType") or "").replace("https://proto.atlas/ontology/", "")
            nodes[to_key] = {
                "id": to_key,
                "label": row.get("toName", to_key),
                "type": to_type or "Unknown",
                "cluster": to_type or "Unknown",
                "importance": 0.5,
                "size": 5,
                "color": TYPE_COLORS.get(to_type, "#555"),
                "highlighted": False,  # Neighbor, not directly matched
            }

    # Build edges
    edges = []
    seen_edges = set()

    for row in edge_rows:
        from_key = row.get("from", "").replace("https://proto.atlas/data/", "")
        to_key = row.get("to", "").replace("https://proto.atlas/data/", "")
        rel = row.get("relLabel", "RELATED")
        edge_id = f"{from_key}-{rel}-{to_key}"
        if edge_id not in seen_edges:
            seen_edges.add(edge_id)
            edges.append({
                "id": edge_id,
                "source": from_key,
                "target": to_key,
                "type": rel,
                "weight": 1.0,
            })

    for row in neighbor_rows:
        from_key = row.get("from", "").replace("https://proto.atlas/data/", "")
        to_key = row.get("to", "").replace("https://proto.atlas/data/", "")
        rel_uri = row.get("rel", "")
        rel = rel_uri.replace("https://proto.atlas/relationship/", "")
        edge_id = f"{from_key}-{rel}-{to_key}"
        if edge_id not in seen_edges:
            seen_edges.add(edge_id)
            edges.append({
                "id": edge_id,
                "source": from_key,
                "target": to_key,
                "type": rel,
                "weight": 0.5,
            })

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "highlighted_count": sum(1 for n in nodes.values() if n.get("highlighted")),
        "total_count": len(nodes),
    }