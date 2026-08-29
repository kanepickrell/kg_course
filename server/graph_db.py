"""
GraphDB Adapter for ProtoGraph ATLAS
=====================================
Provides the same data shapes as the ArangoDB queries in main.py,
but sources data from GraphDB via SPARQL.

Usage:
    from graph_db import GraphDBAdapter
    
    gdb = GraphDBAdapter("http://localhost:7200", "my-repo")
    
    # Same shape as: db.collection("SourceFile").get("src_logger_ps1")
    doc = gdb.get_artifact("SourceFile", "src_logger_ps1")
    
    # Same shape as: /graph endpoint returns
    graph = gdb.get_full_graph()
    
    # Same shape as: /neighbors endpoint returns
    neighbors = gdb.get_neighbors("SourceFile/src_logger_ps1", depth=2)

All responses match the JSON shapes your React frontend expects.
No frontend changes needed.
"""

import httpx
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone


# ============================================================
# NAMESPACE PREFIXES
# ============================================================

PREFIXES = """
PREFIX rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs:  <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:   <http://www.w3.org/2002/07/owl#>
PREFIX xsd:   <http://www.w3.org/2001/XMLSchema#>
PREFIX skos:  <http://www.w3.org/2004/02/skos/core#>
PREFIX sh:    <http://www.w3.org/ns/shacl#>
PREFIX proto: <https://proto.atlas/ontology/>
PREFIX data:  <https://proto.atlas/data/>
PREFIX tax:   <https://proto.atlas/taxonomy/>
PREFIX rel:   <https://proto.atlas/relationship/>
"""

# NOTE: there is deliberately no CLASS_TO_COLLECTION / COLLECTION_TO_CLASS map
# here any more.
#
# The old dict mapped each class URI to its own local name \u2014 an identity
# mapping. It translated nothing. Its only real effect was acting as a hidden
# allowlist: create_node raised ValueError for any class not listed, so every
# class declared through the ontology manager ALSO had to be added to this file
# and the server restarted before it could be written.
#
# Class names now come from the ontology in GraphDB. See:
#   GraphDBAdapter.live_class_uris()       \u2014 declared owl:Class URIs, cached
#   GraphDBAdapter.uri_to_collection()     \u2014 URI  -> collection name (reads)
#   GraphDBAdapter.collection_to_class_uri() \u2014 name -> URI, validated (writes)

# NOTE: there is deliberately no REL_URI_TO_LABEL map here either.
#
# Like the class map, it was an identity mapping \u2014 every relationship URI to its
# own local name. See GraphDBAdapter._rel_label() and live_relationship_uris().

DATA_NS = "https://proto.atlas/data/"
ONTOLOGY_NS = "https://proto.atlas/ontology/"
REL_NS = "https://proto.atlas/relationship/"
TAX_NS = "https://proto.atlas/taxonomy/"


