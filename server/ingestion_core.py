"""
Ingestion Core - GraphDB Native
================================
Triplestore-native ingestion service for ProtoGraph ATLAS.

Replaces: ingestion_endpoint.py (ArangoDB version)
Requires: graph_db.py adapter with GraphDB connection

Architecture:
  Tier 1: RDF triples in GraphDB (metadata, relationships, classification)
  Tier 2: JSON payload files on disk (operational detail - inputs/outputs/params)

Core Flow (no LLM required):
  1. POST /api/ingest/commit  { type, attributes }
  2. Map type → OWL class, resolve taxonomy fields → SKOS URIs
  3. SPARQL INSERT DATA → GraphDB (SHACL validates on commit)
  4. Save full payload to ./data/payloads/{key}.json

Optional LLM Flow:
  1. POST /api/ingest/analyze  { raw_data }
  2. LLM classifies against ontology types → returns suggested type + attributes
  3. User reviews/edits → calls /commit
"""

import os
import re
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel


# ============================================================================
# CONFIG
# ============================================================================

PAYLOAD_STORAGE_DIR = os.getenv("PAYLOAD_STORAGE_DIR", "./data/payloads")

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])

# GraphDB adapter — injected via init_ingestion_core()
gdb = None
rules_engine = None


# ============================================================================
# MODELS
# ============================================================================

class CommitRequest(BaseModel):
    """Commit a new artifact to the graph."""
    type: str                          # OWL class label, e.g. "Library Module"
    attributes: Dict[str, Any]         # Field values
    key: Optional[str] = None          # Explicit _key (auto-generated if omitted)
    save_payload: bool = True          # Save full JSON to disk
    skip_validation: bool = False      # If true, catch SHACL errors but don't block


class CommitResponse(BaseModel):
    success: bool
    artifact_type: str
    collection: str
    document_id: str
    document_key: str
    payload_url: Optional[str] = None
    payload_saved: bool = False
    shacl_error: Optional[str] = None
    edges_created: List[Dict[str, Any]] = []
    edge_count: int = 0


class ValidateRequest(BaseModel):
    type: str
    attributes: Dict[str, Any]


class ValidateResponse(BaseModel):
    valid: bool
    errors: List[Dict[str, str]] = []
    normalizations: List[Dict[str, str]] = []
    normalized_attributes: Dict[str, Any] = {}


# ============================================================================
# INITIALIZATION
# ============================================================================

def init_ingestion_core(graphdb_adapter):
    """
    Initialize with a GraphDBAdapter instance.

    Call from main.py:
        from ingestion_core import init_ingestion_core, router as ingest_router
        init_ingestion_core(gdb)
        app.include_router(ingest_router)
    """
    global gdb, rules_engine
    gdb = graphdb_adapter

    # Initialize rules engine
    from relationship_rules import RelationshipRulesEngine
    rules_engine = RelationshipRulesEngine(gdb)

    Path(PAYLOAD_STORAGE_DIR).mkdir(parents=True, exist_ok=True)

    types = gdb.get_ontology_types()
    type_labels = [t["label"] for t in types]
    print(f"✓ Ingestion core initialized — {len(types)} types: {', '.join(type_labels)}")
    print(f"✓ Relationship rules engine loaded")
    print(f"✓ Payload storage: {PAYLOAD_STORAGE_DIR}")


def _require_gdb():
    if gdb is None:
        raise HTTPException(status_code=503, detail="Ingestion not initialized (GraphDB not connected)")


# ============================================================================
# TAXONOMY RESOLUTION
# ============================================================================

# Map of property names → SKOS scheme IDs
TAXONOMY_FIELDS = {
    "category": "c2-frameworks",
    "riskLevel": "risk-levels",
    "owner": "teams",
    "team": "teams",
}


