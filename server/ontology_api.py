#!/usr/bin/env python3
"""
Ontology API - Full CRUD for Ontology Management
Handles concepts, taxonomies, terms, and relationship types stored in ArangoDB

Collections:
- _ontology_concepts: Concept definitions (classes/types)
- _ontology_edges: IS-A relationships between concepts
- _taxonomy_schemes: Controlled vocabulary definitions
- _taxonomy_terms: Terms within taxonomies
- _relationship_types: Edge type definitions with domain/range constraints
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
import os

router = APIRouter(prefix="/api/ontology", tags=["ontology"])

# =====================================================
# DATABASE CONNECTION (injected from main.py)
# =====================================================
db = None

# Collection names
CONCEPTS_COLLECTION = "ontology_concepts"
EDGES_COLLECTION = "ontology_edges"
TAXONOMY_SCHEMES_COLLECTION = "taxonomy_schemes"
TAXONOMY_TERMS_COLLECTION = "taxonomy_terms"
RELATIONSHIP_TYPES_COLLECTION = "relationship_types"

ALL_COLLECTIONS = [
    CONCEPTS_COLLECTION,
    EDGES_COLLECTION,
    TAXONOMY_SCHEMES_COLLECTION,
    TAXONOMY_TERMS_COLLECTION,
    RELATIONSHIP_TYPES_COLLECTION,
]


# =====================================================
# MODELS - Concepts
# =====================================================

class PropertyDefinition(BaseModel):
    """Defines a property that a concept can have"""
    name: str
    type: str = "string"  # string, integer, datetime, uri, object, string[], uri[]
    required: bool = False
    taxonomy: Optional[str] = None  # Reference to taxonomy scheme ID
    range: Optional[str] = None  # For uri types, concept URI that can be referenced
    description: Optional[str] = None
    default: Optional[Any] = None


class ConceptCreate(BaseModel):
    """Create a new ontology concept"""
    uri: str = Field(..., description="Unique URI like 'proto:concept/LibraryModule'")
    label: str = Field(..., description="Human-readable label")
    definition: str = Field(..., description="Description of what this concept represents")
    parent_uri: Optional[str] = Field(None, description="Parent concept URI for IS-A hierarchy")
    abstract: bool = Field(False, description="If true, cannot be instantiated directly")
    collection: Optional[str] = Field(None, description="ArangoDB collection name for instances")
    properties: List[PropertyDefinition] = Field(default_factory=list)


class ConceptUpdate(BaseModel):
    """Update an existing concept"""
    label: Optional[str] = None
    definition: Optional[str] = None
    parent_uri: Optional[str] = None
    abstract: Optional[bool] = None
    collection: Optional[str] = None
    properties: Optional[List[PropertyDefinition]] = None


# =====================================================
# MODELS - Taxonomies
# =====================================================

class TaxonomyCreate(BaseModel):
    """Create a new taxonomy scheme"""
    taxonomy_id: str = Field(..., description="Unique ID like 'c2_frameworks'")
    label: str = Field(..., description="Human-readable label")
    description: str = Field("", description="What this taxonomy represents")
    version: str = Field("1.0.0", description="Version string")


class TaxonomyUpdate(BaseModel):
    """Update taxonomy metadata"""
    label: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None


class TermCreate(BaseModel):
    """Create a new term in a taxonomy"""
    uri: str = Field(..., description="Unique URI like 'proto:c2/cobalt_strike'")
    label: str = Field(..., description="Canonical label (what gets stored in data)")
    definition: str = Field("", description="What this term means")
    aliases: List[str] = Field(default_factory=list, description="Alternative labels that resolve to this term")
    broader: Optional[str] = Field(None, description="Parent term URI for hierarchy")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extra fields (color, icon, etc.)")


class TermUpdate(BaseModel):
    """Update an existing term"""
    label: Optional[str] = None
    definition: Optional[str] = None
    aliases: Optional[List[str]] = None
    broader: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class BulkTermsCreate(BaseModel):
    """Bulk create terms in a taxonomy"""
    terms: List[TermCreate]


# =====================================================
# MODELS - Relationship Types
# =====================================================

class RelationshipTypeCreate(BaseModel):
    """Create a new relationship type"""
    uri: str = Field(..., description="Unique URI like 'proto:rel/PRODUCES'")
    label: str = Field(..., description="Edge label used in graph")
    definition: str = Field(..., description="What this relationship means")
    domain: List[str] = Field(..., description="Concept URIs that can be the source")
    range: List[str] = Field(..., description="Concept URIs that can be the target")
    inverse: Optional[str] = Field(None, description="Inverse relationship URI")
    symmetric: bool = Field(False, description="If true, A-R->B implies B-R->A")
    transitive: bool = Field(False, description="If true, A-R->B and B-R->C implies A-R->C")


class RelationshipTypeUpdate(BaseModel):
    """Update a relationship type"""
    label: Optional[str] = None
    definition: Optional[str] = None
    domain: Optional[List[str]] = None
    range: Optional[List[str]] = None
    inverse: Optional[str] = None
    symmetric: Optional[bool] = None
    transitive: Optional[bool] = None


# =====================================================
# INITIALIZATION
# =====================================================

def init_collections():
    """Ensure all ontology collections exist"""
    if not db:
        print("⚠️ Ontology API: Database not connected")
        return False
    
    try:
        for coll_name in ALL_COLLECTIONS:
            if coll_name == EDGES_COLLECTION:
                # Edge collection
                if not db.has_collection(coll_name):
                    db.create_collection(coll_name, edge=True)
                    print(f"  ✓ Created edge collection: {coll_name}")
            else:
                # Document collection
                if not db.has_collection(coll_name):
                    db.create_collection(coll_name)
                    print(f"  ✓ Created collection: {coll_name}")
        
        print(f"✓ Ontology collections initialized")
        return True
    except Exception as e:
        print(f"✗ Failed to initialize ontology collections: {e}")
        return False


# =====================================================
# HELPER FUNCTIONS
# =====================================================

def uri_to_key(uri: str) -> str:
    """Convert URI to valid ArangoDB document key"""
    return uri.replace(":", "_").replace("/", "_").replace(" ", "_")


def get_timestamp() -> str:
    """Get current ISO timestamp"""
    return datetime.now().isoformat()


def concept_exists(uri: str) -> bool:
    """Check if a concept exists"""
    key = uri_to_key(uri)
    try:
        return db.collection(CONCEPTS_COLLECTION).has(key)
    except:
        return False


def taxonomy_exists(taxonomy_id: str) -> bool:
    """Check if a taxonomy scheme exists"""
    try:
        return db.collection(TAXONOMY_SCHEMES_COLLECTION).has(taxonomy_id)
    except:
        return False


def term_exists(uri: str) -> bool:
    """Check if a term exists"""
    key = uri_to_key(uri)
    try:
        return db.collection(TAXONOMY_TERMS_COLLECTION).has(key)
    except:
        return False


# =====================================================
# CONCEPTS - CRUD
# =====================================================

@router.get("/concepts", summary="List all concepts")
async def list_concepts(
    include_abstract: bool = Query(True, description="Include abstract concepts"),
    parent_uri: Optional[str] = Query(None, description="Filter by parent concept")
):
    """List all ontology concepts"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    bind_vars = {}
    filters = []
    
    if not include_abstract:
        filters.append("c.abstract != true")
    
    if parent_uri:
        filters.append("c.parent_uri == @parent_uri")
        bind_vars["parent_uri"] = parent_uri
    
    filter_clause = f"FILTER {' AND '.join(filters)}" if filters else ""
    
    query = f"""
        FOR c IN {CONCEPTS_COLLECTION}
            {filter_clause}
            SORT c.label ASC
            RETURN c
    """
    
    cursor = db.aql.execute(query, bind_vars=bind_vars)
    concepts = list(cursor)
    
    return {"concepts": concepts, "count": len(concepts)}


