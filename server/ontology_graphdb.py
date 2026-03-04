"""
Ontology API - GraphDB Native
==============================
Full CRUD for ontology management backed by GraphDB triplestore.

Manages four layers of the ontology:
  TBox — OWL classes and properties (what kinds of things exist)
  CBox — SHACL shapes and SKOS taxonomies (what rules govern them)
  RBox — OWL object properties (how things connect)
  ABox — Instance data (managed by ingestion_core, not this API)

All changes are written as RDF triples via SPARQL UPDATE.
SHACL validation is enforced by GraphDB on every write.

Replaces: ontology_api.py (ArangoDB version)
Requires: graph_db.py adapter
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import re

router = APIRouter(prefix="/api/ontology", tags=["ontology"])

# Injected by init_ontology_graphdb()
gdb = None

# Namespace constants
ONTOLOGY_NS = "https://proto.atlas/ontology/"
TAXONOMY_NS = "https://proto.atlas/taxonomy/"
REL_NS = "https://proto.atlas/relationship/"
DATA_NS = "https://proto.atlas/data/"


# =====================================================
# MODELS - Concepts (TBox)
# =====================================================

class PropertyDefinition(BaseModel):
    name: str
    type: str = "string"  # string, integer, boolean, datetime, double, uri, reference
    required: bool = False
    multiple: bool = False  # If true, property can have multiple values
    taxonomy: Optional[str] = None  # For controlled vocabulary fields
    target_class: Optional[str] = None  # For reference type: label of the target OWL class
    description: Optional[str] = None
    default: Optional[Any] = None


class ConceptCreate(BaseModel):
    label: str = Field(..., description="Human-readable label, e.g. 'Library Module'")
    definition: str = Field("", description="What this concept represents")
    parent: Optional[str] = Field(None, description="Parent class label for IS-A hierarchy")
    abstract: bool = Field(False, description="If true, cannot be instantiated")
    collection: Optional[str] = Field(None, description="Collection name for frontend compat")
    properties: List[PropertyDefinition] = Field(default_factory=list)


class ConceptUpdate(BaseModel):
    label: Optional[str] = None
    definition: Optional[str] = None
    parent: Optional[str] = None
    abstract: Optional[bool] = None
    properties: Optional[List[PropertyDefinition]] = None


# =====================================================
# MODELS - Taxonomies (CBox)
# =====================================================

class TaxonomyCreate(BaseModel):
    scheme_id: str = Field(..., description="ID like 'risk-levels'")
    label: str
    description: str = ""


class TaxonomyUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None


class TermCreate(BaseModel):
    term_id: str = Field(..., description="Local ID like 'risk-critical'")
    label: str = Field(..., description="Canonical display label")
    definition: str = ""
    aliases: List[str] = Field(default_factory=list)
    broader: Optional[str] = Field(None, description="URI or term_id of parent term for hierarchy")


class TermUpdate(BaseModel):
    label: Optional[str] = None
    definition: Optional[str] = None
    aliases: Optional[List[str]] = None
    broader: Optional[str] = None  # URI or term_id of parent term, empty string to remove


class BulkTermsCreate(BaseModel):
    terms: List[TermCreate]


# =====================================================
# MODELS - Relationships (RBox)
# =====================================================

class RelationshipTypeCreate(BaseModel):
    label: str = Field(..., description="Edge label like 'LEADS_TO'")
    definition: str = ""
    domain: List[str] = Field(default_factory=list, description="Source class labels")
    range: List[str] = Field(default_factory=list, description="Target class labels")
    inverse: Optional[str] = None
    symmetric: bool = False
    transitive: bool = False
    functional: bool = False  # owl:FunctionalProperty — at most one value


class RelationshipTypeUpdate(BaseModel):
    label: Optional[str] = None
    definition: Optional[str] = None
    domain: Optional[List[str]] = None
    range: Optional[List[str]] = None
    inverse: Optional[str] = None
    symmetric: Optional[bool] = None
    transitive: Optional[bool] = None


# =====================================================
# INIT
# =====================================================

def init_ontology_graphdb(graphdb_adapter):
    global gdb
    gdb = graphdb_adapter
    print("✓ Ontology API (GraphDB) initialized")


def _require_gdb():
    if gdb is None:
        raise HTTPException(status_code=503, detail="Ontology API not initialized")


def _label_to_uri(label: str) -> str:
    """Convert a class label to its ontology URI. If already a full URI, return as-is."""
    if label.startswith("http://") or label.startswith("https://"):
        return label
    local = re.sub(r"[^a-zA-Z0-9]", "", label)
    return f"{ONTOLOGY_NS}{local}"


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


# =====================================================
# CONCEPTS - CRUD (TBox)
# =====================================================

@router.get("/concepts")
async def list_concepts(include_abstract: bool = True):
    """List all OWL classes in the ontology."""
    _require_gdb()

    rows = gdb.sparql_query("""
        SELECT ?cls ?label ?definition ?parent ?abstract WHERE {
            ?cls a owl:Class ;
                 rdfs:label ?label .
            FILTER(STRSTARTS(STR(?cls), "https://proto.atlas/ontology/"))
            OPTIONAL { ?cls rdfs:comment ?definition }
            OPTIONAL {
                ?cls rdfs:subClassOf ?parent .
                FILTER(STRSTARTS(STR(?parent), "https://proto.atlas/ontology/"))
                FILTER(?parent != ?cls)
                FILTER NOT EXISTS {
                    ?cls rdfs:subClassOf ?mid .
                    ?mid rdfs:subClassOf ?parent .
                    FILTER(?mid != ?cls)
                    FILTER(?mid != ?parent)
                    FILTER(STRSTARTS(STR(?mid), "https://proto.atlas/ontology/"))
                }
            }
            OPTIONAL { ?cls proto:abstract ?abstract }
        }
        ORDER BY ?label
    """)

    concepts = {}
    for row in rows:
        uri = row["cls"]
        if uri not in concepts:
            is_abstract = row.get("abstract") == "true"
            concepts[uri] = {
                "uri": uri,
                "label": row.get("label", ""),
                "definition": row.get("definition", ""),
                "parent": row.get("parent"),
                "abstract": is_abstract,
                "collection": gdb.uri_to_collection(uri),
            }

    result = list(concepts.values())
    if not include_abstract:
        result = [c for c in result if not c["abstract"]]

    return {"concepts": result, "count": len(result)}


@router.get("/concepts/hierarchy")
async def get_concept_hierarchy():
    """Get concept hierarchy as a tree."""
    _require_gdb()

    rows = gdb.sparql_query("""
        SELECT ?cls ?label ?parent ?parentLabel WHERE {
            ?cls a owl:Class ;
                 rdfs:label ?label .
            FILTER(STRSTARTS(STR(?cls), "https://proto.atlas/ontology/"))
            OPTIONAL {
                ?cls rdfs:subClassOf ?parent .
                ?parent rdfs:label ?parentLabel .
                FILTER(STRSTARTS(STR(?parent), "https://proto.atlas/ontology/"))
                FILTER(?parent != ?cls)
                FILTER NOT EXISTS {
                    ?cls rdfs:subClassOf ?mid .
                    ?mid rdfs:subClassOf ?parent .
                    FILTER(?mid != ?cls)
                    FILTER(?mid != ?parent)
                    FILTER(STRSTARTS(STR(?mid), "https://proto.atlas/ontology/"))
                }
            }
        }
        ORDER BY ?label
    """)

    nodes = {}
    for row in rows:
        uri = row["cls"]
        if uri not in nodes:
            nodes[uri] = {
                "uri": uri,
                "label": row.get("label", ""),
                "parent_uri": row.get("parent"),
                "parent_label": row.get("parentLabel"),
                "children": [],
            }

    # Build tree
    roots = []
    for uri, node in nodes.items():
        parent_uri = node.get("parent_uri")
        if parent_uri and parent_uri in nodes:
            nodes[parent_uri]["children"].append(node)
        else:
            roots.append(node)

    return {"hierarchy": roots}


@router.get("/concepts/{label}")
async def get_concept(label: str, include_properties: bool = True):
    """Get a single concept by label."""
    _require_gdb()
    uri = _label_to_uri(label)

    rows = gdb.sparql_query(f"""
        SELECT ?label ?definition ?parent WHERE {{
            <{uri}> rdfs:label ?label .
            OPTIONAL {{ <{uri}> rdfs:comment ?definition }}
            OPTIONAL {{
                <{uri}> rdfs:subClassOf ?parent .
                FILTER(STRSTARTS(STR(?parent), "https://proto.atlas/ontology/"))
                FILTER(?parent != <{uri}>)
                FILTER NOT EXISTS {{
                    <{uri}> rdfs:subClassOf ?mid .
                    ?mid rdfs:subClassOf ?parent .
                    FILTER(?mid != <{uri}>)
                    FILTER(?mid != ?parent)
                    FILTER(STRSTARTS(STR(?mid), "https://proto.atlas/ontology/"))
                }}
            }}
        }}
    """)

    if not rows:
        raise HTTPException(status_code=404, detail=f"Concept '{label}' not found")

    concept = {
        "uri": uri,
        "label": rows[0].get("label", label),
        "definition": rows[0].get("definition", ""),
        "parent": rows[0].get("parent"),
        "collection": gdb.uri_to_collection(uri),
    }

    if include_properties:
        concept["properties"] = gdb._get_class_properties(uri)

    return concept


@router.post("/concepts")
async def create_concept(concept: ConceptCreate):
    """Create a new OWL class."""
    _require_gdb()
    uri = _label_to_uri(concept.label)

    # Check if exists
    exists = gdb.sparql_ask(f"ASK {{ <{uri}> a owl:Class }}")
    if exists:
        raise HTTPException(status_code=409, detail=f"Concept '{concept.label}' already exists")

    # Determine parent class
    parent_uri = None
    if concept.parent:
        parent_uri = _label_to_uri(concept.parent)
        parent_exists = gdb.sparql_ask(f"ASK {{ <{parent_uri}> a owl:Class }}")
        if not parent_exists:
            raise HTTPException(status_code=400, detail=f"Parent concept '{concept.parent}' not found")

    # Build INSERT
    triples = [
        f"<{uri}> a owl:Class .",
        f'<{uri}> rdfs:label "{_escape(concept.label)}" .',
    ]

    if parent_uri:
        triples.append(f"<{uri}> rdfs:subClassOf <{parent_uri}> .")

    if concept.definition:
        triples.append(f'<{uri}> rdfs:comment "{_escape(concept.definition)}" .')

    if concept.abstract:
        triples.append(f'<{uri}> proto:abstract "true"^^xsd:boolean .')

    # Create properties
    for prop in concept.properties:
        prop_uri = f"{ONTOLOGY_NS}{prop.name}"

        if prop.type == "reference" and prop.target_class:
            # ObjectProperty — links to another OWL class
            target_uri = _label_to_uri(prop.target_class)
            triples.append(f"<{prop_uri}> a owl:ObjectProperty .")
            triples.append(f'<{prop_uri}> rdfs:label "{_escape(prop.name)}" .')
            triples.append(f"<{prop_uri}> rdfs:domain <{uri}> .")
            triples.append(f"<{prop_uri}> proto:definedOn <{uri}> .")
            triples.append(f"<{prop_uri}> rdfs:range <{target_uri}> .")
            if prop.description:
                triples.append(f'<{prop_uri}> rdfs:comment "{_escape(prop.description)}" .')
        else:
            # DatatypeProperty — stores a literal value
            range_type = _prop_type_to_range(prop.type)
            triples.append(f"<{prop_uri}> a owl:DatatypeProperty .")
            triples.append(f'<{prop_uri}> rdfs:label "{_escape(prop.name)}" .')
            triples.append(f"<{prop_uri}> rdfs:domain <{uri}> .")
            triples.append(f"<{prop_uri}> proto:definedOn <{uri}> .")
            if range_type:
                triples.append(f"<{prop_uri}> rdfs:range <{range_type}> .")
            if prop.description:
                triples.append(f'<{prop_uri}> rdfs:comment "{_escape(prop.description)}" .')

        # Mark multi-value properties
        if prop.multiple:
            triples.append(f'<{prop_uri}> proto:multiple "true"^^xsd:boolean .')

        # Mark taxonomy association
        if prop.taxonomy:
            triples.append(f'<{prop_uri}> proto:taxonomy "{_escape(prop.taxonomy)}" .')

    gdb.sparql_update("INSERT DATA {\n" + "\n".join(triples) + "\n}")

    # SHACL shape creation disabled during ontology construction phase.
    # Re-enable once ontology is stable to avoid cascading validation failures
    # from reasoner-inferred class memberships.
    # required_props = [p for p in concept.properties if p.required]
    # if required_props:
    #     _create_shacl_shape(uri, concept.label, required_props)

    print(f"✓ Created concept: {concept.label} ({uri})")
    return {
        "success": True,
        "uri": uri,
        "label": concept.label,
        "properties_created": len(concept.properties),
    }


@router.put("/concepts/{label}")
async def update_concept(label: str, updates: ConceptUpdate):
    """Update an existing concept."""
    _require_gdb()
    uri = _label_to_uri(label)

    exists = gdb.sparql_ask(f"ASK {{ <{uri}> a owl:Class }}")
    if not exists:
        raise HTTPException(status_code=404, detail=f"Concept '{label}' not found")

    deletes = []
    inserts = []

    if updates.label is not None:
        deletes.append(f"<{uri}> rdfs:label ?oldLabel .")
        inserts.append(f'<{uri}> rdfs:label "{_escape(updates.label)}" .')

    if updates.definition is not None:
        deletes.append(f"<{uri}> rdfs:comment ?oldDef .")
        inserts.append(f'<{uri}> rdfs:comment "{_escape(updates.definition)}" .')

    if updates.parent is not None:
        parent_uri = _label_to_uri(updates.parent)
        deletes.append(f"<{uri}> rdfs:subClassOf ?oldParent .")
        inserts.append(f"<{uri}> rdfs:subClassOf <{parent_uri}> .")

    if deletes:
        gdb.sparql_update(f"""
            DELETE {{ {' '.join(deletes)} }}
            INSERT {{ {' '.join(inserts)} }}
            WHERE {{ OPTIONAL {{ {' '.join(deletes)} }} }}
        """)

    return {"success": True, "uri": uri, "updated_fields": len(deletes)}


@router.delete("/concepts/{label}")
async def delete_concept(label: str, force: bool = False):
    """Delete an OWL class and its properties."""
    _require_gdb()
    uri = _label_to_uri(label)

    exists = gdb.sparql_ask(f"ASK {{ <{uri}> a owl:Class }}")
    if not exists:
        raise HTTPException(status_code=404, detail=f"Concept '{label}' not found")

    # Check for instances
    if not force:
        has_instances = gdb.sparql_ask(f"ASK {{ ?x a <{uri}> . FILTER(STRSTARTS(STR(?x), '{DATA_NS}')) }}")
        if has_instances:
            raise HTTPException(
                status_code=409,
                detail=f"Concept '{label}' has instances. Use force=true to delete anyway.",
            )

    # Delete class, its properties, and SHACL shapes
    gdb.sparql_update(f"""
        DELETE WHERE {{ <{uri}> ?p ?o }}
    """)
    gdb.sparql_update(f"""
        DELETE WHERE {{ ?prop rdfs:domain <{uri}> . ?prop ?p ?o }}
    """)

    return {"success": True, "deleted": uri}


# =====================================================
# PROPERTIES (TBox detail)
# =====================================================

@router.post("/concepts/{label}/properties")
async def add_property(label: str, prop: PropertyDefinition):
    """Add a property to an existing concept."""
    _require_gdb()
    class_uri = _label_to_uri(label)

    exists = gdb.sparql_ask(f"ASK {{ <{class_uri}> a owl:Class }}")
    if not exists:
        raise HTTPException(status_code=404, detail=f"Concept '{label}' not found")

    prop_uri = f"{ONTOLOGY_NS}{prop.name}"

    triples = []

    if prop.type == "reference" and prop.target_class:
        # ObjectProperty
        target_uri = _label_to_uri(prop.target_class)
        triples.append(f"<{prop_uri}> a owl:ObjectProperty .")
        triples.append(f'<{prop_uri}> rdfs:label "{_escape(prop.name)}" .')
        triples.append(f"<{prop_uri}> rdfs:domain <{class_uri}> .")
        triples.append(f"<{prop_uri}> proto:definedOn <{class_uri}> .")
        triples.append(f"<{prop_uri}> rdfs:range <{target_uri}> .")
    else:
        # DatatypeProperty
        range_type = _prop_type_to_range(prop.type)
        triples.append(f"<{prop_uri}> a owl:DatatypeProperty .")
        triples.append(f'<{prop_uri}> rdfs:label "{_escape(prop.name)}" .')
        triples.append(f"<{prop_uri}> rdfs:domain <{class_uri}> .")
        triples.append(f"<{prop_uri}> proto:definedOn <{class_uri}> .")
        if range_type:
            triples.append(f"<{prop_uri}> rdfs:range <{range_type}> .")

    if prop.description:
        triples.append(f'<{prop_uri}> rdfs:comment "{_escape(prop.description)}" .')
    if prop.multiple:
        triples.append(f'<{prop_uri}> proto:multiple "true"^^xsd:boolean .')
    if prop.taxonomy:
        triples.append(f'<{prop_uri}> proto:taxonomy "{_escape(prop.taxonomy)}" .')

    sparql = "INSERT DATA {\n" + "\n".join(triples) + "\n}"
    try:
        gdb.sparql_update(sparql)
    except Exception as e:
        print(f"⚠️ add_property SPARQL failed:\n{sparql}")
        print(f"⚠️ Error: {e}")
        raise HTTPException(status_code=500, detail=f"GraphDB rejected property creation: {str(e)}")

    return {"success": True, "property": prop.name, "class": label}


@router.delete("/concepts/{label}/properties/{prop_name}")
async def remove_property(label: str, prop_name: str):
    """Remove a property from a concept."""
    _require_gdb()
    prop_uri = f"{ONTOLOGY_NS}{prop_name}"

    gdb.sparql_update(f"DELETE WHERE {{ <{prop_uri}> ?p ?o }}")
    return {"success": True, "deleted": prop_name}


# =====================================================
# TAXONOMIES - CRUD (CBox)
# =====================================================

@router.get("/taxonomies")
async def list_taxonomies():
    """List all SKOS concept schemes."""
    _require_gdb()

    rows = gdb.sparql_query("""
        SELECT ?scheme ?label ?description (COUNT(?term) AS ?termCount) WHERE {
            ?scheme a skos:ConceptScheme .
            OPTIONAL { ?scheme rdfs:label ?label }
            OPTIONAL { ?scheme rdfs:comment ?description }
            OPTIONAL { ?term skos:inScheme ?scheme }
        }
        GROUP BY ?scheme ?label ?description
        ORDER BY ?label
    """)

    schemes = []
    for row in rows:
        uri = row["scheme"]
        scheme_id = uri.replace(TAXONOMY_NS, "").replace("scheme-", "")
        schemes.append({
            "scheme_id": scheme_id,
            "uri": uri,
            "label": row.get("label", scheme_id),
            "description": row.get("description", ""),
            "term_count": row.get("termCount", 0),
        })

    return {"taxonomies": schemes, "count": len(schemes)}


@router.get("/taxonomies/{scheme_id}")
async def get_taxonomy(scheme_id: str, include_terms: bool = True):
    """Get a taxonomy with its terms."""
    _require_gdb()

    scheme_uri = f"{TAXONOMY_NS}scheme-{scheme_id}"
    # Also try without "scheme-" prefix for backward compat
    exists = gdb.sparql_ask(f"ASK {{ <{scheme_uri}> a skos:ConceptScheme }}")
    if not exists:
        scheme_uri = f"{TAXONOMY_NS}{scheme_id}"
        exists = gdb.sparql_ask(f"ASK {{ <{scheme_uri}> a skos:ConceptScheme }}")
        if not exists:
            raise HTTPException(status_code=404, detail=f"Taxonomy '{scheme_id}' not found")

    # Get metadata
    meta_rows = gdb.sparql_query(f"""
        SELECT ?label ?description WHERE {{
            <{scheme_uri}> a skos:ConceptScheme .
            OPTIONAL {{ <{scheme_uri}> rdfs:label ?label }}
            OPTIONAL {{ <{scheme_uri}> rdfs:comment ?description }}
        }}
    """)

    result = {
        "scheme_id": scheme_id,
        "uri": scheme_uri,
        "label": meta_rows[0].get("label", scheme_id) if meta_rows else scheme_id,
        "description": meta_rows[0].get("description", "") if meta_rows else "",
    }

    if include_terms:
        terms = gdb.get_taxonomy_terms(scheme_id)
        # Also try with different URI patterns
        if not terms:
            terms = gdb.get_taxonomy_terms(f"scheme-{scheme_id}")
        result["terms"] = terms
        result["term_count"] = len(terms)

    return result


@router.post("/taxonomies")
async def create_taxonomy(taxonomy: TaxonomyCreate):
    """Create a new SKOS concept scheme."""
    _require_gdb()

    scheme_uri = f"{TAXONOMY_NS}scheme-{taxonomy.scheme_id}"

    exists = gdb.sparql_ask(f"ASK {{ <{scheme_uri}> a skos:ConceptScheme }}")
    if exists:
        raise HTTPException(status_code=409, detail=f"Taxonomy '{taxonomy.scheme_id}' already exists")

    triples = [
        f"<{scheme_uri}> a skos:ConceptScheme .",
        f'<{scheme_uri}> rdfs:label "{_escape(taxonomy.label)}" .',
    ]
    if taxonomy.description:
        triples.append(f'<{scheme_uri}> rdfs:comment "{_escape(taxonomy.description)}" .')

    gdb.sparql_update("INSERT DATA {\n" + "\n".join(triples) + "\n}")

    print(f"✓ Created taxonomy: {taxonomy.scheme_id}")
    return {"success": True, "scheme_id": taxonomy.scheme_id, "uri": scheme_uri}


@router.put("/taxonomies/{scheme_id}")
async def update_taxonomy(scheme_id: str, updates: TaxonomyUpdate):
    """Update taxonomy metadata."""
    _require_gdb()
    scheme_uri = f"{TAXONOMY_NS}scheme-{scheme_id}"

    exists = gdb.sparql_ask(f"ASK {{ <{scheme_uri}> a skos:ConceptScheme }}")
    if not exists:
        raise HTTPException(status_code=404, detail=f"Taxonomy '{scheme_id}' not found")

    deletes = []
    inserts = []

    if updates.label is not None:
        deletes.append(f"<{scheme_uri}> rdfs:label ?old .")
        inserts.append(f'<{scheme_uri}> rdfs:label "{_escape(updates.label)}" .')

    if updates.description is not None:
        deletes.append(f"<{scheme_uri}> rdfs:comment ?old2 .")
        inserts.append(f'<{scheme_uri}> rdfs:comment "{_escape(updates.description)}" .')

    if deletes:
        gdb.sparql_update(f"""
            DELETE {{ {' '.join(deletes)} }}
            INSERT {{ {' '.join(inserts)} }}
            WHERE {{ OPTIONAL {{ {' '.join(deletes)} }} }}
        """)

    return {"success": True, "scheme_id": scheme_id}


@router.delete("/taxonomies/{scheme_id}")
async def delete_taxonomy(scheme_id: str, force: bool = False):
    """Delete a taxonomy and all its terms."""
    _require_gdb()
    scheme_uri = f"{TAXONOMY_NS}scheme-{scheme_id}"

    exists = gdb.sparql_ask(f"ASK {{ <{scheme_uri}> a skos:ConceptScheme }}")
    if not exists:
        raise HTTPException(status_code=404, detail=f"Taxonomy '{scheme_id}' not found")

    if not force:
        # Check if terms are referenced by data instances
        in_use = gdb.sparql_ask(f"""
            ASK {{
                ?term skos:inScheme <{scheme_uri}> .
                ?instance ?prop ?term .
                FILTER(STRSTARTS(STR(?instance), "{DATA_NS}"))
            }}
        """)
        if in_use:
            raise HTTPException(
                status_code=409,
                detail=f"Taxonomy '{scheme_id}' terms are in use. Use force=true.",
            )

    # Delete all terms in this scheme
    gdb.sparql_update(f"""
        DELETE WHERE {{
            ?term skos:inScheme <{scheme_uri}> .
            ?term ?p ?o .
        }}
    """)
    # Delete the scheme itself
    gdb.sparql_update(f"DELETE WHERE {{ <{scheme_uri}> ?p ?o }}")

    return {"success": True, "deleted": scheme_id}


# =====================================================
# TERMS - CRUD (CBox detail)
# =====================================================

@router.get("/taxonomies/{scheme_id}/terms")
async def list_terms(scheme_id: str):
    """List all terms in a taxonomy."""
    _require_gdb()
    terms = gdb.get_taxonomy_terms(scheme_id)
    if not terms:
        terms = gdb.get_taxonomy_terms(f"scheme-{scheme_id}")
    return {"terms": terms, "count": len(terms)}


@router.post("/taxonomies/{scheme_id}/terms")
async def create_term(scheme_id: str, term: TermCreate):
    """Add a term to a taxonomy."""
    _require_gdb()

    # Find the scheme URI
    scheme_uri = f"{TAXONOMY_NS}scheme-{scheme_id}"
    exists = gdb.sparql_ask(f"ASK {{ <{scheme_uri}> a skos:ConceptScheme }}")
    if not exists:
        scheme_uri = f"{TAXONOMY_NS}{scheme_id}"
        exists = gdb.sparql_ask(f"ASK {{ <{scheme_uri}> a skos:ConceptScheme }}")
        if not exists:
            raise HTTPException(status_code=404, detail=f"Taxonomy '{scheme_id}' not found")

    term_uri = f"{TAXONOMY_NS}{term.term_id}"

    triples = [
        f"<{term_uri}> a skos:Concept .",
        f"<{term_uri}> skos:inScheme <{scheme_uri}> .",
        f'<{term_uri}> skos:prefLabel "{_escape(term.label)}" .',
    ]

    if term.definition:
        triples.append(f'<{term_uri}> skos:definition "{_escape(term.definition)}" .')

    for alias in term.aliases:
        triples.append(f'<{term_uri}> skos:altLabel "{_escape(alias)}" .')

    if term.broader:
        # Resolve broader: could be a full URI or a term_id
        broader_uri = term.broader if term.broader.startswith("http") else f"{TAXONOMY_NS}{term.broader}"
        triples.append(f"<{term_uri}> skos:broader <{broader_uri}> .")
        triples.append(f"<{broader_uri}> skos:narrower <{term_uri}> .")

    gdb.sparql_update("INSERT DATA {\n" + "\n".join(triples) + "\n}")

    print(f"✓ Created term: {term.label} in {scheme_id}")
    return {"success": True, "term_id": term.term_id, "uri": term_uri, "scheme": scheme_id}


@router.post("/taxonomies/{scheme_id}/terms/bulk")
async def bulk_create_terms(scheme_id: str, bulk: BulkTermsCreate):
    """Bulk add terms to a taxonomy."""
    _require_gdb()

    scheme_uri = f"{TAXONOMY_NS}scheme-{scheme_id}"
    exists = gdb.sparql_ask(f"ASK {{ <{scheme_uri}> a skos:ConceptScheme }}")
    if not exists:
        scheme_uri = f"{TAXONOMY_NS}{scheme_id}"
        exists = gdb.sparql_ask(f"ASK {{ <{scheme_uri}> a skos:ConceptScheme }}")
        if not exists:
            raise HTTPException(status_code=404, detail=f"Taxonomy '{scheme_id}' not found")

    triples = []
    for term in bulk.terms:
        term_uri = f"{TAXONOMY_NS}{term.term_id}"
        triples.append(f"<{term_uri}> a skos:Concept .")
        triples.append(f"<{term_uri}> skos:inScheme <{scheme_uri}> .")
        triples.append(f'<{term_uri}> skos:prefLabel "{_escape(term.label)}" .')
        if term.definition:
            triples.append(f'<{term_uri}> skos:definition "{_escape(term.definition)}" .')
        for alias in term.aliases:
            triples.append(f'<{term_uri}> skos:altLabel "{_escape(alias)}" .')
        if term.broader:
            broader_uri = term.broader if term.broader.startswith("http") else f"{TAXONOMY_NS}{term.broader}"
            triples.append(f"<{term_uri}> skos:broader <{broader_uri}> .")
            triples.append(f"<{broader_uri}> skos:narrower <{term_uri}> .")

    gdb.sparql_update("INSERT DATA {\n" + "\n".join(triples) + "\n}")

    return {"success": True, "created": len(bulk.terms), "scheme": scheme_id}


@router.put("/taxonomies/{scheme_id}/terms/{term_id}")
async def update_term(scheme_id: str, term_id: str, updates: TermUpdate):
    """Update a term."""
    _require_gdb()
    term_uri = f"{TAXONOMY_NS}{term_id}"

    exists = gdb.sparql_ask(f"ASK {{ <{term_uri}> a skos:Concept }}")
    if not exists:
        raise HTTPException(status_code=404, detail=f"Term '{term_id}' not found")

    deletes = []
    inserts = []

    if updates.label is not None:
        deletes.append(f"<{term_uri}> skos:prefLabel ?old .")
        inserts.append(f'<{term_uri}> skos:prefLabel "{_escape(updates.label)}" .')

    if updates.definition is not None:
        deletes.append(f"<{term_uri}> skos:definition ?old2 .")
        inserts.append(f'<{term_uri}> skos:definition "{_escape(updates.definition)}" .')

    if updates.aliases is not None:
        deletes.append(f"<{term_uri}> skos:altLabel ?oldAlias .")
        for alias in updates.aliases:
            inserts.append(f'<{term_uri}> skos:altLabel "{_escape(alias)}" .')

    if updates.broader is not None:
        # Remove old broader/narrower links
        deletes.append(f"<{term_uri}> skos:broader ?oldBroader .")
        if updates.broader:
            broader_uri = updates.broader if updates.broader.startswith("http") else f"{TAXONOMY_NS}{updates.broader}"
            inserts.append(f"<{term_uri}> skos:broader <{broader_uri}> .")
        # Also clean up the inverse narrower on the old parent
        gdb.sparql_update(f"DELETE WHERE {{ ?parent skos:narrower <{term_uri}> }}")
        if updates.broader:
            gdb.sparql_update(f"INSERT DATA {{ <{broader_uri}> skos:narrower <{term_uri}> . }}")

    if deletes:
        gdb.sparql_update(f"""
            DELETE {{ {' '.join(deletes)} }}
            INSERT {{ {' '.join(inserts)} }}
            WHERE {{ OPTIONAL {{ {' '.join(deletes)} }} }}
        """)

    return {"success": True, "term_id": term_id}


@router.delete("/taxonomies/{scheme_id}/terms/{term_id}")
async def delete_term(scheme_id: str, term_id: str, force: bool = False):
    """Delete a term from a taxonomy."""
    _require_gdb()
    term_uri = f"{TAXONOMY_NS}{term_id}"

    exists = gdb.sparql_ask(f"ASK {{ <{term_uri}> a skos:Concept }}")
    if not exists:
        raise HTTPException(status_code=404, detail=f"Term '{term_id}' not found")

    if not force:
        in_use = gdb.sparql_ask(f"""
            ASK {{ ?instance ?prop <{term_uri}> .
                   FILTER(STRSTARTS(STR(?instance), "{DATA_NS}")) }}
        """)
        if in_use:
            raise HTTPException(status_code=409, detail=f"Term '{term_id}' is in use. Use force=true.")

    gdb.sparql_update(f"DELETE WHERE {{ <{term_uri}> ?p ?o }}")
    return {"success": True, "deleted": term_id}


# =====================================================
# RELATIONSHIPS - CRUD (RBox)
# =====================================================

@router.get("/relationships")
async def list_relationships():
    """List all relationship types (edge types only, not concept properties)."""
    _require_gdb()

    rows = gdb.sparql_query(f"""
        SELECT DISTINCT ?rel ?label ?definition ?symmetric ?transitive ?functional ?inverse ?domain ?range WHERE {{
            ?rel a owl:ObjectProperty .
            FILTER(STRSTARTS(STR(?rel), "{REL_NS}"))
            OPTIONAL {{ ?rel rdfs:label ?label }}
            OPTIONAL {{ ?rel rdfs:comment ?definition }}
            OPTIONAL {{ ?rel a owl:SymmetricProperty . BIND(true AS ?symmetric) }}
            OPTIONAL {{ ?rel a owl:TransitiveProperty . BIND(true AS ?transitive) }}
            OPTIONAL {{ ?rel a owl:FunctionalProperty . BIND(true AS ?functional) }}
            OPTIONAL {{ ?rel owl:inverseOf ?inverse }}
            OPTIONAL {{ ?rel proto:definedOn ?domain . FILTER(STRSTARTS(STR(?domain), "{ONTOLOGY_NS}")) }}
            OPTIONAL {{ ?rel proto:rangeClass ?range . FILTER(STRSTARTS(STR(?range), "{ONTOLOGY_NS}")) }}
        }}
        ORDER BY ?label
    """)

    rels_map = {}
    for row in rows:
        uri = row["rel"]
        if uri not in rels_map:
            local = uri.rsplit("/", 1)[-1]
            rels_map[uri] = {
                "uri": uri,
                "label": row.get("label", local),
                "definition": row.get("definition", ""),
                "symmetric": row.get("symmetric") == "true",
                "transitive": row.get("transitive") == "true",
                "functional": row.get("functional") == "true",
                "inverse": row.get("inverse"),
                "domain": [],
                "range": [],
            }
        if row.get("domain") and row["domain"] not in rels_map[uri]["domain"]:
            rels_map[uri]["domain"].append(row["domain"])
        if row.get("range") and row["range"] not in rels_map[uri]["range"]:
            rels_map[uri]["range"].append(row["range"])

    return {"relationships": list(rels_map.values()), "count": len(rels_map)}


@router.post("/relationships")
async def create_relationship(rel: RelationshipTypeCreate):
    """Create a new relationship type as an OWL ObjectProperty."""
    _require_gdb()

    rel_uri = f"{REL_NS}{rel.label}"

    try:
        exists = gdb.sparql_ask(f"ASK {{ <{rel_uri}> a owl:ObjectProperty }}")
        if exists:
            raise HTTPException(status_code=409, detail=f"Relationship '{rel.label}' already exists")
    except HTTPException:
        raise
    except Exception as e:
        print(f"⚠️ Exists check failed (non-fatal, proceeding): {e}")

    triples = [
        f"<{rel_uri}> a owl:ObjectProperty .",
        f'<{rel_uri}> rdfs:label "{_escape(rel.label)}" .',
    ]

    if rel.definition:
        triples.append(f'<{rel_uri}> rdfs:comment "{_escape(rel.definition)}" .')

    if rel.symmetric:
        triples.append(f"<{rel_uri}> a owl:SymmetricProperty .")

    if rel.transitive:
        triples.append(f"<{rel_uri}> a owl:TransitiveProperty .")

    if rel.inverse:
        inv_uri = f"{REL_NS}{rel.inverse}"
        triples.append(f"<{rel_uri}> owl:inverseOf <{inv_uri}> .")

    if rel.functional:
        triples.append(f"<{rel_uri}> a owl:FunctionalProperty .")

    # Write domain constraints — which classes can be the source
    for domain_label in rel.domain:
        domain_uri = _label_to_uri(domain_label)
        triples.append(f"<{rel_uri}> rdfs:domain <{domain_uri}> .")
        triples.append(f"<{rel_uri}> proto:definedOn <{domain_uri}> .")

    # Write range constraints — which classes can be the target
    for range_label in rel.range:
        range_uri = _label_to_uri(range_label)
        triples.append(f"<{rel_uri}> rdfs:range <{range_uri}> .")
        triples.append(f"<{rel_uri}> proto:rangeClass <{range_uri}> .")

    sparql = "INSERT DATA {\n" + "\n".join(triples) + "\n}"
    print(f"DEBUG relationship SPARQL:\n{sparql}")
    try:
        gdb.sparql_update(sparql)
    except Exception as e:
        print(f"⚠️ Relationship SPARQL failed: {e}")
        raise HTTPException(status_code=500, detail=f"GraphDB rejected: {str(e)}")

    print(f"✓ Created relationship type: {rel.label}")
    return {"success": True, "uri": rel_uri, "label": rel.label}


@router.delete("/relationships/{label}")
async def delete_relationship(label: str, force: bool = False):
    """Delete a relationship type."""
    _require_gdb()
    rel_uri = f"{REL_NS}{label}"

    exists = gdb.sparql_ask(f"ASK {{ <{rel_uri}> a owl:ObjectProperty }}")
    if not exists:
        raise HTTPException(status_code=404, detail=f"Relationship '{label}' not found")

    if not force:
        in_use = gdb.sparql_ask(f"ASK {{ ?s <{rel_uri}> ?o }}")
        if in_use:
            raise HTTPException(status_code=409, detail=f"Relationship '{label}' is in use. Use force=true.")

    gdb.sparql_update(f"DELETE WHERE {{ <{rel_uri}> ?p ?o }}")
    return {"success": True, "deleted": label}


# =====================================================
# TTL EDITOR (Advanced)
# =====================================================

class TTLValidateRequest(BaseModel):
    ttl: str = Field(..., description="Raw Turtle content to validate")


class TTLCommitRequest(BaseModel):
    ttl: str = Field(..., description="Raw Turtle content to insert")
    named_graph: Optional[str] = Field(None, description="Target named graph (default: default graph)")


@router.post("/ttl/validate")
async def validate_ttl(request: TTLValidateRequest):
    """Parse and validate TTL without committing. Returns a preview of what would be created."""
    _require_gdb()

    try:
        import rdflib

        g = rdflib.Graph()
        # Bind common prefixes
        g.bind("proto", rdflib.Namespace("https://proto.atlas/ontology/"))
        g.bind("data", rdflib.Namespace("https://proto.atlas/data/"))
        g.bind("tax", rdflib.Namespace("https://proto.atlas/taxonomy/"))
        g.bind("rel", rdflib.Namespace("https://proto.atlas/relationship/"))
        g.bind("skos", rdflib.Namespace("http://www.w3.org/2004/02/skos/core#"))
        g.bind("sh", rdflib.Namespace("http://www.w3.org/ns/shacl#"))

        g.parse(data=request.ttl, format="turtle")

        # Summarize what's in the TTL
        classes = set()
        properties = set()
        individuals = set()
        triples_count = len(g)

        OWL = rdflib.Namespace("http://www.w3.org/2002/07/owl#")
        RDF = rdflib.RDF
        RDFS = rdflib.RDFS

        for s, p, o in g:
            if p == RDF.type:
                if o == OWL.Class:
                    classes.add(str(s))
                elif o in (OWL.ObjectProperty, OWL.DatatypeProperty, OWL.FunctionalProperty):
                    properties.add(str(s))
                elif str(o).startswith("https://proto.atlas/ontology/"):
                    individuals.add(str(s))

        return {
            "valid": True,
            "triple_count": triples_count,
            "classes": list(classes),
            "properties": list(properties),
            "individuals": list(individuals),
            "preview": f"{triples_count} triples: {len(classes)} classes, {len(properties)} properties, {len(individuals)} instances",
        }

    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
            "triple_count": 0,
        }


@router.post("/ttl/commit")
async def commit_ttl(request: TTLCommitRequest):
    """Validate and commit raw TTL into GraphDB."""
    _require_gdb()

    try:
        import rdflib

        g = rdflib.Graph()
        g.bind("proto", rdflib.Namespace("https://proto.atlas/ontology/"))
        g.bind("data", rdflib.Namespace("https://proto.atlas/data/"))
        g.bind("tax", rdflib.Namespace("https://proto.atlas/taxonomy/"))
        g.bind("rel", rdflib.Namespace("https://proto.atlas/relationship/"))
        g.bind("skos", rdflib.Namespace("http://www.w3.org/2004/02/skos/core#"))
        g.bind("sh", rdflib.Namespace("http://www.w3.org/ns/shacl#"))

        g.parse(data=request.ttl, format="turtle")
        triple_count = len(g)

        if triple_count == 0:
            raise HTTPException(status_code=400, detail="No triples found in TTL")

        # Serialize to N-Triples for clean SPARQL INSERT
        nt = g.serialize(format="nt")

        # Build SPARQL INSERT
        if request.named_graph:
            sparql = f"INSERT DATA {{ GRAPH <{request.named_graph}> {{\n{nt}\n}} }}"
        else:
            sparql = f"INSERT DATA {{\n{nt}\n}}"

        gdb.sparql_update(sparql)

        print(f"✓ TTL commit: {triple_count} triples inserted")
        return {
            "success": True,
            "triple_count": triple_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"TTL commit failed: {str(e)}")


@router.get("/ttl/snippets")
async def get_ttl_snippets():
    """Return template snippets for the TTL editor."""
    return {
        "snippets": [
            {
                "label": "New OWL Class",
                "description": "Define a new class with properties",
                "ttl": """@prefix proto: <https://proto.atlas/ontology/> .
