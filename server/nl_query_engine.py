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

# LLM config is now centralised in llm_client.py
# These vars are kept for reference but the actual client reads from llm_client
from llm_client import chat_completion as _llm_chat, get_embedding as _llm_embed, active_model, active_embed_model, backend_info as _llm_backend_info
OLLAMA_HOST  = os.getenv("OLLAMA_HOST",  "http://10.10.80.99:4001")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:120b")
EMBED_MODEL  = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest")

# Storage paths
DATA_DIR          = Path(os.getenv("PAYLOAD_STORAGE_DIR", "./data")).parent / "data"
FEWSHOT_PATH      = DATA_DIR / "fewshot_library.json"
SCHEMA_INDEX_PATH = DATA_DIR / "schema_vector_index.json"

# RAG tuning
SCHEMA_TOP_K   = 8   # schema fragments to retrieve per query
FEWSHOT_TOP_K  = 3   # few-shot examples to inject per query
TAXONOMY_LABEL_CAP = 40  # max term labels per taxonomy RAG fragment
RECON_PROP_CAP = 8       # lowest-cardinality props sampled per NL request
RECON_VALUE_LIMIT = 40   # distinct values per property
RECON_CHAR_BUDGET = 3000 # hard cap on the ACTUAL STORED VALUES block


# ============================================================
# MODELS
# ============================================================

class NaturalQueryRequest(BaseModel):
    question: str
    show_sparql: bool = True
    max_results: int = 25
    plugin_id: Optional[str] = None       # if set, load agent system prompt from disk
    system_prompt: Optional[str] = None   # or pass directly


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


def _normalize_taxonomy_ref(tax_ref: str) -> str:
    """Normalize a proto:taxonomy annotation value to a bare scheme_id."""
    ref = tax_ref.strip()
    if ref.startswith("http://") or ref.startswith("https://"):
        ref = ref.rsplit("/", 1)[-1]
    if ref.startswith("scheme-"):
        ref = ref[len("scheme-"):]
    return ref