@router.get("/concepts/hierarchy", summary="Get concept hierarchy as tree")
async def get_concept_hierarchy():
    """Get concepts organized as a tree structure"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    # Get all concepts
    cursor = db.aql.execute(f"FOR c IN {CONCEPTS_COLLECTION} RETURN c")
    concepts = {c["uri"]: c for c in cursor}
    
    # Build tree
    def build_tree(parent_uri: Optional[str]) -> List[Dict]:
        children = []
        for uri, concept in concepts.items():
            if concept.get("parent_uri") == parent_uri:
                node = {
                    "uri": concept["uri"],
                    "label": concept["label"],
                    "abstract": concept.get("abstract", False),
                    "collection": concept.get("collection"),
                    "children": build_tree(uri)
                }
                children.append(node)
        return sorted(children, key=lambda x: x["label"])
    
    tree = build_tree(None)
    return {"hierarchy": tree}


@router.get("/concepts/{uri:path}", summary="Get a single concept")
async def get_concept(uri: str, include_inherited_properties: bool = True):
    """Get a concept by URI with optional inherited properties"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    key = uri_to_key(uri)
    
    try:
        concept = db.collection(CONCEPTS_COLLECTION).get(key)
    except:
        concept = None
    
    if not concept:
        raise HTTPException(404, f"Concept not found: {uri}")
    
    result = dict(concept)

    result["all_properties"] = list(concept.get("properties", []))
    
    # Get inherited properties
    if include_inherited_properties and concept.get("parent_uri"):
        all_properties = list(concept.get("properties", []))
        own_property_names = {p["name"] for p in all_properties}
        
        # Walk up the hierarchy
        current_parent = concept.get("parent_uri")
        while current_parent:
            parent_key = uri_to_key(current_parent)
            try:
                parent = db.collection(CONCEPTS_COLLECTION).get(parent_key)
            except:
                parent = None
            
            if parent:
                for prop in parent.get("properties", []):
                    if prop["name"] not in own_property_names:
                        inherited_prop = dict(prop)
                        inherited_prop["inherited_from"] = current_parent
                        all_properties.append(inherited_prop)
                        own_property_names.add(prop["name"])
                current_parent = parent.get("parent_uri")
            else:
                break
        
        result["all_properties"] = all_properties
    
    # Get instance count if collection exists
    if concept.get("collection"):
        try:
            if db.has_collection(concept["collection"]):
                result["instance_count"] = db.collection(concept["collection"]).count()
            else:
                result["instance_count"] = 0
        except:
            result["instance_count"] = 0
    
    return result