def resolve_taxonomies(
    attributes: Dict[str, Any],
    type_properties: List[Dict[str, Any]],
) -> tuple[Dict[str, Any], List[Dict[str, str]], List[Dict[str, str]]]:
    """
    For each taxonomy-backed field, resolve the plain string to a SKOS URI.

    Returns:
        (resolved_attrs, normalizations, errors)
    """
    resolved = attributes.copy()
    normalizations = []
    errors = []

    for prop in type_properties:
        scheme_id = prop.get("taxonomy")
        field = prop["name"]
        if not scheme_id or field not in resolved:
            continue

        value = resolved[field]
        if not value or (isinstance(value, str) and not value.strip()):
            continue

        match = gdb.resolve_taxonomy_value(scheme_id, str(value))
        if match:
            # Store the URI — the adapter's create_node handles URI→triple mapping
            resolved[field] = match["label"]  # Keep canonical label for the node
            if match["label"] != str(value):
                normalizations.append({
                    "field": field,
                    "original": str(value),
                    "normalized": match["label"],
                })
        else:
            # Not found in taxonomy
            terms = gdb.get_taxonomy_terms(scheme_id)
            valid = [t["label"] for t in terms[:6]]
            errors.append({
                "field": field,
                "message": f"'{value}' not in {scheme_id} taxonomy. Valid: {', '.join(valid)}",
            })

    return resolved, normalizations, errors


# ============================================================================
# KEY GENERATION
# ============================================================================

def generate_key(type_label: str, attributes: Dict[str, Any], explicit_key: Optional[str] = None) -> str:
    """Generate a safe _key for the artifact."""
    if explicit_key:
        return _sanitize_key(explicit_key)

    # Try common ID fields
    for field in ["_key", "id", "key", "name"]:
        val = attributes.get(field)
        if val and isinstance(val, str) and val.strip():
            return _sanitize_key(val)

    # Fallback: type + timestamp
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return _sanitize_key(f"{type_label}_{ts}")


def _sanitize_key(raw: str) -> str:
    """Make a string safe for use as an RDF local name / ArangoDB key."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", raw.strip().lower()).strip("-")


# ============================================================================
# REFERENCE PROPERTY → EDGE CREATION
# ============================================================================

# Map: property name → relationship type in the rel: namespace
# This connects the concept reference properties to the relationship edge types
REFERENCE_TO_RELATIONSHIP = {
    "mapsToTechnique": "MAPS_TO_TECHNIQUE",
    "supportsTechnique": "SUPPORTS_TECHNIQUE",
    "requiresTechnique": "REQUIRES_TECHNIQUE",
    "requiresModule": "REQUIRES_MODULE",
    "targetEnvironment": "TARGET_ENVIRONMENT",
    "owner": "OWNED_BY",
}

# Map: property name → target collection (for resolving node keys)
REFERENCE_TARGET_COLLECTION = {
    "mapsToTechnique": "TTP",
    "supportsTechnique": "TTP",
    "requiresTechnique": "TTP",
    "requiresModule": "LibraryModule",
    "targetEnvironment": "RangeEnvironment",
    "owner": "Team",
}


def _create_reference_edges(
    source_key: str,
    source_collection: str,
    attributes: Dict[str, Any],
    type_properties: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    For each reference property with a value, find the target node and create an edge.
    
    Handles both single values and arrays (multiple=True).
    Values can be: node key, node name, or full URI.
    """
    edges = []
    
    for prop in type_properties:
        if prop.get("type") != "reference":
            continue
        
        field = prop["name"]
        rel_type = REFERENCE_TO_RELATIONSHIP.get(field)
        target_collection = REFERENCE_TARGET_COLLECTION.get(field)
        
        if not rel_type or not target_collection:
            continue
        
        value = attributes.get(field)
        if not value:
            continue
        
        # Handle both single values and arrays
        values = value if isinstance(value, list) else [value]
        
        for val in values:
            if not val or (isinstance(val, str) and not val.strip()):
                continue
            
            val = str(val).strip()
            
            # Try to resolve the value to a node key
            target_key = _resolve_reference_target(val, target_collection)
            
            if target_key:
                try:
                    from_coll = source_collection
                    from_key = source_key
                    to_coll = target_collection
                    to_key = target_key
                    
                    result = gdb.create_edge(from_coll, from_key, to_coll, to_key, rel_type)
                    
                    edge_info = {
                        "success": True,
                        "_id": result["_id"],
                        "_from": f"{from_coll}/{from_key}",
                        "_to": f"{to_coll}/{to_key}",
                        "relationship_type": rel_type,
                        "source": "reference_property",
                        "property": field,
                    }
                    edges.append(edge_info)
                    print(f"  🔗 Edge: {from_coll}/{from_key} --{rel_type}--> {to_coll}/{to_key}")
                    
                except Exception as e:
                    print(f"  ⚠️ Edge creation failed for {field}={val}: {e}")
            else:
                print(f"  ⚠️ Could not resolve {field}='{val}' to a {target_collection} node")
    
    return edges


