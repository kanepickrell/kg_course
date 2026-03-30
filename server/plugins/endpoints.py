#!/usr/bin/env python3
"""
Plugin Management Endpoints
============================
Handles plugin registry introspection, activate/deactivate, and scaffolding.
Routes: GET/POST /api/plugins/*

Multi-agent architecture
─────────────────────────
Agents scaffolded here operate in two modes (see base.py for full explanation):

  STANDALONE  — called directly by a human. Runs full intent classification.
  DELEGATED   — called by the Orchestrator. Skips classification entirely.
                The `delegated` flag in the request payload signals this mode.

The ADAS / HyperAgents insight applied here: an agent that has been tasked
by the orchestrator does not need to re-evaluate whether the task is in scope.
That decision was made upstream. A well-specified capability manifest (declared
during App Onboarding) is what allows the orchestrator to make that decision
correctly — so the manifest is the real scope-enforcement mechanism.

The generated agent.py therefore has two entry points:
  handle(req)   — human-facing, full routing pipeline
  forward(req)  — orchestrator-facing, direct execution

As agents mature and the orchestrator proves competent at routing, operators
can gradually reduce the intent-classification overhead in handle() or
delegate more tasks via forward() directly.

Code generation safety
──────────────────────
All _write_*() functions build generated source as lists of plain strings
joined at the end. See the comment in _write_agent_py for full rationale.
Triple-quote injection is blocked by _sanitise_for_triple_quote().
"""

import json
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .base import (
    CapabilityManifest,
    OrchestratorRegistry,
    PluginRegistry,
)

router = APIRouter(prefix="/api/plugins", tags=["plugins"])

PLUGINS_DIR = Path(__file__).parent
DATA_DIR    = Path(__file__).parent.parent / "data"
LOG_DIR     = DATA_DIR / "plugin_logs"

_SYSTEM_PLUGINS = frozenset({"operator"})


# ── Helpers ────────────────────────────────────────────────────────────────────

def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _sanitise_for_triple_quote(text: str) -> str:
    """Prevent triple-quote injection in generated source files."""
    text = text.replace('"""', '\\"\\"\\"')
    text = text.replace("'''", "\\'\\'\\'")
    return text


def _log_dir(plugin_id: str) -> Path:
    d = LOG_DIR / plugin_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_system_prompt_to_agent(agent_path: Path, new_prompt: str) -> bool:
    """
    Replace the SYSTEM_PROMPT block in an existing agent.py.
    Single canonical implementation used by both update_prompt and patch_plugin_config.
    """
    if not agent_path.exists():
        return False
    src         = agent_path.read_text()
    safe_prompt = _sanitise_for_triple_quote(new_prompt.strip())
    new_block   = f'SYSTEM_PROMPT = """\n{safe_prompt}\n"""'
    new_src     = re.sub(
        r'SYSTEM_PROMPT\s*=\s*""".*?"""',
        new_block,
        src,
        count=1,
        flags=re.DOTALL,
    )
    if new_src == src:
        return False
    agent_path.write_text(new_src)
    return True


def _update_live_config(plugin_id: str, **kwargs) -> None:
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        return
    cfg = getattr(plugin, "config", plugin)
    for key, value in kwargs.items():
        try:
            setattr(cfg, key, value)
        except Exception:
            pass


def _persist_manifest_patch(plugin_id: str, **kwargs) -> None:
    manifest_path = DATA_DIR / "plugin_manifests" / f"{plugin_id}.json"
    if not manifest_path.exists():
        return
    try:
        data = json.loads(manifest_path.read_text())
        for key, value in kwargs.items():
            if key == "filters" and isinstance(value, dict):
                data.setdefault("filters", {})
                if isinstance(data["filters"], dict):
                    data["filters"].update(value)
                else:
                    data["filters"] = value
            else:
                data[key] = value
        manifest_path.write_text(json.dumps(data, indent=2))
    except Exception as e:
        print(f"⚠️  Failed to persist manifest patch for {plugin_id}: {e}")


# ── Fixed routes (must come before /{plugin_id}/…) ────────────────────────────

@router.get("")
async def get_all_plugins():
    plugins = PluginRegistry.get_all()
    return {"success": True, "count": len(plugins), "plugins": [p.dict() for p in plugins]}


@router.get("/active")
async def get_active_plugins():
    plugins = PluginRegistry.get_active()
    return {"success": True, "count": len(plugins), "plugins": [p.dict() for p in plugins]}


# ── Manifest models ────────────────────────────────────────────────────────────

class GeneratedTool(BaseModel):
    name:            str
    signature:       str
    description:     Optional[str]           = None
    sparql_template: Optional[str]           = None
    arg_types:       Optional[Dict[str, str]] = None
    return_type:     Optional[str]           = None
    source:          Optional[str]           = "ontology"


class ExecutionContextManifest(BaseModel):
    start_mode:         Optional[str] = None
    working_dir:        Optional[str] = ""
    start_command:      Optional[str] = ""
    ready_signal_type:  Optional[str] = "exit_code"
    ready_signal_value: Optional[str] = "0"
    stop_command:       Optional[str] = "kill -SIGTERM $PID"


class ImprovementPolicyManifest(BaseModel):
    enabled:                         bool  = False
    correction_threshold:            float = 0.25
    tool_usage_window_days:          int   = 7
    prompt_revision_requires_review: bool  = True
    track_execution_failures:        bool  = True
    auto_propose_tool_additions:     bool  = False