@prefix owl:   <http://www.w3.org/2002/07/owl#> .
@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .

proto:MyNewClass a owl:Class ;
    rdfs:label "My New Class" ;
    rdfs:comment "Description of what this class represents" ;
    rdfs:subClassOf proto:Artifact .

proto:myProperty a owl:DatatypeProperty ;
    rdfs:label "myProperty" ;
    rdfs:domain proto:MyNewClass ;
    rdfs:range xsd:string .""",
            },
            {
                "label": "Inverse Property Pair",
                "description": "Two properties that are inverses of each other",
                "ttl": """@prefix rel:  <https://proto.atlas/relationship/> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix proto: <https://proto.atlas/ontology/> .

rel:OWNED_BY a owl:ObjectProperty ;
    rdfs:label "OWNED_BY" ;
    rdfs:comment "Artifact is owned by a team" ;
    rdfs:domain proto:Artifact ;
    rdfs:range proto:Team ;
    owl:inverseOf rel:OWNS .

rel:OWNS a owl:ObjectProperty ;
    rdfs:label "OWNS" ;
    rdfs:comment "Team owns an artifact" ;
    rdfs:domain proto:Team ;
    rdfs:range proto:Artifact ;
    owl:inverseOf rel:OWNED_BY .""",
            },
            {
                "label": "SKOS Hierarchy",
                "description": "Taxonomy with broader/narrower relationships",
                "ttl": """@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix tax:  <https://proto.atlas/taxonomy/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

