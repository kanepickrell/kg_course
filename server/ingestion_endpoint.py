#!/usr/bin/env python3
"""
Ingestion API v2 - Lightweight Metadata + Heavy Payload Architecture

This module handles data ingestion with a two-tier storage strategy:
- Tier 1: ArangoDB document (lightweight metadata for graph/search)
- Tier 2: Payload file (full data for operational use)

Flow:
1. User submits raw data (JSON/text)
2. LLM classifies against ontology_concepts (concrete types only)
3. Extract metadata fields → save to ArangoDB
4. Save full payload → write to ./data/payloads/{_key}.json
5. Set payload_url field pointing to that file
"""

import os
import json
import re
import httpx
from datetime import datetime
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from pathlib import Path

# Get configuration from environment
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://10.10.80.99:4001")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:120b")
PAYLOAD_STORAGE_DIR = os.getenv("PAYLOAD_STORAGE_DIR", "./data/payloads")

print(f"🔧 Ingestion v2 using OLLAMA_HOST: {OLLAMA_HOST}")
print(f"🔧 Ingestion v2 using OLLAMA_MODEL: {OLLAMA_MODEL}")
print(f"🔧 Ingestion v2 using PAYLOAD_STORAGE_DIR: {PAYLOAD_STORAGE_DIR}")

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])

# These get initialized by init_ingestion()
db = None
ontology_manager = None
taxonomy_registry = None


# ============================================================================
# METADATA EXTRACTION CONFIGURATION
# ============================================================================

# Fields to extract for lightweight ArangoDB documents
# Everything else goes to the payload file
METADATA_FIELDS = {
    # Universal fields (all artifact types)
    "universal": [
        "_key", "id", "name", "label", "title",
        "description", "icon", "status", "owner",
        "tags", "category", "subcategory",
        "created_at", "updated_at",
    ],
    
    # LibraryModule specific - includes fields needed by Operator
    "Library Module": [
        "tactic", "mitre", "riskLevel", "executionType",
        "estimatedDuration", "collaboration_with",
        "cobaltStrikeCommand", "shellCommand",
        "requirements", "metadata",
        # CRITICAL: These are needed for Operator canvas and Script View
        "inputs",
        "outputs",
        "parameters",
        "robotFramework",
    ],
    
    # Process/Workflow specific
    "Process": [
        "process_type", "team", "priority",
    ],
    
    # TTP specific
    "TTP": [
        "mitre_id", "technique_id", "tactic",
    ],
    
    # Default fallback
    "default": [
        "type", "cluster", "importance", "scenario_id",
    ]
}


# ============================================================================
# MODELS
# ============================================================================

class IngestionRequest(BaseModel):
    """Request to analyze and ingest data"""
    raw_data: str  # JSON string or structured text
    source_hint: Optional[str] = None
    artifact_type: Optional[str] = None  # Optional: skip LLM classification
    collection: Optional[str] = None  # Optional: explicit collection target


class ValidationErrorItem(BaseModel):
    field: str
    message: str


class NormalizationItem(BaseModel):
    field: str
    original: str
    normalized: str


class ClassificationResult(BaseModel):
    """Result of LLM classification"""
    artifact_type: str
    confidence: float
    reasoning: str
    extracted_attributes: Dict[str, Any]
    validation_errors: List[ValidationErrorItem] = []
    normalizations: List[NormalizationItem] = []
    match_found: bool = True
    suggested_action: Optional[str] = None
    schema_properties: List[Dict[str, Any]] = []
    # New fields for payload architecture
    metadata_preview: Dict[str, Any] = {}
    payload_fields: List[str] = []


class CommitRequest(BaseModel):
    """Request to commit classified data"""
    artifact_type: str
    attributes: Dict[str, Any]
    skip_validation: bool = False
    save_payload: bool = True  # New: whether to save full payload


class CommitResponse(BaseModel):
    """Response from commit operation"""
    success: bool
    artifact_type: str
    collection: str
    document_id: str
    document_key: str
    payload_url: Optional[str] = None
    payload_saved: bool = False


