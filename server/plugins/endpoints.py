#!/usr/bin/env python3
"""
Plugin API Endpoints
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
import os
import json
from .base import PluginRegistry, PluginConfig

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


@router.get("")
async def get_all_plugins():
    """Get all registered plugins"""
    plugins = PluginRegistry.get_all()
    return {
        "success": True,
        "count": len(plugins),
        "plugins": [p.dict() for p in plugins]
    }


@router.get("/active")
async def get_active_plugins():
    """Get only active plugins"""
    plugins = PluginRegistry.get_active()
    return {
        "success": True,
        "count": len(plugins),
        "plugins": [p.dict() for p in plugins]
    }


@router.post("/{plugin_id}/activate")
async def activate_plugin(plugin_id: str):
    """Activate a plugin"""
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    PluginRegistry.activate(plugin_id)
    
    return {
        "success": True,
        "message": f"Plugin '{plugin.config.name}' activated"
    }


@router.post("/{plugin_id}/deactivate")
async def deactivate_plugin(plugin_id: str):
    """Deactivate a plugin"""
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    PluginRegistry.deactivate(plugin_id)
    
    return {
        "success": True,
        "message": f"Plugin '{plugin.config.name}' deactivated"
    }


@router.get("/{plugin_id}/data")
async def get_plugin_data(
    plugin_id: str,
    category: Optional[str] = None,
    tactic: Optional[str] = None,
    limit: int = 100
):
    """
    Get data exposed by a specific plugin.
    This is the DYNAMIC endpoint that serves data based on plugin configuration.
    """
    from arango import ArangoClient
    
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    if not plugin.config.active:
        raise HTTPException(status_code=403, detail="Plugin is not active")
    
    # Get database connection (imported from main)
    try:
        from main import db
    except:
        raise HTTPException(status_code=503, detail="Database not available")
    
    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        # Fetch nodes from configured collections
        all_nodes = []
        
        for collection_name in plugin.config.collections:
            if not db.has_collection(collection_name):
                continue
            
            # Build filters
            filters = []
            bind_vars = {"limit": limit}
            
            if category:
                filters.append("doc.category == @category")
                bind_vars["category"] = category
            
            if tactic:
                filters.append("doc.tactic == @tactic")
                bind_vars["tactic"] = tactic
            
            filter_clause = " AND ".join(filters) if filters else "true"
            
            # Query
            query = f"""
                FOR doc IN {collection_name}
                    FILTER {filter_clause}
                    LIMIT @limit
                    RETURN doc
            """
            
            nodes = list(db.aql.execute(query, bind_vars=bind_vars))
            all_nodes.extend(nodes)
        
        # Load payloads
        payloads = {}
        payload_dir = os.getenv("PAYLOAD_STORAGE_DIR", "./data/payloads")
        
        for node in all_nodes:
            node_key = node.get("_key")
            if not node_key:
                continue
            
            payload_path = os.path.join(payload_dir, f"{node_key}.json")
            
            if os.path.exists(payload_path):
                try:
                    with open(payload_path, 'r') as f:
                        payloads[node_key] = json.load(f)
                except Exception as e:
                    print(f"⚠️  Failed to load payload for {node_key}: {e}")
                    payloads[node_key] = {}
            else:
                payloads[node_key] = {}
        
        # Transform data using plugin
        transformed_data = plugin.transform_data(all_nodes, payloads)
        
        # Validate
        if not plugin.validate_data(transformed_data):
            raise HTTPException(status_code=500, detail="Data validation failed")
        
        print(f"✅ Served {len(transformed_data)} items to plugin '{plugin_id}'")
        
        return {
            "success": True,
            "plugin": plugin_id,
            "count": len(transformed_data),
            "data": transformed_data
        }
        
    except Exception as e:
        print(f"❌ Plugin data fetch failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))