class GraphDBAdapter:
    """
    Drop-in adapter that translates ArangoDB-style calls to SPARQL queries.
    Returns JSON shapes identical to what main.py currently returns.
    """

    def __init__(self, endpoint: str = "http://localhost:7200", repo: str = ""):
        self.endpoint = endpoint.rstrip("/")
        if not repo:
            raise ValueError(
                "GraphDBAdapter requires an explicit repo name. There is no default "
                "repository \u2014 set GRAPHDB_REPO."
            )
        self.repo = repo
        self.query_url = f"{self.endpoint}/repositories/{self.repo}"
        self.update_url = f"{self.endpoint}/repositories/{self.repo}/statements"
        self.client = httpx.Client(timeout=30.0)
        # scheme_id â†’ resolved URI. Only successful lookups are cached so a
        # later TTL commit that inserts a ConceptScheme is still discoverable.
        self._scheme_uri_cache: Dict[str, str] = {}
        # Relationship types declared in THIS repo's ontology. Cached because
        # edge traversal needs them on every call; invalidated by
        # invalidate_relationship_cache() after an ontology change.
        self._rel_uri_cache: Optional[List[str]] = None
        # Declared owl:Class URIs for this repo. Same lifecycle as the
        # relationship cache; invalidate_ontology_cache() clears both.
        self._class_uri_cache: Optional[List[str]] = None
        # Property name -> taxonomy scheme, from proto:taxonomy.
        self._tax_prop_cache: Optional[Dict[str, str]] = None
        print(f"âœ“ GraphDB adapter initialized: {self.query_url}")

    # ============================================================
    # LOW-LEVEL SPARQL EXECUTION
    # ============================================================

    def sparql_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute a SPARQL SELECT and return list of binding dicts."""
        full_query = PREFIXES + "\n" + query
        response = self.client.post(
            self.query_url,
            data={"query": full_query},
            headers={"Accept": "application/sparql-results+json"},
        )
        response.raise_for_status()
        results = response.json()

        rows = []
        for binding in results.get("results", {}).get("bindings", []):
            row = {}
            for var, val in binding.items():
                if val["type"] == "uri":
                    row[var] = val["value"]
                elif val["type"] == "literal":
                    # Handle typed literals
                    datatype = val.get("datatype", "")
                    if "integer" in datatype:
                        row[var] = int(val["value"])
                    elif "float" in datatype or "double" in datatype or "decimal" in datatype:
                        row[var] = float(val["value"])
                    elif "boolean" in datatype:
                        row[var] = val["value"].lower() == "true"
                    else:
                        row[var] = val["value"]
                else:
                    row[var] = val["value"]
            rows.append(row)
        return rows

    def sparql_update(self, update: str) -> bool:
        """Execute a SPARQL UPDATE (INSERT/DELETE)."""
        full_update = PREFIXES + "\n" + update
        response = self.client.post(
            self.update_url,
            data={"update": full_update},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return True

    def sparql_ask(self, query: str) -> bool:
        """Execute a SPARQL ASK and return boolean."""
        full_query = PREFIXES + "\n" + query
        response = self.client.post(
            self.query_url,
            data={"query": full_query},
            headers={"Accept": "application/sparql-results+json"},
        )
        response.raise_for_status()
        return response.json().get("boolean", False)

    # ============================================================
    # URI / ID CONVERSION HELPERS
    # ============================================================

    def key_to_uri(self, key: str) -> str:
        """Convert an artifact key to a data: URI."""
        return f"{DATA_NS}{key}"

    def uri_to_key(self, uri: str) -> str:
        """Extract the key portion from a data: URI."""
        if uri.startswith(DATA_NS):
            return uri[len(DATA_NS):]
        return uri.rsplit("/", 1)[-1]

    def uri_to_collection(self, class_uri: str) -> str:
        """
        Convert a class URI to an ArangoDB-style collection name.

        The collection name IS the URI's local name. The old lookup table mapped
        each URI to exactly that string, so this is the same result with no list
        to keep in sync.
        """
        return class_uri.rsplit("/", 1)[-1]

    # ============================================================
    # LIVE ONTOLOGY (classes + relationship types)
    # ============================================================
    # Nothing below hardcodes a class or relationship name. The ontology in
    # GraphDB is the single source of truth, so a type declared through the
    # ontology manager is usable immediately \u2014 no code edit, no restart.

    def live_class_uris(self, refresh: bool = False) -> List[str]:
        """Concrete owl:Class URIs declared in this repository's ontology."""
        if self._class_uri_cache is not None and not refresh:
            return self._class_uri_cache
        try:
            rows = self.sparql_query(f"""
                SELECT DISTINCT ?cls WHERE {{
                    ?cls a owl:Class .
                    FILTER(STRSTARTS(STR(?cls), "{ONTOLOGY_NS}"))
                    FILTER(?cls NOT IN (proto:Thing, proto:Artifact, proto:Agent, proto:WorkItem))
                }}
                ORDER BY ?cls
            """)
            self._class_uri_cache = [r["cls"] for r in rows]
        except Exception as e:
            print(f"\u26a0\ufe0f  Could not read ontology classes: {e}")
            self._class_uri_cache = []
        return self._class_uri_cache

    def live_collections(self, refresh: bool = False) -> List[str]:
        """Declared class names (collection names), e.g. ['Codebase', 'SourceFile']."""
        return [u.rsplit("/", 1)[-1] for u in self.live_class_uris(refresh=refresh)]

    def collection_to_class_uri(self, collection: str) -> Optional[str]:
        """
        Resolve a collection name to its declared class URI, or None if the
        ontology does not declare it.

        Case-insensitive, because callers arrive with 'sourcefile', 'SourceFile'
        and 'source_file' depending on which layer they came through.
        """
        want = collection.replace("_", "").lower()
        for uri in self.live_class_uris():
            if uri.rsplit("/", 1)[-1].replace("_", "").lower() == want:
                return uri
        return None

    def taxonomy_properties(self, refresh: bool = False) -> Dict[str, str]:
        """
        Property name -> taxonomy scheme, for every property the ontology marks
        as taxonomy-valued via proto:taxonomy.
        """
        if self._tax_prop_cache is not None and not refresh:
            return self._tax_prop_cache
        try:
            rows = self.sparql_query(f"""
                SELECT DISTINCT ?prop ?taxonomy WHERE {{
                    ?prop proto:taxonomy ?taxonomy .
                    FILTER(STRSTARTS(STR(?prop), "{ONTOLOGY_NS}"))
                }}
            """)
            self._tax_prop_cache = {
                r["prop"].rsplit("/", 1)[-1]: r["taxonomy"] for r in rows
            }
        except Exception as e:
            print(f"\u26a0\ufe0f  Could not read taxonomy properties: {e}")
            self._tax_prop_cache = {}
        return self._tax_prop_cache

    def _is_taxonomy_property(self, field: str) -> bool:
        """True if the ontology declares this property as taxonomy-valued."""
        return field in self.taxonomy_properties()

    def invalidate_ontology_cache(self) -> None:
        """
        Clear both ontology caches.

        Call after the ontology manager declares or removes a class or
        relationship type, otherwise this process keeps serving the shape the
        ontology had at first use.
        """
        self._class_uri_cache = None
        self._rel_uri_cache = None
        self._tax_prop_cache = None

    # ============================================================
    # LIVE RELATIONSHIP TYPES
    # ============================================================

    def live_relationship_uris(self, refresh: bool = False) -> List[str]:
        """
        Relationship type URIs declared in this repository's ontology.

        Read from GraphDB rather than a fixed list: a hardcoded set silently
        stops traversing any relationship type the ontology manager adds later,
        and returns an empty result that looks like a finding rather than a bug.
        """
        if self._rel_uri_cache is not None and not refresh:
            return self._rel_uri_cache
        try:
            rows = self.sparql_query(f"""
                SELECT DISTINCT ?rel WHERE {{
                    ?rel a owl:ObjectProperty .
                    FILTER(STRSTARTS(STR(?rel), "{REL_NS}"))
                }}
                ORDER BY ?rel
            """)
            self._rel_uri_cache = [r["rel"] for r in rows]
        except Exception as e:
            print(f"\u26a0\ufe0f  Could not read relationship types: {e}")
            self._rel_uri_cache = []
        return self._rel_uri_cache

    def invalidate_relationship_cache(self) -> None:
        """Call after the ontology manager declares or removes a relationship type."""
        self._rel_uri_cache = None

    def _rel_label(self, rel_uri: str) -> str:
        """
        Display label for an edge predicate.

        This is the URI's local name. The ontology manager creates relationship
        types whose rdfs:label already equals that local name, so there is
        nothing to translate and no list to maintain.
        """
        return rel_uri.rsplit("/", 1)[-1]

    def arango_id(self, class_uri: str, entity_uri: str) -> str:
        """Build an ArangoDB-style _id like 'SourceFile/src_logger_ps1'."""
        collection = self.uri_to_collection(class_uri)
        key = self.uri_to_key(entity_uri)
        return f"{collection}/{key}"

    def resolve_taxonomy_label(self, uri: str) -> Optional[str]:
        """Resolve a taxonomy URI to its prefLabel."""
        rows = self.sparql_query(f"""
            SELECT ?label WHERE {{
                <{uri}> skos:prefLabel ?label .
            }}
        """)
        return rows[0]["label"] if rows else None

    # ============================================================
    # GET ARTIFACT (replaces db.collection(X).get(key))
    # ============================================================

    def get_artifact(self, collection: str, key: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single artifact as a dict matching ArangoDB document shape.
        
        Returns dict with _id, _key, name, description, etc.
        Returns None if not found.
        """
        uri = self.key_to_uri(key)

        # Query 1: Get all types for this entity
        type_rows = self.sparql_query(f"""
            SELECT DISTINCT ?type WHERE {{
                <{uri}> a ?type .
                FILTER(STRSTARTS(STR(?type), "{ONTOLOGY_NS}"))
                FILTER(?type != owl:NamedIndividual)
            }}
        """)

        if not type_rows:
            return None

        types = {row["type"] for row in type_rows}

        # Query 2: Get all properties (DISTINCT eliminates reasoner duplication)
        prop_rows = self.sparql_query(f"""
            SELECT DISTINCT ?p ?o WHERE {{
                <{uri}> ?p ?o .
            }}
        """)

        props = {}
        for row in prop_rows:
            pred = row["p"]
            obj = row["o"]

            # Convert predicate URI to field name
            field = self._pred_to_field(pred)
            if field:
                # If the object is a taxonomy URI, resolve to label
                if isinstance(obj, str) and obj.startswith(TAX_NS):
                    resolved = self.resolve_taxonomy_label(obj)
                    if resolved:
                        obj = resolved
                # Handle multi-value (collect into list, but deduplicate)
                if field in props:
                    existing = props[field]
                    if isinstance(existing, list):
                        if obj not in existing:
                            existing.append(obj)
                    elif existing != obj:
                        props[field] = [existing, obj]
                    # else: same value, skip duplicate
                else:
                    props[field] = obj

        # Determine the most specific class (not Thing, not Artifact)
        specific_type = self._most_specific_type(types)
        coll_name = self.uri_to_collection(specific_type) if specific_type else collection

        doc = {
            "_id": f"{coll_name}/{key}",
            "_key": key,
            "_artifact_type": self.uri_to_collection(specific_type) if specific_type else collection,
            "payload_url": f"/api/ingest/payloads/{key}.json",
            **props,
        }

        return doc

    # ============================================================
    # GET FULL GRAPH (replaces /graph endpoint)
    # ============================================================

    def get_full_graph(self, include_schema: bool = False) -> Dict[str, Any]:
        """
        Fetch all nodes and edges. Returns same shape as /graph endpoint:
        { "nodes": [...], "edges": [...], "count": N }
        """
        # Fetch all artifact instances with every literal property they carry.
        #
        # This used to SELECT a fixed column list (riskLevel, tactic, mitreId,
        # category, subcategory, estimatedDuration, color \u2026) \u2014 atlas property
        # names baked into the query. In any other repository those OPTIONALs
        # bound nothing and every node came back padded with empty strings for
        # properties that do not exist, while properties that DO exist were
        # dropped because they were not in the column list.
        #
        # Now: one row per (entity, predicate, value), assembled per entity.
        node_rows = self.sparql_query(f"""
            SELECT ?entity ?type ?prop ?value ?label WHERE {{
                ?entity a ?type .
                FILTER(STRSTARTS(STR(?entity), "{DATA_NS}"))
                FILTER(STRSTARTS(STR(?type), "{ONTOLOGY_NS}"))
                FILTER(?type NOT IN (proto:Thing, proto:Artifact, proto:Agent, proto:WorkItem))

                OPTIONAL {{
                    ?entity ?prop ?value .
                    FILTER(STRSTARTS(STR(?prop), "{ONTOLOGY_NS}"))
                    # Resolve taxonomy/concept references to their label
                    OPTIONAL {{ ?value skos:prefLabel ?label }}
                }}
            }}
        """)

        # Assemble: entity URI -> {type, properties}
        by_entity: Dict[str, Dict[str, Any]] = {}
        for row in node_rows:
            entity_uri = row["entity"]
            rec = by_entity.setdefault(
                entity_uri, {"type": row["type"], "props": {}}
            )
            prop_uri = row.get("prop")
            if not prop_uri:
                continue
            field = prop_uri.rsplit("/", 1)[-1]
            # Prefer a resolved concept label over a raw URI
            rec["props"][field] = row.get("label") or row.get("value", "")

        nodes = []
        for entity_uri, rec in by_entity.items():
            type_uri = rec["type"]
            props = rec["props"]
            key = self.uri_to_key(entity_uri)
            collection = self.uri_to_collection(type_uri)
            artifact_type = collection.replace("_", " ")

            desc = str(props.get("description", ""))
            if len(desc) > 200:
                desc = desc[:200]

            node = {
                "id": f"{collection}/{key}",
                "label": props.get("name", key),
                "type": artifact_type,
                "_artifact_type": artifact_type,
                "description": desc,
                "importance": 0.5,
            }
            # Everything else the ontology actually defines for this artifact,
            # passed through under its own name rather than a fixed column set.
            for field, value in props.items():
                if field not in ("name", "description"):
                    node[field] = value
            nodes.append(node)

        # Fetch all relationship edges
        edge_rows = self.sparql_query("""
            SELECT ?from ?rel ?to WHERE {
                ?from ?rel ?to .
                FILTER(STRSTARTS(STR(?rel), "https://proto.atlas/relationship/"))
                FILTER(STRSTARTS(STR(?from), "https://proto.atlas/data/"))
                FILTER(STRSTARTS(STR(?to), "https://proto.atlas/data/"))
            }
        """)

        # Build node_id set for filtering (only include edges where both endpoints exist)
        node_ids = set(n["id"] for n in nodes)

        edges = []
        for row in edge_rows:
            from_key = self.uri_to_key(row["from"])
            to_key = self.uri_to_key(row["to"])
            rel_label = self._rel_label(row["rel"])

            # Need to find the collection for from/to to build ArangoDB-style IDs
            from_id = self._find_node_id(from_key, node_ids)
            to_id = self._find_node_id(to_key, node_ids)

            if from_id and to_id and from_id in node_ids and to_id in node_ids:
                edges.append({
                    "id": f"{rel_label}/{from_key}-{to_key}",
                    "source": from_id,
                    "target": to_id,
                    "type": rel_label.lower(),
                    "relationship_type": rel_label,
                    "weight": 1.0,
                    "confidence": 0,
                })

        print(f"âœ… GraphDB: Returning {len(nodes)} nodes and {len(edges)} edges")
        return {"nodes": nodes, "edges": edges, "count": len(nodes)}

    # ============================================================
    # GET NEIGHBORS (replaces /neighbors endpoint)
    # ============================================================

    def get_neighbors(self, node_id: str, depth: int = 1) -> Dict[str, Any]:
        """
        Fetch connected nodes within N hops. Returns same shape as /neighbors.
        
        node_id: ArangoDB-style "Collection/key"
        """
        collection, key = node_id.split("/", 1)
        uri = self.key_to_uri(key)

        # Get center node
        center = self.get_artifact(collection, key)
        if not center:
            return None

        # Property path with depth control
        # {1,N} syntax for variable-length paths
        path_expr = f"1,{depth}" if depth > 1 else "1"

        # Outbound + inbound neighbors via relationship edges
        neighbor_rows = self.sparql_query(f"""
            SELECT DISTINCT ?neighbor ?type ?name ?rel ?direction WHERE {{
                {{
                    <{uri}> ?rel ?neighbor .
                    BIND("outbound" AS ?direction)
                }} UNION {{
                    ?neighbor ?rel <{uri}> .
                    BIND("inbound" AS ?direction)
                }}
                FILTER(STRSTARTS(STR(?rel), "{REL_NS}"))
                FILTER(STRSTARTS(STR(?neighbor), "{DATA_NS}"))

                ?neighbor a ?type .
                FILTER(STRSTARTS(STR(?type), "{ONTOLOGY_NS}"))
                FILTER(?type NOT IN (proto:Thing, proto:Artifact, proto:Agent, proto:WorkItem))

                OPTIONAL {{ ?neighbor proto:name ?name }}
            }}
        """)

        # Build neighbor nodes and edges
        seen_nodes = set()
        nodes = []
        edges = []

        for row in neighbor_rows:
            n_uri = row["neighbor"]
            n_key = self.uri_to_key(n_uri)
            n_type = row["type"]
            n_collection = self.uri_to_collection(n_type)
            n_id = f"{n_collection}/{n_key}"
            rel_label = self._rel_label(row["rel"])

            if n_uri not in seen_nodes:
                seen_nodes.add(n_uri)
                # Fetch full artifact for neighbor
                neighbor_doc = self.get_artifact(n_collection, n_key)
                if neighbor_doc:
                    nodes.append(neighbor_doc)

            # Build edge
            if row.get("direction") == "outbound":
                edge_from = node_id
                edge_to = n_id
            else:
                edge_from = n_id
                edge_to = node_id

            edge_id = f"{rel_label}/{self.uri_to_key(edge_from.split('/')[-1])}-{n_key}"
            edges.append({
                "_id": edge_id,
                "_from": edge_from,
                "_to": edge_to,
                "type": rel_label.lower(),
                "relationship_type": rel_label,
                "weight": 1.0,
            })

        # Multi-hop for depth > 1
        if depth > 1:
            nodes, edges = self._expand_depth(uri, node_id, nodes, edges, seen_nodes, depth)

        return {
            "center": center,
            "depth": depth,
            "nodes": nodes,
            "edges": edges,
            "count": len(nodes),
        }

    # ============================================================
    # SEARCH (replaces /api/search/smart)
    # ============================================================

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Text search across all artifacts. Uses SPARQL regex filtering.
        Returns list of artifact dicts.
        """
        # Escape special regex characters
        safe_query = query.replace("\\", "\\\\").replace('"', '\\"')

        rows = self.sparql_query(f"""
            SELECT DISTINCT ?entity ?type ?name ?description WHERE {{
                ?entity a ?type ;
                        proto:name ?name .
                FILTER(STRSTARTS(STR(?entity), "{DATA_NS}"))
                FILTER(STRSTARTS(STR(?type), "{ONTOLOGY_NS}"))
                FILTER(?type NOT IN (proto:Thing, proto:Artifact, proto:Agent, proto:WorkItem))

                OPTIONAL {{ ?entity proto:description ?description }}

                FILTER(
                    REGEX(?name, "{safe_query}", "i") ||
                    REGEX(COALESCE(?description, ""), "{safe_query}", "i")
                )
            }}
            LIMIT {limit}
        """)

        results = []
        for row in rows:
            key = self.uri_to_key(row["entity"])
            collection = self.uri_to_collection(row["type"])
            results.append({
                "_id": f"{collection}/{key}",
                "_key": key,
                "name": row.get("name", key),
                "description": row.get("description", ""),
                "_artifact_type": collection,
                "type": collection,
            })
        return results

    # ============================================================
    # CRUD - CREATE NODE
    # ============================================================

    def create_node(
        self,
        key: str,
        artifact_type: str,
        properties: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Insert a new artifact. 
        
        artifact_type: a class name the ontology declares, e.g. "SourceFile".
        """
        uri = self.key_to_uri(key)

        # Validate against the ontology, not a list in this file. A class
        # declared through the ontology manager is writable immediately.
        class_uri = self.collection_to_class_uri(artifact_type)
        if not class_uri:
            declared = self.live_collections()
            if declared:
                raise ValueError(
                    f"Unknown artifact type: {artifact_type!r}. "
                    f"Declared classes in this repository: {', '.join(declared)}. "
                    f"Declare it in the ontology manager first."
                )
            raise ValueError(
                f"Unknown artifact type: {artifact_type!r}. This repository has no "
                f"owl:Class declarations at all \u2014 load a bootstrap ontology before "
                f"writing artifacts."
            )

        # Build INSERT DATA triples
        triples = [f"    <{uri}> a <{class_uri}> ."]

        for field, value in properties.items():
            triple = self._field_to_triple(uri, field, value)
            if triple:
                triples.append(triple)

        insert_query = "INSERT DATA {\n" + "\n".join(triples) + "\n}"
        self.sparql_update(insert_query)

        print(f"âœ“ GraphDB: Created {artifact_type}/{key}")
        return {
            "success": True,
            "_id": f"{artifact_type}/{key}",
            "_key": key,
            "_artifact_type": artifact_type,
        }

    # ============================================================
    # CRUD - CREATE EDGE
    # ============================================================

    def create_edge(
        self,
        from_collection: str,
        from_key: str,
        to_collection: str,
        to_key: str,
        relationship_type: str,
        source: str = "manual",
        confidence: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Insert a relationship edge between two artifacts.

        source: provenance tag â€” "ontology_rule", "operator_authored",
                "manual", "execution_log", "llm_suggested"
        confidence: 0.0â€“1.0 (1.0 for deterministic rules)
        """
        from_uri = self.key_to_uri(from_key)
        to_uri = self.key_to_uri(to_key)
        rel_uri = f"{REL_NS}{relationship_type}"

        # Edge as a triple
        edge_triple = f"<{from_uri}> <{rel_uri}> <{to_uri}>"

        # Use RDF reification to attach provenance to the edge
        import hashlib
        edge_id = hashlib.md5(f"{from_key}-{relationship_type}-{to_key}".encode()).hexdigest()[:12]
        stmt_uri = f"{DATA_NS}edge-{edge_id}"

        self.sparql_update(f"""
            INSERT DATA {{
                {edge_triple} .
                <{stmt_uri}> a rdf:Statement ;
                    rdf:subject <{from_uri}> ;
                    rdf:predicate <{rel_uri}> ;
                    rdf:object <{to_uri}> ;
                    proto:edgeSource "{source}" ;
                    proto:edgeConfidence "{confidence}"^^xsd:double .
            }}
        """)

        from_id = f"{from_collection}/{from_key}"
        to_id = f"{to_collection}/{to_key}"
        print(f"âœ“ GraphDB: Edge {from_id} --{relationship_type}--> {to_id} [source={source}]")

        return {
            "success": True,
            "_id": f"{relationship_type}/{from_key}-{to_key}",
            "_from": from_id,
            "_to": to_id,
            "relationship_type": relationship_type,
            "source": source,
            "confidence": confidence,
        }

    # ============================================================
    # CRUD - DELETE NODE
    # ============================================================

    def delete_node(self, collection: str, key: str) -> bool:
        """Delete an artifact and all its edges."""
        uri = self.key_to_uri(key)

        # Delete all triples where this entity is subject or object
        self.sparql_update(f"""
            DELETE WHERE {{ <{uri}> ?p ?o . }}
        """)
        self.sparql_update(f"""
            DELETE WHERE {{ ?s ?p <{uri}> . }}
        """)

        print(f"âœ“ GraphDB: Deleted {collection}/{key}")
        return True

    # ============================================================
    # CRUD - DELETE EDGE
    # ============================================================

    def delete_edge(self, from_key: str, to_key: str, relationship_type: str) -> bool:
        """Delete a specific relationship edge."""
        from_uri = self.key_to_uri(from_key)
        to_uri = self.key_to_uri(to_key)
        rel_uri = f"{REL_NS}{relationship_type}"

        self.sparql_update(f"""
            DELETE DATA {{
                <{from_uri}> <{rel_uri}> <{to_uri}> .
            }}
        """)

        print(f"âœ“ GraphDB: Deleted edge {from_key} --{relationship_type}--> {to_key}")
        return True

    # ============================================================
    # CRUD - UPDATE NODE
    # ============================================================

    def update_node(self, collection: str, key: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update fields on an existing artifact."""
        uri = self.key_to_uri(key)

        for field, value in updates.items():
            pred_uri = self._field_to_pred_uri(field)
            if not pred_uri:
                continue

            # Delete old value, insert new
            self.sparql_update(f"""
                DELETE WHERE {{ <{uri}> <{pred_uri}> ?old . }}
            """)

            triple = self._field_to_triple(uri, field, value)
            if triple:
                self.sparql_update(f"INSERT DATA {{\n{triple}\n}}")

        return {
            "success": True,
            "_id": f"{collection}/{key}",
            "_key": key,
        }

    # ============================================================
    # UTILITY: Get all collections (types with instances)
    # ============================================================

    def get_collections(self) -> List[str]:
        """Return list of artifact type names that have instances (like collection list)."""
        rows = self.sparql_query(f"""
            SELECT DISTINCT ?type WHERE {{
                ?entity a ?type .
                FILTER(STRSTARTS(STR(?entity), "{DATA_NS}"))
                FILTER(STRSTARTS(STR(?type), "{ONTOLOGY_NS}"))
                FILTER(?type NOT IN (proto:Thing, proto:Artifact, proto:Agent, proto:WorkItem))
            }}
        """)
        return [self.uri_to_collection(row["type"]) for row in rows]

    # ============================================================
    # UTILITY: Check if artifact exists
    # ============================================================

    def has_artifact(self, key: str) -> bool:
        """Check if an artifact exists by key."""
        uri = self.key_to_uri(key)
        return self.sparql_ask(f"""
            ASK {{ <{uri}> a ?type }}
        """)

    # ============================================================
    # UTILITY: Taxonomy scheme / terms
    # ============================================================

    @staticmethod
    def _bare_scheme_id(scheme_id: str) -> str:
        """Normalize scheme_id, stripping a leading 'scheme-' if present."""
        return scheme_id[len("scheme-"):] if scheme_id.startswith("scheme-") else scheme_id

    def invalidate_scheme_uri_cache(self, scheme_id: Optional[str] = None) -> None:
        """Drop cached scheme URI lookups. Pass scheme_id to clear one entry, or None for all."""
        if scheme_id is None:
            self._scheme_uri_cache.clear()
        else:
            self._scheme_uri_cache.pop(self._bare_scheme_id(scheme_id), None)

    def resolve_scheme_uri(self, scheme_id: str) -> Optional[str]:
        """Resolve a scheme_id to its actual URI.

        Handles both conventions:
          - tax:scheme-{id}  â€” minted by Ontology Manager create_taxonomy
          - tax:{id}         â€” used by seeded / hand-loaded TTL

        Successful lookups are cached; misses are not (so TTL-inserted schemes
        remain discoverable). Call invalidate_scheme_uri_cache after
        create_taxonomy / delete_taxonomy / ttl commit.
        """
        bare_id = self._bare_scheme_id(scheme_id)
        if bare_id in self._scheme_uri_cache:
            return self._scheme_uri_cache[bare_id]

        for candidate in (f"{TAX_NS}scheme-{bare_id}", f"{TAX_NS}{bare_id}"):
            if self.sparql_ask(f"ASK {{ <{candidate}> a skos:ConceptScheme }}"):
                self._scheme_uri_cache[bare_id] = candidate
                return candidate
        return None

    def get_filterable_properties(
        self,
        max_cardinality: int = 50,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Low-cardinality ontology properties worth sampling for FILTER grounding."""
        rows = self.sparql_query(f"""
            SELECT ?p (COUNT(DISTINCT ?v) AS ?card)
                   (SAMPLE(?v) AS ?sample) WHERE {{
                ?s ?p ?v .
                FILTER(STRSTARTS(STR(?p), "{ONTOLOGY_NS}"))
            }}
            GROUP BY ?p
            HAVING (COUNT(DISTINCT ?v) > 1 && COUNT(DISTINCT ?v) <= {int(max_cardinality)})
            ORDER BY ?card
            LIMIT {int(limit)}
        """)

        deny = {
            "name", "description", "id", "key", "comment", "definition",
            "label", "prefLabel", "altLabel",
        }
        out: List[Dict[str, Any]] = []
        for row in rows:
            prop_uri = str(row.get("p") or "")
            if not prop_uri:
                continue
            local = prop_uri.rsplit("/", 1)[-1]
            if local in deny:
                continue
            sample = str(row.get("sample", "") or "")
            # Free-text values are long even at low cardinality on small graphs
            if len(sample) > 60:
                continue
            out.append({
                "property": prop_uri,
                "cardinality": int(row.get("card", 0) or 0),
                "kind": "skos" if sample.startswith("http") else "literal",
            })
        return out

    def get_taxonomy_schemes(self) -> List[Dict[str, Any]]:
        """All SKOS concept schemes in the graph, with term counts."""
        rows = self.sparql_query("""
            SELECT ?scheme ?label ?description (COUNT(?term) AS ?termCount) WHERE {
                ?scheme a skos:ConceptScheme .
                OPTIONAL { ?scheme rdfs:label ?label }
                OPTIONAL { ?scheme rdfs:comment ?description }
                OPTIONAL { ?term skos:inScheme ?scheme }
            }
            GROUP BY ?scheme ?label ?description
            ORDER BY ?label
        """)

        out: List[Dict[str, Any]] = []
        for row in rows:
            uri = row["scheme"]
            if uri.startswith(TAX_NS):
                local = uri[len(TAX_NS):]
            else:
                local = uri.rsplit("/", 1)[-1]
            # removeprefix semantics â€” do not use unanchored .replace("scheme-", "")
            scheme_id = local[len("scheme-"):] if local.startswith("scheme-") else local
            out.append({
                "scheme_id": scheme_id,
                "uri": uri,
                "label": row.get("label", scheme_id),
                "description": row.get("description", ""),
                "term_count": int(row.get("termCount", 0) or 0),
            })
        return out

    def get_taxonomy_terms(self, scheme_id: str) -> List[Dict[str, str]]:
        """Get all terms in a taxonomy scheme."""
        scheme_uri = self.resolve_scheme_uri(scheme_id)
        if not scheme_uri:
            return []

        rows = self.sparql_query(f"""
            SELECT ?term ?label ?alias WHERE {{
                ?term skos:inScheme <{scheme_uri}> ;
                      skos:prefLabel ?label .
                OPTIONAL {{ ?term skos:altLabel ?alias }}
            }}
            ORDER BY ?label
        """)

        terms = {}
        for row in rows:
            uri = row["term"]
            if uri not in terms:
                terms[uri] = {
                    "uri": uri,
                    "label": row["label"],
                    "aliases": [],
                }
            if row.get("alias"):
                terms[uri]["aliases"].append(row["alias"])

        return list(terms.values())

    # ============================================================
    # INGESTION: Ontology & Taxonomy Helpers
    # ============================================================

    def resolve_taxonomy_value(self, scheme_id: str, value: str) -> Optional[Dict[str, str]]:
        """
        Resolve a string value to a SKOS concept URI within a taxonomy scheme.
        Matches against prefLabel and altLabel (case-insensitive).
        Returns {"uri": ..., "label": ...} or None.
        """
        scheme_uri = self.resolve_scheme_uri(scheme_id)
        if not scheme_uri:
            return None

        safe_val = value.replace('"', '\\"')
        rows = self.sparql_query(f"""
            SELECT ?term ?label WHERE {{
                ?term skos:inScheme <{scheme_uri}> ;
                      skos:prefLabel ?label .
                OPTIONAL {{ ?term skos:altLabel ?alias }}
                FILTER(
                    LCASE(?label) = LCASE("{safe_val}") ||
                    LCASE(?alias) = LCASE("{safe_val}")
                )
            }}
            LIMIT 1
        """)
        if rows:
            return {"uri": rows[0]["term"], "label": rows[0]["label"]}
        return None

    def get_ontology_types(self) -> List[Dict[str, Any]]:
        """
        Get all concrete (instantiable) artifact types from the OWL ontology.
        Returns list of {label, uri, definition, collection, properties}.
        """
        rows = self.sparql_query("""
            SELECT ?cls ?label ?definition WHERE {
                ?cls a owl:Class ;
                     rdfs:label ?label .
                OPTIONAL { ?cls rdfs:comment ?definition }
                FILTER(STRSTARTS(STR(?cls), "https://proto.atlas/ontology/"))
                FILTER(?cls NOT IN (proto:Thing, proto:Artifact, proto:Agent, proto:WorkItem))
            }
            ORDER BY ?label
        """)

        types = []
        for row in rows:
            cls_uri = row["cls"]
            label = row.get("label", "")
            coll = self.uri_to_collection(cls_uri)

            # Get properties for this class
            props = self._get_class_properties(cls_uri)

            types.append({
                "label": label,
                "uri": cls_uri,
                "definition": row.get("definition", ""),
                "collection": coll,
                "properties": props,
            })

        return types

    def _get_class_properties(self, class_uri: str) -> List[Dict[str, Any]]:
        """
        Get the properties defined for an OWL class by checking
        rdfs:domain declarations. Uses explicit graph only to avoid
        OWL2-RL reasoner propagating domains up the hierarchy.
        Also walks up parent chain manually to get inherited properties.
        """
        # Step 1: Get the class hierarchy (explicit parents only)
        hierarchy = self.sparql_query(f"""
            SELECT ?ancestor WHERE {{
                <{class_uri}> rdfs:subClassOf* ?ancestor .
                FILTER(STRSTARTS(STR(?ancestor), "https://proto.atlas/ontology/"))
            }}
        """)
        ancestor_uris = [class_uri] + [r["ancestor"] for r in hierarchy if r["ancestor"] != class_uri]

        # Step 2: Query properties using proto:definedOn (our custom predicate)
        # The reasoner doesn't touch proto: predicates, so scoping is exact
        domain_values = " ".join([f"<{uri}>" for uri in ancestor_uris])
        
        rows = self.sparql_query(f"""
            SELECT DISTINCT ?prop ?propLabel ?range ?propType ?multiple ?taxonomy ?description ?domain
            WHERE {{
                VALUES ?domain {{ {domain_values} }}
                ?prop proto:definedOn ?domain .
                OPTIONAL {{ ?prop rdfs:label ?propLabel }}
                OPTIONAL {{ ?prop rdfs:range ?range }}
                OPTIONAL {{ ?prop a ?propType . FILTER(?propType IN (owl:ObjectProperty, owl:DatatypeProperty)) }}
                OPTIONAL {{ ?prop proto:multiple ?multiple }}
                OPTIONAL {{ ?prop proto:taxonomy ?taxonomy }}
                OPTIONAL {{ ?prop rdfs:comment ?description }}
                OPTIONAL {{ ?prop proto:required ?required }}
                OPTIONAL {{
                    ?shape sh:targetClass ?domain ;
                           sh:property ?pshape .
                    ?pshape sh:path ?prop ;
                            sh:minCount ?minCount .
                }}
                FILTER(STRSTARTS(STR(?prop), "https://proto.atlas/ontology/"))
            }}
            ORDER BY ?propLabel
        """)

        # Required fields come from the ontology, per property:
        #   proto:required true       \u2014 set by the ontology manager, or
        #   sh:minCount >= 1          \u2014 set by a SHACL node shape
        # This used to be a dict of atlas class names in this file, which meant a
        # class declared through the ontology manager silently got "name" as its
        # only required field no matter what its shape said.
        required_for_this_class = set()
        for row in rows:
            prop_name = row["prop"].rsplit("/", 1)[-1]
            if row.get("required") in (True, "true"):
                required_for_this_class.add(prop_name)
            min_count = row.get("minCount")
            if min_count is not None:
                try:
                    if int(min_count) >= 1:
                        required_for_this_class.add(prop_name)
                except (TypeError, ValueError):
                    pass

        props = []
        seen = set()
        for row in rows:
            prop_uri = row["prop"]
            if prop_uri in seen:
                continue
            seen.add(prop_uri)

            name = prop_uri.split("/")[-1]
            range_uri = row.get("range", "")
            owl_type = row.get("propType", "")
            is_multiple = row.get("multiple") == "true"
            taxonomy_value = row.get("taxonomy")
            desc = row.get("description")

            # Determine type from OWL property type and range
            prop_type = "string"
            target_class = None

            if owl_type and "ObjectProperty" in owl_type:
                # Reference to another OWL class
                prop_type = "reference"
                if range_uri and range_uri.startswith("https://proto.atlas/ontology/"):
                    target_class = range_uri.split("/")[-1]
            elif "integer" in range_uri:
                prop_type = "integer"
            elif "boolean" in range_uri:
                prop_type = "boolean"
            elif "dateTime" in range_uri:
                prop_type = "datetime"
            elif "double" in range_uri:
                prop_type = "double"
            elif "Concept" in range_uri:
                prop_type = "uri"

            prop_entry = {
                "name": name,
                "label": row.get("propLabel", name),
                "type": prop_type,
                "required": name in required_for_this_class,
                "multiple": is_multiple,
            }

            if target_class:
                prop_entry["target_class"] = target_class

            # Taxonomy comes from the graph (proto:taxonomy) or not at all.
            if taxonomy_value:
                prop_entry["taxonomy"] = taxonomy_value

            if desc:
                prop_entry["description"] = desc

            props.append(prop_entry)

        return props

    # _detect_taxonomy_scheme() was removed.
    #
    # It guessed a property's taxonomy scheme from a hardcoded map of four atlas
    # property names (category, riskLevel, team, tactic). The ontology already
    # states this per property via proto:taxonomy, which the property query above
    # reads directly \u2014 so the guess only ever fired for properties whose scheme
    # was NOT declared, silently attaching an atlas scheme to a same-named
    # property in an unrelated repository.
    #
    # A property with no proto:taxonomy now simply has no taxonomy. Declare it in
    # the ontology manager if it should have one.

    # ============================================================
    # GENERIC ARTIFACT QUERIES
    # ============================================================
    # These replace get_library_modules / get_library_module /
    # get_library_module_categories / get_library_module_tactics /
    # get_library_module_stats, which hardcoded `?entity a proto:LibraryModule`
    # plus filters on `tactic` and `riskLevel` \u2014 atlas properties that do not
    # exist in an arbitrary repository.
    #
    # BREAKING: plugins/operator_plugin.py and any Lumen/Operator endpoint that
    # called the old methods must be updated to pass the collection explicitly:
    #     gdb.get_library_modules(tactic="TA0006")
    #  -> gdb.get_artifacts_by_type("LibraryModule", filters={"tactic": "TA0006"})
    #     gdb.get_library_module_tactics()
    #  -> gdb.get_property_value_counts("LibraryModule", "tactic")

    def get_artifacts_by_type(
        self,
        collection: str,
        filters: Optional[Dict[str, str]] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        List artifacts of a declared class, optionally filtered by property value.

        collection: a class name the ontology declares, e.g. "SourceFile".
        filters:    {property_name: value}. Values are matched against the
                    literal or, for taxonomy-valued properties, the concept's
                    skos:prefLabel.
        """
        class_uri = self.collection_to_class_uri(collection)
        if not class_uri:
            declared = self.live_collections()
            raise ValueError(
                f"Unknown artifact type: {collection!r}. "
                f"Declared classes: {', '.join(declared) if declared else '(none)'}."
            )

        clauses = []
        for i, (field, value) in enumerate((filters or {}).items()):
            safe = str(value).replace('"', '\\"')
            var = f"?f{i}"
            clauses.append(f"""
                ?entity <{ONTOLOGY_NS}{field}> {var} .
                OPTIONAL {{ {var} skos:prefLabel {var}Label }}
                FILTER(STR(COALESCE({var}Label, {var})) = "{safe}")
            """)

        rows = self.sparql_query(f"""
            SELECT ?entity ?prop ?value ?label WHERE {{
                ?entity a <{class_uri}> .
                {''.join(clauses)}
                OPTIONAL {{
                    ?entity ?prop ?value .
                    FILTER(STRSTARTS(STR(?prop), "{ONTOLOGY_NS}"))
                    OPTIONAL {{ ?value skos:prefLabel ?label }}
                }}
            }}
            LIMIT {limit * 50}
        """)

        by_entity: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            rec = by_entity.setdefault(row["entity"], {})
            prop_uri = row.get("prop")
            if not prop_uri:
                continue
            field = prop_uri.rsplit("/", 1)[-1]
            rec[field] = row.get("label") or row.get("value", "")

        out = []
        for entity_uri, props in list(by_entity.items())[:limit]:
            key = self.uri_to_key(entity_uri)
            doc = {"_id": f"{collection}/{key}", "_key": key,
                   "_artifact_type": collection}
            doc.update(props)
            out.append(doc)
        return out

    def get_property_value_counts(
        self, collection: str, property_name: str,
    ) -> List[Dict[str, Any]]:
        """
        Distinct values of one property across a class, with counts.

        Replaces the old per-property helpers. Works for
        any property the ontology defines on any declared class.
        """
        class_uri = self.collection_to_class_uri(collection)
        if not class_uri:
            raise ValueError(f"Unknown artifact type: {collection!r}")

        rows = self.sparql_query(f"""
            SELECT ?value ?label (COUNT(DISTINCT ?entity) AS ?count) WHERE {{
                ?entity a <{class_uri}> ;
                        <{ONTOLOGY_NS}{property_name}> ?value .
                OPTIONAL {{ ?value skos:prefLabel ?label }}
            }}
            GROUP BY ?value ?label
            ORDER BY DESC(?count)
        """)
        return [
            {"value": r.get("label") or r.get("value", ""), "count": r["count"]}
            for r in rows
        ]

    def get_type_stats(self, collection: str) -> Dict[str, Any]:
        """Total count for a class, plus value breakdowns for its taxonomy properties."""
        class_uri = self.collection_to_class_uri(collection)
        if not class_uri:
            raise ValueError(f"Unknown artifact type: {collection!r}")

        total_rows = self.sparql_query(f"""
            SELECT (COUNT(DISTINCT ?e) AS ?total) WHERE {{ ?e a <{class_uri}> }}
        """)
        stats: Dict[str, Any] = {
            "collection": collection,
            "total": total_rows[0]["total"] if total_rows else 0,
        }

        # Break down by whichever properties the ontology marks taxonomy-valued.
        for prop_name in self.taxonomy_properties():
            counts = self.get_property_value_counts(collection, prop_name)
            if counts:
                stats[f"by{prop_name[0].upper()}{prop_name[1:]}"] = counts
        return stats

    # ------------------------------------------------------------
    # Field name <-> predicate URI
    # ------------------------------------------------------------
    # Both directions used to consult an alias table of eight atlas property
    # names (mitreId->mitre_id, storyPoints->story_points, payloadUrl->
    # payload_url, ...). Any property outside that list passed through
    # unchanged, so the snake_case convention was applied only to atlas fields
    # and inconsistently everywhere else. The field name is now simply the
    # ontology property's local name, in both directions.

    def _pred_to_field(self, pred_uri: str) -> Optional[str]:
        """Convert a predicate URI to a document field name."""
        if pred_uri.startswith(ONTOLOGY_NS):
            return pred_uri[len(ONTOLOGY_NS):]

        # Skip RDF/OWL/RDFS predicates
        if any(pred_uri.startswith(ns) for ns in [
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "http://www.w3.org/2000/01/rdf-schema#",
            "http://www.w3.org/2002/07/owl#",
        ]):
            return None

        return None

    def _field_to_pred_uri(self, field: str) -> Optional[str]:
        """Convert a field name to a predicate URI."""
        # Skip internal fields
        if field.startswith("_"):
            return None
        return f"{ONTOLOGY_NS}{field}"

    def _field_to_triple(self, uri: str, field: str, value: Any) -> Optional[str]:
        """Convert a field/value pair to a SPARQL triple string."""
        pred_uri = self._field_to_pred_uri(field)
        if not pred_uri:
            return None

        # Handle taxonomy references.
        #
        # Which fields are taxonomy-valued used to be a fixed list of four atlas
        # property names. It now comes from the ontology: a property is
        # taxonomy-valued if it declares proto:taxonomy.
        if isinstance(value, str) and self._is_taxonomy_property(field):
            tax_uri = self._resolve_term_by_label(value)
            if tax_uri:
                return f"    <{uri}> <{pred_uri}> <{tax_uri}> ."

        # Handle different value types
        if isinstance(value, bool):
            return f'    <{uri}> <{pred_uri}> "{str(value).lower()}"^^xsd:boolean .'
        elif isinstance(value, int):
            return f'    <{uri}> <{pred_uri}> "{value}"^^xsd:integer .'
        elif isinstance(value, float):
            return f'    <{uri}> <{pred_uri}> "{value}"^^xsd:double .'
        elif isinstance(value, str):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            return f'    <{uri}> <{pred_uri}> "{escaped}" .'
        elif isinstance(value, list):
            # Multi-value: create multiple triples
            triples = []
            for v in value:
                t = self._field_to_triple(uri, field, v)
                if t:
                    triples.append(t)
            return "\n".join(triples) if triples else None

        return None

    def _resolve_term_by_label(self, label: str) -> Optional[str]:
        """Find a taxonomy term URI by its label or alias."""
        rows = self.sparql_query(f"""
            SELECT ?term WHERE {{
                {{ ?term skos:prefLabel "{label}" }}
                UNION
                {{ ?term skos:altLabel "{label}" }}
            }}
            LIMIT 1
        """)
        return rows[0]["term"] if rows else None

    def _most_specific_type(self, type_uris: set) -> Optional[str]:
        """Given a set of class URIs, return the most specific (leaf) one."""
        # Filter to only our ontology types
        onto_types = {t for t in type_uris if t.startswith(ONTOLOGY_NS)}
        # Prefer concrete types over abstract
        abstract = {
            f"{ONTOLOGY_NS}Thing",
            f"{ONTOLOGY_NS}Artifact",
            f"{ONTOLOGY_NS}Agent",
            f"{ONTOLOGY_NS}WorkItem",
        }
        concrete = onto_types - abstract
        if concrete:
            return next(iter(concrete))
        return next(iter(onto_types)) if onto_types else None

    # _infer_cluster() was removed.
    #
    # It bucketed artifacts into "Automation" / "Range" / "Content Development" /
    # "OPFOR" by substring-matching the owner or collection name \u2014 the 318th
    # RANS team structure hardcoded into the adapter. In any other repository
    # every node fell through to "Unassigned", and the value was invented by
    # string matching rather than read from the graph either way.
    #
    # If clustering is wanted, derive it from a property the ontology declares.

    def _find_node_id(self, key: str, node_ids: set) -> Optional[str]:
        """Find the full ID for a key from the node set."""
        for nid in node_ids:
            if nid.endswith(f"/{key}"):
                return nid
        return None

    def _expand_depth(
        self, center_uri: str, center_id: str,
        nodes: List, edges: List, seen: set, depth: int,
    ) -> Tuple[List, List]:
        """
        Expand neighbors beyond depth 1 using property paths.

        The alternation is built from the ontology's declared relationship types.
        It used to be a fixed list of nine predicates, which meant any type added
        through the ontology manager was silently not traversed \u2014 producing an
        empty result indistinguishable from a genuine absence of neighbours.

        SPARQL property paths cannot take a variable predicate, so an explicit
        alternation is unavoidable here; the fix is to generate it rather than
        freeze it.
        """
        rel_uris = self.live_relationship_uris()
        if not rel_uris:
            # No declared relationship types: there is nothing to traverse and an
            # empty alternation is a syntax error. Return what depth 1 found.
            print("\u26a0\ufe0f  _expand_depth: no relationship types declared; skipping expansion")
            return nodes, edges

        # Forward and inverse for each declared type.
        alternation = "|".join(
            [f"<{u}>" for u in rel_uris] + [f"^<{u}>" for u in rel_uris]
        )

        rows = self.sparql_query(f"""
            SELECT DISTINCT ?from ?rel ?to ?toType ?toName WHERE {{
                <{center_uri}> ({alternation}){{1,{depth}}} ?to .

                ?to a ?toType .
                FILTER(STRSTARTS(STR(?toType), "{ONTOLOGY_NS}"))
                FILTER(?toType NOT IN (proto:Thing, proto:Artifact, proto:Agent, proto:WorkItem))
                OPTIONAL {{ ?to proto:name ?toName }}
            }}
        """)

        for row in rows:
            n_uri = row["to"]
            if n_uri in seen:
                continue
            seen.add(n_uri)

            n_key = self.uri_to_key(n_uri)
            n_collection = self.uri_to_collection(row["toType"])
            neighbor_doc = self.get_artifact(n_collection, n_key)
            if neighbor_doc:
                nodes.append(neighbor_doc)

        return nodes, edges

    # ============================================================
    # HEALTH CHECK
    # ============================================================

    def health(self) -> Dict[str, Any]:
        """Check GraphDB connection and return stats."""
        try:
            rows = self.sparql_query("""
                SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }
            """)
            triple_count = rows[0]["triples"] if rows else 0

            type_rows = self.sparql_query(f"""
                SELECT ?type (COUNT(?entity) AS ?count) WHERE {{
                    ?entity a ?type .
                    FILTER(STRSTARTS(STR(?entity), "{DATA_NS}"))
                    FILTER(STRSTARTS(STR(?type), "{ONTOLOGY_NS}"))
                    FILTER(?type NOT IN (proto:Thing, proto:Artifact, proto:Agent, proto:WorkItem))
                }}
                GROUP BY ?type
                ORDER BY DESC(?count)
            """)

            return {
                "status": "connected",
                "endpoint": self.query_url,
                "total_triples": triple_count,
                "artifact_counts": {
                    self.uri_to_collection(r["type"]): r["count"]
                    for r in type_rows
                },
            }
        except Exception as e:
            return {
                "status": "error",
                "endpoint": self.query_url,
                "error": str(e),
            }
