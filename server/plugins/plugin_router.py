"""
Plugin Data Router
==================
Serves actual data through plugin endpoints.

All routes require the relevant plugin to be active (check_plugin_active).
GraphDB is the only backend — ArangoDB fallbacks removed.

Routes mounted at /api/plugins/* (same prefix as endpoints.py, no conflict
because these are all under /operator/* subpaths).

Lumen/Operator API contract:
  GET /api/plugins/operator/modules
  GET /api/plugins/operator/modules/{key}
  GET /api/plugins/operator/categories
  GET /api/plugins/operator/tactics
  GET /api/plugins/operator/stats
  POST /api/plugins/operator/validate
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict
import os
import json

from .base import PluginRegistry

router = APIRouter(prefix="/api/plugins", tags=["Plugin Data"])

# Injected by create_plugin_data_router()
gdb = None
payload_base_dir = "./data/payloads"


# ============================================================
# HELPERS
# ============================================================

def _require_active(plugin_id: str):
    """Raise 403 if the plugin is not registered and active."""
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    if not plugin.config.active:
        raise HTTPException(
            status_code=403,
            detail=f"Plugin '{plugin_id}' is disabled. Enable it in the Plugin Manager.",
        )


def _require_gdb():
    if gdb is None:
        raise HTTPException(status_code=503, detail="GraphDB not connected")


OPERATOR_PAYLOAD_FIELDS = [
    "inputs", "outputs", "parameters", "requirements",
    "executionType", "cobaltStrikeCommand", "robotKeyword",
    "robotTemplate", "shellCommand", "estimatedDuration",
    "subcategory", "icon", "robotFramework",
]


def _merge_payload(doc: dict) -> dict:
    """
    Merge payload file fields into a module dict.
    Payload fields overwrite graph fields when present.
    """
    key = doc.get("_key", "")
    if not key:
        return doc

    payload_path = os.path.join(payload_base_dir, f"{key}.json")
    if not os.path.exists(payload_path):
        for field in ["inputs", "outputs", "parameters"]:
            doc.setdefault(field, [])
        return doc

    try:
        with open(payload_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        for field in OPERATOR_PAYLOAD_FIELDS:
            if field in payload:
                doc[field] = payload[field]
    except Exception as e:
        print(f"Warning: payload load failed for {key}: {e}")

    return doc


def _load_payload_requirements(module_key: str) -> dict:
    """Load just the requirements block from a payload file."""
    path = os.path.join(payload_base_dir, f"{module_key}.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f).get("requirements", {})
    except Exception:
        return {}


# ============================================================
# OPERATOR ENDPOINTS
# ============================================================

@router.get("/operator/modules")
async def get_operator_modules(
    category: Optional[str] = Query(None),
    tactic: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
):
    """List library modules for the Operator/Lumen workflow builder."""
    _require_active("operator")
    _require_gdb()

    try:
        result = gdb.get_library_modules(
            category=category,
            tactic=tactic,
            search=search,
            risk_level=risk_level,
            limit=limit,
            offset=offset,
        )
        modules = [_merge_payload(m) for m in result["modules"]]
        print(f"✓ Operator modules: {len(modules)} returned")
        return {
            "success": True,
            "modules": modules,
            "count": len(modules),
            "total": result.get("total", len(modules)),
            "pagination": {
                "limit": limit,
                "offset": offset,
                "hasMore": offset + len(modules) < result.get("total", len(modules)),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/operator/modules/{module_key}")
async def get_operator_module(module_key: str):
    """Get a single module by key."""
    _require_active("operator")
    _require_gdb()

    try:
        doc = gdb.get_library_module(module_key)
        if doc is None:
            raise HTTPException(status_code=404, detail=f"Module '{module_key}' not found")
        return {"success": True, "module": _merge_payload(doc)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/operator/categories")
async def get_operator_categories():
    """Distinct category values with counts."""
    _require_active("operator")
    _require_gdb()

    try:
        return {"success": True, "data": gdb.get_library_module_categories()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/operator/tactics")
async def get_operator_tactics():
    """Distinct tactic values with counts."""
    _require_active("operator")
    _require_gdb()

    try:
        return {"success": True, "data": gdb.get_library_module_tactics()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/operator/stats")
async def get_operator_stats():
    """Module statistics — total, by category, tactic, risk level."""
    _require_active("operator")
    _require_gdb()

    try:
        return {"success": True, "stats": gdb.get_library_module_stats()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/operator/validate")
async def validate_operator_requirements(request: dict):
    """
    Validate a module's requirements against the current execution environment.

    Body: { "moduleKey": "cs-lateral-psexec", "environment": { "c2Server": true, ... } }
    """
    _require_active("operator")
    _require_gdb()

    module_key = request.get("moduleKey")
    environment = request.get("environment", {})

    if not module_key:
        raise HTTPException(status_code=400, detail="moduleKey is required")

    try:
        doc = gdb.get_library_module(module_key)
        if doc is None:
            raise HTTPException(status_code=404, detail=f"Module '{module_key}' not found")

        requirements = _load_payload_requirements(module_key)
        missing = []

        if requirements.get("c2Server") and not environment.get("c2Server"):
            missing.append("C2 server connection required")

        for listener in requirements.get("listeners", []):
            if listener not in environment.get("listeners", []):
                missing.append(f"Listener required: {listener}")

        for tool in requirements.get("externalTools", []):
            if tool not in environment.get("externalTools", []):
                missing.append(f"External tool required: {tool}")

        for lib in requirements.get("libraries", []):
            if lib not in environment.get("libraries", []):
                missing.append(f"Robot library required: {lib}")

        return {
            "valid": len(missing) == 0,
            "missing": missing,
            "moduleKey": module_key,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# FACTORY
# ============================================================

def create_plugin_data_router(database, payload_dir: str = "./data/payloads", graphdb_adapter=None):
    """
    Inject dependencies and return the router.

    Usage in main.py:
        from plugins.plugin_router import create_plugin_data_router
        plugin_data_router = create_plugin_data_router(None, PAYLOAD_DIR, gdb)
        app.include_router(plugin_data_router)
    """
    global gdb, payload_base_dir
    gdb = graphdb_adapter
    payload_base_dir = payload_dir
    return router