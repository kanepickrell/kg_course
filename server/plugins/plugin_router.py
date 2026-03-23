"""
Plugin Router
=============
Serves data through plugin endpoints with enable/disable control.

When a plugin is disabled (active: false), all its endpoints return 403.
When enabled, it serves data from the configured collections.

This is the bridge between:
- Plugin configurations (stored in PluginRegistry)
- Actual data (stored in LibraryModule, etc.)

Phase 2: GraphDB adapter support — reads from GraphDB when available,
falls back to ArangoDB.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
import os
import json
from datetime import datetime

from .base import PluginRegistry  # Use the existing registry!

router = APIRouter(prefix="/api/plugins", tags=["Plugin Data"])

# Will be injected from main.py
db = None
gdb = None  # GraphDB adapter (Phase 2)
payload_base_dir = "./data/payloads"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def check_plugin_active(plugin_id: str) -> bool:
    """Check if a plugin is active/enabled using PluginRegistry."""
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        return False
    return plugin.config.active


def merge_payload(doc: Dict, payload_fields: List[str]) -> Dict:
    """Merge payload file data into document."""
    key = doc.get("_key", "")
    payload_path = os.path.join(payload_base_dir, f"{key}.json")
    
    if not os.path.exists(payload_path):
        # Set empty defaults for expected fields
        for field in payload_fields:
            if field not in doc:
                doc[field] = [] if field in ["inputs", "outputs", "parameters"] else None
        return doc
    
    try:
        with open(payload_path, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        
        for field in payload_fields:
            if field in payload:
                doc[field] = payload[field]
            elif field.capitalize() in payload:
                doc[field] = payload[field.capitalize()]
        
        return doc
    except Exception as e:
        print(f"Warning: Failed to load payload for {key}: {e}")
        return doc


# Payload fields that Operator expects on every module
OPERATOR_PAYLOAD_FIELDS = [
    "inputs", "outputs", "parameters", "requirements",
    "executionType", "cobaltStrikeCommand", "robotKeyword",
    "robotTemplate", "shellCommand", "estimatedDuration",
    "subcategory", "icon", "robotFramework"
]


# =============================================================================
# OPERATOR PLUGIN ENDPOINTS
# =============================================================================

@router.get("/operator/modules")
async def get_operator_modules(
    category: Optional[str] = Query(None),
    tactic: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0)
):
    """
    Get library modules for Operator.
    
    Returns 403 if the Operator plugin is disabled.
    """
    if not check_plugin_active("operator"):
        raise HTTPException(
            status_code=403, 
            detail="Operator plugin is disabled. Enable it in ProtoGraph to access modules."
        )
    
    # =====================================================
    # GRAPHDB PATH (Phase 2)
    # =====================================================
    if gdb:
        try:
            result = gdb.get_library_modules(
                category=category,
                tactic=tactic,
                search=search,
                risk_level=risk_level,
                limit=limit,
                offset=offset,
            )
            # Merge disk payloads (inputs/outputs/parameters/robotTemplate etc.)
            modules = [merge_payload(m, OPERATOR_PAYLOAD_FIELDS) for m in result["modules"]]
            
            print(f"✅ [GraphDB] Operator modules: {len(modules)} returned")
            return {
                "success": True,
                "modules": modules,
                "count": len(modules),
                "total": result["total"],
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "hasMore": offset + len(modules) < result["total"]
                }
            }
        except Exception as e:
            print(f"⚠️ [GraphDB] Operator modules failed, falling back to ArangoDB: {e}")

    # =====================================================
    # ARANGODB PATH (original)
    # =====================================================
    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    if not db.has_collection("LibraryModule"):
        return {"success": True, "modules": [], "count": 0, "total": 0}
    
    # Build filter conditions
    conditions = ["true"]
    
    if category:
        conditions.append(f"doc.category == '{category}'")
    if tactic:
        conditions.append(f"doc.tactic == '{tactic}'")
    if risk_level:
        conditions.append(f"doc.riskLevel == '{risk_level}'")
    if search:
        escaped_search = search.replace("'", "\\'")
        conditions.append(
            f"(CONTAINS(LOWER(doc.name || ''), LOWER('{escaped_search}')) OR "
            f"CONTAINS(LOWER(doc.description || ''), LOWER('{escaped_search}')))"
        )
    
    filter_clause = " AND ".join(conditions)
    
    # Get total count
    count_query = f"""
        FOR doc IN LibraryModule
            FILTER {filter_clause}
            COLLECT WITH COUNT INTO total
            RETURN total
    """
    total = list(db.aql.execute(count_query))[0]
    
    # Get data
    data_query = f"""
        FOR doc IN LibraryModule
            FILTER {filter_clause}
            SORT doc.name ASC
            LIMIT @offset, @limit
            RETURN doc
    """
    
    cursor = db.aql.execute(data_query, bind_vars={"offset": offset, "limit": limit})
    documents = list(cursor)
    
    # Merge payloads
    modules = [merge_payload(doc, OPERATOR_PAYLOAD_FIELDS) for doc in documents]
    
    return {
        "success": True,
        "modules": modules,
        "count": len(modules),
        "total": total,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "hasMore": offset + len(modules) < total
        }
    }


@router.get("/operator/modules/{module_key}")
async def get_operator_module(module_key: str):
    """Get a single module by key."""
    if not check_plugin_active("operator"):
        raise HTTPException(status_code=403, detail="Operator plugin is disabled")
    
    # =====================================================
    # GRAPHDB PATH (Phase 2)
    # =====================================================
    if gdb:
        try:
            doc = gdb.get_library_module(module_key)
            if doc is None:
                raise HTTPException(status_code=404, detail="Module not found")
            module = merge_payload(doc, OPERATOR_PAYLOAD_FIELDS)
            return {"success": True, "module": module}
        except HTTPException:
            raise
        except Exception as e:
            print(f"⚠️ [GraphDB] Module detail failed, falling back to ArangoDB: {e}")

    # =====================================================
    # ARANGODB PATH (original)
    # =====================================================
    if not db or not db.has_collection("LibraryModule"):
        raise HTTPException(status_code=404, detail="Module not found")
    
    collection = db.collection("LibraryModule")
    
    if not collection.has(module_key):
        raise HTTPException(status_code=404, detail="Module not found")
    
    doc = collection.get(module_key)
    module = merge_payload(doc, OPERATOR_PAYLOAD_FIELDS)
    
    return {"success": True, "module": module}


@router.get("/operator/categories")
async def get_operator_categories():
    """Get all categories with counts."""
    if not check_plugin_active("operator"):
        raise HTTPException(status_code=403, detail="Operator plugin is disabled")
    
    # =====================================================
    # GRAPHDB PATH (Phase 2)
    # =====================================================
    if gdb:
        try:
            data = gdb.get_library_module_categories()
            return {"success": True, "data": data}
        except Exception as e:
            print(f"⚠️ [GraphDB] Categories failed, falling back to ArangoDB: {e}")

    # =====================================================
    # ARANGODB PATH (original)
    # =====================================================
    if not db or not db.has_collection("LibraryModule"):
        return {"success": True, "data": []}
    
    query = """
        FOR doc IN LibraryModule
            FILTER doc.category != null
            COLLECT category = doc.category WITH COUNT INTO count
            SORT category ASC
            RETURN {value: category, count: count}
    """
    
    results = list(db.aql.execute(query))
    return {"success": True, "data": results}


@router.get("/operator/tactics")
async def get_operator_tactics():
    """Get all tactics with counts."""
    if not check_plugin_active("operator"):
        raise HTTPException(status_code=403, detail="Operator plugin is disabled")
    
    # =====================================================
    # GRAPHDB PATH (Phase 2)
    # =====================================================
    if gdb:
        try:
            data = gdb.get_library_module_tactics()
            return {"success": True, "data": data}
        except Exception as e:
            print(f"⚠️ [GraphDB] Tactics failed, falling back to ArangoDB: {e}")

    # =====================================================
    # ARANGODB PATH (original)
    # =====================================================
    if not db or not db.has_collection("LibraryModule"):
        return {"success": True, "data": []}
    
    query = """
        FOR doc IN LibraryModule
            FILTER doc.tactic != null
            COLLECT tactic = doc.tactic WITH COUNT INTO count
            SORT tactic ASC
            RETURN {value: tactic, count: count}
    """
    
    results = list(db.aql.execute(query))
    return {"success": True, "data": results}


@router.get("/operator/stats")
async def get_operator_stats():
    """Get module statistics."""
    if not check_plugin_active("operator"):
        raise HTTPException(status_code=403, detail="Operator plugin is disabled")
    
    # =====================================================
    # GRAPHDB PATH (Phase 2)
    # =====================================================
    if gdb:
        try:
            stats = gdb.get_library_module_stats()
            return {"success": True, "stats": stats}
        except Exception as e:
            print(f"⚠️ [GraphDB] Stats failed, falling back to ArangoDB: {e}")

    # =====================================================
    # ARANGODB PATH (original)
    # =====================================================
    if not db or not db.has_collection("LibraryModule"):
        return {"success": True, "stats": {"total": 0}}
    
    collection = db.collection("LibraryModule")
    total = collection.count()
    
    stats = {"total": total}
    
    # By category
    cat_query = """
        FOR doc IN LibraryModule
            FILTER doc.category != null
            COLLECT category = doc.category WITH COUNT INTO count
            RETURN {category: category, count: count}
    """
    stats["byCategory"] = list(db.aql.execute(cat_query))
    
    # By tactic
    tactic_query = """
        FOR doc IN LibraryModule
            FILTER doc.tactic != null
            COLLECT tactic = doc.tactic WITH COUNT INTO count
            RETURN {tactic: tactic, count: count}
    """
    stats["byTactic"] = list(db.aql.execute(tactic_query))
    
    # By risk level
    risk_query = """
        FOR doc IN LibraryModule
            FILTER doc.riskLevel != null
            COLLECT riskLevel = doc.riskLevel WITH COUNT INTO count
            RETURN {riskLevel: riskLevel, count: count}
    """
    stats["byRiskLevel"] = list(db.aql.execute(risk_query))
    
    return {"success": True, "stats": stats}


@router.post("/operator/validate")
async def validate_operator_requirements(request: dict):
    """Validate module requirements against environment."""
    if not check_plugin_active("operator"):
        raise HTTPException(status_code=403, detail="Operator plugin is disabled")
    
    module_key = request.get("moduleKey")
    environment = request.get("environment", {})
    
    if not module_key:
        raise HTTPException(status_code=400, detail="moduleKey required")
    
    # =====================================================
    # GRAPHDB PATH (Phase 2)
    # =====================================================
    if gdb:
        try:
            doc = gdb.get_library_module(module_key)
            if doc is None:
                raise HTTPException(status_code=404, detail="Module not found")
            # Requirements come from disk payload, not the graph
            payload_path = os.path.join(payload_base_dir, f"{module_key}.json")
            requirements = {}
            if os.path.exists(payload_path):
                try:
                    with open(payload_path, 'r') as f:
                        payload = json.load(f)
                        requirements = payload.get("requirements", {})
                except:
                    pass
            
            missing = []
            if requirements.get("c2Server") and not environment.get("c2Server"):
                missing.append("C2 Server connection required")
            
            required_listeners = requirements.get("listeners", [])
            available_listeners = environment.get("listeners", [])
            for listener in required_listeners:
                if listener not in available_listeners:
                    missing.append(f"Listener required: {listener}")
            
            return {
                "valid": len(missing) == 0,
                "missing": missing,
                "moduleKey": module_key
            }
        except HTTPException:
            raise
        except Exception as e:
            print(f"⚠️ [GraphDB] Validate failed, falling back to ArangoDB: {e}")

    # =====================================================
    # ARANGODB PATH (original)
    # =====================================================
    if not db or not db.has_collection("LibraryModule"):
        raise HTTPException(status_code=404, detail="Module not found")
    
    collection = db.collection("LibraryModule")
    
    if not collection.has(module_key):
        raise HTTPException(status_code=404, detail="Module not found")
    
    doc = collection.get(module_key)
    
    # Merge payload to get requirements
    payload_path = os.path.join(payload_base_dir, f"{module_key}.json")
    requirements = {}
    
    if os.path.exists(payload_path):
        try:
            with open(payload_path, 'r') as f:
                payload = json.load(f)
                requirements = payload.get("requirements", {})
        except:
            pass
    
    # Validate
    missing = []
    
    if requirements.get("c2Server") and not environment.get("c2Server"):
        missing.append("C2 Server connection required")
    
    required_listeners = requirements.get("listeners", [])
    available_listeners = environment.get("listeners", [])
    for listener in required_listeners:
        if listener not in available_listeners:
            missing.append(f"Listener required: {listener}")
    
    return {
        "valid": len(missing) == 0,
        "missing": missing,
        "moduleKey": module_key
    }


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_plugin_data_router(database, payload_dir: str = "./data/payloads", graphdb_adapter=None):
    """
    Factory function to create the router with dependencies injected.
    
    Usage in main.py:
        from plugins.plugin_router import create_plugin_data_router
        
        plugin_data_router = create_plugin_data_router(db, "./data/payloads", gdb)
        app.include_router(plugin_data_router)
    """
    global db, gdb, payload_base_dir
    db = database
    gdb = graphdb_adapter
    payload_base_dir = payload_dir
    return router