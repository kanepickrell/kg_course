#!/usr/bin/env python3
"""
ProtoGraph Plugin System — base.py
====================================
Base classes, registry, and orchestration layer.

Architecture
─────────────
Agents in this system operate in two distinct modes, inspired by the
HyperAgents paper (Zhang et al., 2026) and the ADAS meta-agent pattern
(Hu, Lu & Clune, 2024):

  STANDALONE mode  — agent is called directly by a human via the dashboard
                     or API. The agent's handle() function runs the full
                     intent-classification → tool-dispatch → narration chain.

  DELEGATED mode   — agent is called by the Orchestrator (or another agent)
                     with a structured task payload. The routing has already
                     happened upstream. The agent skips classification and
                     executes its forward() function directly.

This mirrors the HyperAgents distinction between the meta-agent (which
decides what to do) and the task agent (which executes a specific task
without needing to re-evaluate scope). The task agent trusts the caller.

The Orchestrator reads each agent's `capabilities` manifest at runtime to
build a routing table. When a workflow request arrives, it scores each
active agent's capability match and delegates subtasks accordingly.

Over time, as more agents are registered and proven competent, the
Orchestrator can chain them into multi-step workflows automatically —
each agent passing structured results to the next without human routing.

Key additions over the previous version
─────────────────────────────────────────
  PluginConfig.capabilities     — machine-readable description for routing
  PluginConfig.accepts_delegation — whether agent supports direct task calls
  PluginConfig.agent_peers      — IDs of agents this agent may call
  CapabilityManifest            — structured capability declaration
  OrchestratorRegistry          — builds and queries the capability graph
  PluginRegistry.deregister()   — public deregister method
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ── Field mapping ──────────────────────────────────────────────────────────────

class FieldMapping(BaseModel):
    source: str
    target: str
    transform: Optional[str] = None


# ── Intent rules (human-facing routing, editable in dashboard) ─────────────────

class IntentRules(BaseModel):
    """
    Routing hints used when an agent is called in STANDALONE mode by a human.
    These are edited live in the dashboard — never hardcoded in agent.py.

    In DELEGATED mode (orchestrator-to-agent calls) these rules are bypassed
    entirely. The orchestrator has already decided who should handle the task.
    """
    direct_answer_triggers: List[str] = [
        "what kind of analyst",
        "who are you",
        "what can you do",
        "what do you do",
        "tell me about yourself",
        "your capabilities",
    ]
    decline_triggers: List[str] = []   # Rarely needed — see architecture note above
    graph_query_triggers: List[str] = []


# ── Capability manifest ────────────────────────────────────────────────────────

class CapabilityManifest(BaseModel):
    """
    Machine-readable description of what an agent can do.

    The Orchestrator reads this at runtime to build the capability routing
    table. It is the agent's "advertisement" to the rest of the system.

    Fields
    ──────
    verbs          actions this agent can perform (e.g. "hash", "encode", "search")
    entity_types   ontology classes this agent reasons about
    input_schema   what a delegated task payload should look like (JSON schema fragment)
    output_schema  what the agent's forward() returns
    example_tasks  natural language examples used for semantic routing scoring
    cost_estimate  relative cost hint ("low" | "medium" | "high") for orchestrator planning
    """
    verbs:          List[str]       = []
    entity_types:   List[str]       = []
    input_schema:   Dict[str, Any]  = {}
    output_schema:  Dict[str, Any]  = {}
    example_tasks:  List[str]       = []
    cost_estimate:  str             = "low"


# ── Plugin config ──────────────────────────────────────────────────────────────

class PluginConfig(BaseModel):
    # Core identity
    id:           str
    name:         str
    description:  str
    endpoint:     str
    icon:         str
    active:       bool = False

    # Graph domain
    collections:      List[str]
    field_mappings:   List[FieldMapping]
    filters:          Dict[str, Any] = {}

    # Timestamps / provenance
    created_at:  str
    updated_at:  str
    created_by:  str

    # Agent behaviour (set by App Onboarding, editable in dashboard)
    mode:              Optional[str]             = "action"
    llm_model:         Optional[str]             = None
    domain_classes:    Optional[List[str]]       = []
    domain_relationships: Optional[List[str]]   = []
    write_permissions: Optional[List[str]]       = []
    session_cache_ttl: Optional[int]             = 300
    system_prompt:     Optional[str]             = None
    has_code:          bool                      = False
    generated_tools:   Optional[List[Dict[str, Any]]] = []
    improvement_policy: Optional[Dict[str, Any]] = None

    # ── Multi-agent collaboration fields ──────────────────────────────────────
    #
    # capabilities      — what this agent can do (read by Orchestrator)
    # accepts_delegation — True means the agent exposes a forward() endpoint
    #                      that the Orchestrator can call directly without
    #                      going through the full human-facing handle() flow
    # agent_peers       — IDs of agents this agent is permitted to call as
    #                      sub-tasks (empty = no peer calls allowed)
    #
    capabilities:        Optional[CapabilityManifest] = None
    accepts_delegation:  bool                         = False
    agent_peers:         List[str]                    = []

    # ── Intent rule helpers ───────────────────────────────────────────────────

    def get_intent_rules(self) -> IntentRules:
        raw = self.filters.get("intent_rules", {})
        return IntentRules(**raw) if raw else IntentRules()

    def set_intent_rules(self, rules: IntentRules):
        self.filters["intent_rules"] = rules.model_dump()
        self.updated_at = datetime.now().isoformat()


# ── Plugin base class ──────────────────────────────────────────────────────────

class Plugin:
    def __init__(self, config: PluginConfig):
        self.config = config

    def transform_data(self, nodes: List[dict], payloads: Dict[str, dict]) -> List[dict]:
        raise NotImplementedError

    def validate_data(self, data: List[dict]) -> bool:
        return True


# ── Persistence ────────────────────────────────────────────────────────────────

PLUGIN_CONFIG_DIR = os.environ.get("PLUGIN_CONFIG_DIR", "./data/plugins")


def _config_path(plugin_id: str) -> str:
    return os.path.join(PLUGIN_CONFIG_DIR, f"{plugin_id}.json")


def persist_config(config: PluginConfig):
    os.makedirs(PLUGIN_CONFIG_DIR, exist_ok=True)
    with open(_config_path(config.id), "w", encoding="utf-8") as f:
        json.dump(config.model_dump(), f, indent=2)


def load_config(plugin_id: str) -> Optional[PluginConfig]:
    path = _config_path(plugin_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return PluginConfig(**json.load(f))


# ── Plugin Registry ────────────────────────────────────────────────────────────

class PluginRegistry:
    """In-memory registry for all plugins."""

    _plugins: Dict[str, Plugin]       = {}
    _configs: Dict[str, PluginConfig] = {}

    @classmethod
    def register(cls, plugin: Plugin):
        cls._plugins[plugin.config.id] = plugin
        cls._configs[plugin.config.id] = plugin.config
        # Notify orchestrator so the capability table stays current
        OrchestratorRegistry.refresh(plugin.config)
        print(f"✓ Registered plugin: {plugin.config.name} (active={plugin.config.active})")

    @classmethod
    def deregister(cls, plugin_id: str):
        """Public deregister — removes from registry and capability table."""
        cls._plugins.pop(plugin_id, None)
        cls._configs.pop(plugin_id, None)
        OrchestratorRegistry.remove(plugin_id)

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
        Apply a partial update to a plugin's config. Persists to disk immediately.
        Called by PATCH /api/plugins/{id}/config from the dashboard.
        """
        config = cls._configs.get(plugin_id)
        if not config:
            return None

        MUTABLE = {
            "system_prompt", "llm_model", "session_cache_ttl",
            "filters", "mode", "active", "improvement_policy",
            "capabilities", "accepts_delegation", "agent_peers",
        }
        for key, value in patch.items():
            if key in MUTABLE:
                if key == "capabilities" and isinstance(value, dict):
                    value = CapabilityManifest(**value)
                setattr(config, key, value)

        config.updated_at = datetime.now().isoformat()

        if plugin_id in cls._plugins:
            cls._plugins[plugin_id].config = config

        persist_config(config)
        OrchestratorRegistry.refresh(config)
        return config

    @classmethod
    def activate(cls, plugin_id: str):
        cls.update_config(plugin_id, {"active": True})

    @classmethod
    def deactivate(cls, plugin_id: str):
        cls.update_config(plugin_id, {"active": False})


