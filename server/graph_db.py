"""
GraphDB Adapter for ProtoGraph ATLAS
=====================================
Provides the same data shapes as the ArangoDB queries in main.py,
but sources data from GraphDB via SPARQL.

Usage:
    from graph_db import GraphDBAdapter
    
    gdb = GraphDBAdapter("http://localhost:7200", "atlas")
    
    # Same shape as: db.collection("LibraryModule").get("cs-start-c2")
    doc = gdb.get_artifact("LibraryModule", "cs-start-c2")
    
    # Same shape as: /graph endpoint returns
    graph = gdb.get_full_graph()
    
    # Same shape as: /neighbors endpoint returns
    neighbors = gdb.get_neighbors("LibraryModule/cs-start-c2", depth=2)

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

# Map RDF class URIs to ArangoDB-style collection names (for frontend compat)
CLASS_TO_COLLECTION = {
    "https://proto.atlas/ontology/LibraryModule": "LibraryModule",
    "https://proto.atlas/ontology/ExecutionPlan": "ExecutionPlan",
    "https://proto.atlas/ontology/Scenario": "Scenario",
    "https://proto.atlas/ontology/RangeEnvironment": "RangeEnvironment",
    "https://proto.atlas/ontology/RobotLog": "RobotLog",
    "https://proto.atlas/ontology/Person": "Person",
    "https://proto.atlas/ontology/Team": "Team",
    "https://proto.atlas/ontology/DevelopmentStory": "DevelopmentStory",
    "https://proto.atlas/ontology/TTP": "TTP",
}

COLLECTION_TO_CLASS = {v: k for k, v in CLASS_TO_COLLECTION.items()}

# Map relationship URIs to edge labels
REL_URI_TO_LABEL = {
    "https://proto.atlas/relationship/CONTAINS": "CONTAINS",
    "https://proto.atlas/relationship/PRODUCES": "PRODUCES",
    "https://proto.atlas/relationship/REFERENCES": "REFERENCES",
    "https://proto.atlas/relationship/LEADS_TO": "LEADS_TO",
    "https://proto.atlas/relationship/ASSIGNED_TO": "ASSIGNED_TO",
    "https://proto.atlas/relationship/BELONGS_TO": "BELONGS_TO",
    "https://proto.atlas/relationship/DEPENDS_ON": "DEPENDS_ON",
    "https://proto.atlas/relationship/TESTS": "TESTS",
    "https://proto.atlas/relationship/RELATED_TO": "RELATED_TO",
}

DATA_NS = "https://proto.atlas/data/"
ONTOLOGY_NS = "https://proto.atlas/ontology/"
REL_NS = "https://proto.atlas/relationship/"
TAX_NS = "https://proto.atlas/taxonomy/"


class GraphDBAdapter:
    """
    Drop-in adapter that translates ArangoDB-style calls to SPARQL queries.
    Returns JSON shapes identical to what main.py currently returns.
    """

    def __init__(self, endpoint: str = "http://localhost:7200", repo: str = "atlas"):
        self.endpoint = endpoint.rstrip("/")
        self.repo = repo
        self.query_url = f"{self.endpoint}/repositories/{self.repo}"
        self.update_url = f"{self.endpoint}/repositories/{self.repo}/statements"
        self.client = httpx.Client(timeout=30.0)
        print(f"✓ GraphDB adapter initialized: {self.query_url}")

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
        """Convert a class URI to an ArangoDB-style collection name."""
        return CLASS_TO_COLLECTION.get(class_uri, class_uri.rsplit("/", 1)[-1])

    def arango_id(self, class_uri: str, entity_uri: str) -> str:
        """Build an ArangoDB-style _id like 'LibraryModule/cs-start-c2'."""
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
        # Fetch all artifact instances with their key properties
        node_rows = self.sparql_query("""
            SELECT ?entity ?type ?name ?description ?owner ?status ?icon
                   ?riskLevel ?category ?tactic ?subcategory ?estimatedDuration
                   ?color ?mitreId
            WHERE {
                ?entity a ?type .
                FILTER(STRSTARTS(STR(?entity), "https://proto.atlas/data/"))
                FILTER(STRSTARTS(STR(?type), "https://proto.atlas/ontology/"))

                # Skip abstract parent types (we want the most specific)
                FILTER(?type NOT IN (proto:Thing, proto:Artifact, proto:Agent, proto:WorkItem))

                OPTIONAL { ?entity proto:name ?name }
                OPTIONAL { ?entity proto:description ?description }
                OPTIONAL { 
                    ?entity proto:owner ?ownerConcept .
                    ?ownerConcept skos:prefLabel ?owner .
                }
                OPTIONAL { ?entity proto:status ?status }
                OPTIONAL { ?entity proto:icon ?icon }
                OPTIONAL {
                    ?entity proto:riskLevel ?riskConcept .
                    ?riskConcept skos:prefLabel ?riskLevel .
                }
                OPTIONAL {
                    ?entity proto:category ?catConcept .
                    ?catConcept skos:prefLabel ?category .
                }
                OPTIONAL { ?entity proto:tactic ?tactic }
                OPTIONAL { ?entity proto:subcategory ?subcategory }
                OPTIONAL { ?entity proto:estimatedDuration ?estimatedDuration }
                OPTIONAL { ?entity proto:color ?color }
                OPTIONAL { ?entity proto:mitreId ?mitreId }
            }
        """)

        nodes = []
        seen_entities = set()
        for row in node_rows:
            entity_uri = row["entity"]
            if entity_uri in seen_entities:
                continue
            seen_entities.add(entity_uri)

            type_uri = row["type"]
            key = self.uri_to_key(entity_uri)
            collection = self.uri_to_collection(type_uri)
            artifact_type = collection.replace("_", " ")

            # Cluster inference from owner
            owner = row.get("owner", "")
            cluster = self._infer_cluster(owner, collection)

            name = row.get("name", key)
            desc = row.get("description", "")
            if desc and len(desc) > 200:
                desc = desc[:200]

            nodes.append({
                "id": f"{collection}/{key}",
                "label": name,
                "cluster": cluster,
                "type": artifact_type,
                "_artifact_type": artifact_type,
                "owner": owner,
                "scenario_id": "unknown",
                "status": row.get("status", ""),
                "importance": 0.5,
                "description": desc,
                # Operator-critical fields
                "icon": row.get("icon", ""),
                "tactic": row.get("tactic", ""),
                "category": row.get("category", ""),
                "subcategory": row.get("subcategory", ""),
                "riskLevel": row.get("riskLevel", ""),
                "estimatedDuration": row.get("estimatedDuration", ""),
                "color": row.get("color", ""),
                "mitre_id": row.get("mitreId", ""),
            })

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
            rel_label = REL_URI_TO_LABEL.get(row["rel"], row["rel"].rsplit("/", 1)[-1])

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

        print(f"✅ GraphDB: Returning {len(nodes)} nodes and {len(edges)} edges")
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
            rel_label = REL_URI_TO_LABEL.get(row["rel"], row["rel"].rsplit("/", 1)[-1])

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
        Insert a new artifact. Returns ArangoDB-style response.
        
        artifact_type: "LibraryModule", "TTP", etc.
        """
        uri = self.key_to_uri(key)
        class_uri = COLLECTION_TO_CLASS.get(artifact_type)
        if not class_uri:
            raise ValueError(f"Unknown artifact type: {artifact_type}")

        # Build INSERT DATA triples
        triples = [f"    <{uri}> a <{class_uri}> ."]

        for field, value in properties.items():
            triple = self._field_to_triple(uri, field, value)
            if triple:
                triples.append(triple)

        insert_query = "INSERT DATA {\n" + "\n".join(triples) + "\n}"
        self.sparql_update(insert_query)

        print(f"✓ GraphDB: Created {artifact_type}/{key}")
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

        source: provenance tag — "ontology_rule", "operator_authored",
                "manual", "execution_log", "llm_suggested"
        confidence: 0.0–1.0 (1.0 for deterministic rules)
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
        print(f"✓ GraphDB: Edge {from_id} --{relationship_type}--> {to_id} [source={source}]")

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

        print(f"✓ GraphDB: Deleted {collection}/{key}")
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

        print(f"✓ GraphDB: Deleted edge {from_key} --{relationship_type}--> {to_key}")
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
        """Return list of artifact type names that have instances (like ArangoDB collection list)."""
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
    # UTILITY: Get taxonomy terms
    # ============================================================

    def get_taxonomy_terms(self, scheme_id: str) -> List[Dict[str, str]]:
        """Get all terms in a taxonomy scheme."""
        scheme_uri = f"{TAX_NS}{scheme_id}"
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
        scheme_uri = f"{TAX_NS}{scheme_id}"
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
                FILTER(STRSTARTS(STR(?prop), "https://proto.atlas/ontology/"))
            }}
            ORDER BY ?propLabel
        """)

        # Known required fields per class (matches SHACL shapes)
        REQUIRED_BY_CLASS = {
            f"{ONTOLOGY_NS}LibraryModule": {"name", "category", "tactic"},
            f"{ONTOLOGY_NS}TTP": {"name", "mitreId"},
            f"{ONTOLOGY_NS}ExecutionPlan": {"name"},
            f"{ONTOLOGY_NS}DevelopmentStory": {"name"},
            f"{ONTOLOGY_NS}Person": {"name"},
            f"{ONTOLOGY_NS}Team": {"name"},
        }
        required_for_this_class = REQUIRED_BY_CLASS.get(class_uri, {"name"})

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

            # Use taxonomy from graph triple if available, fall back to detection
            if taxonomy_value:
                prop_entry["taxonomy"] = taxonomy_value
            elif prop_type != "reference":
                scheme = self._detect_taxonomy_scheme(name)
                if scheme:
                    prop_entry["taxonomy"] = scheme

            if desc:
                prop_entry["description"] = desc

            props.append(prop_entry)

        return props

    def _detect_taxonomy_scheme(self, property_name: str) -> Optional[str]:
        """Map a property name to its taxonomy scheme ID."""
        mapping = {
            "category": "c2-frameworks",
            "riskLevel": "risk-levels",
            "team": "teams",
            "tactic": "mitre-tactics",
        }
        return mapping.get(property_name)

    # ============================================================
    # OPERATOR: Library Module Queries
    # ============================================================

    def get_library_modules(
        self,
        category: Optional[str] = None,
        tactic: Optional[str] = None,
        search: Optional[str] = None,
        risk_level: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Query LibraryModules with optional filters.
        Returns same shape as plugin_router's /operator/modules.
        """
        # Build FILTER clauses
        filters = []
        if category:
            # Category is a SKOS concept — match by prefLabel
            filters.append(f'?catLabel = "{category}"')
        if tactic:
            filters.append(f'?tactic = "{tactic}"')
        if risk_level:
            filters.append(f'?riskLabel = "{risk_level}"')
        if search:
            safe = search.replace("\\", "\\\\").replace('"', '\\"')
            filters.append(
                f'(REGEX(?name, "{safe}", "i") || REGEX(COALESCE(?description, ""), "{safe}", "i"))'
            )

        filter_clause = "\n                ".join(f"FILTER({f})" for f in filters)

        query = f"""
            SELECT ?entity ?name ?description ?icon ?tactic ?subcategory
                   ?estimatedDuration ?catLabel ?riskLabel ?ownerLabel
            WHERE {{
                ?entity a proto:LibraryModule .
                OPTIONAL {{ ?entity proto:name ?name }}
                OPTIONAL {{ ?entity proto:description ?description }}
                OPTIONAL {{ ?entity proto:icon ?icon }}
                OPTIONAL {{ ?entity proto:tactic ?tactic }}
                OPTIONAL {{ ?entity proto:subcategory ?subcategory }}
                OPTIONAL {{ ?entity proto:estimatedDuration ?estimatedDuration }}
                OPTIONAL {{ ?entity proto:category ?catLabel . }}
                OPTIONAL {{ ?entity proto:riskLevel ?riskLabel . }}
                OPTIONAL {{ ?entity proto:owner ?ownerLabel . }}
                {filter_clause}
            }}
            ORDER BY ?name
            LIMIT {limit}
            OFFSET {offset}
        """

        rows = self.sparql_query(query)

        modules = []
        seen = set()
        for row in rows:
            uri = row["entity"]
            if uri in seen:
                continue
            seen.add(uri)

            key = self.uri_to_key(uri)

            def strip_uri(val):
                """Extract plain value from taxonomy URI or return as-is."""
                if not val:
                    return ""
                if val.startswith("https://proto.atlas/taxonomy/"):
                    slug = val.split("/")[-1]
                    # mitre-TA0005 -> TA0005
                    if slug.startswith("mitre-"):
                        return slug[6:]
                    # risk-medium -> Medium
                    if slug.startswith("risk-"):
                        return slug[5:].capitalize()
                    # c2-cobalt-strike -> Cobalt Strike
                    if slug.startswith("c2-"):
                        return slug[3:].replace("-", " ").title()
                    # status-active -> active
                    if slug.startswith("status-"):
                        return slug[7:]
                    # team-automation -> Automation
                    if slug.startswith("team-"):
                        return slug[5:].title()
                    return slug
                return val

            modules.append({
                "_id": f"LibraryModule/{key}",
                "_key": key,
                "_artifact_type": "Library Module",
                "name": row.get("name", key),
                "description": row.get("description", ""),
                "icon": row.get("icon", "⚡"),
                "tactic": strip_uri(row.get("tactic", "")),
                "category": strip_uri(row.get("catLabel", "")),
                "subcategory": row.get("subcategory", ""),
                "riskLevel": strip_uri(row.get("riskLabel", "")),
                "estimatedDuration": row.get("estimatedDuration", ""),
                "owner": strip_uri(row.get("ownerLabel", "")),
            })

        # Total count (separate query for pagination)
        count_rows = self.sparql_query("""
            SELECT (COUNT(DISTINCT ?entity) AS ?total) WHERE {
                ?entity a proto:LibraryModule .
            }
        """)
        total = count_rows[0]["total"] if count_rows else len(modules)

        return {
            "modules": modules,
            "count": len(modules),
            "total": total,
        }

    def get_library_module(self, key: str) -> Optional[Dict[str, Any]]:
        """Get a single LibraryModule by key. Returns full doc or None."""
        return self.get_artifact("LibraryModule", key)

    def get_library_module_categories(self) -> List[Dict[str, Any]]:
        """Get distinct categories with counts."""
        rows = self.sparql_query("""
            SELECT ?catLabel (COUNT(DISTINCT ?entity) AS ?count) WHERE {
                ?entity a proto:LibraryModule ;
                        proto:category ?cat .
                ?cat skos:prefLabel ?catLabel .
            }
            GROUP BY ?catLabel
            ORDER BY ?catLabel
        """)
        return [{"value": r["catLabel"], "count": r["count"]} for r in rows]

    def get_library_module_tactics(self) -> List[Dict[str, Any]]:
        """Get distinct tactics with counts."""
        rows = self.sparql_query("""
            SELECT ?tactic (COUNT(DISTINCT ?entity) AS ?count) WHERE {
                ?entity a proto:LibraryModule ;
                        proto:tactic ?tactic .
                FILTER(?tactic != "")
            }
            GROUP BY ?tactic
            ORDER BY ?tactic
        """)
        return [{"value": r["tactic"], "count": r["count"]} for r in rows]

    def get_library_module_stats(self) -> Dict[str, Any]:
        """Get module statistics — total, by category, by tactic, by risk level."""
        total_rows = self.sparql_query("""
            SELECT (COUNT(DISTINCT ?e) AS ?total) WHERE { ?e a proto:LibraryModule }
        """)
        total = total_rows[0]["total"] if total_rows else 0

        by_category = self.get_library_module_categories()

        by_tactic = self.get_library_module_tactics()

        risk_rows = self.sparql_query("""
            SELECT ?riskLabel (COUNT(DISTINCT ?entity) AS ?count) WHERE {
                ?entity a proto:LibraryModule ;
                        proto:riskLevel ?risk .
                ?risk skos:prefLabel ?riskLabel .
            }
            GROUP BY ?riskLabel
            ORDER BY ?riskLabel
        """)
        by_risk = [{"riskLevel": r["riskLabel"], "count": r["count"]} for r in risk_rows]

        return {
            "total": total,
            "byCategory": [{"category": c["value"], "count": c["count"]} for c in by_category],
            "byTactic": [{"tactic": t["value"], "count": t["count"]} for t in by_tactic],
            "byRiskLevel": by_risk,
        }

    # ============================================================
    # PRIVATE HELPERS
    # ============================================================

    def _pred_to_field(self, pred_uri: str) -> Optional[str]:
        """Convert a predicate URI to a document field name."""
        if pred_uri.startswith(ONTOLOGY_NS):
            field = pred_uri[len(ONTOLOGY_NS):]
            # Convert camelCase ontology names to snake_case where needed
            field_map = {
                "payloadUrl": "payload_url",
                "estimatedDuration": "estimatedDuration",
                "targetNetwork": "target_network",
                "exerciseType": "exercise_type",
                "networkTopology": "network_topology",
                "executionTime": "execution_time",
                "storyPoints": "story_points",
                "mitreId": "mitre_id",
            }
            return field_map.get(field, field)

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
        # Reverse map
        reverse_map = {
            "payload_url": "payloadUrl",
            "target_network": "targetNetwork",
            "exercise_type": "exerciseType",
            "network_topology": "networkTopology",
            "execution_time": "executionTime",
            "story_points": "storyPoints",
            "mitre_id": "mitreId",
        }
        onto_field = reverse_map.get(field, field)

        # Skip internal ArangoDB fields
        if field.startswith("_"):
            return None

        return f"{ONTOLOGY_NS}{onto_field}"

    def _field_to_triple(self, uri: str, field: str, value: Any) -> Optional[str]:
        """Convert a field/value pair to a SPARQL triple string."""
        pred_uri = self._field_to_pred_uri(field)
        if not pred_uri:
            return None

        # Handle taxonomy references
        if field in ("category", "riskLevel", "owner", "team") and isinstance(value, str):
            # Try to resolve as taxonomy term
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

    def _infer_cluster(self, owner: str, collection: str) -> str:
        """Infer cluster/team from owner or collection name (matches main.py logic)."""
        if owner:
            ol = owner.lower()
            if "automation" in ol:
                return "Automation"
            elif "range" in ol:
                return "Range"
            elif "content" in ol:
                return "Content Development"
            elif "opfor" in ol:
                return "OPFOR"
            return owner

        if "Execution" in collection or "Orchestration" in collection:
            return "Automation"
        elif "Range" in collection or "Network" in collection:
            return "Range"
        elif "Content" in collection or "Intel" in collection:
            return "Content Development"
        elif "OPFOR" in collection or "Red" in collection:
            return "OPFOR"

        return "Unassigned"

    def _find_node_id(self, key: str, node_ids: set) -> Optional[str]:
        """Find the full ArangoDB-style ID for a key from the node set."""
        for nid in node_ids:
            if nid.endswith(f"/{key}"):
                return nid
        return None

    def _expand_depth(
        self, center_uri: str, center_id: str,
        nodes: List, edges: List, seen: set, depth: int,
    ) -> Tuple[List, List]:
        """Expand neighbors beyond depth 1 using property paths."""
        # For depth > 1, use transitive property paths
        rows = self.sparql_query(f"""
            SELECT DISTINCT ?from ?rel ?to ?toType ?toName WHERE {{
                <{center_uri}> (rel:LEADS_TO|rel:CONTAINS|rel:PRODUCES|rel:REFERENCES|
                                rel:DEPENDS_ON|rel:TESTS|rel:ASSIGNED_TO|rel:BELONGS_TO|
                                rel:RELATED_TO|
                                ^rel:LEADS_TO|^rel:CONTAINS|^rel:PRODUCES|^rel:REFERENCES|
                                ^rel:DEPENDS_ON|^rel:TESTS|^rel:ASSIGNED_TO|^rel:BELONGS_TO|
                                ^rel:RELATED_TO){{1,{depth}}} ?to .

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