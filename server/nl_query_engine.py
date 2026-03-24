"""
Natural Language Query Engine
==============================
Translates natural language questions into SPARQL queries
using the ontology schema as context for the LLM.

The LLM never sees raw data — it only sees the schema (classes,
properties, taxonomies, relationship types) and generates SPARQL.
GraphDB executes the query and returns results.

Improvements over v1:
  - RAG over ontology: embeds schema elements, retrieves relevant
    slice per query instead of dumping the full schema every time.
  - Dynamic few-shot library: stores (NL question → SPARQL) pairs on
    disk, retrieves top-k most similar examples at query time.
  - Correction feedback loop: every successful/repaired query is saved
    back to the few-shot library so it improves over time.

Endpoint: POST /api/query/natural
"""

import os
import json
import time
import re
import math
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


router = APIRouter(prefix="/api/query", tags=["natural-language-query"])

# Injected by init
gdb = None

OLLAMA_HOST  = os.getenv("OLLAMA_HOST",  "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
EMBED_MODEL  = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest")

# Storage paths
DATA_DIR          = Path(os.getenv("PAYLOAD_STORAGE_DIR", "./data")).parent / "data"
FEWSHOT_PATH      = DATA_DIR / "fewshot_library.json"
SCHEMA_INDEX_PATH = DATA_DIR / "schema_vector_index.json"

# RAG tuning
SCHEMA_TOP_K   = 8   # schema fragments to retrieve per query
FEWSHOT_TOP_K  = 3   # few-shot examples to inject per query


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
    # Context surfaced to the UI
    rag_context: Optional[List[Dict[str, str]]] = None        # retrieved schema fragments
    few_shot_examples: Optional[List[Dict[str, str]]] = None  # retrieved NL→SPARQL pairs
    recon_values: Optional[str] = None                        # live graph value sample (reconnaissance)


# ============================================================
# INIT
# ============================================================

def init_query_engine(graphdb_adapter):
    global gdb
    gdb = graphdb_adapter
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Seed few-shot library from hardcoded patterns if it doesn't exist yet
    if not FEWSHOT_PATH.exists():
        _seed_fewshot_library()

    print("✓ Natural language query engine initialized")
    print(f"  Few-shot library: {FEWSHOT_PATH}")
    print(f"  Schema index:     {SCHEMA_INDEX_PATH}")


def _require_gdb():
    if gdb is None:
        raise HTTPException(status_code=503, detail="Query engine not initialized")


# ============================================================
# IMPROVEMENT 1 — SCHEMA VECTOR INDEX (RAG over ontology)
# ============================================================

class SchemaVectorIndex:
    """
    Embeds each ontology element (class, property, relationship type,
    taxonomy term) as a vector and retrieves the most relevant slice
    for a given query — instead of dumping the entire schema every time.

    Index is built lazily on first use and persisted to disk.
    It rebuilds automatically when the ontology changes (keyed by a
    hash of the schema content).
    """

    def __init__(self):
        self._index: List[Dict] = []   # [{text, embedding, category, label}, ...]
        self._schema_hash: str = ""
        self._loaded = False

    def _cosine(self, a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na  = math.sqrt(sum(x * x for x in a))
        nb  = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb + 1e-9)

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        try:
            import httpx
            res = httpx.post(
                f"{OLLAMA_HOST}/api/embeddings",
                json={"model": EMBED_MODEL, "prompt": text[:512]},
                timeout=30.0,
            )
            if res.status_code == 200:
                data = res.json()
                return data.get("embedding") or data.get("embeddings", [None])[0]
        except Exception as e:
            print(f"⚠️  Embedding error: {e}")
        return None

    def _build_schema_elements(self) -> List[Dict[str, str]]:
        """Decompose the ontology into individual indexable fragments."""
        elements = []

        # Fixed namespace block — always included
        elements.append({
            "category": "namespaces",
            "label": "SPARQL namespace prefixes",
            "text": (
                "NAMESPACE PREFIXES:\n"
                "  proto: <https://proto.atlas/ontology/>\n"
                "  data:  <https://proto.atlas/data/>\n"
                "  tax:   <https://proto.atlas/taxonomy/>\n"
                "  rel:   <https://proto.atlas/relationship/>\n"
                "  skos:  <http://www.w3.org/2004/02/skos/core#>\n"
                "SPARQL NOTES:\n"
                "  - Taxonomy fields link to SKOS concepts; use skos:prefLabel\n"
                "  - Use OPTIONAL for non-required fields\n"
                "  - Filter by class: ?x a proto:LibraryModule\n"
                "  - Instances: data:{key} e.g. data:cs-start-c2"
            ),
        })

        # One fragment per OWL class + its properties
        try:
            types = gdb.get_ontology_types()
            for t in types:
                props = t.get("properties", [])
                prop_lines = []
                for p in props:
                    req = " (REQUIRED)" if p.get("required") else ""
                    tax = f" [taxonomy: {p['taxonomy']}]" if p.get("taxonomy") else ""
                    prop_lines.append(f"  - proto:{p['name']} : {p.get('type', 'string')}{req}{tax}")
                text = (
                    f"CLASS proto:{t['collection']} ({t['label']})\n"
                    f"  Definition: {t.get('definition', '')}\n"
                )
                if prop_lines:
                    text += "  Properties:\n" + "\n".join(prop_lines)
                elements.append({
                    "category": "class",
                    "label": t["label"],
                    "text": text,
                })
        except Exception as e:
            print(f"⚠️  Schema index: could not load classes: {e}")

        # One fragment per taxonomy scheme
        for scheme_id in ["c2-frameworks", "mitre-tactics", "risk-levels", "teams"]:
            try:
                terms = gdb.get_taxonomy_terms(scheme_id)
                if terms:
                    labels = [t["label"] for t in terms]
                    elements.append({
                        "category": "taxonomy",
                        "label": scheme_id,
                        "text": (
                            f"TAXONOMY {scheme_id}:\n"
                            f"  Valid values: {', '.join(labels)}\n"
                            f"  Use in FILTER: ?x proto:{scheme_id.replace('-','_')} ?v . "
                            f"?v skos:prefLabel \"<value>\""
                        ),
                    })
            except Exception:
                pass

        # Relationship types as a single fragment
        elements.append({
            "category": "relationships",
            "label": "edge relationship types",
            "text": (
                "RELATIONSHIP TYPES (edge predicates):\n"
                "  rel:LEADS_TO — sequential dependency (transitive)\n"
                "  rel:MAPS_TO_TECHNIQUE — module implements a MITRE technique\n"
                "  rel:SUPPORTS_TECHNIQUE — range env supports a technique\n"
                "  rel:REQUIRES_TECHNIQUE — scenario requires a technique\n"
                "  rel:OWNED_BY — artifact is owned by a team (inverse: rel:OWNS)\n"
                "  rel:OWNS — team owns an artifact\n"
                "  rel:BELONGS_TO — person belongs to a team\n"
                "  rel:RELATED_TO — general semantic relationship (symmetric)"
            ),
        })

        return elements

    def build(self, force: bool = False):
        """Build or rebuild the vector index from the live ontology.

        Dual-channel embeddings: each fragment stores both a label embedding
        and a full-text embedding.  At retrieval time we score both channels
        and take the maximum, so a class fragment can be retrieved because its
        label is mentioned in the question OR because its property descriptions
        are semantically relevant — whichever signal is stronger.
        """
        elements = self._build_schema_elements()
        content_hash = hashlib.md5(
            json.dumps([e["text"] for e in elements], sort_keys=True).encode()
        ).hexdigest()

        # Load from disk if hash matches
        if not force and SCHEMA_INDEX_PATH.exists():
            try:
                saved = json.loads(SCHEMA_INDEX_PATH.read_text())
                if saved.get("hash") == content_hash:
                    self._index = saved["entries"]
                    self._schema_hash = content_hash
                    self._loaded = True
                    print(f"✓ Schema index loaded from disk ({len(self._index)} fragments)")
                    return
            except Exception:
                pass

        print(f"🔧 Building schema vector index ({len(elements)} fragments, dual-channel)...")
        entries = []
        for elem in elements:
            # Channel 1: label embedding (short, high signal for exact-name queries)
            label_emb = self._get_embedding(elem["label"])
            # Channel 2: full-text embedding (captures property-level relevance)
            text_emb  = self._get_embedding(elem["text"])
            if label_emb or text_emb:
                entries.append({
                    **elem,
                    "embedding":       text_emb,        # kept for backward compat
                    "label_embedding": label_emb,
                })
            else:
                # Store without embeddings — fallback text still available
                entries.append({**elem, "embedding": None, "label_embedding": None})

        self._index = entries
        self._schema_hash = content_hash
        self._loaded = True

        # Persist
        try:
            SCHEMA_INDEX_PATH.write_text(json.dumps({
                "hash": content_hash,
                "entries": entries,
            }, indent=2))
            print(f"✓ Schema index saved ({len(entries)} fragments)")
        except Exception as e:
            print(f"⚠️  Could not save schema index: {e}")

    def retrieve(self, question: str, top_k: int = SCHEMA_TOP_K) -> List[Dict[str, str]]:
        """
        Return the top-k most relevant schema fragments for the question.
        Always includes the namespaces fragment.

        Scoring uses dual-channel max similarity: each fragment is scored on
        both its label embedding and its full-text embedding, and the higher
        of the two scores is used.  This means:
          - A class whose name appears verbatim in the question ranks highly
            via the label channel.
          - A class whose properties are semantically relevant (even if the
            class name isn't mentioned) ranks highly via the text channel.

        Falls back to returning all fragments if embeddings aren't available.
        """
        if not self._loaded:
            self.build()

        # Namespace fragment is always included
        fixed = [e for e in self._index if e["category"] == "namespaces"]

        # Entries that have at least one embedding channel
        embeddable = [
            e for e in self._index
            if (e.get("embedding") or e.get("label_embedding"))
            and e["category"] != "namespaces"
        ]

        if not embeddable:
            return [{"category": e["category"], "label": e["label"], "text": e["text"]}
                    for e in self._index]

        query_emb = self._get_embedding(question)
        if query_emb is None:
            return [{"category": e["category"], "label": e["label"], "text": e["text"]}
                    for e in self._index]

        def _dual_score(entry: Dict) -> float:
            text_score  = self._cosine(query_emb, entry["embedding"])  if entry.get("embedding")       else 0.0
            label_score = self._cosine(query_emb, entry["label_embedding"]) if entry.get("label_embedding") else 0.0
            return max(text_score, label_score)

        scored = sorted(embeddable, key=_dual_score, reverse=True)

        retrieved = fixed + scored[:top_k]
        return [{"category": e["category"], "label": e["label"], "text": e["text"]}
                for e in retrieved]

    def invalidate(self):
        """Call after ontology changes to force a rebuild on next query."""
        self._loaded = False
        if SCHEMA_INDEX_PATH.exists():
            SCHEMA_INDEX_PATH.unlink()


# Singleton
_schema_index = SchemaVectorIndex()


# ============================================================
# IMPROVEMENT 2 — DYNAMIC FEW-SHOT LIBRARY
# ============================================================

class FewShotLibrary:
    """
    Persistent store of (natural language question → correct SPARQL) pairs.

    At query time, retrieves the top-k most semantically similar examples
    to prepend as few-shot demonstrations in the LLM prompt.

    Grows via the correction feedback loop (Improvement 3): every
    successful or repaired query is added automatically.
    """

    def __init__(self):
        self._entries: List[Dict] = []
        self._loaded = False

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        try:
            import httpx
            res = httpx.post(
                f"{OLLAMA_HOST}/api/embeddings",
                json={"model": EMBED_MODEL, "prompt": text[:256]},
                timeout=30.0,
            )
            if res.status_code == 200:
                data = res.json()
                return data.get("embedding") or data.get("embeddings", [None])[0]
        except Exception:
            pass
        return None

    def _cosine(self, a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na  = math.sqrt(sum(x * x for x in a))
        nb  = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb + 1e-9)

    def load(self):
        if self._loaded:
            return
        if FEWSHOT_PATH.exists():
            try:
                self._entries = json.loads(FEWSHOT_PATH.read_text())
                print(f"✓ Few-shot library loaded ({len(self._entries)} examples)")
            except Exception as e:
                print(f"⚠️  Few-shot library load failed: {e}")
                self._entries = []
        self._loaded = True

    def save(self):
        try:
            FEWSHOT_PATH.write_text(json.dumps(self._entries, indent=2))
        except Exception as e:
            print(f"⚠️  Few-shot library save failed: {e}")

    def add(self, question: str, sparql: str, source: str = "auto"):
        """
        Add a (question, sparql) pair.

        Deduplication strategy (two-pass):
          1. Exact string match — instant, covers re-queries of the same question.
          2. Semantic near-duplicate check — if an existing entry has cosine
             similarity > DEDUP_THRESHOLD with the new question, treat it as the
             same question and update its SPARQL rather than creating a second
             entry.  This prevents the library from accumulating many nearly-
             identical pairs that waste retrieval slots.

        Source priority: "confirmed" > "repair" > "auto" > "seed".
        A higher-priority source always overwrites a lower-priority one.
        """
        DEDUP_THRESHOLD = 0.92   # cosine similarity above which we consider two questions identical
        SOURCE_PRIORITY = {"seed": 0, "auto": 1, "repair": 2, "confirmed": 3}

        self.load()
        question = question.strip()
        sparql   = sparql.strip()
        new_prio = SOURCE_PRIORITY.get(source, 1)

        # Pass 1: exact match
        for entry in self._entries:
            if entry["question"].strip().lower() == question.lower():
                existing_prio = SOURCE_PRIORITY.get(entry.get("source", "auto"), 1)
                if new_prio >= existing_prio:
                    entry["sparql"]  = sparql
                    entry["source"]  = source
                self.save()
                return

        # Pass 2: semantic near-duplicate
        embedding = self._get_embedding(question)
        if embedding:
            for entry in self._entries:
                if entry.get("embedding"):
                    sim = self._cosine(embedding, entry["embedding"])
                    if sim >= DEDUP_THRESHOLD:
                        existing_prio = SOURCE_PRIORITY.get(entry.get("source", "auto"), 1)
                        if new_prio >= existing_prio:
                            # Update the existing entry rather than add a duplicate
                            entry["sparql"]    = sparql
                            entry["source"]    = source
                            entry["question"]  = question   # adopt the newer phrasing
                            entry["embedding"] = embedding
                        self.save()
                        return

        # No duplicate found — add new entry
        self._entries.append({
            "question":  question,
            "sparql":    sparql,
            "source":    source,
            "embedding": embedding,
        })
        self.save()
        print(f"✓ Few-shot library: added example (total {len(self._entries)})")

    def retrieve(self, question: str, top_k: int = FEWSHOT_TOP_K) -> List[Dict[str, str]]:
        """
        Return the top-k most similar (question, sparql) pairs.
        Returns plain dicts without embeddings (safe to serialise).
        """
        self.load()

        embeddable = [e for e in self._entries if e.get("embedding")]
        if not embeddable:
            # No embeddings yet — return first few as static examples
            return [{"question": e["question"], "sparql": e["sparql"]}
                    for e in self._entries[:top_k]]

        query_emb = self._get_embedding(question)
        if query_emb is None:
            return [{"question": e["question"], "sparql": e["sparql"]}
                    for e in self._entries[:top_k]]

        scored = sorted(
            embeddable,
            key=lambda e: self._cosine(query_emb, e["embedding"]),
            reverse=True,
        )

        # Exclude near-exact matches (the question itself being re-queried)
        filtered = [
            e for e in scored
            if e["question"].strip().lower() != question.strip().lower()
        ]

        return [{"question": e["question"], "sparql": e["sparql"]}
                for e in filtered[:top_k]]


# Singleton
_fewshot_library = FewShotLibrary()


def _seed_fewshot_library():
    """
    Bootstrap the few-shot library from the hardcoded pattern-match
    queries so the very first real query already has examples available.
    """
    seeds = [
        (
            "What library modules do we have?",
            """SELECT ?name ?tactic ?category ?riskLevel ?owner WHERE {
    ?m a proto:LibraryModule ;
       proto:name ?name .
    OPTIONAL { ?m proto:tactic ?tactic }
    OPTIONAL { ?m proto:category ?cat . ?cat skos:prefLabel ?category }
    OPTIONAL { ?m proto:riskLevel ?rl . ?rl skos:prefLabel ?riskLevel }
    OPTIONAL { ?m proto:owner ?ow . ?ow skos:prefLabel ?owner }
} ORDER BY ?name""",
        ),
        (
            "Show me credential access modules",
            """SELECT ?name ?description ?tactic ?riskLevel WHERE {
    ?m a proto:LibraryModule ;
       proto:name ?name ;
       proto:tactic "Credential Access" .
    OPTIONAL { ?m proto:description ?description }
    OPTIONAL { ?m proto:riskLevel ?rl . ?rl skos:prefLabel ?riskLevel }
} ORDER BY ?name""",
        ),
        (
            "Show me all TTPs in the graph",
            """SELECT ?name ?mitreId ?description WHERE {
    ?t a proto:TTP ;
       proto:name ?name .
    OPTIONAL { ?t proto:mitreId ?mitreId }
    OPTIONAL { ?t proto:description ?description }
} ORDER BY ?name""",
        ),
        (
            "Which tactics have the fewest modules?",
            """SELECT ?tacticLabel (COUNT(?m) AS ?moduleCount) WHERE {
    ?tactic a skos:Concept ;
            skos:inScheme ?scheme ;
            skos:prefLabel ?tacticLabel .
    FILTER(CONTAINS(STR(?scheme), "mitre-tactics"))
    OPTIONAL {
        ?m a proto:LibraryModule ;
           proto:tactic ?tacticLabel .
    }
} GROUP BY ?tacticLabel ORDER BY ?moduleCount""",
        ),
        (
            "What teams own the most modules?",
            """SELECT ?teamName (COUNT(?m) AS ?moduleCount) WHERE {
    ?team a proto:Team ;
          proto:name ?teamName .
    OPTIONAL {
        ?m a proto:LibraryModule .
        ?m proto:owner ?team .
    }
} GROUP BY ?teamName ORDER BY DESC(?moduleCount)""",
        ),
        (
            "Show high risk modules",
            """SELECT ?name ?tactic ?riskLevel WHERE {
    ?m a proto:LibraryModule ;
       proto:name ?name .
    ?m proto:riskLevel ?rl .
    ?rl skos:prefLabel ?riskLevel .
    FILTER(?riskLevel = "High" || ?riskLevel = "Critical")
    OPTIONAL { ?m proto:tactic ?tactic }
} ORDER BY ?name""",
        ),
        (
            "How many library modules are there?",
            "SELECT (COUNT(?m) AS ?count) WHERE { ?m a proto:LibraryModule }",
        ),
        (
            "Show attack chains — what leads to what?",
            """SELECT ?fromName ?toName WHERE {
    ?from rel:LEADS_TO ?to .
    ?from proto:name ?fromName .
    ?to proto:name ?toName .
} ORDER BY ?fromName""",
        ),
    ]

    print(f"🌱 Seeding few-shot library with {len(seeds)} examples...")
    for question, sparql in seeds:
        _fewshot_library.add(question, sparql, source="seed")


# ============================================================
# IMPROVEMENT 1b — GRAPH-STATE RECONNAISSANCE
# ============================================================

# Properties whose actual stored values are sampled before SPARQL generation.
# The LLM sees real values (e.g. "Initial Access", "initial-access") rather than
# whatever label it guesses from training knowledge.
_FILTERABLE_PROPERTIES = [
    ("proto:tactic",     None),        # string literal
    ("proto:riskLevel",  "skos"),      # SKOS concept → prefLabel
    ("proto:category",   "skos"),
    ("proto:owner",      "skos"),
]

def _sample_graph_values() -> str:
    """
    Issue lightweight SPARQL against the live graph to discover actual stored
    values for filterable properties.  Returns a compact string block that is
    appended to the schema context so the LLM can use verbatim values in
    FILTER expressions.

    This is the reconnaissance step described by Neptune/TigerGraph NL2SPARQL
    pipelines: ground the query in graph reality, not schema assumptions.
    Only runs if gdb is available; returns "" otherwise.
    """
    if gdb is None:
        return ""

    blocks = []
    for prop, kind in _FILTERABLE_PROPERTIES:
        try:
            if kind == "skos":
                rows = gdb.sparql_query(f"""
                    SELECT DISTINCT ?label WHERE {{
                        ?x {prop} ?v .
                        ?v skos:prefLabel ?label .
                    }} LIMIT 40
                """)
            else:
                rows = gdb.sparql_query(f"""
                    SELECT DISTINCT ?val WHERE {{
                        ?x {prop} ?val .
                        FILTER(isLiteral(?val))
                    }} LIMIT 40
                """)
            values = [
                str(r.get("label") or r.get("val") or "")
                for r in rows if (r.get("label") or r.get("val"))
            ]
            if values:
                blocks.append(f"  {prop}: {', '.join(sorted(values))}")
        except Exception:
            pass  # Graph unreachable or property absent — skip silently

    if not blocks:
        return ""

    return (
        "\nACTUAL STORED VALUES (use these verbatim in FILTER clauses — "
        "do not guess alternative spellings):\n"
        + "\n".join(blocks)
    )




def _build_schema_context(question: str = "") -> Tuple[str, List[Dict[str, str]]]:
    """
    Build the schema context string for the LLM prompt.

    Step 1 — RAG: retrieve only relevant schema fragments for the question
    (falls back to full dump when index is unavailable).

    Step 2 — Reconnaissance: append actual stored values for filterable
    properties sampled from the live graph.  This prevents the LLM from
    generating FILTER clauses with guessed values (e.g. "Initial Access")
    when the graph actually stores "initial-access".

    Returns:
        (context_string, retrieved_fragments)
    """
    if question:
        fragments = _schema_index.retrieve(question)
    else:
        fragments = _schema_index.retrieve("") if _schema_index._loaded else []
        if not fragments:
            return _build_full_schema_context(), []

    context = "=== KNOWLEDGE GRAPH SCHEMA (relevant fragments) ===\n\n"
    for frag in fragments:
        context += frag["text"] + "\n\n"

    # Append live graph values — grounds the LLM in actual stored strings
    recon = _sample_graph_values()
    if recon:
        context += recon + "\n"

    return context.strip(), fragments


def _build_full_schema_context() -> str:
    """Full schema dump — used as fallback and for /schema endpoint."""
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
    lines.append("CLASSES AND PROPERTIES:")
    try:
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
    except Exception:
        pass
    lines.append("TAXONOMY VALUES:")
    for scheme_id in ["c2-frameworks", "mitre-tactics", "risk-levels", "teams"]:
        try:
            terms = gdb.get_taxonomy_terms(scheme_id)
            if terms:
                labels = [t["label"] for t in terms]
                lines.append(f"  {scheme_id}: {', '.join(labels)}")
        except Exception:
            pass
    lines.append("")
    lines.append("RELATIONSHIP TYPES (edge predicates):")
    lines.append("  rel:LEADS_TO  rel:MAPS_TO_TECHNIQUE  rel:SUPPORTS_TECHNIQUE")
    lines.append("  rel:REQUIRES_TECHNIQUE  rel:OWNED_BY  rel:OWNS")
    lines.append("  rel:BELONGS_TO  rel:RELATED_TO")
    return "\n".join(lines)


# ============================================================
# SPARQL GENERATION
# ============================================================

def _build_prompt(question: str, schema: str, few_shot: List[Dict[str, str]]) -> str:
    """
    Build the LLM prompt with RAG schema context + few-shot examples.

    The prompt includes three evidence layers, in order of reliability:
      1. Schema fragments (retrieved by RAG) — what classes/properties exist
      2. Actual stored values (from graph reconnaissance) — what values to use
      3. Few-shot examples (retrieved by similarity) — how to structure queries

    A brief chain-of-thought scaffold is appended, which the literature
    (Zahera et al. SEMANTiCS 2024, INTERACSPARQL 2025) shows reduces
    structural errors in LLM-generated SPARQL.
    """

    few_shot_block = ""
    if few_shot:
        few_shot_block = "EXAMPLE QUERIES (use as structural patterns — adapt don't copy):\n"
        for i, ex in enumerate(few_shot, 1):
            few_shot_block += f"\nExample {i}:\n"
            few_shot_block += f"  Question: {ex['question']}\n"
            few_shot_block += f"  SPARQL:\n{ex['sparql']}\n"
        few_shot_block += "\n"

    return f"""You are a SPARQL query generator for a cyber range knowledge graph.

{schema}

{few_shot_block}USER QUESTION: {question}

INSTRUCTIONS:
1. If the schema above includes an "ACTUAL STORED VALUES" block, use those exact \
strings verbatim in FILTER clauses — do not substitute synonyms or alternative spellings.
2. Use OPTIONAL for all non-required properties.
3. Always SELECT human-readable labels (proto:name, skos:prefLabel, rdfs:label).
4. Limit to 25 results unless the question asks for a count or total.
5. Use the prefixes defined in the schema — do not invent new ones.

Think through which classes and properties are needed, then write the query.
Return ONLY the SPARQL query — no explanation, no markdown fences, no commentary."""


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

    # Strip markdown fences
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

    if content.lower().startswith("sparql"):
        content = content[6:].strip()

    return content


def _extract_sparql(raw: str) -> str:
    match = re.search(r'(SELECT\s.+)', raw, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return raw.strip()


async def _generate_answer(question: str, results: List[Dict], sparql: str) -> str:
    if not results:
        return "No results found for your query."

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
        return f"Found {len(results)} results."


# ============================================================
# ENDPOINT
# ============================================================

@router.post("/natural", response_model=NaturalQueryResponse)
async def natural_language_query(request: NaturalQueryRequest):
    """
    Translate a natural language question into SPARQL, execute it,
    and return structured results with a natural language answer.

    Pipeline:
      1. RAG: retrieve relevant schema fragments for the question
      2. Few-shot: retrieve top-k similar past queries
      3. LLM: generate SPARQL from schema + examples
      4. Execute against GraphDB; repair on failure
      5. Feedback loop: save successful query to few-shot library
      6. Generate natural language answer
    """
    _require_gdb()

    start    = time.time()
    question = request.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    sparql        = None
    llm_available = True
    rag_fragments: List[Dict[str, str]] = []
    few_shot_used: List[Dict[str, str]] = []
    recon_block:  str = ""

    try:
        # ── Step 1: RAG schema retrieval + graph reconnaissance ───────
        # Sample live values first so they're available for the repair
        # prompt too — the same value-grounding that prevents silent
        # FILTER mismatches on the first pass is equally important when
        # repairing a failed query.
        recon_block   = _sample_graph_values()
        schema, rag_fragments = _build_schema_context(question)

        # ── Step 2: Few-shot retrieval ────────────────────────────────
        few_shot_used = _fewshot_library.retrieve(question)

        # ── Step 3: LLM SPARQL generation ────────────────────────────
        prompt   = _build_prompt(question, schema, few_shot_used)
        raw      = await _call_llm(prompt)
        sparql   = _extract_sparql(raw)

    except Exception as llm_err:
        llm_available = False
        # Fall back to pattern matching (legacy hardcoded queries)
        sparql = _pattern_match_sparql(question)
        if not sparql:
            elapsed = int((time.time() - start) * 1000)
            return NaturalQueryResponse(
                success=False,
                question=question,
                error=f"LLM unavailable and no pattern match. LLM error: {str(llm_err)[:100]}",
                timing_ms=elapsed,
                rag_context=rag_fragments,
                few_shot_examples=few_shot_used,
                recon_values=recon_block or None,
            )

    repaired = False
    try:
        # ── Step 4: Execute ───────────────────────────────────────────
        try:
            results = gdb.sparql_query(sparql)
        except Exception as exec_err:
            if llm_available:
                # Repair prompt includes the same value grounding as the
                # original — the most common cause of repair-loop failure is
                # the LLM substituting a synonym value on the second attempt.
                fix_prompt = (
                    f"SPARQL query failed with error: {str(exec_err)[:200]}\n\n"
                    f"Original query:\n{sparql}\n\n"
                    f"{recon_block}\n"
                    f"Fix the query. Use verbatim values from ACTUAL STORED VALUES above "
                    f"if present. Return ONLY the corrected SPARQL."
                )
                fixed_raw  = await _call_llm(fix_prompt)
                sparql     = _extract_sparql(fixed_raw)
                results    = gdb.sparql_query(sparql)
                repaired   = True
            else:
                raise

        results = results[:request.max_results]

        # ── Step 5: Feedback loop — save to few-shot library ──────────
        # IMPORTANT: we only save queries that demonstrate correct behaviour:
        #   - Repaired queries: the LLM fixed its own mistake — always save
        #     because the corrected form is explicitly better than the original.
        #   - Auto queries that returned results: empty-result queries pass
        #     syntactically but may be semantically wrong (e.g. a FILTER value
        #     that silently matches nothing).  We only save them when they
        #     actually found something, which is the weakest confirmation of
        #     correctness available without explicit user feedback.
        #
        # This addresses the flaw identified in the literature (Auto-KGQA 2025,
        # INTERACSPARQL 2025): saving every syntactically-valid query as a
        # training pair degrades the few-shot library with false positives.
        should_save = repaired or (len(results) > 0)
        if should_save:
            source = "repair" if repaired else "auto"
            _fewshot_library.add(question, sparql, source=source)

        # ── Step 6: Generate answer ───────────────────────────────────
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
            rag_context=rag_fragments,
            few_shot_examples=few_shot_used,
            recon_values=recon_block or None,
        )

    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        return NaturalQueryResponse(
            success=False,
            question=question,
            sparql=sparql,
            error=str(e),
            timing_ms=elapsed,
            rag_context=rag_fragments,
            few_shot_examples=few_shot_used,
            recon_values=recon_block or None,
        )


# ============================================================
# PATTERN MATCHING (LLM fallback — unchanged from v1)
# ============================================================

def _pattern_match_sparql(question: str) -> Optional[str]:
    """
    Hardcoded NL → SPARQL fallback for when LLM is unavailable.
    These patterns also seed the few-shot library on first boot.
    """
    q = question.lower().strip().rstrip("?")

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
        return """SELECT ?name ?tactic ?category ?riskLevel ?owner WHERE {
    ?m a proto:LibraryModule ;
       proto:name ?name .
    OPTIONAL { ?m proto:tactic ?tactic }
    OPTIONAL { ?m proto:category ?cat . ?cat skos:prefLabel ?category }
    OPTIONAL { ?m proto:riskLevel ?rl . ?rl skos:prefLabel ?riskLevel }
    OPTIONAL { ?m proto:owner ?ow . ?ow skos:prefLabel ?owner }
} ORDER BY ?name"""

    if any(kw in q for kw in ["ttp", "technique", "mitre", "att&ck", "attack"]):
        return """SELECT ?name ?mitreId ?description WHERE {
    ?t a proto:TTP ;
       proto:name ?name .
    OPTIONAL { ?t proto:mitreId ?mitreId }
    OPTIONAL { ?t proto:description ?description }
} ORDER BY ?name"""

    if any(kw in q for kw in ["team", "teams", "who owns", "ownership"]):
        return """SELECT ?teamName (COUNT(?m) AS ?moduleCount) WHERE {
    ?team a proto:Team ;
          proto:name ?teamName .
    OPTIONAL {
        ?m a proto:LibraryModule .
        ?m proto:owner ?team .
    }
} GROUP BY ?teamName ORDER BY DESC(?moduleCount)"""

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
        return """SELECT ?fromName ?relType ?toName WHERE {
    ?from ?rel ?to .
    FILTER(STRSTARTS(STR(?rel), "https://proto.atlas/relationship/"))
    FILTER(STRSTARTS(STR(?from), "https://proto.atlas/data/"))
    FILTER(STRSTARTS(STR(?to), "https://proto.atlas/data/"))
    ?from proto:name ?fromName .
    ?to proto:name ?toName .
    BIND(STRAFTER(STR(?rel), "https://proto.atlas/relationship/") AS ?relType)
} LIMIT 25"""

    if any(kw in q for kw in ["chain", "path", "leads to", "attack flow", "execution"]):
        return """SELECT ?fromName ?toName WHERE {
    ?from rel:LEADS_TO ?to .
    ?from proto:name ?fromName .
    ?to proto:name ?toName .
} ORDER BY ?fromName"""

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

    if any(kw in q for kw in ["how many", "count", "total"]):
        if "module" in q:
            return "SELECT (COUNT(?m) AS ?count) WHERE { ?m a proto:LibraryModule }"
        if "ttp" in q:
            return "SELECT (COUNT(?t) AS ?count) WHERE { ?t a proto:TTP }"
        if "team" in q:
            return "SELECT (COUNT(?t) AS ?count) WHERE { ?t a proto:Team }"
        return """SELECT ?type (COUNT(?x) AS ?count) WHERE {
    ?x a ?type .
    FILTER(STRSTARTS(STR(?x), "https://proto.atlas/data/"))
    FILTER(STRSTARTS(STR(?type), "https://proto.atlas/ontology/"))
} GROUP BY ?type ORDER BY DESC(?count)"""

    if any(kw in q for kw in ["everything", "all", "summary", "overview", "graph"]):
        return """SELECT ?type (COUNT(?x) AS ?count) WHERE {
    ?x a ?type .
    FILTER(STRSTARTS(STR(?x), "https://proto.atlas/data/"))
    FILTER(STRSTARTS(STR(?type), "https://proto.atlas/ontology/"))
} GROUP BY ?type ORDER BY DESC(?count)"""

    return None


def _generate_mock_answer(question: str, results: List[Dict]) -> str:
    if not results:
        return "No results found for your query."
    count = len(results)
    keys  = list(results[0].keys())
    if count == 1 and "count" in results[0]:
        return f"The count is {results[0]['count']}."
    name_key = next(
        (k for k in keys if k.lower() in ("name", "teamname", "fromname", "tacticlabel")),
        None,
    )
    if name_key:
        names  = [str(r.get(name_key, "")) for r in results[:8]]
        listed = ", ".join(names)
        suffix = f" (and {count - 8} more)" if count > 8 else ""
        return f"Found {count} results: {listed}{suffix}."
    return f"Query returned {count} results across {len(keys)} columns: {', '.join(keys)}."


# ============================================================
# SCHEMA INTROSPECTION ENDPOINT
# ============================================================

@router.get("/schema")
async def get_query_schema():
    """Return the full schema context (for debugging / Ontology Manager)."""
    _require_gdb()
    return {
        "schema": _build_full_schema_context(),
        "model":  OLLAMA_MODEL,
        "host":   OLLAMA_HOST,
        "index_built": _schema_index._loaded,
        "fewshot_count": len(_fewshot_library._entries),
    }


@router.post("/schema/rebuild")
async def rebuild_schema_index():
    """Force-rebuild the schema vector index (call after ontology changes)."""
    _require_gdb()
    _schema_index.invalidate()
    _schema_index.build(force=True)
    return {"success": True, "fragments": len(_schema_index._index)}


@router.post("/fewshot/confirm")
async def confirm_fewshot_entry(payload: dict):
    """
    Explicitly mark a (question, sparql) pair as correct.

    This is the highest-quality feedback signal — human confirmation that
    a generated query answered the question correctly.  Call this from the
    UI when the user clicks 'This answer was correct' or similar.

    Body: {"question": str, "sparql": str}

    The pair is upserted into the few-shot library with source="confirmed",
    which downstream tooling can use to prioritise it over auto/repair entries.
    """
    question = (payload.get("question") or "").strip()
    sparql   = (payload.get("sparql")   or "").strip()
    if not question or not sparql:
        raise HTTPException(status_code=400, detail="question and sparql are required")
    _fewshot_library.add(question, sparql, source="confirmed")
    return {"success": True, "question": question}


@router.get("/fewshot")
async def get_fewshot_library():
    """Inspect the few-shot library contents."""
    _fewshot_library.load()
    return {
        "count": len(_fewshot_library._entries),
        "examples": [
            {"question": e["question"], "sparql": e["sparql"], "source": e.get("source", "unknown")}
            for e in _fewshot_library._entries
        ],
    }


@router.delete("/fewshot/{index}")
async def delete_fewshot_entry(index: int):
    """Remove a single entry from the few-shot library by index."""
    _fewshot_library.load()
    if index < 0 or index >= len(_fewshot_library._entries):
        raise HTTPException(status_code=404, detail="Index out of range")
    removed = _fewshot_library._entries.pop(index)
    _fewshot_library.save()
    return {"removed": removed["question"]}


# ============================================================
# EXAMPLE QUERIES
# ============================================================

@router.get("/examples")
async def get_example_queries():
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


# ============================================================
# SUBGRAPH ENDPOINT (unchanged from v1)
# ============================================================

@router.post("/subgraph")
async def get_result_subgraph(request: dict):
    """
    Given SPARQL results, extract node URIs and return a visualization subgraph.
    """
    _require_gdb()

    node_keys  = set()
    node_names = set()

    for key in request.get("node_keys", []):
        node_keys.add(key)

    for row in request.get("results", []):
        for field, val in row.items():
            val_str = str(val)
            if val_str.startswith("https://proto.atlas/data/"):
                node_keys.add(val_str.replace("https://proto.atlas/data/", ""))
            elif field.lower() in ("name", "fromname", "toname", "teamname", "modulename", "ttpname"):
                if val_str and val_str != "None":
                    node_names.add(val_str)

    if not node_keys and node_names:
        name_filters = " || ".join(f'(?name = "{n}")' for n in node_names)
        try:
            resolved = gdb.sparql_query(f"""
                SELECT ?node ?name WHERE {{
                    ?node proto:name ?name .
                    FILTER(STRSTARTS(STR(?node), "https://proto.atlas/data/"))
                    FILTER({name_filters})
                }}
            """)
            for row in resolved:
                uri = row.get("node", "")
                if uri.startswith("https://proto.atlas/data/"):
                    node_keys.add(uri.replace("https://proto.atlas/data/", ""))
        except Exception as e:
            print(f"⚠️  Subgraph name resolution failed: {e}")

    if not node_keys:
        return {"nodes": [], "edges": [], "count": 0}

    uri_values = " ".join(f"data:{k}" for k in node_keys)

    TYPE_COLORS = {
        "LibraryModule": "#6EBE46", "TTP": "#E84855", "Team": "#4DA8DA",
        "Person": "#FFA552", "ExecutionPlan": "#9B5DE5", "Scenario": "#F15BB5",
        "DevelopmentStory": "#FFD166", "RobotLog": "#06D6A0", "RangeEnvironment": "#118AB2",
    }

    try:
        node_rows     = gdb.sparql_query(f"""
            SELECT ?node ?name ?type ?typeLabel WHERE {{
                VALUES ?node {{ {uri_values} }}
                ?node proto:name ?name .
                ?node a ?type .
                FILTER(STRSTARTS(STR(?type), "https://proto.atlas/ontology/"))
                ?type rdfs:label ?typeLabel .
            }}
        """)
        edge_rows     = gdb.sparql_query(f"""
            SELECT ?from ?rel ?to ?relLabel WHERE {{
                VALUES ?from {{ {uri_values} }}
                VALUES ?to   {{ {uri_values} }}
                ?from ?rel ?to .
                FILTER(STRSTARTS(STR(?rel), "https://proto.atlas/relationship/"))
                BIND(STRAFTER(STR(?rel), "https://proto.atlas/relationship/") AS ?relLabel)
            }}
        """)
        neighbor_rows = gdb.sparql_query(f"""
            SELECT ?from ?rel ?to ?toName ?toType WHERE {{
                VALUES ?from {{ {uri_values} }}
                ?from ?rel ?to .
                FILTER(STRSTARTS(STR(?rel), "https://proto.atlas/relationship/"))
                FILTER(STRSTARTS(STR(?to),  "https://proto.atlas/data/"))
                ?to proto:name ?toName .
                OPTIONAL {{ ?to a ?toType . FILTER(STRSTARTS(STR(?toType), "https://proto.atlas/ontology/")) }}
            }}
        """)
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    nodes = {}
    for row in node_rows:
        node_uri   = row.get("node", "")
        key        = node_uri.replace("https://proto.atlas/data/", "")
        type_label = row.get("typeLabel", "Unknown")
        nodes[key] = {
            "id": key, "label": row.get("name", key), "type": type_label,
            "cluster": type_label, "importance": 1.0, "size": 8,
            "color": TYPE_COLORS.get(type_label, "#888"), "highlighted": True,
        }

    for row in neighbor_rows:
        to_uri  = row.get("to", "")
        to_key  = to_uri.replace("https://proto.atlas/data/", "")
        if to_key not in nodes:
            to_type = (row.get("toType") or "").replace("https://proto.atlas/ontology/", "")
            nodes[to_key] = {
                "id": to_key, "label": row.get("toName", to_key),
                "type": to_type or "Unknown", "cluster": to_type or "Unknown",
                "importance": 0.5, "size": 5,
                "color": TYPE_COLORS.get(to_type, "#555"), "highlighted": False,
            }

    edges     = []
    seen_edges = set()

    for row in edge_rows:
        fk  = row.get("from", "").replace("https://proto.atlas/data/", "")
        tk  = row.get("to",   "").replace("https://proto.atlas/data/", "")
        rel = row.get("relLabel", "RELATED")
        eid = f"{fk}-{rel}-{tk}"
        if eid not in seen_edges:
            seen_edges.add(eid)
            edges.append({"id": eid, "source": fk, "target": tk, "type": rel, "weight": 1.0})

    for row in neighbor_rows:
        fk  = row.get("from", "").replace("https://proto.atlas/data/", "")
        tk  = row.get("to",   "").replace("https://proto.atlas/data/", "")
        rel = row.get("rel",  "").replace("https://proto.atlas/relationship/", "")
        eid = f"{fk}-{rel}-{tk}"
        if eid not in seen_edges:
            seen_edges.add(eid)
            edges.append({"id": eid, "source": fk, "target": tk, "type": rel, "weight": 0.5})

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "highlighted_count": sum(1 for n in nodes.values() if n.get("highlighted")),
        "total_count": len(nodes),
    }