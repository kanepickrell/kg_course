#!/usr/bin/env python3
"""
ProtoGraph Plugin System
Base classes and registry for exposing graph data to external tools.
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel
from datetime import datetime


class FieldMapping(BaseModel):
    source: str   # ProtoGraph field path (e.g. "name" or "payload.parameters")
    target: str   # Plugin field name
    transform: Optional[str] = None


class PluginConfig(BaseModel):
    id: str
    name: str
    description: str
    endpoint: str
    icon: str
    active: bool = False
    collections: List[str]
    field_mappings: List[FieldMapping]
    filters: Dict[str, Any] = {}
    created_at: str
    updated_at: str
    created_by: str


class Plugin:
    def __init__(self, config: PluginConfig):
        self.config = config

    def transform_data(self, nodes: List[dict], payloads: Dict[str, dict]) -> List[dict]:
        raise NotImplementedError

    def validate_data(self, data: List[dict]) -> bool:
        return True


class PluginRegistry:
    """In-memory registry for all plugins."""

    _plugins: Dict[str, Plugin] = {}
    _configs: Dict[str, PluginConfig] = {}

    @classmethod
    def register(cls, plugin: Plugin):
        cls._plugins[plugin.config.id] = plugin
        cls._configs[plugin.config.id] = plugin.config
        print(f"✓ Registered plugin: {plugin.config.name} (active={plugin.config.active})")

    @classmethod
    def get(cls, plugin_id: str) -> Optional[Plugin]:
        return cls._plugins.get(plugin_id)

    @classmethod
    def get_all(cls) -> List[PluginConfig]:
        return list(cls._configs.values())

    @classmethod
    def get_active(cls) -> List[PluginConfig]:
        return [c for c in cls._configs.values() if c.active]

    @classmethod
    def activate(cls, plugin_id: str):
        if plugin_id in cls._configs:
            cls._configs[plugin_id].active = True
            cls._configs[plugin_id].updated_at = datetime.now().isoformat()
            if plugin_id in cls._plugins:
                cls._plugins[plugin_id].config.active = True

    @classmethod
    def deactivate(cls, plugin_id: str):
        if plugin_id in cls._configs:
            cls._configs[plugin_id].active = False
            cls._configs[plugin_id].updated_at = datetime.now().isoformat()
            if plugin_id in cls._plugins:
                cls._plugins[plugin_id].config.active = False