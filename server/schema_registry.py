#!/usr/bin/env python3
"""
Schema Registry - Manages learned artifact type schemas
Enables progressive learning and schema evolution
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
import os
from arango import ArangoClient

# =====================================================
# ROUTER SETUP
# =====================================================
router = APIRouter(prefix="/api/schemas", tags=["schema-registry"])

# =====================================================
# DATABASE CONNECTION
# =====================================================
# try:
#     client = ArangoClient(hosts=os.getenv("ARANGO_HOST", "http://localhost:8529"))
#     db = client.db(
#         os.getenv("ARANGO_DB", "AUTO_DB"),
#         username=os.getenv("ARANGO_USER", "root"),
#         password=os.getenv("ARANGO_PASSWORD", "")
#     )
#     print(f"✓ Schema Registry connected to ArangoDB: {db.name}")
# except Exception as e:
#     print(f"✗ Schema Registry failed to connect to ArangoDB: {e}")
#     db = None

db = None

# =====================================================
# MODELS
# =====================================================

class ArtifactTypeSchema(BaseModel):
    """Learned schema for an artifact type"""
    type_name: str = Field(..., description="Human-readable artifact type name")
    metadata_fields: List[str] = Field(..., description="Fields that go in graph metadata")
    payload_structure: Dict[str, Any] = Field(..., description="Expected payload structure")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Schema confidence (0-1)")
    example_count: int = Field(1, ge=1, description="Number of examples this schema learned from")
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    created_by: str = Field("user", description="User or system that created this schema")
    description: Optional[str] = Field(None, description="Optional description of this artifact type")


class SchemaUpdateRequest(BaseModel):
    """Request to update an existing schema with new example"""
    artifact_data: Dict[str, Any]
    detected_fields: List[str]


class SchemaValidationRequest(BaseModel):
    """Request to validate data against a schema"""
    type_name: str
    data: Dict[str, Any]


# =====================================================
# ENDPOINTS
# =====================================================

@router.get("/types")
async def get_artifact_types():
    """
    Get all learned artifact type schemas.
    
    Returns:
        List of all registered artifact types with their schemas
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        # Create collection if it doesn't exist
        if not db.has_collection("ArtifactTypeSchema"):
            db.create_collection("ArtifactTypeSchema")
            print("✓ Created ArtifactTypeSchema collection")
        
        collection = db.collection("ArtifactTypeSchema")
        schemas = list(collection.all())
        
        return {
            "success": True,
            "count": len(schemas),
            "types": schemas
        }
        
    except Exception as e:
        print(f"❌ Failed to fetch artifact types: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/types/{type_name}")