@router.post("/concepts", summary="Create a new concept")
async def create_concept(concept: ConceptCreate):
    """Create a new ontology concept"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    key = uri_to_key(concept.uri)
    
    # Check doesn't already exist
    if db.collection(CONCEPTS_COLLECTION).has(key):
        raise HTTPException(409, f"Concept already exists: {concept.uri}")
    
    # Validate parent exists if specified
    if concept.parent_uri:
        if not concept_exists(concept.parent_uri):
            raise HTTPException(400, f"Parent concept not found: {concept.parent_uri}")
    
    # Validate taxonomy references in properties
    for prop in concept.properties:
        if prop.taxonomy:
            if not taxonomy_exists(prop.taxonomy):
                raise HTTPException(400, f"Taxonomy not found for property '{prop.name}': {prop.taxonomy}")
    
    # Create document
    doc = {
        "_key": key,
        "uri": concept.uri,
        "label": concept.label,
        "definition": concept.definition,
        "parent_uri": concept.parent_uri,
        "abstract": concept.abstract,
        "collection": concept.collection,
        "properties": [p.dict() for p in concept.properties],
        "created_at": get_timestamp(),
        "updated_at": get_timestamp()
    }
    
    result = db.collection(CONCEPTS_COLLECTION).insert(doc)
    
    # Create IS-A edge if parent specified
    if concept.parent_uri:
        edge_doc = {
            "_from": f"{CONCEPTS_COLLECTION}/{key}",
            "_to": f"{CONCEPTS_COLLECTION}/{uri_to_key(concept.parent_uri)}",
            "type": "IS_A",
            "created_at": get_timestamp()
        }
        db.collection(EDGES_COLLECTION).insert(edge_doc)
    
    # Invalidate cache
    _invalidate_ontology_cache()
    
    return {
        "success": True,
        "uri": concept.uri,
        "_id": result["_id"],
        "_key": result["_key"]
    }


@router.put("/concepts/{uri:path}", summary="Update a concept")
async def update_concept(uri: str, updates: ConceptUpdate):
    """Update an existing concept"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    key = uri_to_key(uri)
    
    if not db.collection(CONCEPTS_COLLECTION).has(key):
        raise HTTPException(404, f"Concept not found: {uri}")
    
    # Get existing concept
    existing = db.collection(CONCEPTS_COLLECTION).get(key)
    
    # Build update document
    update_doc = {"updated_at": get_timestamp()}
    
    if updates.label is not None:
        update_doc["label"] = updates.label
    
    if updates.definition is not None:
        update_doc["definition"] = updates.definition
    
    if updates.abstract is not None:
        update_doc["abstract"] = updates.abstract
    
    if updates.collection is not None:
        update_doc["collection"] = updates.collection
    
    if updates.properties is not None:
        # Validate taxonomy references
        for prop in updates.properties:
            if prop.taxonomy:
                if not taxonomy_exists(prop.taxonomy):
                    raise HTTPException(400, f"Taxonomy not found for property '{prop.name}': {prop.taxonomy}")
        update_doc["properties"] = [p.dict() for p in updates.properties]
    
    # Handle parent change
    if updates.parent_uri is not None:
        old_parent = existing.get("parent_uri")
        new_parent = updates.parent_uri if updates.parent_uri != "" else None
        
        if new_parent != old_parent:
            # Validate new parent exists
            if new_parent and not concept_exists(new_parent):
                raise HTTPException(400, f"Parent concept not found: {new_parent}")
            
            # Prevent circular hierarchy
            if new_parent:
                current = new_parent
                while current:
                    if current == uri:
                        raise HTTPException(400, "Cannot create circular hierarchy")
                    parent_concept = db.collection(CONCEPTS_COLLECTION).get(uri_to_key(current))
                    current = parent_concept.get("parent_uri") if parent_concept else None
            
            # Remove old IS-A edge
            db.aql.execute(f"""
                FOR e IN {EDGES_COLLECTION}
                    FILTER e._from == @from AND e.type == "IS_A"
                    REMOVE e IN {EDGES_COLLECTION}
            """, bind_vars={"from": f"{CONCEPTS_COLLECTION}/{key}"})
            
            # Create new IS-A edge
            if new_parent:
                edge_doc = {
                    "_from": f"{CONCEPTS_COLLECTION}/{key}",
                    "_to": f"{CONCEPTS_COLLECTION}/{uri_to_key(new_parent)}",
                    "type": "IS_A",
                    "created_at": get_timestamp()
                }
                db.collection(EDGES_COLLECTION).insert(edge_doc)
            
            update_doc["parent_uri"] = new_parent
    
    # Apply update
    db.collection(CONCEPTS_COLLECTION).update({**update_doc, "_key": key})
    
    _invalidate_ontology_cache()
    
    return {"success": True, "uri": uri}


@router.delete("/concepts/{uri:path}", summary="Delete a concept")
async def delete_concept(
    uri: str,
    force: bool = Query(False, description="Force delete even if instances exist")
):
    """Delete a concept"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    key = uri_to_key(uri)
    
    concept = db.collection(CONCEPTS_COLLECTION).get(key)
    if not concept:
        raise HTTPException(404, f"Concept not found: {uri}")
    
    # Check for instances
    if concept.get("collection") and not force:
        try:
            if db.has_collection(concept["collection"]):
                count = db.collection(concept["collection"]).count()
                if count > 0:
                    raise HTTPException(
                        400, 
                        f"Cannot delete: {count} instances exist in collection '{concept['collection']}'. Use force=true to override."
                    )
        except HTTPException:
            raise
        except:
            pass
    
    # Check for child concepts
    children = list(db.aql.execute(f"""
        FOR c IN {CONCEPTS_COLLECTION}
            FILTER c.parent_uri == @uri
            RETURN c.uri
    """, bind_vars={"uri": uri}))
    
    if children and not force:
        raise HTTPException(
            400, 
            f"Cannot delete: has {len(children)} child concepts: {children[:5]}. Use force=true to override."
        )
    
    # Delete IS-A edges involving this concept
    db.aql.execute(f"""
        FOR e IN {EDGES_COLLECTION}
            FILTER e._from == @id OR e._to == @id
            REMOVE e IN {EDGES_COLLECTION}
    """, bind_vars={"id": f"{CONCEPTS_COLLECTION}/{key}"})
    
    # Delete concept
    db.collection(CONCEPTS_COLLECTION).delete(key)
    
    _invalidate_ontology_cache()
    
    return {"success": True, "deleted": uri}


@router.post("/concepts/{uri:path}/properties", summary="Add a property to a concept")
async def add_concept_property(uri: str, property: PropertyDefinition):
    """Add a property to an existing concept"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    key = uri_to_key(uri)
    
    concept = db.collection(CONCEPTS_COLLECTION).get(key)
    if not concept:
        raise HTTPException(404, f"Concept not found: {uri}")
    
    # Check property doesn't already exist
    existing_props = concept.get("properties", [])
    if any(p["name"] == property.name for p in existing_props):
        raise HTTPException(409, f"Property already exists: {property.name}")
    
    # Validate taxonomy reference
    if property.taxonomy and not taxonomy_exists(property.taxonomy):
        raise HTTPException(400, f"Taxonomy not found: {property.taxonomy}")
    
    # Add property
    existing_props.append(property.dict())
    db.collection(CONCEPTS_COLLECTION).update({
        "_key": key,
        "properties": existing_props,
        "updated_at": get_timestamp()
    })
    
    _invalidate_ontology_cache()
    
    return {"success": True, "uri": uri, "property": property.name}