class ValidateRequest(BaseModel):
    artifact_type: str
    attributes: Dict[str, Any]


class ValidateResponse(BaseModel):
    valid: bool
    validation_errors: List[ValidationErrorItem] = []
    normalizations: List[NormalizationItem] = []
    normalized_attributes: Dict[str, Any] = {}


# ============================================================================
# INITIALIZATION
# ============================================================================

def init_ingestion(arango_db):
    """Initialize ingestion with ArangoDB connection and ontology"""
    global db, ontology_manager, taxonomy_registry
    db = arango_db
    
    # Import here to avoid circular imports
    from ontology_bridge import OntologyManager, TaxonomyRegistry
    
    ontology_manager = OntologyManager(db)
    taxonomy_registry = TaxonomyRegistry(db)
    
    # Ensure payload directory exists
    Path(PAYLOAD_STORAGE_DIR).mkdir(parents=True, exist_ok=True)
    
    concepts = ontology_manager.get_concrete_concepts()
    print(f"✓ Ingestion v2 initialized with {len(concepts)} artifact types")
    print(f"✓ Payload storage: {PAYLOAD_STORAGE_DIR}")


# ============================================================================
# METADATA/PAYLOAD SEPARATION
# ============================================================================

def extract_metadata(full_data: Dict[str, Any], artifact_type: str) -> Dict[str, Any]:
    """
    Extract lightweight metadata fields from full data.
    
    Returns only the fields needed for graph visualization and search.
    """
    metadata = {}
    
    # Get fields to extract for this type
    fields_to_extract = set(METADATA_FIELDS["universal"])
    fields_to_extract.update(METADATA_FIELDS.get(artifact_type, []))
    fields_to_extract.update(METADATA_FIELDS["default"])
    
    for field in fields_to_extract:
        if field in full_data:
            value = full_data[field]
            # Only include non-empty values
            if value is not None and value != "" and value != []:
                metadata[field] = value
    
    return metadata


def save_payload(artifact_key: str, full_data: Dict[str, Any]) -> str:
    """
    Save full payload to file and return the URL.
    
    Args:
        artifact_key: The _key of the artifact (used as filename)
        full_data: Complete data structure to save
        
    Returns:
        URL path to the saved payload
    """
    # Ensure directory exists
    Path(PAYLOAD_STORAGE_DIR).mkdir(parents=True, exist_ok=True)
    
    # Build filename
    safe_key = artifact_key.replace("/", "_").replace("\\", "_")
    filename = f"{safe_key}.json"
    filepath = Path(PAYLOAD_STORAGE_DIR) / filename
    
    # Add ingestion metadata
    payload_with_meta = {
        "_payload_version": "2.0",
        "_saved_at": datetime.utcnow().isoformat(),
        "_artifact_key": artifact_key,
        **full_data
    }
    
    # Write to file
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(payload_with_meta, f, indent=2, default=str)
    
    print(f"✓ Saved payload: {filepath}")
    
    # Return URL path (relative to API)
    return f"/api/ingest/payloads/{filename}"