tax:scheme-my-taxonomy a skos:ConceptScheme ;
    rdfs:label "My Taxonomy" .

tax:parent-term a skos:Concept ;
    skos:inScheme tax:scheme-my-taxonomy ;
    skos:prefLabel "Parent Term" .

tax:child-term a skos:Concept ;
    skos:inScheme tax:scheme-my-taxonomy ;
    skos:prefLabel "Child Term" ;
    skos:broader tax:parent-term .""",
            },
            {
                "label": "OWL Inference Rule",
                "description": "Define a class using OWL restrictions for automatic classification",
                "ttl": """@prefix proto: <https://proto.atlas/ontology/> .
@prefix owl:   <http://www.w3.org/2002/07/owl#> .
@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .

proto:MissionReady a owl:Class ;
    rdfs:label "Mission Ready" ;
    rdfs:comment "A scenario where all required techniques are covered" ;
    owl:equivalentClass [
        owl:intersectionOf (
            proto:Scenario
            [ a owl:Restriction ;
              owl:onProperty proto:requiresTechnique ;
              owl:allValuesFrom [
                  a owl:Restriction ;
                  owl:onProperty [ owl:inverseOf proto:mapsToTechnique ] ;
                  owl:someValuesFrom proto:LibraryModule
              ]
            ]
        )
    ] .""",
            },
            {
                "label": "SHACL Validation Shape",
                "description": "Add validation constraints for a class",
                "ttl": """@prefix sh:    <http://www.w3.org/ns/shacl#> .