@router.delete("/concept-properties")
async def remove_concept_property(uri: str = Query(...), property_name: str = Query(...)):
    """Remove a property from a concept"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    key = uri_to_key(uri)
    
    concept = db.collection(CONCEPTS_COLLECTION).get(key)
    if not concept:
        raise HTTPException(404, f"Concept not found: {uri}")
    
    existing_props = concept.get("properties", [])
    new_props = [p for p in existing_props if p["name"] != property_name]
    
    if len(new_props) == len(existing_props):
        raise HTTPException(404, f"Property not found: {property_name}")
    
    db.collection(CONCEPTS_COLLECTION).update({"_key": key, "properties": new_props, "updated_at": get_timestamp()})
    
    _invalidate_ontology_cache()
    
    return {"success": True, "uri": uri, "removed": property_name}


# =====================================================
# TAXONOMIES - CRUD
# =====================================================

@router.get("/taxonomies", summary="List all taxonomies")
async def list_taxonomies():
    """List all taxonomy schemes with term counts"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    query = f"""
        FOR t IN {TAXONOMY_SCHEMES_COLLECTION}
            LET term_count = LENGTH(
                FOR term IN {TAXONOMY_TERMS_COLLECTION}
                    FILTER term.scheme_id == t.taxonomy_id
                    RETURN 1
            )
            SORT t.label ASC
            RETURN MERGE(t, {{term_count: term_count}})
    """
    
    cursor = db.aql.execute(query)
    taxonomies = list(cursor)
    
    return {"taxonomies": taxonomies, "count": len(taxonomies)}


@router.get("/taxonomies/{taxonomy_id}", summary="Get a taxonomy with its terms")
async def get_taxonomy(
    taxonomy_id: str,
    include_terms: bool = Query(True, description="Include all terms")
):
    """Get a taxonomy scheme with optional terms"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    scheme = db.collection(TAXONOMY_SCHEMES_COLLECTION).get(taxonomy_id)
    if not scheme:
        raise HTTPException(404, f"Taxonomy not found: {taxonomy_id}")
    
    result = dict(scheme)
    
    if include_terms:
        cursor = db.aql.execute(f"""
            FOR t IN {TAXONOMY_TERMS_COLLECTION}
                FILTER t.scheme_id == @id
                SORT t.label ASC
                RETURN t
        """, bind_vars={"id": taxonomy_id})
        result["terms"] = list(cursor)
    
    # Find which concepts use this taxonomy
    cursor = db.aql.execute(f"""
        FOR c IN {CONCEPTS_COLLECTION}
            FOR prop IN (c.properties || [])
                FILTER prop.taxonomy == @id
                RETURN DISTINCT {{
                    concept_uri: c.uri,
                    concept_label: c.label,
                    property_name: prop.name
                }}
    """, bind_vars={"id": taxonomy_id})
    result["used_by"] = list(cursor)
    
    return result


@router.post("/taxonomies", summary="Create a new taxonomy")
async def create_taxonomy(taxonomy: TaxonomyCreate):
    """Create a new taxonomy scheme"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    if db.collection(TAXONOMY_SCHEMES_COLLECTION).has(taxonomy.taxonomy_id):
        raise HTTPException(409, f"Taxonomy already exists: {taxonomy.taxonomy_id}")
    
    doc = {
        "_key": taxonomy.taxonomy_id,
        "taxonomy_id": taxonomy.taxonomy_id,
        "label": taxonomy.label,
        "description": taxonomy.description,
        "version": taxonomy.version,
        "created_at": get_timestamp(),
        "updated_at": get_timestamp()
    }
    
    result = db.collection(TAXONOMY_SCHEMES_COLLECTION).insert(doc)
    
    _invalidate_taxonomy_cache()
    
    return {
        "success": True,
        "taxonomy_id": taxonomy.taxonomy_id,
        "_id": result["_id"]
    }


@router.put("/taxonomies/{taxonomy_id}", summary="Update taxonomy metadata")
async def update_taxonomy(taxonomy_id: str, updates: TaxonomyUpdate):
    """Update taxonomy scheme metadata"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    if not db.collection(TAXONOMY_SCHEMES_COLLECTION).has(taxonomy_id):
        raise HTTPException(404, f"Taxonomy not found: {taxonomy_id}")
    
    update_doc = {"updated_at": get_timestamp()}
    
    if updates.label is not None:
        update_doc["label"] = updates.label
    if updates.description is not None:
        update_doc["description"] = updates.description
    if updates.version is not None:
        update_doc["version"] = updates.version
    
    db.collection(TAXONOMY_SCHEMES_COLLECTION).update({**update_doc, "_key": taxonomy_id})
    
    _invalidate_taxonomy_cache()
    
    return {"success": True, "taxonomy_id": taxonomy_id}