def get_payload_fields(full_data: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
    """Get list of fields that will be stored in payload but not metadata."""
    all_fields = set(full_data.keys())
    metadata_fields = set(metadata.keys())
    return sorted(all_fields - metadata_fields)


# ============================================================================
# ONTOLOGY HELPERS
# ============================================================================

def get_available_types() -> List[Dict[str, Any]]:
    """Get all concrete (instantiable) artifact types from ontology"""
    if not ontology_manager:
        return []
    
    concepts = ontology_manager.get_concrete_concepts()
    result = []
    for c in concepts:
        props = ontology_manager.get_all_properties(c.get("label"))
        result.append({
            "label": c.get("label"),
            "definition": c.get("definition"),
            "collection": c.get("collection"),
            "properties": props
        })
    return result


def get_schema_for_type(type_label: str) -> List[Dict[str, Any]]:
    """Get the schema properties for a specific artifact type"""
    types = get_available_types()
    for t in types:
        if t["label"] == type_label:
            return t.get("properties", [])
    return []


def build_taxonomy_constraint(taxonomy_name: str, max_values: int = 8) -> str:
    """Build a constraint string showing valid values for a taxonomy"""
    if not taxonomy_registry:
        return ""
    
    values = taxonomy_registry.get_valid_values(taxonomy_name)
    if not values:
        return ""
    
    if len(values) <= max_values:
        return f"Valid values: {', '.join(values)}"
    else:
        sample = values[:max_values]
        return f"Valid values include: {', '.join(sample)} (and {len(values) - max_values} more)"


def validate_and_normalize_attributes(
    artifact_type: str,
    attributes: Dict[str, Any]
) -> tuple[List[ValidationErrorItem], List[NormalizationItem], Dict[str, Any]]:
    """Validate attributes against schema and normalize taxonomy values."""
    errors: List[ValidationErrorItem] = []
    normalizations: List[NormalizationItem] = []
    normalized_attrs = attributes.copy()
    
    available_types = get_available_types()
    type_info = None
    for t in available_types:
        if t["label"] == artifact_type:
            type_info = t
            break
    
    if not type_info:
        errors.append(ValidationErrorItem(
            field="_type",
            message=f"Unknown artifact type: {artifact_type}"
        ))
        return errors, normalizations, normalized_attrs
    
    schema_props = type_info.get("properties", [])
    
    # Check required fields
    for prop in schema_props:
        if prop.get("required"):
            prop_name = prop.get("name")
            value = normalized_attrs.get(prop_name)
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(ValidationErrorItem(
                    field=prop_name,
                    message=f"Required field '{prop_name}' is missing"
                ))
    
    # Validate taxonomy fields
    if taxonomy_registry:
        for prop in schema_props:
            tax_id = prop.get("taxonomy")
            prop_name = prop.get("name")
            if tax_id and prop_name in normalized_attrs:
                value = normalized_attrs[prop_name]
                
                if value is None or (isinstance(value, str) and not value.strip()):
                    continue
                
                is_valid, canonical, uri = taxonomy_registry.validate(tax_id, str(value))
                
                if not is_valid:
                    extracted_id = extract_mitre_id(str(value))
                    if extracted_id:
                        is_valid, canonical, uri = taxonomy_registry.validate(tax_id, extracted_id)
                
                if is_valid:
                    if canonical and canonical != value:
                        normalizations.append(NormalizationItem(
                            field=prop_name,
                            original=str(value),
                            normalized=canonical
                        ))
                        normalized_attrs[prop_name] = canonical
                else:
                    valid_values = taxonomy_registry.get_valid_values(tax_id)
                    if valid_values:
                        sample = valid_values[:5]
                        more = f" (and {len(valid_values) - 5} more)" if len(valid_values) > 5 else ""
                        suggestion = f"Valid options include: {', '.join(sample)}{more}"
                    else:
                        suggestion = f"No valid values found in taxonomy '{tax_id}'"
                    
                    errors.append(ValidationErrorItem(
                        field=prop_name,
                        message=f"Invalid value '{value}'. {suggestion}"
                    ))
    
    return errors, normalizations, normalized_attrs


def extract_mitre_id(value: str) -> Optional[str]:
    """Extract MITRE ATT&CK IDs from a string."""
    tactic_match = re.search(r'(TA\d{4})', value, re.IGNORECASE)
    if tactic_match:
        return tactic_match.group(1).upper()
    
    technique_match = re.search(r'(T\d{4}(?:\.\d{3})?)', value, re.IGNORECASE)
    if technique_match:
        return technique_match.group(1).upper()
    
    return None


# ============================================================================
# LLM CLASSIFICATION
# ============================================================================

async def classify_with_llm(data: str, source_hint: Optional[str] = None) -> ClassificationResult:
    """Use LLM to classify data against ontology-defined types"""
    
    available_types = get_available_types()
    if not available_types:
        return ClassificationResult(
            artifact_type="Unknown",
            confidence=0.0,
            reasoning="No artifact types defined in ontology",
            extracted_attributes={},
            match_found=False,
            suggested_action="Define artifact types in Ontology Manager first"
        )
    
    type_descriptions = "\n".join([
        f"- {t['label']}: {t['definition']}"
        for t in available_types
    ])
    
    prompt = f"""You are a data classifier for ProtoGraph, a knowledge graph system.
Analyze the following data and classify it into ONE of these artifact types:

AVAILABLE TYPES:
{type_descriptions}

DATA TO CLASSIFY:
{data}

{f"Source hint: {source_hint}" if source_hint else ""}

INSTRUCTIONS:
1. Choose the artifact type that best matches the data
2. Extract key identification fields (id, name, category, tactic, etc.)
3. Generate a unique 'id' if one is not provided

Respond with ONLY valid JSON:
{{
    "artifact_type": "<exact type label>",
    "confidence": <0.0-1.0>,
    "reasoning": "<brief explanation>",
    "extracted_attributes": {{
        "id": "<unique identifier>",
        <other key-value pairs>
    }}
}}"""

    # Try Ollama endpoints
    ollama_endpoints = [
        f"{OLLAMA_HOST}/api/chat",
        f"{OLLAMA_HOST}/api/generate",
        f"{OLLAMA_HOST}/v1/chat/completions",
    ]
    
    last_error = None
    for endpoint in ollama_endpoints:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                if "chat" in endpoint and "v1" not in endpoint:
                    response = await client.post(
                        endpoint,
                        json={
                            "model": OLLAMA_MODEL,
                            "messages": [{"role": "user", "content": prompt}],
                            "stream": False,
                            "format": "json"
                        }
                    )
                elif "v1" in endpoint:
                    response = await client.post(
                        endpoint,
                        json={
                            "model": OLLAMA_MODEL,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.3
                        }
                    )
                else:
                    response = await client.post(
                        endpoint,
                        json={
                            "model": OLLAMA_MODEL,
                            "prompt": prompt,
                            "stream": False,
                            "format": "json"
                        }
                    )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    if "message" in result:
                        text = result["message"].get("content", "")
                    elif "choices" in result:
                        text = result["choices"][0]["message"]["content"]
                    elif "response" in result:
                        text = result["response"]
                    else:
                        text = str(result)
                    
                    try:
                        text = text.strip()
                        if text.startswith("```"):
                            text = text.split("```")[1]
                            if text.startswith("json"):
                                text = text[4:]
                        
                        parsed = json.loads(text)
                        return await process_llm_result(parsed)
                    except json.JSONDecodeError as e:
                        last_error = f"LLM returned invalid JSON: {str(e)}"
                        continue
                else:
                    last_error = f"Ollama returned status {response.status_code}"
                    
        except Exception as e:
            last_error = f"{type(e).__name__}: {str(e)}"
    
    type_list = [t["label"] for t in available_types]
    return ClassificationResult(
        artifact_type="Unknown",
        confidence=0.0,
        reasoning=f"LLM classification service unavailable: {last_error}",
        extracted_attributes={},
        match_found=False,
        suggested_action=f"Select artifact type manually from: {', '.join(type_list)}"
    )


async def process_llm_result(parsed: Dict[str, Any]) -> ClassificationResult:
    """Process and validate LLM classification result"""
    artifact_type = parsed.get("artifact_type", "Unknown")
    extracted = parsed.get("extracted_attributes", {})
    
    available_types = get_available_types()
    type_info = None
    for t in available_types:
        if t["label"] == artifact_type:
            type_info = t
            break
    
    if not type_info:
        return ClassificationResult(
            artifact_type=artifact_type,
            confidence=parsed.get("confidence", 0.0),
            reasoning=parsed.get("reasoning", ""),
            extracted_attributes=extracted,
            match_found=False,
            suggested_action=f"Type '{artifact_type}' not in ontology."
        )
    
    errors, normalizations, normalized_attrs = validate_and_normalize_attributes(artifact_type, extracted)
    
    # Generate metadata preview
    metadata_preview = extract_metadata(normalized_attrs, artifact_type)
    payload_fields = get_payload_fields(normalized_attrs, metadata_preview)
    
    return ClassificationResult(
        artifact_type=artifact_type,
        confidence=parsed.get("confidence", 0.0),
        reasoning=parsed.get("reasoning", ""),
        extracted_attributes=normalized_attrs,
        validation_errors=errors,
        normalizations=normalizations,
        match_found=True,
        schema_properties=type_info.get("properties", []),
        metadata_preview=metadata_preview,
        payload_fields=payload_fields
    )


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/types")
async def get_artifact_types():
    """Get available artifact types from ontology"""
    types = get_available_types()
    return {"types": types}


@router.post("/analyze", response_model=ClassificationResult)
async def analyze_data(request: IngestionRequest):
    """Analyze and classify submitted data"""
    print(f"📥 Analyze request: {len(request.raw_data)} bytes")
    
    # If artifact_type provided, skip LLM classification
    if request.artifact_type:
        try:
            full_data = json.loads(request.raw_data)
        except json.JSONDecodeError:
            full_data = {"raw_content": request.raw_data}
        
        errors, normalizations, normalized = validate_and_normalize_attributes(
            request.artifact_type, full_data
        )
        
        metadata_preview = extract_metadata(normalized, request.artifact_type)
        payload_fields = get_payload_fields(normalized, metadata_preview)
        
        return ClassificationResult(
            artifact_type=request.artifact_type,
            confidence=1.0,
            reasoning="User-specified artifact type",
            extracted_attributes=normalized,
            validation_errors=errors,
            normalizations=normalizations,
            match_found=True,
            metadata_preview=metadata_preview,
            payload_fields=payload_fields
        )
    
    result = await classify_with_llm(request.raw_data, request.source_hint)
    return result


@router.post("/validate", response_model=ValidateResponse)
async def validate_attributes(request: ValidateRequest):
    """Validate and normalize attributes after user edits"""
    errors, normalizations, normalized_attrs = validate_and_normalize_attributes(
        request.artifact_type,
        request.attributes
    )
    
    return ValidateResponse(
        valid=len(errors) == 0,
        validation_errors=errors,
        normalizations=normalizations,
        normalized_attributes=normalized_attrs
    )


@router.post("/commit", response_model=CommitResponse)
async def commit_artifact(request: CommitRequest):
    """
    Save the artifact using two-tier storage:
    1. Lightweight metadata → ArangoDB
    2. Full payload → File system
    """
    if not db:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    # Validate
    errors, normalizations, normalized_attrs = validate_and_normalize_attributes(
        request.artifact_type,
        request.attributes
    )
    
    if errors and not request.skip_validation:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validation failed",
                "validation_errors": [{"field": e.field, "message": e.message} for e in errors]
            }
        )
    
    # Get collection
    available_types = get_available_types()
    type_info = None
    for t in available_types:
        if t["label"] == request.artifact_type:
            type_info = t
            break
    
    if not type_info:
        raise HTTPException(status_code=400, detail=f"Unknown artifact type: {request.artifact_type}")
    
    collection_name = type_info.get("collection")
    if not collection_name:
        raise HTTPException(status_code=400, detail=f"No collection for type: {request.artifact_type}")
    
    # Ensure collection exists
    if not db.has_collection(collection_name):
        db.create_collection(collection_name)
        print(f"✓ Created collection: {collection_name}")
    
    collection = db.collection(collection_name)
    
    # Generate _key
    artifact_key = normalized_attrs.get("_key") or normalized_attrs.get("id")
    if not artifact_key:
        artifact_key = f"{request.artifact_type.lower()}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    artifact_key = str(artifact_key).replace(" ", "_").replace("/", "_")
    
    # === TIER 2: Save full payload to file ===
    payload_url = None
    if request.save_payload:
        payload_url = save_payload(artifact_key, normalized_attrs)
    
    # === TIER 1: Extract metadata and save to ArangoDB ===
    metadata = extract_metadata(normalized_attrs, request.artifact_type)
    metadata["_key"] = artifact_key
    metadata["_artifact_type"] = request.artifact_type
    metadata["_ingested_at"] = datetime.utcnow().isoformat()
    
    if payload_url:
        metadata["payload_url"] = payload_url
    
    # Insert/update document
    try:
        if collection.has(artifact_key):
            result = collection.update(metadata)
            print(f"✓ Updated: {collection_name}/{artifact_key}")
        else:
            result = collection.insert(metadata)
            print(f"✓ Inserted: {collection_name}/{artifact_key}")
        
        return CommitResponse(
            success=True,
            artifact_type=request.artifact_type,
            collection=collection_name,
            document_id=result["_id"],
            document_key=result["_key"],
            payload_url=payload_url,
            payload_saved=payload_url is not None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")


# ============================================================================
# PAYLOAD SERVING ENDPOINTS
# ============================================================================

@router.get("/payloads/{filename}")
async def get_payload(filename: str):
    """
    Serve a payload file directly.
    
    This endpoint serves the raw JSON payload file, allowing:
    - Direct browser viewing (opens in new tab)
    - API consumption by Operator frontend
    """
    # Security: prevent directory traversal
    safe_filename = Path(filename).name
    if safe_filename != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    filepath = Path(PAYLOAD_STORAGE_DIR) / safe_filename
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Payload not found: {filename}")
    
    # Return as JSON with proper content type
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            payload_data = json.load(f)
        return JSONResponse(
            content=payload_data,
            media_type="application/json"
        )
    except json.JSONDecodeError:
        # If not valid JSON, serve as file
        return FileResponse(
            filepath,
            media_type="application/json",
            filename=safe_filename
        )


@router.get("/payloads")
async def list_payloads(
    prefix: Optional[str] = None,
    limit: int = 100
):
    """
    List available payload files.
    
    Useful for debugging and admin purposes.
    """
    payload_dir = Path(PAYLOAD_STORAGE_DIR)
    
    if not payload_dir.exists():
        return {"payloads": [], "count": 0}
    
    files = []
    for filepath in payload_dir.glob("*.json"):
        if prefix and not filepath.stem.startswith(prefix):
            continue
        
        stat = filepath.stat()
        files.append({
            "filename": filepath.name,
            "url": f"/api/ingest/payloads/{filepath.name}",
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
        })
        
        if len(files) >= limit:
            break
    
    # Sort by modification time, newest first
    files.sort(key=lambda x: x["modified_at"], reverse=True)
    
    return {
        "payloads": files,
        "count": len(files),
        "storage_dir": str(payload_dir)
    }


@router.delete("/payloads/{filename}")
async def delete_payload(filename: str):
    """Delete a payload file (admin only)."""
    safe_filename = Path(filename).name
    if safe_filename != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    filepath = Path(PAYLOAD_STORAGE_DIR) / safe_filename
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Payload not found: {filename}")
    
    try:
        filepath.unlink()
        return {"success": True, "deleted": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {str(e)}")


# ============================================================================
# DEBUG ENDPOINTS
# ============================================================================

@router.get("/debug")
async def debug_ingestion():
    """Debug endpoint to check ingestion state"""
    payload_dir = Path(PAYLOAD_STORAGE_DIR)
    payload_count = len(list(payload_dir.glob("*.json"))) if payload_dir.exists() else 0
    
    return {
        "db_connected": db is not None,
        "ontology_loaded": ontology_manager is not None,
        "taxonomy_loaded": taxonomy_registry is not None,
        "available_types": [t["label"] for t in get_available_types()],
        "ollama_host": OLLAMA_HOST,
        "ollama_model": OLLAMA_MODEL,
        "payload_storage_dir": str(payload_dir),
        "payload_count": payload_count,
        "metadata_fields": METADATA_FIELDS
    }


@router.post("/refresh")
async def refresh_registries():
    """Refresh ontology and taxonomy caches from database"""
    global ontology_manager, taxonomy_registry
    
    refreshed = []
    
    if taxonomy_registry:
        taxonomy_registry.refresh()
        refreshed.append("taxonomy_registry")
    
    if ontology_manager:
        ontology_manager.refresh()
        refreshed.append("ontology_manager")
    
    return {
        "success": True,
        "refreshed": refreshed
    }