class CapabilityManifestInput(BaseModel):
    """
    Declared during App Onboarding.
    Drives the Orchestrator's routing decisions — the more precise this is,
    the better the orchestrator can match tasks to agents without LLM overhead.
    """
    verbs:          List[str] = []
    entity_types:   List[str] = []
    input_schema:   Dict[str, Any] = {}
    output_schema:  Dict[str, Any] = {}
    example_tasks:  List[str] = []
    cost_estimate:  str = "low"


class RegisterManifest(BaseModel):
    id:                   str
    name:                 str
    description:          Optional[str]                       = ""
    icon:                 Optional[str]                       = "⚙️"
    mode:                 Optional[str]                       = "action"
    domain_classes:       Optional[List[str]]                 = []
    domain_relationships: Optional[List[str]]                 = []
    write_permissions:    Optional[List[str]]                 = []
    llm_model:            Optional[str]                       = "gpt-4o-mini"
    system_prompt:        Optional[str]                       = ""
    session_cache_ttl:    Optional[int]                       = 300
    generated_tools:      Optional[List[GeneratedTool]]       = []
    execution_context:    Optional[ExecutionContextManifest]  = None
    improvement_policy:   Optional[ImprovementPolicyManifest] = None
    # Multi-agent fields
    capabilities:         Optional[CapabilityManifestInput]   = None
    accepts_delegation:   bool                                = False
    agent_peers:          Optional[List[str]]                 = []


# ── Register ───────────────────────────────────────────────────────────────────

@router.post("/register")
def register_plugin(manifest: RegisterManifest):
    """
    Register a new application from the AppOnboarding wizard manifest.
    1. Persist manifest → data/plugin_manifests/{id}.json
    2. Scaffold plugins/{id}/ with domain.py, tools.py, agent.py
    3. Register in live PluginRegistry (which also updates OrchestratorRegistry)
    """
    plugin_id = _slugify(manifest.id) or _slugify(manifest.name)
    if not plugin_id:
        raise HTTPException(status_code=400, detail="id is required")

    manifests_dir = DATA_DIR / "plugin_manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    (manifests_dir / f"{plugin_id}.json").write_text(manifest.model_dump_json(indent=2))

    plugin_dir = PLUGINS_DIR / plugin_id
    plugin_dir.mkdir(exist_ok=True)
    _ensure_init(plugin_dir)
    _write_domain_py(plugin_dir, manifest)
    _write_tools_py(plugin_dir, manifest)
    _write_agent_py(plugin_dir, manifest)

    try:
        from .base import PluginConfig, Plugin

        now = datetime.now(timezone.utc).isoformat()
        cfg = PluginConfig(
            id=plugin_id,
            name=manifest.name,
            description=manifest.description or "",
            endpoint=f"/api/plugins/{plugin_id}/agent",
            icon=manifest.icon or "⚙️",
            active=True,
            collections=manifest.domain_classes or [],
            field_mappings=[],
            filters={},
            created_at=now,
            updated_at=now,
            created_by="app_onboarding",
        )
        cfg.mode               = manifest.mode
        cfg.llm_model          = manifest.llm_model
        cfg.domain_classes     = manifest.domain_classes or []
        cfg.domain_relationships = manifest.domain_relationships or []
        cfg.write_permissions  = manifest.write_permissions or []
        cfg.session_cache_ttl  = manifest.session_cache_ttl
        cfg.system_prompt      = manifest.system_prompt
        cfg.has_code           = manifest.execution_context is not None
        cfg.generated_tools    = [t.model_dump() for t in (manifest.generated_tools or [])]
        cfg.improvement_policy = (
            manifest.improvement_policy.model_dump() if manifest.improvement_policy else None
        )
        cfg.accepts_delegation = manifest.accepts_delegation
        cfg.agent_peers        = manifest.agent_peers or []
        if manifest.capabilities:
            cfg.capabilities = CapabilityManifest(**manifest.capabilities.model_dump())

        class _ScaffoldedPlugin(Plugin):
            def transform_data(self, nodes, payloads):
                return nodes

        PluginRegistry.register(_ScaffoldedPlugin(cfg))

    except Exception as e:
        return {
            "success":          True,
            "id":               plugin_id,
            "scaffolded_at":    str(plugin_dir),
            "registry_warning": (
                f"Scaffolded OK. Live registration failed: {e}. Restart to load."
            ),
        }

    return {"success": True, "id": plugin_id, "scaffolded_at": str(plugin_dir)}


# ── Agent call ─────────────────────────────────────────────────────────────────

class AgentRequest(BaseModel):
    action:     Optional[str]            = None
    params:     Optional[Dict[str, Any]] = None
    message:    Optional[str]            = None
    session_id: Optional[str]            = None
    # Orchestrator sets this when calling in delegated mode
    delegated:  bool                     = False
    caller:     Optional[str]            = None