@router.delete("/taxonomies/{taxonomy_id}", summary="Delete a taxonomy")
async def delete_taxonomy(
    taxonomy_id: str,
    force: bool = Query(False, description="Force delete even if in use")
):
    """Delete a taxonomy scheme and all its terms"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    if not db.collection(TAXONOMY_SCHEMES_COLLECTION).has(taxonomy_id):
        raise HTTPException(404, f"Taxonomy not found: {taxonomy_id}")
    
    # Check if taxonomy is used by any concept properties
    if not force:
        cursor = db.aql.execute(f"""
            FOR c IN {CONCEPTS_COLLECTION}
                FOR prop IN (c.properties || [])
                    FILTER prop.taxonomy == @id
                    RETURN DISTINCT c.uri
        """, bind_vars={"id": taxonomy_id})
        used_by = list(cursor)
        
        if used_by:
            raise HTTPException(
                400,
                f"Cannot delete: taxonomy is used by {len(used_by)} concepts: {used_by[:5]}. Use force=true to override."
            )
    
    # Delete all terms in this taxonomy
    db.aql.execute(f"""
        FOR t IN {TAXONOMY_TERMS_COLLECTION}
            FILTER t.scheme_id == @id
            REMOVE t IN {TAXONOMY_TERMS_COLLECTION}
    """, bind_vars={"id": taxonomy_id})
    
    # Delete the scheme
    db.collection(TAXONOMY_SCHEMES_COLLECTION).delete(taxonomy_id)
    
    _invalidate_taxonomy_cache()
    
    return {"success": True, "deleted": taxonomy_id}


# =====================================================
# TAXONOMY TERMS - CRUD
# =====================================================

@router.get("/taxonomies/{taxonomy_id}/terms", summary="List terms in a taxonomy")
async def list_taxonomy_terms(taxonomy_id: str):
    """List all terms in a taxonomy"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    if not db.collection(TAXONOMY_SCHEMES_COLLECTION).has(taxonomy_id):
        raise HTTPException(404, f"Taxonomy not found: {taxonomy_id}")
    
    cursor = db.aql.execute(f"""
        FOR t IN {TAXONOMY_TERMS_COLLECTION}
            FILTER t.scheme_id == @id
            SORT t.label ASC
            RETURN t
    """, bind_vars={"id": taxonomy_id})
    
    terms = list(cursor)
    
    return {"taxonomy_id": taxonomy_id, "terms": terms, "count": len(terms)}


@router.get("/taxonomies/{taxonomy_id}/terms/{term_uri:path}", summary="Get a single term")
async def get_taxonomy_term(taxonomy_id: str, term_uri: str):
    """Get a single term by URI"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    key = uri_to_key(term_uri)
    
    term = db.collection(TAXONOMY_TERMS_COLLECTION).get(key)
    if not term or term.get("scheme_id") != taxonomy_id:
        raise HTTPException(404, f"Term not found: {term_uri}")
    
    return term


@router.post("/taxonomies/{taxonomy_id}/terms", summary="Add a term to a taxonomy")
async def create_taxonomy_term(taxonomy_id: str, term: TermCreate):
    """Add a new term to a taxonomy"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    if not db.collection(TAXONOMY_SCHEMES_COLLECTION).has(taxonomy_id):
        raise HTTPException(404, f"Taxonomy not found: {taxonomy_id}")
    
    key = uri_to_key(term.uri)
    
    if db.collection(TAXONOMY_TERMS_COLLECTION).has(key):
        raise HTTPException(409, f"Term already exists: {term.uri}")
    
    # Validate broader term if specified
    if term.broader:
        broader_key = uri_to_key(term.broader)
        broader_term = db.collection(TAXONOMY_TERMS_COLLECTION).get(broader_key)
        if not broader_term or broader_term.get("scheme_id") != taxonomy_id:
            raise HTTPException(400, f"Broader term not found in this taxonomy: {term.broader}")
    
    doc = {
        "_key": key,
        "uri": term.uri,
        "scheme_id": taxonomy_id,
        "label": term.label,
        "definition": term.definition,
        "aliases": term.aliases,
        "broader": term.broader,
        "metadata": term.metadata,
        "created_at": get_timestamp(),
        "updated_at": get_timestamp()
    }
    
    result = db.collection(TAXONOMY_TERMS_COLLECTION).insert(doc)
    
    _invalidate_taxonomy_cache()
    
    return {
        "success": True,
        "uri": term.uri,
        "taxonomy_id": taxonomy_id,
        "_id": result["_id"]
    }


@router.post("/taxonomies/{taxonomy_id}/terms/bulk", summary="Bulk add terms to a taxonomy")
async def bulk_create_taxonomy_terms(taxonomy_id: str, bulk: BulkTermsCreate):
    """Bulk add multiple terms to a taxonomy"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    if not db.collection(TAXONOMY_SCHEMES_COLLECTION).has(taxonomy_id):
        raise HTTPException(404, f"Taxonomy not found: {taxonomy_id}")
    
    created = []
    errors = []
    
    for term in bulk.terms:
        key = uri_to_key(term.uri)
        
        if db.collection(TAXONOMY_TERMS_COLLECTION).has(key):
            errors.append({"uri": term.uri, "error": "Already exists"})
            continue
        
        # Validate broader term if specified
        if term.broader:
            broader_key = uri_to_key(term.broader)
            broader_term = db.collection(TAXONOMY_TERMS_COLLECTION).get(broader_key)
            if not broader_term:
                errors.append({"uri": term.uri, "error": f"Broader term not found: {term.broader}"})
                continue
        
        doc = {
            "_key": key,
            "uri": term.uri,
            "scheme_id": taxonomy_id,
            "label": term.label,
            "definition": term.definition,
            "aliases": term.aliases,
            "broader": term.broader,
            "metadata": term.metadata,
            "created_at": get_timestamp(),
            "updated_at": get_timestamp()
        }
        
        try:
            db.collection(TAXONOMY_TERMS_COLLECTION).insert(doc)
            created.append(term.uri)
        except Exception as e:
            errors.append({"uri": term.uri, "error": str(e)})
    
    _invalidate_taxonomy_cache()
    
    return {
        "success": len(errors) == 0,
        "created": created,
        "created_count": len(created),
        "errors": errors,
        "error_count": len(errors)
    }


@router.put("/taxonomies/{taxonomy_id}/terms/{term_uri:path}", summary="Update a term")
async def update_taxonomy_term(taxonomy_id: str, term_uri: str, updates: TermUpdate):
    """Update an existing term"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    key = uri_to_key(term_uri)
    
    term = db.collection(TAXONOMY_TERMS_COLLECTION).get(key)
    if not term or term.get("scheme_id") != taxonomy_id:
        raise HTTPException(404, f"Term not found: {term_uri}")
    
    update_doc = {"updated_at": get_timestamp()}
    
    if updates.label is not None:
        update_doc["label"] = updates.label
    if updates.definition is not None:
        update_doc["definition"] = updates.definition
    if updates.aliases is not None:
        update_doc["aliases"] = updates.aliases
    if updates.metadata is not None:
        update_doc["metadata"] = updates.metadata
    
    if updates.broader is not None:
        if updates.broader == "":
            update_doc["broader"] = None
        else:
            # Validate broader term exists
            broader_key = uri_to_key(updates.broader)
            broader_term = db.collection(TAXONOMY_TERMS_COLLECTION).get(broader_key)
            if not broader_term or broader_term.get("scheme_id") != taxonomy_id:
                raise HTTPException(400, f"Broader term not found: {updates.broader}")
            
            # Prevent circular hierarchy
            if updates.broader == term_uri:
                raise HTTPException(400, "Term cannot be its own broader term")
            
            update_doc["broader"] = updates.broader
    
    db.collection(TAXONOMY_TERMS_COLLECTION).update({**update_doc, "_key": key})
    
    _invalidate_taxonomy_cache()
    
    return {"success": True, "uri": term_uri}


