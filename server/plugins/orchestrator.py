#!/usr/bin/env python3
"""
orchestrator.py
===============
The Orchestrator — the meta-agent layer for ATLAS multi-agent workflows.

Architecture (HyperAgents-informed)
─────────────────────────────────────
HyperAgents shows that the most effective self-improving systems separate
concerns into two roles:

  META-AGENT   — reasons about what needs doing and who should do it.
                 It does NOT execute domain tasks itself.
  TASK AGENTS  — execute narrow, specific tasks. They trust the meta-agent's
                 routing decision and do not re-evaluate scope.

This Orchestrator is that meta-agent. It:
  1. Reads the live capability table from OrchestratorRegistry (the "archive")
  2. Decomposes a complex request into subtasks
  3. Routes each subtask to the best-matching specialist agent
  4. Collects results and synthesises a final answer
  5. Logs the workflow for future improvement

The agent system prompt is assembled dynamically from the registry — it
always reflects the current roster of agents, not a hardcoded list.
This is the core ADAS insight: the meta-agent should be informed by an
ever-growing archive of known capabilities, not a static configuration.

As agents mature and more are added, the Orchestrator automatically gains
access to them without code changes. The workflow gradually shifts from
"human picks the right agent" to "orchestrator chains the right agents."

Endpoints
──────────
  POST /api/orchestrator/run       — run a multi-agent workflow
  POST /api/orchestrator/route     — dry-run: show routing decision only
  GET  /api/orchestrator/agents    — list all delegatable agents + capabilities
  GET  /api/orchestrator/graph     — full capability adjacency for dashboard
"""

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .base import OrchestratorRegistry, PluginRegistry

router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator"])


# ── Request / response models ──────────────────────────────────────────────────

class WorkflowRequest(BaseModel):
    task:           str                      # Natural language workflow description
    context:        Optional[Dict[str, Any]] = {}   # Shared context passed to all agents
    max_agents:     int                      = 3    # Max agents to chain in one workflow
    dry_run:        bool                     = False # If True, plan but don't execute
    session_id:     Optional[str]            = None


class RouteRequest(BaseModel):
    task:          str
    require_verbs: Optional[List[str]] = None


# ── Orchestrator system prompt ─────────────────────────────────────────────────
# Built dynamically at request time so it always reflects the live agent roster.
# This is the key pattern from ADAS / HyperAgents: the meta-agent's context
# includes the full archive of what is known.