def _resolve_reference_target(value: str, target_collection: str) -> Optional[str]:
    """
    Resolve a reference value to a node key in the target collection.
    
    Tries:
    1. Sanitized key (convert name to key format — most common case)
    2. Exact key match (if value looks like a key already — no spaces)
    3. Name lookup via SPARQL
    """
    # 1. Strip URI prefix if present
    if value.startswith("https://proto.atlas/data/"):
        value = value.replace("https://proto.atlas/data/", "")
    
    # 2. Try sanitized key first (e.g. "Service Execution" → "service-execution")
    sanitized = _sanitize_key(value)
    if sanitized and gdb.has_artifact(sanitized):
        print(f"  ✓ Resolved '{value}' → key '{sanitized}'")
        return sanitized
    
    # 3. Try exact key match only if value looks like a key (no spaces)
    if " " not in value:
        try:
            if gdb.has_artifact(value):
                print(f"  ✓ Resolved '{value}' → exact key '{value}'")
                return value
        except Exception:
            pass
    
    # 4. Try name lookup via SPARQL — search for nodes with matching name
    try:
        escaped_value = value.replace('"', '\\"')
        rows = gdb.sparql_query(f"""
            SELECT ?key WHERE {{
                ?node proto:name "{escaped_value}" .
                FILTER(STRSTARTS(STR(?node), "https://proto.atlas/data/"))
                BIND(STRAFTER(STR(?node), "https://proto.atlas/data/") AS ?key)
            }}
            LIMIT 1
        """)
        if rows and rows[0].get("key"):
            resolved_key = rows[0]["key"]
            print(f"  ✓ Resolved '{value}' → SPARQL lookup '{resolved_key}'")
            return resolved_key
    except Exception as e:
        print(f"  ⚠️ SPARQL name lookup failed for '{value}': {e}")
    
    return None


# ============================================================================
# PAYLOAD STORAGE
# ============================================================================