@router.delete("/taxonomies/{taxonomy_id}/terms/{term_uri:path}", summary="Delete a term")
async def delete_taxonomy_term(taxonomy_id: str, term_uri: str, force: bool = False):
    """Delete a term from a taxonomy"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    key = uri_to_key(term_uri)
    
    term = db.collection(TAXONOMY_TERMS_COLLECTION).get(key)
    if not term or term.get("scheme_id") != taxonomy_id:
        raise HTTPException(404, f"Term not found: {term_uri}")
    
    # Check for narrower terms
    if not force:
        cursor = db.aql.execute(f"""
            FOR t IN {TAXONOMY_TERMS_COLLECTION}
                FILTER t.broader == @uri
                RETURN t.uri
        """, bind_vars={"uri": term_uri})
        narrower = list(cursor)
        
        if narrower:
            raise HTTPException(
                400,
                f"Cannot delete: term has {len(narrower)} narrower terms: {narrower[:5]}. Use force=true to override."
            )
    
    db.collection(TAXONOMY_TERMS_COLLECTION).delete(key)
    
    _invalidate_taxonomy_cache()
    
    return {"success": True, "deleted": term_uri}


# =====================================================
# RELATIONSHIP TYPES - CRUD
# =====================================================

@router.get("/relationships", summary="List all relationship types")
async def list_relationship_types():
    """List all relationship types"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    cursor = db.aql.execute(f"""
        FOR r IN {RELATIONSHIP_TYPES_COLLECTION}
            SORT r.label ASC
            RETURN r
    """)
    
    relationships = list(cursor)
    
    return {"relationships": relationships, "count": len(relationships)}


@router.get("/relationships/{uri:path}", summary="Get a relationship type")
async def get_relationship_type(uri: str):
    """Get a relationship type by URI"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    key = uri_to_key(uri)
    
    rel = db.collection(RELATIONSHIP_TYPES_COLLECTION).get(key)
    if not rel:
        raise HTTPException(404, f"Relationship type not found: {uri}")
    
    return rel


@router.post("/relationships", summary="Create a relationship type")
async def create_relationship_type(rel: RelationshipTypeCreate):
    """Create a new relationship type"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    key = uri_to_key(rel.uri)
    
    if db.collection(RELATIONSHIP_TYPES_COLLECTION).has(key):
        raise HTTPException(409, f"Relationship type already exists: {rel.uri}")
    
    # Validate domain concepts exist
    for concept_uri in rel.domain:
        if not concept_exists(concept_uri):
            raise HTTPException(400, f"Domain concept not found: {concept_uri}")
    
    # Validate range concepts exist
    for concept_uri in rel.range:
        if not concept_exists(concept_uri):
            raise HTTPException(400, f"Range concept not found: {concept_uri}")
    
    doc = {
        "_key": key,
        "uri": rel.uri,
        "label": rel.label,
        "definition": rel.definition,
        "domain": rel.domain,
        "range": rel.range,
        "inverse": rel.inverse,
        "symmetric": rel.symmetric,
        "transitive": rel.transitive,
        "created_at": get_timestamp(),
        "updated_at": get_timestamp()
    }
    
    result = db.collection(RELATIONSHIP_TYPES_COLLECTION).insert(doc)
    
    return {
        "success": True,
        "uri": rel.uri,
        "_id": result["_id"]
    }


@router.put("/relationships/{uri:path}", summary="Update a relationship type")
async def update_relationship_type(uri: str, updates: RelationshipTypeUpdate):
    """Update a relationship type"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    key = uri_to_key(uri)
    
    if not db.collection(RELATIONSHIP_TYPES_COLLECTION).has(key):
        raise HTTPException(404, f"Relationship type not found: {uri}")
    
    update_doc = {"updated_at": get_timestamp()}
    
    if updates.label is not None:
        update_doc["label"] = updates.label
    if updates.definition is not None:
        update_doc["definition"] = updates.definition
    if updates.inverse is not None:
        update_doc["inverse"] = updates.inverse
    if updates.symmetric is not None:
        update_doc["symmetric"] = updates.symmetric
    if updates.transitive is not None:
        update_doc["transitive"] = updates.transitive
    
    if updates.domain is not None:
        for concept_uri in updates.domain:
            if not concept_exists(concept_uri):
                raise HTTPException(400, f"Domain concept not found: {concept_uri}")
        update_doc["domain"] = updates.domain
    
    if updates.range is not None:
        for concept_uri in updates.range:
            if not concept_exists(concept_uri):
                raise HTTPException(400, f"Range concept not found: {concept_uri}")
        update_doc["range"] = updates.range
    
    db.collection(RELATIONSHIP_TYPES_COLLECTION).update({**update_doc, "_key": key})
    
    return {"success": True, "uri": uri}