# ── Orchestrator Registry ──────────────────────────────────────────────────────

class OrchestratorRegistry:
    """
    Maintains the capability routing table across all registered agents.

    This is the "archive" in HyperAgents terms — the orchestrator reads it
    to decide which agent should handle a given subtask. As agents are added
    and their capabilities mature, the routing table grows without any manual
    wiring.

    Routing works in two passes:
      1. Hard filter  — is the agent active and does it accept delegation?
      2. Soft scoring — how well do its capability verbs / example_tasks
                        match the requested task? (keyword overlap for now;
                        can be upgraded to embedding similarity later)

    The scoring approach is deliberately simple. The ADAS paper shows that
    even keyword-based routing produces good results when agent capabilities
    are well-described, and it's fully transparent / debuggable.
    """

    # capability_table: plugin_id → CapabilityManifest
    _table: Dict[str, CapabilityManifest] = {}
    # tracks which agents accept delegation
    _delegatable: Dict[str, bool] = {}

    @classmethod
    def refresh(cls, config: PluginConfig):
        """Called whenever a plugin is registered or its config changes."""
        if config.capabilities:
            cls._table[config.id] = config.capabilities
        elif config.id in cls._table:
            del cls._table[config.id]
        cls._delegatable[config.id] = config.accepts_delegation and config.active

    @classmethod
    def remove(cls, plugin_id: str):
        cls._table.pop(plugin_id, None)
        cls._delegatable.pop(plugin_id, None)

    @classmethod
    def route(cls, task: str, require_verbs: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Score all delegatable agents against a task description.
        Returns a ranked list of { plugin_id, score, capabilities }.

        task         — natural language description of what needs doing
        require_verbs — optional hard filter (agent must support these verbs)

        The scoring is intentionally transparent:
          +3  per exact verb match (require_verbs or task word → agent verb)
          +2  per entity_type keyword found in task
          +1  per example_task word overlap with task
        """
        task_lower   = task.lower()
        task_words   = set(task_lower.split())
        candidates   = []

        for plugin_id, caps in cls._table.items():
            if not cls._delegatable.get(plugin_id):
                continue

            # Hard verb filter
            if require_verbs:
                agent_verbs = {v.lower() for v in caps.verbs}
                if not all(rv.lower() in agent_verbs for rv in require_verbs):
                    continue

            score = 0

            # Verb match against task words
            for verb in caps.verbs:
                if verb.lower() in task_lower:
                    score += 3

            # Entity type match
            for et in caps.entity_types:
                if et.lower() in task_lower:
                    score += 2

            # Example task overlap
            for example in caps.example_tasks:
                example_words = set(example.lower().split())
                overlap = len(task_words & example_words)
                score  += overlap

            if score > 0:
                candidates.append({
                    "plugin_id":    plugin_id,
                    "score":        score,
                    "capabilities": caps.model_dump(),
                })

        return sorted(candidates, key=lambda x: x["score"], reverse=True)

    @classmethod
    def get_table(cls) -> Dict[str, Any]:
        """Return full capability table — used by the dashboard capability view."""
        return {
            pid: {
                "capabilities":     caps.model_dump(),
                "accepts_delegation": cls._delegatable.get(pid, False),
            }
            for pid, caps in cls._table.items()
        }

    @classmethod
    def describe_agents(cls) -> str:
        """
        Return a human+LLM-readable summary of all delegatable agents.
        Injected into the Orchestrator system prompt so it knows what exists.
        Mirrors the ADAS 'archive' pattern — the orchestrator always sees
        the current agent roster, not a hardcoded list.
        """
        lines = []
        for pid, caps in cls._table.items():
            if not cls._delegatable.get(pid):
                continue
            verbs   = ", ".join(caps.verbs)      or "unspecified"
            types   = ", ".join(caps.entity_types) or "unspecified"
            examples = "; ".join(caps.example_tasks[:3]) or "none"
            lines.append(
                f"- {pid}: verbs=[{verbs}]  entities=[{types}]  "
                f"examples=[{examples}]"
            )
        return "\n".join(lines) if lines else "No delegatable agents registered."