def save_payload(key: str, full_data: Dict[str, Any]) -> str:
    """Save full payload to disk. Returns URL path."""
    Path(PAYLOAD_STORAGE_DIR).mkdir(parents=True, exist_ok=True)

    filename = f"{key}.json"
    filepath = Path(PAYLOAD_STORAGE_DIR) / filename

    payload = {
        "_payload_version": "2.0",
        "_saved_at": datetime.now(timezone.utc).isoformat(),
        "_artifact_key": key,
        **full_data,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    print(f"  📄 Payload saved: {filepath}")
    return f"/api/ingest/payloads/{filename}"


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/types")
async def get_artifact_types():
    """
    Get all concrete artifact types from the OWL ontology.
    Each type includes its schema properties with taxonomy info.
    """
    _require_gdb()
    types = gdb.get_ontology_types()
    return {"success": True, "types": types, "count": len(types)}


@router.get("/types/{type_label}/schema")
async def get_type_schema(type_label: str):
    """Get the full property schema for a specific artifact type."""
    _require_gdb()
    types = gdb.get_ontology_types()

    for t in types:
        if t["label"].lower() == type_label.lower():
            return {
                "success": True,
                "type": t["label"],
                "collection": t["collection"],
                "definition": t.get("definition", ""),
                "properties": t["properties"],
            }

    raise HTTPException(status_code=404, detail=f"Unknown type: {type_label}")


@router.get("/taxonomies/{scheme_id}")
async def get_taxonomy_values(scheme_id: str):
    """Get all valid values for a taxonomy scheme."""
    _require_gdb()
    terms = gdb.get_taxonomy_terms(scheme_id)
    return {
        "success": True,
        "scheme": scheme_id,
        "terms": terms,
        "count": len(terms),
    }


@router.post("/validate", response_model=ValidateResponse)
async def validate_attributes(request: ValidateRequest):
    """
    Validate and normalize attributes against the ontology.
    Does NOT write anything — use /commit to persist.
    """
    _require_gdb()

    types = gdb.get_ontology_types()
    type_info = next((t for t in types if t["label"].lower() == request.type.lower()), None)

    if not type_info:
        return ValidateResponse(
            valid=False,
            errors=[{"field": "_type", "message": f"Unknown type: {request.type}"}],
        )

    props = type_info.get("properties", [])

    # Check required fields
    errors = []
    for prop in props:
        if prop.get("required"):
            val = request.attributes.get(prop["name"])
            if val is None or (isinstance(val, str) and not val.strip()):
                errors.append({
                    "field": prop["name"],
                    "message": f"Required field '{prop['name']}' is missing",
                })

    # Resolve taxonomies
    resolved, normalizations, tax_errors = resolve_taxonomies(request.attributes, props)
    errors.extend(tax_errors)

    return ValidateResponse(
        valid=len(errors) == 0,
        errors=errors,
        normalizations=normalizations,
        normalized_attributes=resolved,
    )


@router.post("/commit", response_model=CommitResponse)
async def commit_artifact(request: CommitRequest):
    """
    Commit an artifact to GraphDB.

    1. Resolve type → OWL class
    2. Resolve taxonomy fields → canonical labels
    3. Generate _key
    4. SPARQL INSERT DATA (SHACL validates)
    5. Save full payload to disk
    """
    _require_gdb()

    # Look up the OWL class
    types = gdb.get_ontology_types()
    type_info = next((t for t in types if t["label"].lower() == request.type.lower()), None)

    if not type_info:
        available = [t["label"] for t in types]
        raise HTTPException(
            status_code=400,
            detail=f"Unknown type '{request.type}'. Available: {', '.join(available)}",
        )

    collection = type_info["collection"]
    props = type_info.get("properties", [])

    # Validate & resolve taxonomies
    resolved, normalizations, errors = resolve_taxonomies(request.attributes, props)

    # Check required fields
    for prop in props:
        if prop.get("required"):
            val = resolved.get(prop["name"])
            if val is None or (isinstance(val, str) and not val.strip()):
                errors.append({
                    "field": prop["name"],
                    "message": f"Required field '{prop['name']}' is missing",
                })

    if errors and not request.skip_validation:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validation failed",
                "errors": errors,
                "normalizations": normalizations,
            },
        )

    # Generate key
    key = generate_key(request.type, resolved, request.key)

    # Save payload to disk FIRST (before graph insert, so we don't lose data)
    payload_url = None
    if request.save_payload:
        payload_url = save_payload(key, {
            "_artifact_type": type_info["label"],
            **resolved,
        })

    # Build properties dict for create_node
    # Map taxonomy fields to their SKOS concept URIs for triple storage
    node_props = {}
    for field, value in resolved.items():
        if field.startswith("_") or field in ("id", "key"):
            continue
        node_props[field] = value

    # Insert into GraphDB via SPARQL
    shacl_error = None
    try:
        result = gdb.create_node(key, collection, node_props)
        doc_id = result["_id"]
        print(f"✅ Ingested: {doc_id}")
    except Exception as e:
        error_str = str(e)
        if "SHACL" in error_str or "ValidationException" in error_str:
            shacl_error = error_str
            if not request.skip_validation:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "SHACL validation failed",
                        "shacl_error": error_str,
                    },
                )
            doc_id = f"{collection}/{key}"
            print(f"⚠️ SHACL error (skipped): {error_str[:200]}")
        else:
            raise HTTPException(status_code=500, detail=f"GraphDB insert failed: {error_str}")

    # === POST-COMMIT: Create edges from reference properties ===
    edges_created = []
    if not shacl_error:
        try:
            ref_edges = _create_reference_edges(key, collection, resolved, props)
            edges_created.extend(ref_edges)
        except Exception as e:
            import traceback
            print(f"⚠️ Reference edge creation error (non-fatal): {e}")
            traceback.print_exc()

    # === POST-COMMIT: Run relationship rules ===
    if rules_engine and not shacl_error:
        try:
            rule_edges = rules_engine.run_rules_for(key, collection, resolved)
            edges_created.extend(rule_edges)
        except Exception as e:
            print(f"⚠️ Rules engine error (non-fatal): {e}")

    return CommitResponse(
        success=True,
        artifact_type=type_info["label"],
        collection=collection,
        document_id=doc_id,
        document_key=key,
        payload_url=payload_url,
        payload_saved=payload_url is not None,
        shacl_error=shacl_error,
        edges_created=edges_created,
        edge_count=len(edges_created),
    )


