#!/usr/bin/env python3
"""
ProtoGraph Plugin System
Base classes and registry for exposing graph data to external tools
"""

from typing import Dict, List, Any, Optional, Callable
from pydantic import BaseModel
from datetime import datetime
import json


class FieldMapping(BaseModel):
    """Mapping from ProtoGraph field to plugin field"""
    source: str          # ProtoGraph field path (e.g., "name" or "payload.parameters")
    target: str          # Plugin field name
    transform: Optional[str] = None  # Optional transformation function name


class PluginConfig(BaseModel):
    """Plugin configuration"""
    id: str
    name: str
    description: str
    endpoint: str
    icon: str
    active: bool = False
    collections: List[str]  # Which ArangoDB collections to expose
    field_mappings: List[FieldMapping]
    filters: Dict[str, Any] = {}  # Optional AQL filters
    created_at: str
    updated_at: str
    created_by: str


class Plugin:
    """Base plugin class"""
    
    def __init__(self, config: PluginConfig):
        self.config = config
    
    def transform_data(self, nodes: List[dict], payloads: Dict[str, dict]) -> List[dict]:
        """
        Transform ProtoGraph data into plugin's expected format.
        Override this method in plugin implementations.
        """
        raise NotImplementedError
    
    def validate_data(self, data: List[dict]) -> bool:
        """
        Validate transformed data meets plugin requirements.
        Override this method in plugin implementations.
        """
        return True


class PluginRegistry:
    """Central registry for all plugins"""
    
    _plugins: Dict[str, Plugin] = {}
    _configs: Dict[str, PluginConfig] = {}
    
    @classmethod
    def register(cls, plugin: Plugin):
        """Register a new plugin"""
        cls._plugins[plugin.config.id] = plugin
        cls._configs[plugin.config.id] = plugin.config
        print(f"✓ Registered plugin: {plugin.config.name}")
    
    @classmethod
    def get(cls, plugin_id: str) -> Optional[Plugin]:
        """Get plugin by ID"""
        return cls._plugins.get(plugin_id)
    
    @classmethod
    def get_all(cls) -> List[PluginConfig]:
        """Get all plugin configs"""
        return list(cls._configs.values())
    
    @classmethod
    def get_active(cls) -> List[PluginConfig]:
        """Get active plugins only"""
        return [c for c in cls._configs.values() if c.active]
    
    @classmethod
    def activate(cls, plugin_id: str):
        """Activate a plugin"""
        if plugin_id in cls._configs:
            cls._configs[plugin_id].active = True
            cls._configs[plugin_id].updated_at = datetime.now().isoformat()
    
    @classmethod
    def deactivate(cls, plugin_id: str):
        """Deactivate a plugin"""
        if plugin_id in cls._configs:
            cls._configs[plugin_id].active = False
            cls._configs[plugin_id].updated_at = datetime.now().isoformat()