#!/usr/bin/env python3
"""
proposal_endpoints.py
======================
FastAPI routes for the Proposals tab and Console outcome logging.

Mount in main.py:
    from plugins.proposal_endpoints import router as proposal_router
    app.include_router(proposal_router)

Routes
───────
  GET  /api/plugins/{id}/proposals              list + auto-analyze
  POST /api/plugins/{id}/proposals/action       approve or reject
  POST /api/plugins/{id}/proposals/analyze      manual trigger
  POST /api/plugins/{id}/interactions/outcome   update confirmed/rejected
  GET  /api/plugins/{id}/execution-log          real execution events
  POST /api/plugins/{id}/log-execution          write execution event
  DELETE /api/plugins/{id}/proposals/{prop_id}  dismiss a proposal
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from .base import PluginRegistry
from .proposal_engine import (
    apply_proposal,
    load_proposals,
    log_execution_event,
    run_analysis,
    update_interaction_outcome,
    _log_dir,
    _save_proposals,
)

router   = APIRouter(prefix="/api/plugins", tags=["proposals"])
DATA_DIR = Path(__file__).parent.parent / "data"


# ── Models ─────────────────────────────────────────────────────────────────────

class ProposalAction(BaseModel):
    proposal_id: str
    action:      Literal["approved", "rejected"]
    note:        Optional[str] = None


class OutcomeUpdate(BaseModel):
    question: str
    outcome:  Literal["confirmed", "rejected"]


class ExecutionEventBody(BaseModel):
    type:       Literal["start", "stop", "failure", "ready"]
    message:    str
    exit_code:  Optional[int]  = None
    stderr_tail: Optional[str] = None
    duration_ms: Optional[int] = None


# ── GET proposals — runs LLM analysis, returns all ────────────────────────────

@router.get("/{plugin_id}/proposals")
async def get_proposals(plugin_id: str, background_tasks: BackgroundTasks):
    """
    Returns all proposals. Triggers LLM analysis in the background so
    the response is fast and new proposals appear on the next load.
    """
    config = PluginRegistry.get_config(plugin_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    policy = config.improvement_policy or {}

    # Return existing proposals immediately
    existing = load_proposals(plugin_id)

    # Run analysis in background so UI isn't blocked by LLM calls
    if policy.get("enabled", False):
        background_tasks.add_task(_run_analysis_bg, plugin_id, policy)

    pending  = [p for p in existing if p["status"] == "pending"]
    resolved = [p for p in existing if p["status"] != "pending"]

    return {
        "success":        True,
        "plugin_id":      plugin_id,
        "policy_enabled": policy.get("enabled", False),
        "analyzing":      policy.get("enabled", False),
        "pending":        pending,
        "resolved":       resolved,
        "total":          len(existing),
        "pending_count":  len(pending),
    }


async def _run_analysis_bg(plugin_id: str, policy: dict):
    """Background task — runs LLM analysis without blocking the response."""
    try:
        await run_analysis(plugin_id, policy)
    except Exception as e:
        print(f"⚠️  Proposal analysis failed for {plugin_id}: {e}")


# ── POST action — approve or reject ────────────────────────────────────────────

@router.post("/{plugin_id}/proposals/action")
async def proposal_action(plugin_id: str, req: ProposalAction):
    config = PluginRegistry.get_config(plugin_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    proposals = load_proposals(plugin_id)
    target    = next((p for p in proposals if p["id"] == req.proposal_id), None)

    if not target:
        raise HTTPException(status_code=404, detail=f"Proposal '{req.proposal_id}' not found")

    if target["status"] != "pending":
        return {
            "success":  True,
            "message":  f"Proposal already {target['status']}",
            "proposal": target,
        }

    apply_result = {"success": True, "applied": False, "message": "Rejected — no changes"}

    if req.action == "approved":
        apply_result = apply_proposal(plugin_id, target)
        if not apply_result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"Failed to apply: {apply_result.get('message')}",
            )

    target["status"]       = req.action
    target["resolved_at"]  = datetime.now(timezone.utc).isoformat()
    target["resolved_by"]  = "operator"
    if req.note:
        target["note"] = req.note
    if req.action == "approved":
        target["apply_result"] = apply_result.get("message")

    _save_proposals(plugin_id, proposals)

    return {
        "success":     True,
        "plugin_id":   plugin_id,
        "proposal_id": req.proposal_id,
        "action":      req.action,
        "apply_result": apply_result,
        "proposal":    target,
    }


# ── POST analyze — manual trigger ──────────────────────────────────────────────

@router.post("/{plugin_id}/proposals/analyze")
async def trigger_analysis(plugin_id: str, background_tasks: BackgroundTasks):
    config = PluginRegistry.get_config(plugin_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    policy = config.improvement_policy or {}
    background_tasks.add_task(_run_analysis_bg, plugin_id, policy)

    return {
        "success":  True,
        "plugin_id": plugin_id,
        "message":  "Analysis running in background — refresh proposals in a moment",
        "policy_enabled": policy.get("enabled", False),
    }


# ── POST outcome — Console thumbs-up / thumbs-down ────────────────────────────

@router.post("/{plugin_id}/interactions/outcome")
async def update_outcome(plugin_id: str, req: OutcomeUpdate):
    """
    Upgrade an 'auto' interaction to 'confirmed' or 'rejected'.
    Called when operator clicks thumbs-up/down in the Console.
    This is what closes the loop — corrections drive future proposals.
    """
    if not PluginRegistry.get_config(plugin_id):
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    updated = update_interaction_outcome(plugin_id, req.question, req.outcome)
    return {"success": True, "updated": updated, "outcome": req.outcome}


# ── GET execution log ─────────────────────────────────────────────────────────

@router.get("/{plugin_id}/execution-log")
async def get_execution_log(plugin_id: str, limit: int = 50):
    """Return real execution events for the Execution tab."""
    if not PluginRegistry.get_config(plugin_id):
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    log_path = _log_dir(plugin_id) / "execution_log.jsonl"
    if not log_path.exists():
        return {"success": True, "events": [], "count": 0}

    events = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                pass

    # Most recent first, capped at limit
    events = list(reversed(events[-limit:]))
    return {"success": True, "events": events, "count": len(events)}


# ── POST log-execution — agent writes lifecycle events ────────────────────────

@router.post("/{plugin_id}/log-execution")
async def log_execution(plugin_id: str, body: ExecutionEventBody):
    """Write a program lifecycle event. Called by agent start/stop commands."""
    if not PluginRegistry.get_config(plugin_id):
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    log_execution_event(
        plugin_id,
        event_type=body.type,
        message=body.message,
        exit_code=body.exit_code,
        stderr_tail=body.stderr_tail,
        duration_ms=body.duration_ms,
    )
    return {"success": True}


# ── DELETE proposal ────────────────────────────────────────────────────────────

@router.delete("/{plugin_id}/proposals/{proposal_id}")
async def delete_proposal(plugin_id: str, proposal_id: str):
    if not PluginRegistry.get_config(plugin_id):
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    proposals = load_proposals(plugin_id)
    filtered  = [p for p in proposals if p["id"] != proposal_id]

    if len(filtered) == len(proposals):
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found")

    _save_proposals(plugin_id, filtered)
    return {"success": True, "deleted": proposal_id}