# ============================================================================
# PAYLOAD SERVING
# ============================================================================

@router.get("/payloads/{filename}")
async def get_payload(filename: str):
    """Serve a payload file."""
    safe = Path(filename).name
    if safe != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = Path(PAYLOAD_STORAGE_DIR) / safe
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Payload not found: {filename}")

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return JSONResponse(content=data)


@router.get("/payloads")
async def list_payloads(prefix: Optional[str] = None, limit: int = 100):
    """List payload files on disk."""
    pdir = Path(PAYLOAD_STORAGE_DIR)
    if not pdir.exists():
        return {"payloads": [], "count": 0}

    files = []
    for fp in pdir.glob("*.json"):
        if prefix and not fp.stem.startswith(prefix):
            continue
        stat = fp.stat()
        files.append({
            "filename": fp.name,
            "url": f"/api/ingest/payloads/{fp.name}",
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
        if len(files) >= limit:
            break

    files.sort(key=lambda x: x["modified_at"], reverse=True)
    return {"payloads": files, "count": len(files)}


@router.delete("/payloads/{filename}")
async def delete_payload(filename: str):
    """Delete a payload file."""
    safe = Path(filename).name
    if safe != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = Path(PAYLOAD_STORAGE_DIR) / safe
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Payload not found: {filename}")

    filepath.unlink()
    return {"success": True, "deleted": filename}


# ============================================================================
# DEBUG
# ============================================================================

@router.get("/debug")
async def debug_ingestion():
    """Check ingestion service state."""
    _require_gdb()

    types = gdb.get_ontology_types()
    pdir = Path(PAYLOAD_STORAGE_DIR)
    payload_count = len(list(pdir.glob("*.json"))) if pdir.exists() else 0

    health = gdb.health()

    return {
        "graphdb_connected": health.get("status") == "connected",
        "graphdb_triples": health.get("total_triples", 0),
        "available_types": [t["label"] for t in types],
        "type_count": len(types),
        "payload_storage": str(pdir),
        "payload_count": payload_count,
        "taxonomy_schemes": ["c2-frameworks", "risk-levels", "teams", "mitre-tactics"],
    }