def _build_orchestrator_prompt() -> str:
    agent_roster = OrchestratorRegistry.describe_agents()
    return (
        "You are the ATLAS Orchestrator — a meta-agent that coordinates specialist agents "
        "to complete complex analytical workflows for the 318th RANS.\n\n"
        "Your role is to PLAN and DELEGATE. You do not perform domain tasks yourself.\n\n"
        "AVAILABLE SPECIALIST AGENTS:\n"
        f"{agent_roster}\n\n"
        "RULES:\n"
        "- Decompose the user request into the minimum number of subtasks needed.\n"
        "- Assign each subtask to exactly one agent using its plugin_id.\n"
        "- If no agent covers a subtask, mark it as 'unresolvable' — do not guess.\n"
        "- Pass the output of one agent as context to the next when tasks are sequential.\n"
        "- Return ONLY valid JSON, no prose outside the JSON block.\n\n"
        "OUTPUT SCHEMA:\n"
        '{"plan": [{"step": 1, "plugin_id": "<id>", "task": "<subtask>", '
        '"depends_on": [], "input_from_step": null}], '
        '"unresolvable": ["<anything no agent covers>"]}'
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/agents")
async def list_delegatable_agents():
    """
    List all agents that accept delegation, with their capability manifests.
    Used by the dashboard capability map and for debugging routing decisions.
    """
    table = OrchestratorRegistry.get_table()
    return {
        "success": True,
        "count":   len(table),
        "agents":  table,
        "summary": OrchestratorRegistry.describe_agents(),
    }


@router.post("/route")
async def route_task(req: RouteRequest):
    """
    Dry-run routing: show which agents would handle a task and their scores.
    Useful during agent development to verify capability declarations work.
    """
    ranked = OrchestratorRegistry.route(req.task, require_verbs=req.require_verbs)
    return {
        "success":  True,
        "task":     req.task,
        "matches":  ranked,
        "top_pick": ranked[0]["plugin_id"] if ranked else None,
    }


@router.post("/run")
async def run_workflow(req: WorkflowRequest):
    """
    Run a multi-agent workflow.

    Phase 1 — PLAN
    The Orchestrator LLM receives the task + the live agent roster and
    returns a structured execution plan (JSON).

    Phase 2 — EXECUTE
    Each step in the plan is dispatched to the designated agent's
    forward() endpoint in dependency order. Results are accumulated
    and passed as context to dependent steps.

    Phase 3 — SYNTHESISE
    Results are returned as a structured workflow result.
    The Orchestrator does NOT re-narrate — that is each agent's job.
    """
    try:
        from llm_client import chat_completion
    except ImportError:
        raise HTTPException(status_code=503, detail="llm_client not available")

    # ── Phase 1: Plan ─────────────────────────────────────────────────────────
    system_prompt = _build_orchestrator_prompt()

    context_str = json.dumps(req.context) if req.context else "{}"
    user_message = (
        f"Task: {req.task}\n\n"
        f"Additional context: {context_str}\n\n"
        f"Produce the execution plan. Max {req.max_agents} agents."
    )

    try:
        raw_plan = await chat_completion(
            user_message,
            system=system_prompt,
            model=_get_orchestrator_model(),
            temperature=0.0,
        )
        plan_data = _parse_json(raw_plan)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Planning failed: {e}")

    steps         = plan_data.get("plan", [])
    unresolvable  = plan_data.get("unresolvable", [])

    if req.dry_run:
        return {
            "success":      True,
            "dry_run":      True,
            "task":         req.task,
            "plan":         steps,
            "unresolvable": unresolvable,
        }

    # ── Phase 2: Execute ──────────────────────────────────────────────────────
    step_results: Dict[int, Any] = {}
    errors:       List[Dict]     = []

    for step in steps:
        step_num  = step.get("step", 0)
        plugin_id = step.get("plugin_id", "")
        subtask   = step.get("task", "")
        deps      = step.get("depends_on", [])
        from_step = step.get("input_from_step")

        # Build input context for this step
        step_context = dict(req.context or {})
        if from_step and from_step in step_results:
            step_context["previous_result"] = step_results[from_step]
        elif deps:
            step_context["dependencies"] = {
                d: step_results[d] for d in deps if d in step_results
            }

        # Dispatch to agent
        result = await _delegate_to_agent(plugin_id, subtask, step_context)

        if result.get("success"):
            step_results[step_num] = result
        else:
            errors.append({"step": step_num, "plugin_id": plugin_id, "error": result})
            # Non-fatal — continue with remaining steps

    # ── Phase 3: Return structured result ─────────────────────────────────────
    final_answer = _synthesise_results(req.task, steps, step_results)

    return {
        "success":      len(errors) == 0,
        "task":         req.task,
        "plan":         steps,
        "results":      step_results,
        "errors":       errors,
        "unresolvable": unresolvable,
        "answer":       final_answer,
        "agents_used":  [s["plugin_id"] for s in steps if s.get("step") in step_results],
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _delegate_to_agent(plugin_id: str, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call a specialist agent in DELEGATED mode.

    The payload signals delegated=True so the agent skips its intent
    classification pass and goes straight to forward() execution.
    This is the key architectural point: routing has already happened.
    The task agent trusts the orchestrator.
    """
    import importlib.util
    from pathlib import Path

    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        return {"success": False, "error": f"Agent '{plugin_id}' not found"}
    if not plugin.config.active:
        return {"success": False, "error": f"Agent '{plugin_id}' is inactive"}
    if not plugin.config.accepts_delegation:
        return {"success": False, "error": f"Agent '{plugin_id}' does not accept delegation"}

    agent_path = Path(__file__).parent / plugin_id / "agent.py"
    if not agent_path.exists():
        return {"success": False, "error": f"agent.py not found for '{plugin_id}'"}

    try:
        spec   = importlib.util.spec_from_file_location(f"plugins.{plugin_id}.agent", agent_path)
        module = importlib.util.module_from_spec(spec)   # type: ignore[arg-type]
        spec.loader.exec_module(module)                  # type: ignore[union-attr]

        if hasattr(module, "forward"):
            # DELEGATED mode — direct task call, no intent classification
            result = await module.forward({
                "task":      task,
                "context":   context,
                "delegated": True,          # agent checks this flag to skip routing
                "caller":    "orchestrator",
            })
            return result

        if hasattr(module, "handle"):
            # Fallback: agent has handle() but not forward() yet — still works,
            # routing overhead is acceptable until the agent is upgraded
            return await module.handle({
                "message":   task,
                "params":    context,
                "delegated": True,
            })

        return {"success": False, "error": f"Agent '{plugin_id}' has no callable entry point"}

    except Exception as e:
        return {"success": False, "error": f"Agent execution error: {e}"}


def _synthesise_results(task: str, steps: List[Dict], results: Dict[int, Any]) -> str:
    """
    Produce a brief structured summary of what was accomplished.
    Each agent already narrated its own result — this just stitches them.
    """
    if not results:
        return "No results were produced."
    parts = []
    for step in steps:
        n = step.get("step")
        r = results.get(n)
        if r and r.get("answer"):
            parts.append(f"Step {n} ({step.get('plugin_id')}): {r['answer']}")
    return "\n".join(parts) if parts else "Workflow completed."


def _parse_json(raw: str) -> dict:
    clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(clean)


def _get_orchestrator_model() -> str:
    """
    The orchestrator uses the strongest available model.
    Falls back to gpt-4o-mini if nothing is configured.
    Operators can override via ORCHESTRATOR_LLM env var.
    """
    import os
    return os.environ.get("ORCHESTRATOR_LLM", "gpt-4o")