@router.delete("/relationships/{uri:path}", summary="Delete a relationship type")
async def delete_relationship_type(uri: str):
    """Delete a relationship type"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    key = uri_to_key(uri)
    
    if not db.collection(RELATIONSHIP_TYPES_COLLECTION).has(key):
        raise HTTPException(404, f"Relationship type not found: {uri}")
    
    # TODO: Check if relationship type is used in any edges
    
    db.collection(RELATIONSHIP_TYPES_COLLECTION).delete(key)
    
    return {"success": True, "deleted": uri}


# =====================================================
# VALIDATION HELPERS (used by ingestion)
# =====================================================

@router.post("/validate", summary="Validate artifact data against ontology")
async def validate_artifact(data: Dict[str, Any], concept_label: str):
    """Validate artifact data against a concept's schema"""
    if not db:
        raise HTTPException(503, "Database not connected")
    
    # Find concept by label
    cursor = db.aql.execute(f"""
        FOR c IN {CONCEPTS_COLLECTION}
            FILTER c.label == @label
            RETURN c
    """, bind_vars={"label": concept_label})
    
    concepts = list(cursor)
    if not concepts:
        raise HTTPException(404, f"Concept not found: {concept_label}")
    
    concept = concepts[0]
    
    # Get all properties including inherited
    concept_with_props = await get_concept(concept["uri"], include_inherited_properties=True)
    all_properties = concept_with_props.get("all_properties", concept.get("properties", []))
    
    errors = []
    warnings = []
    normalized = {}
    
    # Check required properties
    for prop in all_properties:
        if prop.get("required") and prop["name"] not in data:
            errors.append({
                "field": prop["name"],
                "message": f"Required property '{prop['name']}' is missing"
            })
    
    # Validate and normalize taxonomy values
    for prop in all_properties:
        if prop["name"] not in data:
            continue
        
        value = data[prop["name"]]
        taxonomy_id = prop.get("taxonomy")
        
        if taxonomy_id:
            # Look up term by label or alias
            validation_result = _validate_taxonomy_value(taxonomy_id, value)
            
            if validation_result["valid"]:
                if validation_result["canonical"] != value:
                    warnings.append({
                        "field": prop["name"],
                        "message": f"Normalized '{value}' to '{validation_result['canonical']}'"
                    })
                normalized[prop["name"]] = validation_result["canonical"]
            else:
                valid_values = _get_taxonomy_values(taxonomy_id)[:10]
                errors.append({
                    "field": prop["name"],
                    "value": value,
                    "message": f"Invalid value '{value}'. Valid options: {valid_values}..."
                })
    
    return {
        "valid": len(errors) == 0,
        "concept_uri": concept["uri"],
        "concept_label": concept["label"],
        "errors": errors,
        "warnings": warnings,
        "normalized": normalized
    }


def _validate_taxonomy_value(taxonomy_id: str, value: str) -> Dict[str, Any]:
    """Validate a value against a taxonomy, checking label and aliases"""
    if not db:
        return {"valid": False, "canonical": None}
    
    value_lower = value.lower().strip()
    
    # Search for exact label match or alias match
    cursor = db.aql.execute(f"""
        FOR t IN {TAXONOMY_TERMS_COLLECTION}
            FILTER t.scheme_id == @taxonomy_id
            FILTER LOWER(t.label) == @value 
                OR @value IN (FOR a IN (t.aliases || []) RETURN LOWER(a))
            RETURN t
    """, bind_vars={"taxonomy_id": taxonomy_id, "value": value_lower})
    
    terms = list(cursor)
    
    if terms:
        return {"valid": True, "canonical": terms[0]["label"], "uri": terms[0]["uri"]}
    
    return {"valid": False, "canonical": None}


def _get_taxonomy_values(taxonomy_id: str) -> List[str]:
    """Get all valid labels for a taxonomy"""
    if not db:
        return []
    
    cursor = db.aql.execute(f"""
        FOR t IN {TAXONOMY_TERMS_COLLECTION}
            FILTER t.scheme_id == @taxonomy_id
            SORT t.label ASC
            RETURN t.label
    """, bind_vars={"taxonomy_id": taxonomy_id})
    
    return list(cursor)


# =====================================================
# CACHE MANAGEMENT
# =====================================================

_ontology_cache = None
_taxonomy_cache = None


def _invalidate_ontology_cache():
    """Invalidate cached ontology data"""
    global _ontology_cache
    _ontology_cache = None


def _invalidate_taxonomy_cache():
    """Invalidate cached taxonomy data"""
    global _taxonomy_cache
    _taxonomy_cache = None


def get_cached_ontology_manager():
    """
    Get a cached ontology manager-like interface for ingestion validation.
    This provides compatibility with the existing ingestion code.
    """
    global _ontology_cache
    
    if _ontology_cache is None and db:
        _ontology_cache = DatabaseOntologyManager(db)
    
    return _ontology_cache


def get_cached_taxonomy_registry():
    """
    Get a cached taxonomy registry-like interface for ingestion validation.
    This provides compatibility with the existing ingestion code.
    """
    global _taxonomy_cache
    
    if _taxonomy_cache is None and db:
        _taxonomy_cache = DatabaseTaxonomyRegistry(db)
    
    return _taxonomy_cache


# =====================================================
# COMPATIBILITY CLASSES (for ingestion integration)
# =====================================================

class DatabaseTaxonomyRegistry:
    """
    Provides the same interface as the JSON-based TaxonomyRegistry
    but reads from ArangoDB.
    """
    
    def __init__(self, database):
        self.db = database
    
    def validate(self, taxonomy_id: str, value: str):
        """Validate a value against a taxonomy"""
        result = _validate_taxonomy_value(taxonomy_id, value)
        if result["valid"]:
            return (True, result["canonical"], result.get("uri"))
        return (False, None, None)
    
    def get_valid_values(self, taxonomy_id: str) -> List[str]:
        """Get all valid labels for a taxonomy"""
        return _get_taxonomy_values(taxonomy_id)
    
    def resolve_to_canonical(self, taxonomy_id: str, value: str) -> str:
        """Resolve a value to its canonical label"""
        result = _validate_taxonomy_value(taxonomy_id, value)
        return result["canonical"] if result["valid"] else value