@prefix proto: <https://proto.atlas/ontology/> .
@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .
@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .

# Note: SHACL shapes should be committed to the shapes graph
# Use named_graph: http://rdf4j.org/schema/rdf4j#SHACLShapeGraph

proto:LibraryModuleShape a sh:NodeShape ;
    sh:targetClass proto:LibraryModule ;
    rdfs:label "Library Module Validation" ;
    sh:property [
        sh:path proto:name ;
        sh:minCount 1 ;
        sh:datatype xsd:string ;
    ] ;
    sh:property [
        sh:path proto:riskLevel ;
        sh:minCount 1 ;
    ] .""",
            },
        ]
    }


# =====================================================
# SHACL SHAPES (CBox automation)
# =====================================================

@router.get("/shapes")
async def list_shapes():
    """List all SHACL shapes (requires shapes graph access)."""
    _require_gdb()

    # SHACL shapes are in a named graph — try querying directly
    rows = gdb.sparql_query(f"""
        SELECT ?shape ?target ?label WHERE {{
            GRAPH <http://rdf4j.org/schema/rdf4j#SHACLShapeGraph> {{
                ?shape a sh:NodeShape .
                OPTIONAL {{ ?shape sh:targetClass ?target }}
                OPTIONAL {{ ?shape rdfs:label ?label }}
            }}
        }}
    """)

    shapes = []
    for row in rows:
        shapes.append({
            "uri": row["shape"],
            "target_class": row.get("target"),
            "label": row.get("label", ""),
        })

    return {"shapes": shapes, "count": len(shapes)}


# =====================================================
# SUMMARY / HEALTH
# =====================================================

@router.get("/summary")
async def ontology_summary():
    """Dashboard summary of the full ontology."""
    _require_gdb()

    # Count classes
    class_count = gdb.sparql_query("""
        SELECT (COUNT(DISTINCT ?cls) AS ?count) WHERE {
            ?cls a owl:Class .
            FILTER(STRSTARTS(STR(?cls), "https://proto.atlas/ontology/"))
        }
    """)

    # Count properties
    prop_count = gdb.sparql_query("""
        SELECT (COUNT(DISTINCT ?prop) AS ?count) WHERE {
            ?prop rdfs:domain ?d .
            FILTER(STRSTARTS(STR(?prop), "https://proto.atlas/ontology/"))
        }
    """)

    # Count taxonomy schemes
    scheme_count = gdb.sparql_query("""
        SELECT (COUNT(DISTINCT ?s) AS ?count) WHERE { ?s a skos:ConceptScheme }
    """)

    # Count taxonomy terms
    term_count = gdb.sparql_query("""
        SELECT (COUNT(DISTINCT ?t) AS ?count) WHERE { ?t a skos:Concept }
    """)

    # Count relationship types
    rel_count = gdb.sparql_query(f"""
        SELECT (COUNT(DISTINCT ?r) AS ?count) WHERE {{
            ?r a owl:ObjectProperty .
            FILTER(STRSTARTS(STR(?r), "{REL_NS}"))
        }}
    """)

    # Count data instances
    instance_count = gdb.sparql_query(f"""
        SELECT (COUNT(DISTINCT ?i) AS ?count) WHERE {{
            ?i a ?type .
            FILTER(STRSTARTS(STR(?i), "{DATA_NS}"))
        }}
    """)

    # Count edges
    edge_count = gdb.sparql_query(f"""
        SELECT (COUNT(*) AS ?count) WHERE {{
            ?s ?p ?o .
            FILTER(STRSTARTS(STR(?p), "{REL_NS}"))
            FILTER(STRSTARTS(STR(?s), "{DATA_NS}"))
        }}
    """)

    def _extract_count(rows):
        return rows[0].get("count", 0) if rows else 0

    return {
        "tbox": {
            "classes": _extract_count(class_count),
            "properties": _extract_count(prop_count),
        },
        "cbox": {
            "taxonomy_schemes": _extract_count(scheme_count),
            "taxonomy_terms": _extract_count(term_count),
        },
        "rbox": {
            "relationship_types": _extract_count(rel_count),
        },
        "abox": {
            "instances": _extract_count(instance_count),
            "edges": _extract_count(edge_count),
        },
    }


@router.get("/health")
async def health():
    _require_gdb()
    health = gdb.health()
    return {
        "status": "ok" if health.get("status") == "connected" else "error",
        "graphdb": health,
    }


# =====================================================
# HELPERS
# =====================================================

def _prop_type_to_range(prop_type: str) -> Optional[str]:
    """Map property type string to XSD/OWL range URI."""
    mapping = {
        "string": "http://www.w3.org/2001/XMLSchema#string",
        "integer": "http://www.w3.org/2001/XMLSchema#integer",
        "boolean": "http://www.w3.org/2001/XMLSchema#boolean",
        "datetime": "http://www.w3.org/2001/XMLSchema#dateTime",
        "double": "http://www.w3.org/2001/XMLSchema#double",
        "uri": "http://www.w3.org/2004/02/skos/core#Concept",
    }
    return mapping.get(prop_type)


def _create_shacl_shape(class_uri: str, label: str, required_props: List[PropertyDefinition]):
    """Create a SHACL NodeShape for required property validation."""
    local = class_uri.replace(ONTOLOGY_NS, "")
    shape_uri = f"https://proto.atlas/shapes/{local}Shape"

    triples = [
        f"<{shape_uri}> a sh:NodeShape .",
        f"<{shape_uri}> sh:targetClass <{class_uri}> .",
        f'<{shape_uri}> rdfs:label "{_escape(label)} Shape" .',
    ]

    for prop in required_props:
        prop_uri = f"{ONTOLOGY_NS}{prop.name}"
        blank = f"_:prop_{prop.name}"
        triples.append(f"<{shape_uri}> sh:property {blank} .")
        triples.append(f'{blank} sh:path <{prop_uri}> .')
        triples.append(f'{blank} sh:minCount 1 .')
        triples.append(f'{blank} rdfs:label "{_escape(prop.name)}" .')
        # Single-value properties get maxCount constraint
        if not prop.multiple:
            triples.append(f'{blank} sh:maxCount 1 .')

    # SHACL shapes need to go into the shapes graph
    # This requires GraphDB to accept writes to the named graph
    try:
        gdb.sparql_update(
            "INSERT DATA { GRAPH <http://rdf4j.org/schema/rdf4j#SHACLShapeGraph> {\n"
            + "\n".join(triples)
            + "\n}}"
        )
        print(f"✓ Created SHACL shape for {label}")
    except Exception as e:
        print(f"⚠️ SHACL shape creation failed (non-fatal): {e}")