@router.post("/{plugin_id}/agent")
async def call_plugin_agent(plugin_id: str, req: AgentRequest):
    """
    Unified agent endpoint.
    - action+params   → typed tool call
    - message         → natural language, goes through handle()
    - delegated=True  → goes through forward() directly (no routing)
    """
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    agent_module_path = PLUGINS_DIR / plugin_id / "agent.py"
    if agent_module_path.exists():
        import importlib.util
        spec   = importlib.util.spec_from_file_location(
            f"plugins.{plugin_id}.agent", agent_module_path
        )
        module = importlib.util.module_from_spec(spec)   # type: ignore[arg-type]
        spec.loader.exec_module(module)                  # type: ignore[union-attr]

        # DELEGATED mode: bypass routing, go straight to forward()
        if req.delegated and hasattr(module, "forward"):
            return await module.forward(req.dict())

        if hasattr(module, "handle"):
            return await module.handle(req.dict())

    name = (
        getattr(plugin, "name", None)
        or getattr(getattr(plugin, "config", None), "name", plugin_id)
    )
    return {
        "success":      True,
        "plugin_id":    plugin_id,
        "action":       req.action,
        "answer":       (
            f"[{name}] implement handle() in plugins/{plugin_id}/agent.py"
        ),
        "results":      [],
        "result_count": 0,
    }


# ── Activate / Deactivate ──────────────────────────────────────────────────────

@router.post("/{plugin_id}/activate")
async def activate_plugin(plugin_id: str):
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    PluginRegistry.activate(plugin_id)
    name = getattr(plugin, "name", None) or getattr(getattr(plugin, "config", None), "name", plugin_id)
    return {"success": True, "message": f"Plugin '{name}' activated"}


@router.post("/{plugin_id}/deactivate")
async def deactivate_plugin(plugin_id: str):
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    PluginRegistry.deactivate(plugin_id)
    name = getattr(plugin, "name", None) or getattr(getattr(plugin, "config", None), "name", plugin_id)
    return {"success": True, "message": f"Plugin '{name}' deactivated"}


# ── Delete ─────────────────────────────────────────────────────────────────────

@router.delete("/{plugin_id}")
def delete_plugin(plugin_id: str):
    if plugin_id in _SYSTEM_PLUGINS:
        raise HTTPException(
            status_code=403,
            detail=f"'{plugin_id}' is a system plugin and cannot be deleted.",
        )
    if not PluginRegistry.get(plugin_id):
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    if hasattr(PluginRegistry, "deregister"):
        PluginRegistry.deregister(plugin_id)
    else:
        getattr(PluginRegistry, "_plugins", {}).pop(plugin_id, None)
        getattr(PluginRegistry, "_configs", {}).pop(plugin_id, None)

    plugin_dir = PLUGINS_DIR / plugin_id
    if plugin_dir.exists():
        shutil.rmtree(plugin_dir)

    for path in [
        DATA_DIR / "plugin_manifests" / f"{plugin_id}.json",
        DATA_DIR / "plugins"          / f"{plugin_id}.json",
    ]:
        path.unlink(missing_ok=True)

    return {"success": True, "deleted": plugin_id}


# ── Logging & stats ────────────────────────────────────────────────────────────

class InteractionLog(BaseModel):
    question:     str
    sparql:       Optional[str]       = None
    result_count: int                 = 0
    timing_ms:    Optional[int]       = None
    outcome:      str                 = "auto"
    tool_names:   Optional[List[str]] = []
    error:        Optional[str]       = None
    delegated:    bool                = False   # was this call from orchestrator?


@router.post("/{plugin_id}/log-interaction")
def log_interaction(plugin_id: str, log: InteractionLog):
    entry = {"ts": datetime.now(timezone.utc).isoformat(), **log.dict()}
    with open(_log_dir(plugin_id) / "interactions.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")
    return {"success": True}


@router.get("/{plugin_id}/stats")
def get_plugin_stats(plugin_id: str, days: int = 14):
    log_path = _log_dir(plugin_id) / "interactions.jsonl"
    if not log_path.exists():
        return {
            "success": True, "interactions": [], "tool_usage": [],
            "totals": {
                "interactions": 0, "confirmed": 0, "rejected": 0, "auto": 0,
                "delegated": 0, "correction_rate": 0.0,
            },
        }

    cutoff  = datetime.now(timezone.utc) - timedelta(days=days)
    entries = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                if e.get("ts", "") >= cutoff.isoformat():
                    entries.append(e)
            except Exception:
                pass

    by_date: dict     = defaultdict(lambda: {"interactions": 0, "confirmed": 0, "rejected": 0, "auto": 0, "delegated": 0})
    tool_counts: dict = defaultdict(int)

    for e in entries:
        date    = e["ts"][:10]
        outcome = e.get("outcome", "auto")
        by_date[date]["interactions"] += 1
        by_date[date][outcome]         = by_date[date].get(outcome, 0) + 1
        if e.get("delegated"):
            by_date[date]["delegated"] += 1
        for t in (e.get("tool_names") or []):
            tool_counts[t] += 1

    metrics = []
    for date in sorted(by_date.keys()):
        d_data    = by_date[date]
        total     = d_data["interactions"]
        rejected  = d_data.get("rejected", 0) + d_data.get("auto", 0)
        confirmed = d_data.get("confirmed", 0)
        metrics.append({
            "date":            date,
            "interactions":    total,
            "approved":        confirmed,
            "rejected":        rejected,
            "delegated":       d_data.get("delegated", 0),
            "modified":        0,
            "correction_rate": round(rejected / total, 3) if total else 0.0,
        })

    tool_usage = [
        {"name": k, "calls": v, "source": "ontology"}
        for k, v in sorted(tool_counts.items(), key=lambda x: -x[1])
    ]

    totals: dict = {"interactions": 0, "confirmed": 0, "rejected": 0, "auto": 0, "delegated": 0}
    for e in entries:
        totals["interactions"] += 1
        key = e.get("outcome", "auto")
        totals[key]     = totals.get(key, 0) + 1
        totals["delegated"] += int(bool(e.get("delegated")))

    total           = totals["interactions"]
    correction_rate = round(totals.get("rejected", 0) / total, 3) if total else 0.0

    return {
        "success":      True,
        "interactions": metrics,
        "tool_usage":   tool_usage,
        "totals":       {**totals, "correction_rate": correction_rate},
    }


