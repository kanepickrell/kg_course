"""
Plugin Management Endpoints — config editing additions
=======================================================

Add these routes to your existing endpoints.py / main.py router.

New endpoints:
  GET  /api/plugins/{plugin_id}/config          → return full live config
  PATCH /api/plugins/{plugin_id}/config         → partial update (prompt, model, filters, etc.)
  GET  /api/plugins/{plugin_id}/prompt          → return just the system_prompt (used by Overview tab)
  POST /api/plugins/{plugin_id}/update-prompt   → legacy compat shim used by PluginDashboard TabOverview

All writes go to PluginRegistry.update_config() which persists to disk immediately.
The agent reads config via get_config() on every request, so changes are live instantly.
"""

from fastapi import APIRouter, HTTPException
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from plugins.base import PluginRegistry, IntentRules

router = APIRouter(prefix="/api/plugins", tags=["Plugin Config"])


# ── Request models ────────────────────────────────────────────────────────────

class ConfigPatch(BaseModel):
    """
    Fields the dashboard is allowed to edit.
    All optional — only provided fields are updated.
    """
    system_prompt:     Optional[str]            = None
    llm_model:         Optional[str]            = None
    session_cache_ttl: Optional[int]            = None
    mode:              Optional[str]            = None
    filters:           Optional[Dict[str, Any]] = None
    improvement_policy: Optional[Dict[str, Any]] = None


class PromptUpdate(BaseModel):
    """Legacy shape used by TabOverview savePrompt()."""
    system_prompt: str


class IntentRulesPatch(BaseModel):
    """Targeted update for just the intent routing rules."""
    direct_answer_triggers: Optional[List[str]] = None
    decline_triggers:       Optional[List[str]] = None
    graph_query_triggers:   Optional[List[str]] = None


# ── GET full config ───────────────────────────────────────────────────────────

@router.get("/{plugin_id}/config")
async def get_plugin_config(plugin_id: str):
    """
    Return the full live config for a plugin.
    Used by the dashboard to populate editable fields on load.
    """
    config = PluginRegistry.get_config(plugin_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    return {
        "success": True,
        "config": config.model_dump(),
        "intent_rules": config.get_intent_rules().model_dump(),
    }


# ── PATCH config ─────────────────────────────────────────────────────────────

@router.patch("/{plugin_id}/config")
async def patch_plugin_config(plugin_id: str, body: ConfigPatch):
    """
    Partial update for any editable config field.
    Changes take effect on the next agent request — no restart needed.

    Dashboard calls this from:
      - System prompt edit & save (TabOverview)
      - LLM model selector (TabOverview / future settings panel)
      - Intent rules editor (TabOverview)
      - TTL slider (future settings panel)
    """
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")

    updated = PluginRegistry.update_config(plugin_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    return {
        "success": True,
        "plugin_id": plugin_id,
        "updated_fields": list(patch.keys()),
        "config": updated.model_dump(),
    }


# ── GET prompt only (used by TabOverview on mount) ────────────────────────────

@router.get("/{plugin_id}/prompt")
async def get_plugin_prompt(plugin_id: str):
    """Return just the system_prompt string."""
    config = PluginRegistry.get_config(plugin_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    return {"success": True, "prompt": config.system_prompt or ""}


# ── POST update-prompt (legacy shim, keeps TabOverview working as-is) ─────────

@router.post("/{plugin_id}/update-prompt")
async def update_plugin_prompt(plugin_id: str, body: PromptUpdate):
    """
    Legacy endpoint called by TabOverview savePrompt().
    Delegates to update_config so persistence is consistent.
    """
    updated = PluginRegistry.update_config(plugin_id, {"system_prompt": body.system_prompt})
    if not updated:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    return {"success": True, "plugin_id": plugin_id}


# ── PATCH intent rules only (targeted endpoint for the rules editor) ──────────

@router.patch("/{plugin_id}/intent-rules")
async def patch_intent_rules(plugin_id: str, body: IntentRulesPatch):
    """
    Targeted update for just the intent routing trigger lists.
    The Overview tab intent rules editor calls this.
    """
    config = PluginRegistry.get_config(plugin_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    rules = config.get_intent_rules()

    if body.direct_answer_triggers is not None:
        rules.direct_answer_triggers = body.direct_answer_triggers
    if body.decline_triggers is not None:
        rules.decline_triggers = body.decline_triggers
    if body.graph_query_triggers is not None:
        rules.graph_query_triggers = body.graph_query_triggers

    config.set_intent_rules(rules)

    # Persist via update_config so the registry + disk stay in sync
    PluginRegistry.update_config(plugin_id, {"filters": config.filters})

    return {
        "success": True,
        "plugin_id": plugin_id,
        "intent_rules": rules.model_dump(),
    }