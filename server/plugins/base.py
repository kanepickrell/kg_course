#!/usr/bin/env python3
"""
ProtoGraph Plugin System
Base classes and registry for exposing graph data to external tools.

Key change: PluginConfig now carries `filters` which includes intent_rules
(direct_answer_triggers, decline_triggers, graph_query_triggers) that are
edited live in the dashboard and loaded by agent.py at request time.
"""

import json
import os
from typing import Dict, List, Any, Optional
from pydantic import BaseModel
from datetime import datetime


class FieldMapping(BaseModel):
    source: str   # ProtoGraph field path (e.g. "name" or "payload.parameters")
    target: str   # Plugin field name
    transform: Optional[str] = None


class IntentRules(BaseModel):
    """
    Routing rules for the LLM-first orchestration layer.
    Edited via the dashboard — never hardcoded in agent.py.
    """
    direct_answer_triggers: List[str] = [
        "what kind of analyst",
        "who are you",
        "what can you do",
        "what do you do",
        "tell me about yourself",
        "your capabilities",
    ]
    decline_triggers: List[str] = [
        "write code",
        "general IT help",
        "write a script",
        "personal question",
    ]
    graph_query_triggers: List[str] = []   # catch-all if empty → all remaining → graph


class PluginConfig(BaseModel):
    id: str
    name: str
    description: str
    endpoint: str
    icon: str
    active: bool = False
    collections: List[str]
    field_mappings: List[FieldMapping]
    # filters stores intent_rules and any other per-plugin routing config
    filters: Dict[str, Any] = {}
    created_at: str
    updated_at: str
    created_by: str
    # Agent fields (set by App Onboarding wizard, editable in dashboard)
    mode: Optional[str] = "action"
    llm_model: Optional[str] = None
    domain_classes: Optional[List[str]] = []
    domain_relationships: Optional[List[str]] = []
    write_permissions: Optional[List[str]] = []
    session_cache_ttl: Optional[int] = 300
    system_prompt: Optional[str] = None
    has_code: bool = False
    generated_tools: Optional[List[Dict[str, Any]]] = []
    improvement_policy: Optional[Dict[str, Any]] = None

    def get_intent_rules(self) -> IntentRules:
        """Return parsed IntentRules from filters dict."""
        raw = self.filters.get("intent_rules", {})
        return IntentRules(**raw) if raw else IntentRules()

    def set_intent_rules(self, rules: IntentRules):
        self.filters["intent_rules"] = rules.model_dump()
        self.updated_at = datetime.now().isoformat()


class Plugin:
    def __init__(self, config: PluginConfig):
        self.config = config

    def transform_data(self, nodes: List[dict], payloads: Dict[str, dict]) -> List[dict]:
        raise NotImplementedError

    def validate_data(self, data: List[dict]) -> bool:
        return True


# ── Persistence ─────────────────────────────────────────────────────────────

PLUGIN_CONFIG_DIR = os.environ.get("PLUGIN_CONFIG_DIR", "./data/plugins")


def _config_path(plugin_id: str) -> str:
    return os.path.join(PLUGIN_CONFIG_DIR, f"{plugin_id}.json")


def persist_config(config: PluginConfig):
    """Write config to disk so it survives restarts."""
    os.makedirs(PLUGIN_CONFIG_DIR, exist_ok=True)
    with open(_config_path(config.id), "w", encoding="utf-8") as f:
        json.dump(config.model_dump(), f, indent=2)


def load_config(plugin_id: str) -> Optional[PluginConfig]:
    """Load config from disk. Returns None if not found."""
    path = _config_path(plugin_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return PluginConfig(**json.load(f))


# ── Registry ─────────────────────────────────────────────────────────────────

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
    def get_config(cls, plugin_id: str) -> Optional[PluginConfig]:
        return cls._configs.get(plugin_id)

    @classmethod
    def get_all(cls) -> List[PluginConfig]:
        return list(cls._configs.values())

    @classmethod
    def get_active(cls) -> List[PluginConfig]:
        return [c for c in cls._configs.values() if c.active]

    @classmethod
    def update_config(cls, plugin_id: str, patch: Dict[str, Any]) -> Optional[PluginConfig]:
        """
        Apply a partial update to a plugin's config.
        Persists to disk immediately.
        Called by PATCH /api/plugins/{id}/config from the dashboard.
        """
        config = cls._configs.get(plugin_id)
        if not config:
            return None

        # Apply allowed mutable fields
        MUTABLE = {
            "system_prompt", "llm_model", "session_cache_ttl",
            "filters", "mode", "active", "improvement_policy",
        }
        for key, value in patch.items():
            if key in MUTABLE:
                setattr(config, key, value)

        config.updated_at = datetime.now().isoformat()

        # Keep plugin object in sync
        if plugin_id in cls._plugins:
            cls._plugins[plugin_id].config = config

        persist_config(config)
        return config

    @classmethod
    def activate(cls, plugin_id: str):
        cls.update_config(plugin_id, {"active": True})

    @classmethod
    def deactivate(cls, plugin_id: str):
        cls.update_config(plugin_id, {"active": False})