# ── Prompt management ──────────────────────────────────────────────────────────

class UpdatePromptRequest(BaseModel):
    system_prompt: str


@router.post("/{plugin_id}/update-prompt")
def update_prompt(plugin_id: str, req: UpdatePromptRequest):
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    agent_path = PLUGINS_DIR / plugin_id / "agent.py"
    if not agent_path.exists():
        raise HTTPException(status_code=404, detail=f"agent.py not found for '{plugin_id}'")

    src    = agent_path.read_text()
    m_old  = re.search(r'SYSTEM_PROMPT\s*=\s*"""(.*?)"""', src, re.DOTALL)
    old_prompt = m_old.group(1).strip() if m_old else ""

    changed = _write_system_prompt_to_agent(agent_path, req.system_prompt)
    if not changed and old_prompt == req.system_prompt.strip():
        return {"success": True, "changed": False}

    _update_live_config(plugin_id, system_prompt=req.system_prompt)

    d            = _log_dir(plugin_id)
    history_path = d / "prompt_history.json"
    history      = []
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text())
        except Exception:
            pass

    version = len(history) + 1
    history.append({
        "version":     version,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "approved_by": "operator",
        "prompt":      req.system_prompt,
        "old_prompt":  old_prompt,
        "summary":     f"Manual edit via dashboard (v{version})",
    })
    history_path.write_text(json.dumps(history, indent=2))
    return {"success": True, "changed": True, "version": version}


@router.get("/{plugin_id}/prompt-history")
def get_prompt_history(plugin_id: str):
    history_path = _log_dir(plugin_id) / "prompt_history.json"
    if not history_path.exists():
        return {"success": True, "history": []}
    try:
        return {"success": True, "history": json.loads(history_path.read_text())}
    except Exception as e:
        return {"success": False, "error": str(e), "history": []}


@router.get("/{plugin_id}/prompt")
def get_current_prompt(plugin_id: str):
    agent_path = PLUGINS_DIR / plugin_id / "agent.py"
    if not agent_path.exists():
        return {"success": False, "prompt": ""}
    content = agent_path.read_text()
    m       = re.search(r'SYSTEM_PROMPT\s*=\s*"""(.*?)"""', content, re.DOTALL)
    return {"success": True, "prompt": m.group(1).strip() if m else ""}


# ── Patch config ───────────────────────────────────────────────────────────────

class PatchConfigRequest(BaseModel):
    system_prompt:      Optional[str]            = None
    llm_model:          Optional[str]            = None
    session_cache_ttl:  Optional[int]            = None
    filters:            Optional[Dict[str, Any]] = None
    accepts_delegation: Optional[bool]           = None
    agent_peers:        Optional[List[str]]      = None
    capabilities:       Optional[Dict[str, Any]] = None


@router.patch("/{plugin_id}/config")
def patch_plugin_config(plugin_id: str, req: PatchConfigRequest):
    """
    Live-update a plugin's config. Changes take effect immediately.
    Now also supports patching multi-agent fields (delegation, peers, capabilities).
    """
    if not PluginRegistry.get(plugin_id):
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    live_updates:     Dict[str, Any] = {}
    manifest_updates: Dict[str, Any] = {}

    if req.system_prompt is not None:
        _write_system_prompt_to_agent(PLUGINS_DIR / plugin_id / "agent.py", req.system_prompt)
        live_updates["system_prompt"]     = req.system_prompt
        manifest_updates["system_prompt"] = req.system_prompt

    if req.llm_model is not None:
        live_updates["llm_model"]     = req.llm_model
        manifest_updates["llm_model"] = req.llm_model

    if req.session_cache_ttl is not None:
        live_updates["session_cache_ttl"]     = req.session_cache_ttl
        manifest_updates["session_cache_ttl"] = req.session_cache_ttl

    if req.filters is not None:
        live_updates["filters"]     = req.filters
        manifest_updates["filters"] = req.filters

    if req.accepts_delegation is not None:
        live_updates["accepts_delegation"]     = req.accepts_delegation
        manifest_updates["accepts_delegation"] = req.accepts_delegation

    if req.agent_peers is not None:
        live_updates["agent_peers"]     = req.agent_peers
        manifest_updates["agent_peers"] = req.agent_peers

    if req.capabilities is not None:
        cap = CapabilityManifest(**req.capabilities)
        live_updates["capabilities"]     = cap
        manifest_updates["capabilities"] = req.capabilities

    _update_live_config(plugin_id, **live_updates)
    _persist_manifest_patch(plugin_id, **manifest_updates)

    # Refresh orchestrator routing table
    config = PluginRegistry.get_config(plugin_id)
    if config:
        OrchestratorRegistry.refresh(config)

    return {
        "success":   True,
        "plugin_id": plugin_id,
        "patched":   req.dict(exclude_none=True),
    }