class DatabaseOntologyManager:
    """
    Provides the same interface as the JSON-based OntologyManager
    but reads from ArangoDB.
    """
    
    def __init__(self, database):
        self.db = database
        self.taxonomy_registry = DatabaseTaxonomyRegistry(database)
    
    def get_concept_by_label(self, label: str):
        """Get a concept by its label"""
        cursor = self.db.aql.execute(f"""
            FOR c IN {CONCEPTS_COLLECTION}
                FILTER c.label == @label
                RETURN c
        """, bind_vars={"label": label})
        
        concepts = list(cursor)
        return concepts[0] if concepts else None
    
    def get_concept_by_collection(self, collection_name: str):
        """Get a concept by its collection name"""
        cursor = self.db.aql.execute(f"""
            FOR c IN {CONCEPTS_COLLECTION}
                FILTER c.collection == @collection
                RETURN c
        """, bind_vars={"collection": collection_name})
        
        concepts = list(cursor)
        return concepts[0] if concepts else None
    
    def get_concrete_concepts(self) -> List[Dict]:
        """Get all non-abstract concepts"""
        cursor = self.db.aql.execute(f"""
            FOR c IN {CONCEPTS_COLLECTION}
                FILTER c.abstract != true
                SORT c.label ASC
                RETURN c
        """)
        return list(cursor)
    
    def get_all_properties(self, concept_uri: str) -> List[Dict]:
        """Get all properties for a concept including inherited"""
        key = uri_to_key(concept_uri)
        concept = self.db.collection(CONCEPTS_COLLECTION).get(key)
        
        if not concept:
            return []
        
        all_properties = list(concept.get("properties", []))
        own_property_names = {p["name"] for p in all_properties}
        
        # Walk up hierarchy
        current_parent = concept.get("parent_uri")
        while current_parent:
            parent_key = uri_to_key(current_parent)
            parent = self.db.collection(CONCEPTS_COLLECTION).get(parent_key)
            
            if parent:
                for prop in parent.get("properties", []):
                    if prop["name"] not in own_property_names:
                        inherited_prop = dict(prop)
                        inherited_prop["inherited_from"] = current_parent
                        all_properties.append(inherited_prop)
                        own_property_names.add(prop["name"])
                current_parent = parent.get("parent_uri")
            else:
                break
        
        return all_properties
    
    def validate_artifact(self, data: Dict[str, Any], concept_label_or_collection: str) -> Dict[str, Any]:
        """Validate artifact data against ontology schema"""
        # Find concept
        concept = self.get_concept_by_label(concept_label_or_collection)
        if not concept:
            concept = self.get_concept_by_collection(concept_label_or_collection)
        
        if not concept:
            return {
                "valid": False,
                "errors": [{"field": "_type", "message": f"Unknown type: {concept_label_or_collection}"}],
                "warnings": [],
                "normalized": {}
            }
        
        all_properties = self.get_all_properties(concept["uri"])
        
        errors = []
        warnings = []
        normalized = {}
        
        # Check required properties
        for prop in all_properties:
            if prop.get("required") and prop["name"] not in data:
                errors.append({
                    "field": prop["name"],
                    "message": f"Required property '{prop['name']}' is missing"
                })
        
        # Validate taxonomy values
        for prop in all_properties:
            if prop["name"] not in data:
                continue
            
            value = data[prop["name"]]
            taxonomy_id = prop.get("taxonomy")
            
            if taxonomy_id:
                is_valid, canonical, uri = self.taxonomy_registry.validate(taxonomy_id, str(value))
                
                if is_valid:
                    if canonical != value:
                        warnings.append({
                            "field": prop["name"],
                            "message": f"Normalized '{value}' to '{canonical}'"
                        })
                    normalized[prop["name"]] = canonical
                else:
                    valid_values = self.taxonomy_registry.get_valid_values(taxonomy_id)[:10]
                    errors.append({
                        "field": prop["name"],
                        "value": value,
                        "message": f"Invalid value '{value}'. Valid options: {valid_values}..."
                    })
        
        return {
            "valid": len(errors) == 0,
            "concept_uri": concept["uri"],
            "concept_label": concept["label"],
            "errors": errors,
            "warnings": warnings,
            "normalized": normalized
        }
    
    def generate_classification_prompt(self) -> str:
        """Generate prompt text listing all concrete concept types for LLM classification"""
        concepts = self.get_concrete_concepts()
        
        lines = ["Classify this artifact as ONE of these types:"]
        for concept in concepts:
            lines.append(f'- "{concept["label"]}" - {concept.get("definition", "")}')
        
        return "\n".join(lines)


# =====================================================
# HEALTH CHECK
# =====================================================

@router.get("/health", summary="Check ontology system health")
async def health_check():
    """Check ontology system health"""
    if not db:
        return {
            "status": "error",
            "message": "Database not connected",
            "collections_initialized": False
        }
    
    try:
        # Check collections exist
        collections_status = {}
        for coll in ALL_COLLECTIONS:
            collections_status[coll] = db.has_collection(coll)
        
        # Get counts
        counts = {}
        if all(collections_status.values()):
            counts["concepts"] = db.collection(CONCEPTS_COLLECTION).count()
            counts["taxonomies"] = db.collection(TAXONOMY_SCHEMES_COLLECTION).count()
            counts["terms"] = db.collection(TAXONOMY_TERMS_COLLECTION).count()
            counts["relationship_types"] = db.collection(RELATIONSHIP_TYPES_COLLECTION).count()
        
        return {
            "status": "healthy",
            "collections_initialized": all(collections_status.values()),
            "collections": collections_status,
            "counts": counts
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "collections_initialized": False
        }