def _scheme_to_property_names(types: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Reverse map: scheme_id → ontology property names that reference it."""
    mapping: Dict[str, List[str]] = {}
    for t in types:
        for p in t.get("properties", []):
            tax = p.get("taxonomy")
            if not tax:
                continue
            scheme_id = _normalize_taxonomy_ref(str(tax))
            names = mapping.setdefault(scheme_id, [])
            if p["name"] not in names:
                names.append(p["name"])
    return mapping


def _format_term_labels(labels: List[str], cap: int = TAXONOMY_LABEL_CAP) -> str:
    if len(labels) <= cap:
        return ", ".join(labels)
    shown = labels[:cap]
    return f"{', '.join(shown)} … and {len(labels) - cap} more"


def _build_taxonomy_fragment_text(
    scheme: Dict[str, Any],
    terms: List[Dict[str, str]],
    prop_names: List[str],
) -> str:
    """Build one RAG fragment for a taxonomy scheme with real property refs."""
    scheme_id = scheme["scheme_id"]
    label = scheme.get("label") or scheme_id
    labels = [t["label"] for t in terms if t.get("label")]
    lines = [
        f"TAXONOMY {scheme_id} ({label}): {len(terms)} terms",
        f"  Valid values: {_format_term_labels(labels)}",
    ]
    if prop_names:
        refs = ", ".join(f"proto:{n}" for n in prop_names)
        lines.append(f"  Referenced by: {refs}")
        example = labels[0] if labels else "<value>"
        for prop_name in prop_names:
            lines.append(
                f'  Use in FILTER: ?x proto:{prop_name} ?v . '
                f'?v skos:prefLabel "{example}"'
            )
    return "\n".join(lines)


# ============================================================
# IMPROVEMENT 1 — SCHEMA VECTOR INDEX (RAG over ontology)
# ============================================================
# LIVE RELATIONSHIP TYPES
# ============================================================
# Relationship types are whatever the ontology manager has declared in the
# CONNECTED repository. Never hardcode them: a fixed list silently describes a
# different graph the moment the server is pointed at another repo, and the LLM
# will faithfully generate SPARQL against predicates that do not exist.
# Mirrors list_relationships() in ontology_graphdb.py.

REL_NS = "https://proto.atlas/relationship/"
ONTOLOGY_NS = "https://proto.atlas/ontology/"


def _live_relationship_types() -> List[Dict[str, Any]]:
    """Read declared relationship types (owl:ObjectProperty under rel:) from GraphDB."""
    if gdb is None:
        return []
    try:
        rows = gdb.sparql_query(f"""
            SELECT DISTINCT ?rel ?label ?definition ?transitive ?symmetric ?domain ?range WHERE {{
                ?rel a owl:ObjectProperty .
                FILTER(STRSTARTS(STR(?rel), "{REL_NS}"))
                OPTIONAL {{ ?rel rdfs:label ?label }}
                OPTIONAL {{ ?rel rdfs:comment ?definition }}
                OPTIONAL {{ ?rel a owl:TransitiveProperty . BIND(true AS ?transitive) }}
                OPTIONAL {{ ?rel a owl:SymmetricProperty . BIND(true AS ?symmetric) }}
                OPTIONAL {{ ?rel rdfs:domain ?domain . FILTER(STRSTARTS(STR(?domain), "{ONTOLOGY_NS}")) }}
                OPTIONAL {{ ?rel rdfs:range ?range . FILTER(STRSTARTS(STR(?range), "{ONTOLOGY_NS}")) }}
            }}
            ORDER BY ?rel
        """)
    except Exception as e:
        print(f"\u26a0\ufe0f  Could not read relationship types from GraphDB: {e}")
        return []

    rels: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        uri = row["rel"]
        local = uri.rsplit("/", 1)[-1]
        r = rels.setdefault(uri, {
            "uri": uri,
            "local": local,
            "label": row.get("label") or local,
            "definition": row.get("definition", ""),
            "transitive": False,
            "symmetric": False,
            "domain": [],
            "range": [],
        })
        # Flags must be MERGED across rows, not read once. The OPTIONAL clauses
        # produce one row per binding combination; a flag unbound in whichever
        # row happens to arrive first would otherwise be lost permanently.
        if row.get("transitive") == "true":
            r["transitive"] = True
        if row.get("symmetric") == "true":
            r["symmetric"] = True
        for key in ("domain", "range"):
            v = row.get(key)
            if v:
                short = v.rsplit("/", 1)[-1]
                if short not in r[key]:
                    r[key].append(short)
    return list(rels.values())


def _format_relationship_block() -> str:
    """Render declared relationship types for the SPARQL-generation prompt."""
    rels = _live_relationship_types()
    if not rels:
        return (
            "RELATIONSHIP TYPES (edge predicates):\n"
            "  NONE declared in this repository. Do not write any query that\n"
            "  traverses an edge predicate \u2014 there are none. Only class\n"
            "  membership and literal properties can be queried here."
        )

    lines = ["RELATIONSHIP TYPES (edge predicates):"]
    for r in rels:
        flags = []
        if r["transitive"]:
            flags.append("transitive")
        if r["symmetric"]:
            flags.append("symmetric")
        suffix = f" ({', '.join(flags)})" if flags else ""

        sig = ""
        if r["domain"] and r["range"]:
            sig = f"  [{' | '.join(r['domain'])} -> {' | '.join(r['range'])}]"

        desc = f" \u2014 {r['definition']}" if r["definition"] else ""
        lines.append(f"  rel:{r['local']}{desc}{suffix}{sig}")

    lines.append("")
    lines.append("These are the ONLY edge predicates that exist in this graph.")
    lines.append("Never invent others. Usage: ?from rel:PREDICATE ?to .")
    return "\n".join(lines)


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
        # Low-cardinality props for FILTER grounding — refreshed with the index
        self._filterable_properties: List[Dict[str, Any]] = []

    def _cosine(self, a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na  = math.sqrt(sum(x * x for x in a))
        nb  = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb + 1e-9)

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        return _llm_embed(text)

    def _build_schema_elements(self) -> List[Dict[str, str]]:
        """Decompose the ontology into individual indexable fragments."""
        elements = []

        # Namespace + SPARQL-dialect block \u2014 repo-independent, always included.
        # Nothing here may name a class, property or taxonomy: those come from
        # the live ontology fragments below. Anything schema-specific written
        # here becomes a permanent lie the moment the repo changes.
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
                "\n"
                "SPARQL NOTES:\n"
                "  - Instances live under data:{key}\n"
                "  - Filter by class: ?x a proto:ClassName\n"
                "  - Taxonomy-valued properties store URIs, not strings. To compare\n"
                "    against a label, join through skos:prefLabel:\n"
                "      ?x proto:someProp ?v . ?v skos:prefLabel ?label\n"
                "  - Use OPTIONAL for anything not marked REQUIRED\n"
                "  - Only use classes, properties and relationship types that appear\n"
                "    in this context. If the question needs something absent from it,\n"
                "    the graph does not model it \u2014 do not invent a predicate.\n"
                "\n"
                "GENERAL PATTERNS (substitute real names from the context below):\n"
                "  # Count instances of a class:\n"
                "  SELECT (COUNT(?x) AS ?count) WHERE { ?x a proto:ClassName }\n"
                "\n"
                "  # List with optional fields:\n"
                "  SELECT ?name ?extra WHERE {\n"
                "    ?x a proto:ClassName ; proto:name ?name .\n"
                "    OPTIONAL { ?x proto:extra ?extra }\n"
                "  } ORDER BY ?name\n"
                "\n"
                "  # Traverse an edge (only with a declared relationship type):\n"
                "  SELECT ?fromName ?toName WHERE {\n"
                "    ?from rel:PREDICATE ?to .\n"
                "    ?from proto:name ?fromName .\n"
                "    ?to   proto:name ?toName .\n"
                "  }\n"
                "\n"
                "  # Group and count:\n"
                "  SELECT ?key (COUNT(?x) AS ?count) WHERE {\n"
                "    ?x a proto:ClassName ; proto:someProp ?key .\n"
                "  } GROUP BY ?key ORDER BY DESC(?count)\n"
                "\n"
                "  # Instances lacking an edge:\n"
                "  SELECT ?name WHERE {\n"
                "    ?x a proto:ClassName ; proto:name ?name .\n"
                "    FILTER(NOT EXISTS { ?x rel:PREDICATE ?any })\n"
                "  }\n"
                "\n"
                "GRAPHDB RESTRICTIONS:\n"
                "  - NEVER use FILTER(?x NOT IN (SELECT ...)) \u2014 use FILTER(NOT EXISTS {...})\n"
                "  - GROUP BY requires every SELECT var to be aggregated or grouped\n"
                "  - Subqueries must be wrapped: { SELECT ... } inside WHERE\n"
                "  - Reasoning is enabled: transitive properties return inferred\n"
                "    triples alongside asserted ones\n"
            ),
        })

        # One fragment per OWL class + its properties
        types: List[Dict[str, Any]] = []
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

        # One fragment per live taxonomy scheme (discovered from GraphDB)
        scheme_props = _scheme_to_property_names(types)
        try:
            schemes = gdb.get_taxonomy_schemes()
        except Exception as e:
            print(f"⚠️  Schema index: could not list taxonomies: {e}")
            schemes = []

        for scheme in schemes:
            if scheme.get("term_count", 0) == 0:
                continue
            scheme_id = scheme["scheme_id"]
            try:
                terms = gdb.get_taxonomy_terms(scheme_id)
                if not terms:
                    print(f"⚠️  Schema index: scheme '{scheme_id}' reports "
                          f"{scheme['term_count']} terms but query returned none")
                    continue
                elements.append({
                    "category": "taxonomy",
                    "label": scheme.get("label") or scheme_id,
                    "text": _build_taxonomy_fragment_text(
                        scheme, terms, scheme_props.get(scheme_id, []),
                    ),
                })
            except Exception as e:
                print(f"⚠️  Schema index: could not load taxonomy '{scheme_id}': {e}")

        # Relationship types \u2014 read live from the connected repo, never hardcoded.
        elements.append({
            "category": "relationships",
            "label": "edge relationship types",
            "text": _format_relationship_block(),
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
                    self._refresh_filterable_properties()
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
        self._refresh_filterable_properties()

        # Persist
        try:
            SCHEMA_INDEX_PATH.write_text(json.dumps({
                "hash": content_hash,
                "entries": entries,
            }, indent=2))
            print(f"✓ Schema index saved ({len(entries)} fragments)")
        except Exception as e:
            print(f"⚠️  Could not save schema index: {e}")

    def _refresh_filterable_properties(self) -> None:
        """Cache low-cardinality properties for recon (schema-level, not per-request)."""
        if gdb is None:
            self._filterable_properties = []
            return
        try:
            self._filterable_properties = gdb.get_filterable_properties()
            print(f"✓ Filterable properties cached ({len(self._filterable_properties)})")
        except Exception as e:
            print(f"⚠️  Could not discover filterable properties: {e}")
            self._filterable_properties = []

    def get_filterable_properties(self) -> List[Dict[str, Any]]:
        """Return cached filterable properties, refreshing if needed."""
        if not self._loaded:
            self.build()
        if not self._filterable_properties:
            self._refresh_filterable_properties()
        return self._filterable_properties

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
        return _llm_embed(text)

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
    Intentionally a no-op.

    This previously inserted eight examples over proto:LibraryModule, proto:TTP
    and proto:Team. Those classes belong to the `atlas` schema and do not exist
    in every repository \u2014 in `razor-code` they exist in none. Because retrieved
    few-shot examples are the strongest signal the SPARQL generator gets, seeding
    them with a foreign schema made the model reproduce that schema no matter
    what the live ontology said.

    The library now fills from successful queries against whatever repo is
    actually connected. If you want starter examples, add them by hand with
    source="confirmed" so they outrank auto-saved entries \u2014 but write them
    against the connected repo's real classes.
    """
    print("\U0001f331 Few-shot library starts empty; it fills from successful queries.")
    return


# ============================================================
# IMPROVEMENT 1b — GRAPH-STATE RECONNAISSANCE
# ============================================================
# Low-cardinality ontology properties are discovered via
# GraphDBAdapter.get_filterable_properties() and cached on SchemaVectorIndex.
# Values are sampled live per request (once) and injected as ACTUAL STORED VALUES.

def _prop_curie(prop_uri: str) -> str:
    """Compact ontology property URI for prompt display."""
    if prop_uri.startswith("https://proto.atlas/ontology/"):
        return f"proto:{prop_uri[len('https://proto.atlas/ontology/'):]}"
    return f"<{prop_uri}>"


def _sample_property_values(prop_uri: str, kind: str) -> List[str]:
    """Sample distinct values for one property; try the other shape on empty."""
    prop_ref = f"<{prop_uri}>" if prop_uri.startswith("http") else prop_uri

    def _skos() -> List[str]:
        rows = gdb.sparql_query(f"""
            SELECT DISTINCT ?label WHERE {{
                ?x {prop_ref} ?v .
                ?v skos:prefLabel ?label .
            }} LIMIT {RECON_VALUE_LIMIT}
        """)
        return [str(r["label"]) for r in rows if r.get("label")]

    def _literal() -> List[str]:
        rows = gdb.sparql_query(f"""
            SELECT DISTINCT ?val WHERE {{
                ?x {prop_ref} ?val .
                FILTER(isLiteral(?val))
            }} LIMIT {RECON_VALUE_LIMIT}
        """)
        return [str(r["val"]) for r in rows if r.get("val") is not None]

    primary, fallback = (_skos, _literal) if kind == "skos" else (_literal, _skos)
    try:
        values = primary()
    except Exception:
        values = []
    if not values:
        try:
            values = fallback()
        except Exception:
            values = []
    return values


def _sample_graph_values(
    filterable: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Issue lightweight SPARQL against the live graph to discover actual stored
    values for filterable properties.  Returns a compact string block that is
    appended to the schema context so the LLM can use verbatim values in
    FILTER expressions.

    Property *set* comes from SchemaVectorIndex (cardinality discovery, cached
    at index build).  Values are always sampled live.
    """
    if gdb is None:
        return ""

    if filterable is None:
        filterable = _schema_index.get_filterable_properties()

    # Already ordered by ascending cardinality from discovery
    props = filterable[:RECON_PROP_CAP]

    blocks: List[str] = []
    for entry in props:
        prop_uri = entry.get("property") or ""
        if not prop_uri:
            continue
        kind = entry.get("kind") or "literal"
        try:
            values = _sample_property_values(prop_uri, kind)
        except Exception as e:
            print(f"⚠️  Recon: could not sample {prop_uri}: {e}")
            continue
        if values:
            blocks.append(
                f"  {_prop_curie(prop_uri)}: {', '.join(sorted(values))}"
            )

    if not blocks:
        return ""

    header = (
        "\nACTUAL STORED VALUES (use these verbatim in FILTER clauses — "
        "do not guess alternative spellings):\n"
    )
    body = "\n".join(blocks)
    # Truncate by character budget without cutting mid-property line
    if len(header) + len(body) > RECON_CHAR_BUDGET:
        kept: List[str] = []
        budget = RECON_CHAR_BUDGET - len(header) - 20
        used = 0
        for line in blocks:
            if used + len(line) + 1 > budget:
                break
            kept.append(line)
            used += len(line) + 1
        body = "\n".join(kept)
        if len(kept) < len(blocks):
            body += "\n  … (truncated)"

    return header + body


def _build_schema_context(
    question: str = "",
    recon: Optional[str] = None,
) -> Tuple[str, List[Dict[str, str]]]:
    """
    Build the schema context string for the LLM prompt.

    Step 1 — RAG: retrieve only relevant schema fragments for the question
    (falls back to full dump when index is unavailable).

    Step 2 — Reconnaissance: append actual stored values for filterable
    properties sampled from the live graph.  This prevents the LLM from
    generating FILTER clauses with guessed values (e.g. "Initial Access")
    when the graph actually stores "initial-access".

    Args:
        question: NL question for RAG retrieval
        recon: precomputed recon block; if None, samples once here
               (standalone /schema callers). Pass from natural_language_query
               to avoid a second round-trip.

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

    if recon is None:
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
    types: List[Dict[str, Any]] = []
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
    except Exception as e:
        print(f"⚠️  Schema dump: could not load classes: {e}")

    lines.append("TAXONOMY VALUES:")
    scheme_props = _scheme_to_property_names(types)
    try:
        schemes = gdb.get_taxonomy_schemes()
    except Exception as e:
        print(f"⚠️  Schema dump: could not list taxonomies: {e}")
        schemes = []

    for scheme in schemes:
        if scheme.get("term_count", 0) == 0:
            continue
        scheme_id = scheme["scheme_id"]
        try:
            terms = gdb.get_taxonomy_terms(scheme_id)
            if not terms:
                print(f"⚠️  Schema dump: scheme '{scheme_id}' reports "
                      f"{scheme['term_count']} terms but query returned none")
                continue
            labels = [t["label"] for t in terms if t.get("label")]
            prop_names = scheme_props.get(scheme_id, [])
            refs = (
                f" [via {', '.join(f'proto:{n}' for n in prop_names)}]"
                if prop_names else ""
            )
            lines.append(
                f"  {scheme_id} ({scheme.get('label') or scheme_id}): "
                f"{_format_term_labels(labels)}{refs}"
            )
        except Exception as e:
            print(f"⚠️  Schema dump: could not load taxonomy '{scheme_id}': {e}")
    lines.append("")
    lines.append(_format_relationship_block())
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
    """Call LLM via llm_client (routes to OpenAI or Ollama based on env)."""
    raw = await _llm_chat(prompt, temperature=0.1)

    # Strip markdown fences
    content = raw.strip()
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


async def _generate_answer(question: str, results: List[Dict], sparql: str,
                           system_prompt: Optional[str] = None) -> str:
    if not results:
        # Check if question is out of scope based on system prompt
        if system_prompt and any(kw in question.lower() for kw in ["cve", "exploit", "patch", "vulnerability", "nvd"]):
            return "That information is not available in the ProtoGraph knowledge graph. I can only answer questions about Library Modules, TTPs, and Execution Sequences."
        return "No results found for your query."

    result_text = json.dumps(results[:10], indent=2, default=str)

    scope_block = ""
    if system_prompt:
        scope_block = f"""AGENT CONTEXT (follow these rules strictly):
{system_prompt}

"""

    prompt = f"""{scope_block}Given this question and the query results, provide a clear, concise answer.
Do not mention SPARQL or databases. Just answer the question naturally.
Only use information from the results below — do not add external knowledge.

Question: {question}

Results ({len(results)} total):
{result_text}

Answer in 2-3 sentences. Be specific — cite names, counts, and key details from the results.
If the question asks about something not in the results (like CVEs, exploits, or threat intel), say: 'That information is not available in the ProtoGraph knowledge graph.'"""

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

    # Load agent system prompt — from request directly or from disk via plugin_id
    agent_system_prompt: Optional[str] = request.system_prompt
    if not agent_system_prompt and request.plugin_id:
        try:
            import re as _re
            from pathlib import Path as _Path
            agent_py = _Path(__file__).parent.parent / "plugins" / request.plugin_id / "agent.py"
            if agent_py.exists():
                agent_src = agent_py.read_text()
                m = _re.search(r'\s*SYSTEM_PROMPT\s*=\s*"""(.*?)"""', agent_src, _re.DOTALL)
                if m:
                    agent_system_prompt = m.group(1).strip()
        except Exception:
            pass

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
        schema, rag_fragments = _build_schema_context(question, recon=recon_block)

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
            answer = await _generate_answer(question, results, sparql, system_prompt=agent_system_prompt)
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
    Legacy offline fallback, now disabled.

    Every branch of the original implementation queried proto:LibraryModule,
    proto:TTP or proto:Team \u2014 `atlas` classes that do not exist in every
    repository. Against `razor-code` it could only ever return syntactically
    valid SPARQL over classes with zero instances, i.e. a confident empty
    answer that looks like a real finding.

    Returning None makes the caller surface an honest "LLM unavailable" error
    instead. That is strictly better than a plausible wrong answer.

    If you want an offline fallback again, build it from the live ontology
    (see _live_relationship_types and gdb.get_ontology_types) rather than from
    a fixed class list.
    """
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
        "model":  active_model(),
        "embed_model": active_embed_model(),
        "backend": _llm_backend_info()["backend"],
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