@router.get("/{plugin_id}/config")
def get_plugin_config(plugin_id: str):
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    cfg = getattr(plugin, "config", plugin)
    return {
        "success":            True,
        "plugin_id":          plugin_id,
        "system_prompt":      getattr(cfg, "system_prompt", None),
        "llm_model":          getattr(cfg, "llm_model", None),
        "session_cache_ttl":  getattr(cfg, "session_cache_ttl", 300),
        "domain_classes":     getattr(cfg, "domain_classes", []),
        "write_permissions":  getattr(cfg, "write_permissions", []),
        "filters":            getattr(cfg, "filters", {}),
        "mode":               getattr(cfg, "mode", "action"),
        "accepts_delegation": getattr(cfg, "accepts_delegation", False),
        "agent_peers":        getattr(cfg, "agent_peers", []),
        "capabilities":       getattr(cfg, "capabilities", None),
    }


# ── Scaffolding helpers ────────────────────────────────────────────────────────

def _ensure_init(d: Path) -> None:
    init = d / "__init__.py"
    if not init.exists():
        init.write_text("# Auto-generated by ProtoGraph App Onboarding\n")


def _write_domain_py(d: Path, m: RegisterManifest) -> None:
    L = []
    L.append('"""\n')
    L.append(f"Domain boundary for {m.name}.\n")
    L.append("Auto-generated by ProtoGraph App Onboarding — edit freely.\n")
    L.append('"""\n\n')
    L.append(f"DOMAIN_CLASSES = {m.domain_classes!r}\n")
    L.append(f"DOMAIN_RELATIONSHIPS = {m.domain_relationships!r}\n")
    L.append(f"WRITE_PERMISSIONS = {m.write_permissions!r}\n")
    L.append(f"MODE = {m.mode!r}\n")
    L.append(f"ACCEPTS_DELEGATION = {m.accepts_delegation!r}\n")
    L.append(f"AGENT_PEERS = {(m.agent_peers or [])!r}\n")
    (d / "domain.py").write_text("".join(L))


def _code_module_from_manifest(m: RegisterManifest):
    code_module = ""
    if m.execution_context and m.execution_context.start_command:
        cmd = m.execution_context.start_command.strip()
        if "-m " in cmd:
            code_module = cmd.split("-m ")[-1].strip().split()[0]
        elif cmd.startswith("./") or cmd.startswith("/"):
            code_module = cmd.lstrip("./").split()[0].replace(".py", "")
    class_name = (
        "".join(w.capitalize() for w in code_module.replace("_", " ").split())
        if code_module else ""
    )
    return code_module, class_name


def _write_tools_py(d: Path, m: RegisterManifest) -> None:
    code_module, class_name = _code_module_from_manifest(m)
    L = []
    L.append(f'"""Typed tool set for {m.name}. Auto-generated — add domain logic here."""\n')
    L.append("from typing import Any, Dict, List, Optional\n\n")

    for t in (m.generated_tools or []):
        arg_types = t.arg_types or {}
        arg_sig   = ", ".join(f"{a}: {typ}" for a, typ in arg_types.items())
        arg_call  = ", ".join(f"{a}={a}" for a in arg_types.keys())
        desc      = (t.description or t.name).replace("\n", " ")
        ret_type  = t.return_type or "Any"

        L.append(f"def {t.name}({arg_sig}):\n")
        L.append('    """\n')
        L.append(f"    {desc}\n")
        L.append(f"    Return type: {ret_type}\n")
        L.append('    """\n')

        is_code_tool = (
            t.source == "code_analysis"
            and code_module
            and t.name not in ("program_start", "program_stop", "program_status")
        )
        if is_code_tool:
            method = t.name[len("exec_"):] if t.name.startswith("exec_") else t.name
            L.append("    import importlib, os, sys\n")
            L.append("    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n")
            L.append(f"    mod = importlib.import_module({code_module!r})\n")
            L.append(f"    cls = getattr(mod, {class_name!r}, None)\n")
            L.append("    if cls is None:\n")
            L.append(f"        raise RuntimeError(f'Class {class_name!r} not found in {code_module!r}')\n")
            L.append(f"    return cls().{method}({arg_call})\n")
        else:
            L.append(f"    raise NotImplementedError('Implement {t.name} in tools.py')\n")
        L.append("\n")

    (d / "tools.py").write_text("".join(L))


