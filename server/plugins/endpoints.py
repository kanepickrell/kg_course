#!/usr/bin/env python3
"""
Plugin Management Endpoints
============================
Handles plugin registry introspection and activate/deactivate controls.

Routes: GET/POST /api/plugins/*

Note: Actual data-serving routes (e.g. /api/plugins/operator/modules)
live in plugin_router.py, which is mounted separately.
"""

from fastapi import APIRouter, HTTPException
from .base import PluginRegistry

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


@router.get("")
async def get_all_plugins():
    """Return all registered plugins and their config."""
    plugins = PluginRegistry.get_all()
    return {
        "success": True,
        "count": len(plugins),
        "plugins": [p.dict() for p in plugins],
    }


@router.get("/active")
async def get_active_plugins():
    """Return only active plugins."""
    plugins = PluginRegistry.get_active()
    return {
        "success": True,
        "count": len(plugins),
        "plugins": [p.dict() for p in plugins],
    }


@router.post("/{plugin_id}/activate")
async def activate_plugin(plugin_id: str):
    """Activate a plugin by ID."""
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    PluginRegistry.activate(plugin_id)
    return {"success": True, "message": f"Plugin '{plugin.config.name}' activated"}


@router.post("/{plugin_id}/deactivate")
async def deactivate_plugin(plugin_id: str):
    """Deactivate a plugin by ID."""
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    PluginRegistry.deactivate(plugin_id)
    return {"success": True, "message": f"Plugin '{plugin.config.name}' deactivated"}