async def get_schema_by_name(type_name: str):
    """
    Get a specific schema by type name.
    
    Args:
        type_name: Name of the artifact type (e.g., "Library Module")
        
    Returns:
        Schema details for the specified type
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        collection = db.collection("ArtifactTypeSchema")
        schema_key = type_name.replace(" ", "_").lower()
        
        if not collection.has(schema_key):
            raise HTTPException(status_code=404, detail=f"Schema '{type_name}' not found")
        
        schema = collection.get(schema_key)
        
        return {
            "success": True,
            "schema": schema
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to fetch schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/register")
async def register_new_type(schema: ArtifactTypeSchema):
    """
    Register a new artifact type schema.
    
    This is called when a user creates a new artifact type for the first time.
    
    Args:
        schema: Complete schema definition
        
    Returns:
        Success status and registered schema
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        # Create collection if it doesn't exist
        if not db.has_collection("ArtifactTypeSchema"):
            db.create_collection("ArtifactTypeSchema")
        
        collection = db.collection("ArtifactTypeSchema")
        
        # Generate key from type name
        schema_key = schema.type_name.replace(" ", "_").lower()
        
        # Check if already exists
        if collection.has(schema_key):
            raise HTTPException(
                status_code=409, 
                detail=f"Schema '{schema.type_name}' already exists. Use /evolve endpoint to update."
            )
        
        # Prepare document
        schema_doc = {
            "_key": schema_key,
            "type_name": schema.type_name,
            "metadata_fields": schema.metadata_fields,
            "payload_structure": schema.payload_structure,
            "confidence": schema.confidence,
            "example_count": schema.example_count,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "created_by": schema.created_by,
            "description": schema.description
        }
        
        # Insert into database
        result = collection.insert(schema_doc)
        
        print(f"✅ Registered new schema: {schema.type_name}")
        
        return {
            "success": True,
            "message": f"Schema '{schema.type_name}' registered successfully",
            "schema": {
                "_id": result["_id"],
                "_key": result["_key"],
                **schema_doc
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to register schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evolve/{type_name}")
async def evolve_schema(type_name: str, update: SchemaUpdateRequest):
    """
    Update an existing schema based on a new example.
    
    This is called when ingesting a new artifact of an existing type,
    and the new artifact has fields not in the current schema.
    
    Args:
        type_name: Name of the artifact type
        update: New example data and detected fields
        
    Returns:
        Updated schema with increased confidence
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        collection = db.collection("ArtifactTypeSchema")
        schema_key = type_name.replace(" ", "_").lower()
        
        if not collection.has(schema_key):
            raise HTTPException(status_code=404, detail=f"Schema '{type_name}' not found")
        
        schema = collection.get(schema_key)
        
        # Increment example count
        schema["example_count"] += 1
        
        # Check for new fields
        existing_fields = set(schema["metadata_fields"])
        new_fields = set(update.detected_fields) - existing_fields
        
        if new_fields:
            # Add new fields to schema
            schema["metadata_fields"].extend(list(new_fields))
            print(f"  ℹ️  Added {len(new_fields)} new fields: {new_fields}")
        
        # Update confidence (increases with more examples, asymptotically approaches 1.0)
        # Formula: confidence = 1 - (1 / sqrt(example_count))
        import math
        schema["confidence"] = min(1.0, 1.0 - (1.0 / math.sqrt(schema["example_count"])))
        
        # Update timestamp
        schema["updated_at"] = datetime.now().isoformat()
        
        # Save updated schema
        collection.update(schema)
        
        print(f"✅ Evolved schema: {type_name} (now {schema['example_count']} examples, {schema['confidence']:.2%} confidence)")
        
        return {
            "success": True,
            "message": f"Schema evolved with {len(new_fields)} new fields",
            "updated_schema": schema,
            "new_fields": list(new_fields)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to evolve schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate")
async def validate_against_schema(request: SchemaValidationRequest):
    """
    Validate incoming data against a registered schema.
    
    Returns:
    - Whether data matches schema
    - Missing required fields
    - Extra fields not in schema
    - Confidence score
    
    Args:
        request: Type name and data to validate
        
    Returns:
        Validation results
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        collection = db.collection("ArtifactTypeSchema")
        schema_key = request.type_name.replace(" ", "_").lower()
        
        if not collection.has(schema_key):
            return {
                "success": True,
                "is_valid": False,
                "reason": f"No schema found for type '{request.type_name}'",
                "should_evolve": True
            }
        
        schema = collection.get(schema_key)
        
        # Check metadata fields
        data_fields = set(request.data.keys())
        schema_fields = set(schema["metadata_fields"])
        
        missing_fields = schema_fields - data_fields
        extra_fields = data_fields - schema_fields
        
        is_valid = len(missing_fields) == 0
        
        return {
            "success": True,
            "is_valid": is_valid,
            "schema_confidence": schema["confidence"],
            "missing_fields": list(missing_fields),
            "extra_fields": list(extra_fields),
            "should_evolve": len(extra_fields) > 0,
            "match_percentage": len(data_fields & schema_fields) / len(schema_fields) if schema_fields else 0
        }
        
    except Exception as e:
        print(f"❌ Failed to validate: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/types/{type_name}")
async def delete_schema(type_name: str):
    """
    Delete a schema (use with caution).
    
    Args:
        type_name: Name of schema to delete
        
    Returns:
        Success status
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        collection = db.collection("ArtifactTypeSchema")
        schema_key = type_name.replace(" ", "_").lower()
        
        if not collection.has(schema_key):
            raise HTTPException(status_code=404, detail=f"Schema '{type_name}' not found")
        
        collection.delete(schema_key)
        
        print(f"🗑️  Deleted schema: {type_name}")
        
        return {
            "success": True,
            "message": f"Schema '{type_name}' deleted"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to delete schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Check if schema registry is operational"""
    return {
        "status": "healthy",
        "database_connected": db is not None
    }