def _write_agent_py(d: Path, m: RegisterManifest) -> None:
    """
    Generate agent.py.

    Two entry points are scaffolded:

      handle(req)  — STANDALONE mode. Called by humans via the API.
                     Runs full intent classification → tool dispatch → narration.
                     Uses the ADAS-informed prompt structure:
                     expertise claim first, then rules, then schema.

      forward(req) — DELEGATED mode. Called by the Orchestrator.
                     Checks req['delegated'] == True, then executes the task
                     directly without routing overhead. Trusts the caller.

    The system prompts follow the ADAS meta-agent pattern from Hu, Lu & Clune
    (2024): the role claim comes first ("You are an expert X"), followed by
    scope, then schema. This consistently produces more reliable output than
    instruction-first prompts.

    Code generation safety: list-append pattern, no outer f-strings,
    triple-quote content sanitised. See endpoints.py module docstring.
    """
    plugin_id              = m.id
    prompt_body            = _sanitise_for_triple_quote((m.system_prompt or "").strip())
    code_module, class_name = _code_module_from_manifest(m)
    agent_name             = m.name
    domain_classes_str     = ", ".join(m.domain_classes or []) or "general"

    code_tools = [
        t for t in (m.generated_tools or [])
        if t.source == "code_analysis"
        and t.name not in ("program_start", "program_stop", "program_status")
    ]
    has_code_tools = bool(code_tools and code_module)

    def _tool_sig(t: GeneratedTool) -> str:
        args   = ", ".join(f"{a} ({typ})" for a, typ in (t.arg_types or {}).items())
        method = t.name[len("exec_"):] if t.name.startswith("exec_") else t.name
        desc   = _sanitise_for_triple_quote(t.description or t.name)
        return f"  {method}({args}) - {desc}"

    router_tools   = "\n".join(_tool_sig(t) for t in code_tools)
    dispatch_tools = "\n".join(
        "  " + (t.name[len("exec_"):] if t.name.startswith("exec_") else t.name)
        + "(" + ", ".join(f"{a} ({typ})" for a, typ in (t.arg_types or {}).items()) + ")"
        for t in code_tools
    )

    default_intent       = "tool_call" if has_code_tools else "graph_query"
    accepts_delegation_r = repr(m.accepts_delegation)

    L = []

    # ── Imports ────────────────────────────────────────────────────────────────
    L.append("import json\n")
    L.append("import os\n")
    L.append("import sys\n")
    L.append("from typing import Any, Dict, Optional\n\n")
    L.append("from llm_client import chat_completion\n")
    L.append("from plugins.proposal_engine import log_interaction as _log_interaction\n\n")
    L.append(f"PLUGIN_ID = {plugin_id!r}\n")
    L.append(f"ACCEPTS_DELEGATION = {accepts_delegation_r}\n\n")

    if has_code_tools:
        L.append("import os as _os, sys as _sys\n")
        L.append("_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))\n")
        L.append(f"from {code_module} import {class_name}  # noqa: E402\n")
        L.append(f"TOOLS = {class_name}()\n\n")

    # ── Config accessor ────────────────────────────────────────────────────────
    L.append("\ndef get_config():\n")
    L.append("    from plugins.base import PluginRegistry\n")
    L.append("    config = PluginRegistry.get_config(PLUGIN_ID)\n")
    L.append("    if not config:\n")
    L.append('        raise RuntimeError(f"Plugin {PLUGIN_ID!r} is not registered.")\n')
    L.append("    return config\n\n\n")

    # ── SYSTEM_PROMPT ──────────────────────────────────────────────────────────
    # ADAS pattern: expertise claim first, then scope, then rules.
    # The prompt_body from the manifest is the operator-supplied system prompt.
    # We prepend the role claim so even a blank manifest prompt still anchors
    # the model correctly.
    L.append('SYSTEM_PROMPT = """\n')
    L.append(f"You are a specialist agent for {agent_name}.\n")
    L.append(f"Your domain: {domain_classes_str}.\n\n")
    if prompt_body:
        L.append(prompt_body + "\n")
    L.append('"""\n\n\n')

    # ── ROUTER_SYSTEM ──────────────────────────────────────────────────────────
    # Used in STANDALONE mode only. ADAS pattern: expertise claim first.
    L.append('ROUTER_SYSTEM = """\n')
    L.append(f"You are an expert intent classifier for the {agent_name} agent.\n")
    L.append(f"This agent specialises in: {domain_classes_str}.\n\n")
    L.append("Return ONLY valid JSON matching this schema:\n")
    L.append('{"intent": "tool_call"|"direct_answer"|"decline", "answer": "<string or null>"}\n\n')
    L.append("- direct_answer: the user is asking who you are or what you can do\n")
    L.append("- tool_call: the user wants to use the agent tools — default when in doubt\n")
    L.append("- decline: ONLY if the request is completely outside the domain above\n\n")
    L.append("Available tools:\n")
    L.append(router_tools + "\n")
    L.append('"""\n\n\n')

    # ── DISPATCH_SYSTEM ────────────────────────────────────────────────────────
    L.append('DISPATCH_SYSTEM = """\n')
    L.append(f"You are a tool dispatcher for the {agent_name} agent.\n")
    L.append("Return ONLY valid JSON:\n")
    L.append('{"tool": "<tool_name>", "args": {"arg1": value1}}\n\n')
    L.append("Available tools:\n")
    L.append(dispatch_tools + "\n\n")
    L.append("Rules:\n")
    L.append("- Use exact tool names as listed\n")
    L.append("- Convert numeric strings to actual numbers\n")
    L.append('"""\n\n\n')

    # ── NARRATE_SYSTEM ─────────────────────────────────────────────────────────
    L.append('NARRATE_SYSTEM = """\n')
    L.append(f"You are a narration assistant for the {agent_name} agent.\n")
    L.append("The tool result is ground truth. Do NOT correct or recompute any value.\n")
    L.append("Quote numbers and strings exactly as given. Keep it to 1-2 sentences.\n")
    L.append('"""\n\n\n')

    # ── Utilities ──────────────────────────────────────────────────────────────
    L.append("def _parse_json(raw: str) -> dict:\n")
    L.append('    clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()\n')
    L.append("    return json.loads(clean)\n\n\n")

    L.append("def _format_result(result) -> str:\n")
    L.append("    if not isinstance(result, dict):\n")
    L.append("        return str(result)\n")
    L.append('    for key in ("hash", "encoded", "decoded", "password", "result", "reversed"):\n')
    L.append("        if key in result:\n")
    L.append("            return str(result[key])\n")
    L.append('    if "files" in result:\n')
    L.append("        count = result.get('count', 0)\n")
    L.append("        directory = result.get('directory', '.')\n")
    L.append("        files = result['files']\n")
    L.append('        return f"{count} file(s) in {directory}: {files}"\n')
    L.append('    if "error" in result:\n')
    L.append("        error = result['error']\n")
    L.append('        return f"Error: {error}"\n')
    L.append("    return json.dumps(result)\n\n\n")

    L.append('def _error_response(detail: str, action: str = "") -> Dict[str, Any]:\n')
    L.append("    return {\n")
    L.append('        "success": False, "plugin_id": PLUGIN_ID, "action": action,\n')
    L.append('        "answer": f"Error: {detail}", "results": [], "result_count": 0,\n')
    L.append('        "error": detail,\n')
    L.append("    }\n\n\n")

    # ── forward() — DELEGATED mode ─────────────────────────────────────────────
    # This is the Orchestrator-facing entry point. No routing, no classification.
    # The orchestrator already decided this agent should handle the task.
    # Pattern mirrors HyperAgents task_agent.forward() — minimal, trusting,
    # focused only on execution.
    L.append("async def forward(req: Dict[str, Any]) -> Dict[str, Any]:\n")
    L.append('    """\n')
    L.append("    DELEGATED mode entry point.\n")
    L.append("    Called by the Orchestrator — routing has already happened.\n")
    L.append("    Executes the task directly without intent classification.\n")
    L.append('    """\n')
    L.append("    if not ACCEPTS_DELEGATION:\n")
    L.append('        return _error_response("This agent does not accept delegated tasks")\n\n')
    L.append('    task    = req.get("task") or req.get("message") or ""\n')
    L.append('    context = req.get("context") or {}\n\n')
    L.append(f"    if {has_code_tools!r}:\n")
    L.append("        return await _tool_call(task, get_config(), context=context)\n")
    L.append("    return await _graph_query(task, get_config())\n\n\n")

    # ── handle() — STANDALONE mode ─────────────────────────────────────────────
    L.append("async def handle(req: Dict[str, Any]) -> Dict[str, Any]:\n")
    L.append('    """\n')
    L.append("    STANDALONE mode entry point.\n")
    L.append("    Called by humans via the API or dashboard.\n")
    L.append("    Runs full intent classification before execution.\n")
    L.append('    """\n')
    L.append("    # If the orchestrator is calling handle() (e.g. agent has no forward yet),\n")
    L.append("    # skip classification and go straight to execution.\n")
    L.append('    if req.get("delegated"):\n')
    L.append("        return await forward(req)\n\n")
    L.append("    config  = get_config()\n")
    L.append('    message = req.get("message") or req.get("query") or ""\n')
    L.append('    action  = req.get("action")\n\n')
    L.append("    if action and not message:\n")
    L.append('        return await _dispatch_action(action, req.get("params") or {})\n')
    L.append("    if not message:\n")
    L.append('        return _error_response("No message or action provided")\n\n')
    L.append("    # Intent classification — STANDALONE only\n")
    L.append("    try:\n")
    L.append("        raw = await chat_completion(\n")
    L.append('            f"User message: {message!r}\\n\\nClassify intent.",\n')
    L.append("            system=ROUTER_SYSTEM,\n")
    L.append("            model=config.llm_model,\n")
    L.append("            temperature=0.0,\n")
    L.append("        )\n")
    L.append("        decision = _parse_json(raw)\n")
    L.append("    except Exception:\n")
    L.append(f'        decision = {{"intent": {default_intent!r}}}\n\n')
    L.append(f'    intent = decision.get("intent", {default_intent!r})\n\n')
    L.append('    if intent in ("direct_answer", "decline") and decision.get("answer"):\n')
    L.append("        _log_interaction(PLUGIN_ID, {\n")
    L.append('            "question": message, "outcome": "auto",\n')
    L.append('            "tool_names": [], "result_count": 0,\n')
    L.append("        })\n")
    L.append("        return {\n")
    L.append('            "success": True, "plugin_id": PLUGIN_ID, "intent": intent,\n')
    L.append('            "answer": decision["answer"], "results": [], "result_count": 0,\n')
    L.append("        }\n\n")
    L.append(f"    if {has_code_tools!r}:\n")
    L.append("        result = await _tool_call(message, config)\n")
    L.append("    else:\n")
    L.append("        result = await _graph_query(message, config)\n\n")
    L.append("    _log_interaction(PLUGIN_ID, {\n")
    L.append('        "question":     message,\n')
    L.append('        "outcome":      "auto",\n')
    L.append('        "tool_names":   [result.get("tool")] if result.get("tool") else [],\n')
    L.append('        "result_count": result.get("result_count", 0),\n')
    L.append('        "error":        result.get("error"),\n')
    L.append('        "timing_ms":    result.get("timing_ms"),\n')
    L.append("    })\n")
    L.append("    return result\n\n\n")

    # ── _tool_call() ───────────────────────────────────────────────────────────
    L.append("async def _tool_call(message: str, config, context: dict = {}) -> Dict[str, Any]:\n")
    L.append("    try:\n")
    L.append("        raw = await chat_completion(\n")
    L.append('            f"User message: {message!r}\\n\\nContext: {context!r}\\n\\nWhich tool and args?",\n')
    L.append("            system=DISPATCH_SYSTEM,\n")
    L.append("            model=config.llm_model,\n")
    L.append("            temperature=0.0,\n")
    L.append("        )\n")
    L.append("        dispatch  = _parse_json(raw)\n")
    L.append('        tool_name = dispatch.get("tool", "")\n')
    L.append('        args      = dispatch.get("args", {})\n')
    L.append("    except Exception as e:\n")
    L.append('        return _error_response(f"Dispatch failed: {e}")\n\n')
    L.append("    fn = getattr(TOOLS, tool_name, None)\n")
    L.append("    if fn is None:\n")
    L.append('        return _error_response(f"Unknown tool: {tool_name!r}")\n\n')
    L.append("    try:\n")
    L.append("        result = fn(**args)\n")
    L.append("    except Exception as e:\n")
    L.append('        return _error_response(f"Tool error in {tool_name}: {e}")\n\n')
    L.append("    canonical = _format_result(result)\n\n")
    L.append("    try:\n")
    L.append("        narration = await chat_completion(\n")
    L.append("            (\n")
    L.append('                f"User asked: {message!r}\\n"\n')
    L.append('                f"Tool {tool_name}({args}) returned: {canonical!r}\\n\\n"\n')
    L.append('                "Write 1-2 sentences presenting that result."\n')
    L.append("            ),\n")
    L.append("            system=NARRATE_SYSTEM,\n")
    L.append("            model=config.llm_model,\n")
    L.append("            temperature=0.1,\n")
    L.append("        )\n")
    L.append('        answer = f"{narration}\\n  \\u21b3 {canonical}"\n')
    L.append("    except Exception:\n")
    L.append('        answer = f"Tool result: {canonical}"\n\n')
    L.append("    success = result.get('success', True) if isinstance(result, dict) else True\n")
    L.append("    return {\n")
    L.append('        "success": success, "plugin_id": PLUGIN_ID, "intent": "tool_call",\n')
    L.append('        "tool": tool_name, "answer": answer,\n')
    L.append('        "results": [result], "result_count": 1,\n')
    L.append("    }\n\n\n")

    # ── _graph_query() ─────────────────────────────────────────────────────────
    L.append("async def _graph_query(message: str, config) -> Dict[str, Any]:\n")
    L.append("    try:\n")
    L.append("        from nl_query_engine import natural_language_query, NaturalQueryRequest\n")
    L.append("        result = await natural_language_query(NaturalQueryRequest(question=message, show_sparql=True))\n")
    L.append("        result = result.dict()\n")
    L.append('        if result.get("success") and result.get("results"):\n')
    L.append("            narration = await chat_completion(\n")
    L.append("                (\n")
    L.append('                    f"User asked: {message!r}\\n"\n')
    L.append('                    f"Graph returned {result[\'result_count\']} result(s):\\n"\n')
    L.append('                    f"{json.dumps(result[\'results\'][:20], indent=2)}\\n"\n')
    L.append('                    "Write a concise answer."\n')
    L.append("                ),\n")
    L.append("                system=config.system_prompt,\n")
    L.append("                model=config.llm_model,\n")
    L.append("                temperature=0.1,\n")
    L.append("            )\n")
    L.append("        else:\n")
    L.append('            narration = result.get("answer", "No results found.")\n')
    L.append("        return {\n")
    L.append('            "success": result.get("success", False), "plugin_id": PLUGIN_ID,\n')
    L.append('            "intent": "graph_query", "answer": narration,\n')
    L.append('            "sparql": result.get("sparql"), "results": result.get("results", []),\n')
    L.append('            "result_count": result.get("result_count", 0),\n')
    L.append('            "timing_ms": result.get("timing_ms"),\n')
    L.append("        }\n")
    L.append("    except Exception as e:\n")
    L.append("        return _error_response(str(e))\n\n\n")

    # ── _dispatch_action() — direct tool inspector calls ───────────────────────
    L.append("async def _dispatch_action(action: str, params: Dict[str, Any]) -> Dict[str, Any]:\n")
    L.append('    """Handle direct tool calls from the Tool Inspector."""\n')
    L.append(f"    fn = getattr(TOOLS, action, None) if {has_code_tools!r} else None\n")
    L.append("    if fn is None:\n")
    L.append('        return _error_response(f"Tool {action!r} not found", action=action)\n')
    L.append("    try:\n")
    L.append("        result    = fn(**params)\n")
    L.append("        canonical = _format_result(result)\n")
    L.append("        return {\n")
    L.append('            "success": True, "plugin_id": PLUGIN_ID, "intent": "action",\n')
    L.append('            "action": action, "answer": canonical,\n')
    L.append('            "results": [result] if result is not None else [],\n')
    L.append('            "result_count": 1 if result is not None else 0,\n')
    L.append("        }\n")
    L.append("    except Exception as e:\n")
    L.append("        return _error_response(str(e), action=action)\n")

    agent_code = "".join(L)
    agent_path = d / "agent.py"
    if not agent_path.exists():
        agent_path.write_text(agent_code)