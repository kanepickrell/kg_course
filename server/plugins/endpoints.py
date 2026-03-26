#!/usr/bin/env python3
"""
Plugin Management Endpoints
============================
Handles plugin registry introspection and activate/deactivate controls.
Routes: GET/POST /api/plugins/*
Note: Actual data-serving routes (e.g. /api/plugins/operator/modules)
live in plugin_router.py, which is mounted separately.
"""
import json
import os
import re
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonlines  # pip install jsonlines
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .base import PluginRegistry

router = APIRouter(prefix="/api/plugins", tags=["plugins"])

PLUGINS_DIR = Path(__file__).parent
DATA_DIR    = Path(__file__).parent.parent / "data"
LOG_DIR     = DATA_DIR / "plugin_logs"


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _log_dir(plugin_id: str) -> Path:
    d = LOG_DIR / plugin_id
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Route order note ───────────────────────────────────────────────────────────
# Fixed paths (/register, /active, "") MUST be declared before parameterised
# paths (/{plugin_id}/...) so FastAPI does not match "register" as a plugin_id.

# ── List / introspect ──────────────────────────────────────────────────────────

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


# ── Register ───────────────────────────────────────────────────────────────────

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


@router.post("/register")
def register_plugin(manifest: RegisterManifest):
    """
    Register a new application from the AppOnboarding wizard manifest.
    1. Persists manifest to data/plugin_manifests/{id}.json
    2. Scaffolds plugins/{id}/ with domain.py, tools.py, agent.py
    3. Registers in live PluginRegistry
    4. Returns { id, success: true }
    Idempotent — re-registering overwrites domain.py and tools.py but preserves
    a manually edited agent.py if one already exists on disk.
    """
    plugin_id = _slugify(manifest.id) or _slugify(manifest.name)
    if not plugin_id:
        raise HTTPException(status_code=400, detail="id is required")

    # 1. Persist manifest
    manifests_dir = DATA_DIR / "plugin_manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    (manifests_dir / f"{plugin_id}.json").write_text(manifest.model_dump_json(indent=2))

    # 2. Scaffold plugin directory
    plugin_dir = PLUGINS_DIR / plugin_id
    plugin_dir.mkdir(exist_ok=True)
    _ensure_init(plugin_dir)
    _write_domain_py(plugin_dir, manifest)
    _write_tools_py(plugin_dir, manifest)
    # Only write agent.py if it does not already exist — preserves manual edits
    agent_path = plugin_dir / "agent.py"
    if not agent_path.exists():
        _write_agent_py(plugin_dir, manifest)

    # 3. Register in live PluginRegistry
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
        cfg.mode                 = manifest.mode
        cfg.llm_model            = manifest.llm_model
        cfg.domain_classes       = manifest.domain_classes or []
        cfg.domain_relationships = manifest.domain_relationships or []
        cfg.write_permissions    = manifest.write_permissions or []
        cfg.session_cache_ttl    = manifest.session_cache_ttl
        cfg.system_prompt        = manifest.system_prompt
        cfg.has_code             = manifest.execution_context is not None
        cfg.generated_tools      = [t.model_dump() for t in (manifest.generated_tools or [])]
        cfg.improvement_policy   = (
            manifest.improvement_policy.model_dump() if manifest.improvement_policy else None
        )

        class _ScaffoldedPlugin(Plugin):
            def transform_data(self, nodes, payloads):
                return nodes

        PluginRegistry.register(_ScaffoldedPlugin(cfg))

    except Exception as e:
        return {
            "success": True,
            "id": plugin_id,
            "scaffolded_at": str(plugin_dir),
            "registry_warning": (
                f"Scaffolded OK. Live registration failed: {e}. Restart server to load."
            ),
        }

    return {"success": True, "id": plugin_id, "scaffolded_at": str(plugin_dir)}


# ── Delete plugin ──────────────────────────────────────────────────────────────

@router.delete("/{plugin_id}")
def delete_plugin(plugin_id: str):
    """
    Fully remove a plugin:
      1. Deregister from live PluginRegistry
      2. Delete scaffolded plugins/{id}/ directory
      3. Delete data/plugin_manifests/{id}.json
      4. Delete data/plugins/{id}.json (persisted config)
    The operator plugin is protected and cannot be deleted via this endpoint.
    """
    if plugin_id == "operator":
        raise HTTPException(
            status_code=403,
            detail="The operator plugin is a system plugin and cannot be deleted.",
        )

    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    # 1. Remove from live registry
    PluginRegistry._plugins.pop(plugin_id, None)
    PluginRegistry._configs.pop(plugin_id, None)

    # 2. Delete scaffolded directory
    import shutil
    plugin_dir = PLUGINS_DIR / plugin_id
    if plugin_dir.exists():
        shutil.rmtree(plugin_dir)

    # 3. Delete manifest
    manifest_path = DATA_DIR / "plugin_manifests" / f"{plugin_id}.json"
    if manifest_path.exists():
        manifest_path.unlink()

    # 4. Delete persisted plugin config
    plugin_config_path = DATA_DIR / "plugins" / f"{plugin_id}.json"
    if plugin_config_path.exists():
        plugin_config_path.unlink()

    return {"success": True, "deleted": plugin_id}


# ── Agent call ─────────────────────────────────────────────────────────────────

class AgentRequest(BaseModel):
    action:     Optional[str]            = None
    params:     Optional[Dict[str, Any]] = None
    message:    Optional[str]            = None
    session_id: Optional[str]            = None


@router.post("/{plugin_id}/agent")
async def call_plugin_agent(plugin_id: str, req: AgentRequest):
    """
    Unified agent endpoint.
    action-based:   req.action + req.params → typed tool call
    conversational: req.message             → forwarded to agent handle()
    """
    # Validate plugin_id to prevent path traversal
    if not re.match(r'^[a-z0-9_]+$', plugin_id):
        raise HTTPException(status_code=400, detail="Invalid plugin_id")

    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    agent_module_path = PLUGINS_DIR / plugin_id / "agent.py"
    if agent_module_path.exists():
        spec   = importlib.util.spec_from_file_location(
            f"plugins.{plugin_id}.agent", agent_module_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
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
            f"[{name}] agent not yet initialised — "
            f"agent.py missing handle(). Re-register the plugin."
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
    name = (
        getattr(plugin, "name", None)
        or getattr(getattr(plugin, "config", None), "name", plugin_id)
    )
    return {"success": True, "message": f"Plugin '{name}' activated"}


@router.post("/{plugin_id}/deactivate")
async def deactivate_plugin(plugin_id: str):
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    PluginRegistry.deactivate(plugin_id)
    name = (
        getattr(plugin, "name", None)
        or getattr(getattr(plugin, "config", None), "name", plugin_id)
    )
    return {"success": True, "message": f"Plugin '{name}' deactivated"}


# ── Plugin logging & stats ─────────────────────────────────────────────────────

class InteractionLog(BaseModel):
    question:     str
    sparql:       Optional[str]       = None
    result_count: int                 = 0
    timing_ms:    Optional[int]       = None
    outcome:      str                 = "auto"   # "auto" | "confirmed" | "rejected"
    tool_names:   Optional[List[str]] = []
    error:        Optional[str]       = None


@router.post("/{plugin_id}/log-interaction")
def log_interaction(plugin_id: str, log: InteractionLog):
    """Record a single query interaction for this plugin."""
    d = _log_dir(plugin_id)
    entry = {"ts": datetime.now(timezone.utc).isoformat(), **log.dict()}
    with open(d / "interactions.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")
    return {"success": True}


@router.get("/{plugin_id}/stats")
def get_plugin_stats(plugin_id: str, days: int = 14):
    """Return real interaction stats for the performance tab."""
    from datetime import timedelta
    from collections import defaultdict

    log_path = _log_dir(plugin_id) / "interactions.jsonl"

    if not log_path.exists():
        return {
            "success": True,
            "interactions": [],
            "tool_usage": [],
            "totals": {
                "interactions": 0,
                "confirmed": 0,
                "rejected": 0,
                "auto": 0,
                "correction_rate": 0.0,
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

    by_date: dict    = defaultdict(lambda: {"interactions": 0, "confirmed": 0, "rejected": 0, "auto": 0})
    tool_counts: dict = defaultdict(int)

    for e in entries:
        date    = e["ts"][:10]
        outcome = e.get("outcome", "auto")
        by_date[date]["interactions"] += 1
        by_date[date][outcome] = by_date[date].get(outcome, 0) + 1
        for t in (e.get("tool_names") or []):
            tool_counts[t] += 1

    metrics = []
    for date in sorted(by_date.keys()):
        d_data    = by_date[date]
        total     = d_data["interactions"]
        confirmed = d_data.get("confirmed", 0)
        # unconfirmed (rejected + auto) = needs correction
        rejected  = d_data.get("rejected", 0) + d_data.get("auto", 0)
        metrics.append({
            "date":            date,
            "interactions":    total,
            "approved":        confirmed,
            "rejected":        rejected,
            "modified":        0,
            "correction_rate": round(rejected / total, 3) if total else 0.0,
        })

    tool_usage = [
        {"name": k, "calls": v, "source": "ontology"}
        for k, v in sorted(tool_counts.items(), key=lambda x: -x[1])
    ]

    totals: dict = {"interactions": 0, "confirmed": 0, "rejected": 0, "auto": 0}
    for e in entries:
        totals["interactions"] += 1
        key = e.get("outcome", "auto")
        totals[key] = totals.get(key, 0) + 1

    total           = totals["interactions"]
    # correction_rate counts both rejected and auto (unconfirmed)
    unconfirmed     = totals.get("rejected", 0) + totals.get("auto", 0)
    correction_rate = round(unconfirmed / total, 3) if total else 0.0

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
    """Write a new system prompt to plugins/{id}/agent.py and log the change."""
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    agent_path = PLUGINS_DIR / plugin_id / "agent.py"
    if not agent_path.exists():
        raise HTTPException(status_code=404, detail=f"agent.py not found for '{plugin_id}'")

    current = agent_path.read_text()

    # Extract old prompt for history
    old_prompt = ""
    m = re.search(r'^\s*SYSTEM_PROMPT\s*=\s*"""(.*?)"""', current, re.DOTALL | re.MULTILINE)
    if m:
        old_prompt = m.group(1).strip()

    # Guard: if the prompt contains """, escape it so we don't corrupt the file
    safe_prompt = req.system_prompt.replace('"""', "'''")

    new_prompt_block = f'SYSTEM_PROMPT = """\n{safe_prompt.strip()}\n"""'
    new_content = re.sub(
        r'^\s*SYSTEM_PROMPT\s*=\s*""".*?"""',
        new_prompt_block,
        current,
        flags=re.DOTALL | re.MULTILINE,
    )

    if new_content == current and old_prompt == req.system_prompt.strip():
        return {"success": True, "changed": False}

    agent_path.write_text(new_content)

    # Update live registry
    cfg = getattr(plugin, "config", plugin)
    try:
        cfg.system_prompt = req.system_prompt
    except Exception:
        pass

    # Log to prompt history
    history_path = _log_dir(plugin_id) / "prompt_history.json"
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
    """Read current SYSTEM_PROMPT from agent.py on disk."""
    agent_path = PLUGINS_DIR / plugin_id / "agent.py"
    if not agent_path.exists():
        return {"success": False, "prompt": ""}
    content = agent_path.read_text()
    m = re.search(r'^\s*SYSTEM_PROMPT\s*=\s*"""(.*?)"""', content, re.DOTALL | re.MULTILINE)
    prompt = m.group(1).strip() if m else ""
    return {"success": True, "prompt": prompt}


# ── Patch config (live update without restart) ─────────────────────────────────

class PatchConfigRequest(BaseModel):
    system_prompt:    Optional[str]            = None
    llm_model:        Optional[str]            = None
    session_cache_ttl: Optional[int]           = None
    filters:          Optional[Dict[str, Any]] = None


@router.patch("/{plugin_id}/config")
def patch_plugin_config(plugin_id: str, req: PatchConfigRequest):
    """
    Live-update a plugin's config in the registry AND persist to disk.
    Patchable fields: system_prompt, llm_model, session_cache_ttl, filters
    """
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    cfg = getattr(plugin, "config", plugin)

    if req.system_prompt is not None:
        cfg.system_prompt = req.system_prompt
        agent_path = PLUGINS_DIR / plugin_id / "agent.py"
        if agent_path.exists():
            src = agent_path.read_text()
            safe_prompt = req.system_prompt.replace('"""', "'''")
            new_block   = f'SYSTEM_PROMPT = """\n{safe_prompt.strip()}\n"""'
            new_src     = re.sub(
                r'^\s*SYSTEM_PROMPT\s*=\s*""".*?"""',
                "\n" + new_block,
                src,
                flags=re.DOTALL | re.MULTILINE,
            )
            agent_path.write_text(new_src)

    if req.llm_model is not None:
        cfg.llm_model = req.llm_model

    if req.session_cache_ttl is not None:
        cfg.session_cache_ttl = req.session_cache_ttl

    if req.filters is not None:
        existing = getattr(cfg, "filters", {}) or {}
        if isinstance(existing, dict):
            existing.update(req.filters)
        else:
            existing = req.filters
        cfg.filters = existing

    # Persist to manifest
    manifests_dir = DATA_DIR / "plugin_manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifests_dir / f"{plugin_id}.json"
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text())
            if req.system_prompt    is not None: data["system_prompt"]     = req.system_prompt
            if req.llm_model        is not None: data["llm_model"]         = req.llm_model
            if req.session_cache_ttl is not None: data["session_cache_ttl"] = req.session_cache_ttl
            if req.filters          is not None:
                data.setdefault("filters", {})
                if isinstance(data["filters"], dict):
                    data["filters"].update(req.filters)
                else:
                    data["filters"] = req.filters
            manifest_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            print(f"Failed to persist config patch for {plugin_id}: {e}")

    return {"success": True, "plugin_id": plugin_id, "patched": req.dict(exclude_none=True)}


@router.get("/{plugin_id}/config")
def get_plugin_config(plugin_id: str):
    """Return full live config including system_prompt, filters, intent_rules."""
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    cfg = getattr(plugin, "config", plugin)
    return {
        "success":           True,
        "plugin_id":         plugin_id,
        "system_prompt":     getattr(cfg, "system_prompt", None),
        "llm_model":         getattr(cfg, "llm_model", None),
        "session_cache_ttl": getattr(cfg, "session_cache_ttl", 300),
        "domain_classes":    getattr(cfg, "domain_classes", []),
        "write_permissions": getattr(cfg, "write_permissions", []),
        "filters":           getattr(cfg, "filters", {}),
        "mode":              getattr(cfg, "mode", "action"),
    }


# ── Scaffolding helpers ────────────────────────────────────────────────────────

def _ensure_init(d: Path):
    init = d / "__init__.py"
    if not init.exists():
        init.write_text("# Auto-generated by ProtoGraph App Onboarding\n")


def _write_domain_py(d: Path, m: RegisterManifest):
    lines = [
        '"""',
        f"Domain boundary for {m.name}.",
        "Auto-generated by ProtoGraph App Onboarding — edit freely.",
        '"""',
        "",
        "# OWL classes this agent can reason about",
        f"DOMAIN_CLASSES = {m.domain_classes!r}",
        "",
        "# Relationship types in scope",
        f"DOMAIN_RELATIONSHIPS = {m.domain_relationships!r}",
        "",
        "# Write permissions granted",
        f"WRITE_PERMISSIONS = {m.write_permissions!r}",
        "",
        "# Interaction mode: 'action' | 'conversational' | 'hybrid'",
        f"MODE = {m.mode!r}",
    ]
    (d / "domain.py").write_text("\n".join(lines) + "\n")


def _class_name_from_manifest(m: RegisterManifest):
    """
    Derive (ClassName, module_name) from execution_context.start_command.
    Handles: 'python -m simple_tools', './simple_tools.py', 'simple_tools.py'
    Returns ('', '') if not determinable.
    """
    if not m.execution_context:
        return "", ""
    cmd = (m.execution_context.start_command or "").strip()
    module = ""
    if "-m " in cmd:
        module = cmd.split("-m ")[-1].strip().split()[0]
    elif cmd.endswith(".py"):
        # Strip leading ./ and path components, drop extension
        module = cmd.rsplit("/", 1)[-1].replace(".py", "").lstrip("./")
    # Reject generic names that would collide with generated files
    if not module or module in ("tools", "agent", "domain", "__init__"):
        return "", ""
    class_name = "".join(w.capitalize() for w in module.replace("_", " ").split())
    return class_name, module


def _code_tools(m: RegisterManifest) -> list:
    """Return generated_tools that are code_analysis source and not lifecycle stubs."""
    _lifecycle = {"program_start", "program_stop", "program_status"}
    return [
        t for t in (m.generated_tools or [])
        if t.source == "code_analysis" and t.name not in _lifecycle
    ]


def _write_tools_py(d: Path, m: RegisterManifest):
    """
    Generate tools.py as reference documentation only.

    agent.py imports the uploaded class directly — tools.py is no longer the
    execution layer. Keeping it so the Tool Inspector can read signatures.
    No importlib wrappers, no quote-collision SyntaxErrors.
    """
    lines = [
        f'"""Tool signatures for {m.name}. Auto-generated — for reference only.',
        "",
        "agent.py imports the tool class directly. Edit agent.py to change behaviour.",
        '"""',
        "from typing import Any, Dict, List, Optional",
        "",
    ]

    for t in (m.generated_tools or []):
        arg_sig = ", ".join(f"{a}: {typ}" for a, typ in (t.arg_types or {}).items())
        desc    = t.description or t.name
        ret     = t.return_type or "Any"
        body = (
            f"def {t.name}({arg_sig}):\n"
            f'    """{desc}  ->  {ret}"""\n'
            f"    raise NotImplementedError({t.name!r})\n"
        )
        lines.append(body)

    (d / "tools.py").write_text("\n\n".join(lines) + "\n")


def _write_agent_py(d: Path, m: RegisterManifest):
    """
    Generate agent.py using the proven direct-import pattern.

    For code-tool agents:
      1. Scans the plugin directory for the uploaded .py file
         (anything that is not agent.py / tools.py / domain.py / __init__.py)
      2. Falls back to _class_name_from_manifest if file not found yet
      3. Generates: from <module> import <ClassName>; TOOLS = <ClassName>()
      4. Dispatcher calls getattr(TOOLS, tool_name) — no importlib, no SyntaxErrors

    For graph-only agents: unchanged behaviour.

    Only called when agent.py does not already exist — manual edits are safe.
    """
    plugin_id  = _slugify(m.id) or _slugify(m.name)
    exec_tools = _code_tools(m)
    has_code   = bool(exec_tools)
    prompt_body = (m.system_prompt or "").strip().replace('"""', "'''")

    # ── Graph-query-only agent ────────────────────────────────────────────────
    if not has_code:
        agent_code = (
            "import json\n"
            "from typing import Any, Dict\n"
            "\n"
            f"PLUGIN_ID = {plugin_id!r}\n"
            "\n"
            'SYSTEM_PROMPT = """\n'
            f"{prompt_body}\n"
            '"""\n'
            "\n"
            "def get_config():\n"
            "    from plugins.base import PluginRegistry\n"
            "    config = PluginRegistry.get_config(PLUGIN_ID)\n"
            "    if not config:\n"
            "        raise RuntimeError(f\"Plugin {PLUGIN_ID!r} is not registered.\")\n"
            "    return config\n"
            "\n"
            "\n"
            'ROUTER_SYSTEM = """You are a strict intent classifier. Return ONLY a JSON object.\n'
            'Schema: {"intent": "direct_answer"|"graph_query"|"decline", "confidence": 0.0-1.0, "reason": "<one sentence>", "answer": "<string or null>"}\n'
            "- direct_answer: user asks about agent identity or capabilities\n"
            "- graph_query: user asks about domain data\n"
            '- decline: outside domain"""\n'
            "\n"
            "\n"
            "async def handle(req: Dict[str, Any]) -> Dict[str, Any]:\n"
            "    config = get_config()\n"
            "    message = req.get(\"message\") or req.get(\"query\") or \"\"\n"
            "    if not message:\n"
            "        return _error_response(\"No message provided\")\n"
            "    from llm_client import chat_completion\n"
            "    try:\n"
            "        raw = await chat_completion(\n"
            "            f'User message: {json.dumps(message)}\\nClassify intent.',\n"
            "            system=ROUTER_SYSTEM, model=config.llm_model, temperature=0.0,\n"
            "        )\n"
            "        decision = json.loads(raw.strip().lstrip(\"```json\").lstrip(\"```\").rstrip(\"```\").strip())\n"
            "    except Exception:\n"
            "        decision = {\"intent\": \"graph_query\"}\n"
            "    intent = decision.get(\"intent\", \"graph_query\")\n"
            "    if intent == \"direct_answer\" and decision.get(\"answer\"):\n"
            "        return {\"success\": True, \"plugin_id\": PLUGIN_ID, \"intent\": \"direct_answer\",\n"
            "                \"answer\": decision[\"answer\"], \"results\": [], \"result_count\": 0}\n"
            "    if intent == \"decline\" and decision.get(\"answer\"):\n"
            "        return {\"success\": True, \"plugin_id\": PLUGIN_ID, \"intent\": \"decline\",\n"
            "                \"answer\": decision[\"answer\"], \"results\": [], \"result_count\": 0}\n"
            "    return await _graph_query(message, config)\n"
            "\n"
            "\n"
            "async def _graph_query(message: str, config) -> Dict[str, Any]:\n"
            "    try:\n"
            "        from nl_query_engine import natural_language_query, NaturalQueryRequest\n"
            "        from llm_client import chat_completion\n"
            "        result = await natural_language_query(NaturalQueryRequest(question=message, show_sparql=True))\n"
            "        result = result.dict()\n"
            "        if result.get(\"success\") and result.get(\"results\"):\n"
            "            narration = await chat_completion(\n"
            "                f'User asked: {json.dumps(message)}\\nGraph returned {result[\"result_count\"]} result(s):\\n{json.dumps(result[\"results\"][:20], indent=2)}\\nWrite a concise answer.',\n"
            "                system=config.system_prompt, model=config.llm_model, temperature=0.1,\n"
            "            )\n"
            "        else:\n"
            "            narration = result.get(\"answer\", \"No results found.\")\n"
            "        return {\"success\": result.get(\"success\", False), \"plugin_id\": PLUGIN_ID, \"intent\": \"graph_query\",\n"
            "                \"answer\": narration, \"sparql\": result.get(\"sparql\"), \"results\": result.get(\"results\", []),\n"
            "                \"result_count\": result.get(\"result_count\", 0), \"timing_ms\": result.get(\"timing_ms\")}\n"
            "    except Exception as e:\n"
            "        return _error_response(str(e))\n"
            "\n"
            "\n"
            "def _error_response(detail: str, action: str = \"\") -> Dict[str, Any]:\n"
            "    return {\"success\": False, \"plugin_id\": PLUGIN_ID, \"action\": action,\n"
            "            \"answer\": f\"Error: {detail}\", \"results\": [], \"result_count\": 0, \"error\": detail}\n"
        )
        (d / "agent.py").write_text(agent_code)
        return

    # ── Code-tool agent ───────────────────────────────────────────────────────
    # Find the uploaded module by scanning the plugin dir.
    # Excludes the four files we always generate ourselves.
    _generated = {"agent.py", "tools.py", "domain.py", "__init__.py"}
    uploaded_module = ""
    uploaded_class  = ""
    for f in sorted(d.iterdir()):
        if f.suffix == ".py" and f.name not in _generated:
            uploaded_module = f.stem
            uploaded_class  = "".join(w.capitalize() for w in uploaded_module.replace("_", " ").split())
            break

    # save-code hasn't run yet (register before upload) — fall back to manifest
    if not uploaded_module:
        uploaded_class, uploaded_module = _class_name_from_manifest(m)
    if not uploaded_module:
        # Last resort placeholder — agent.py will parse but fail gracefully at runtime
        uploaded_module = "tool_class"
        uploaded_class  = "ToolClass"

    # Build tool descriptions for the system prompts.
    # Use method names without the exec_ prefix — that's what TOOLS exposes.
    tool_desc_lines = "\n".join(
        "  {name}({args})  - {desc}".format(
            name=t.name.replace("exec_", "") if t.name.startswith("exec_") else t.name,
            args=", ".join(t.arg_types.keys()) if t.arg_types else "",
            desc=t.description or t.name,
        )
        for t in exec_tools
    )

    dispatch_tool_lines = "\n".join(
        "  {name}({args})".format(
            name=t.name.replace("exec_", "") if t.name.startswith("exec_") else t.name,
            args=", ".join(
                f"{a} ({typ})" for a, typ in (t.arg_types or {}).items()
            ),
        )
        for t in exec_tools
    )

    agent_code = (
        "import json\n"
        "import os\n"
        "import sys\n"
        "from typing import Any, Dict\n"
        "\n"
        "from llm_client import chat_completion\n"
        "\n"
        f"PLUGIN_ID = {plugin_id!r}\n"
        "\n"
        "# Direct import of the uploaded tool class — no importlib indirection.\n"
        "# If you upload a different file, update the import and class name below.\n"
        "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
        f"from {uploaded_module} import {uploaded_class}  # noqa: E402\n"
        f"TOOLS = {uploaded_class}()\n"
        "\n"
        "\n"
        "def get_config():\n"
        "    from plugins.base import PluginRegistry\n"
        "    config = PluginRegistry.get_config(PLUGIN_ID)\n"
        "    if not config:\n"
        f"        raise RuntimeError(f\"Plugin {plugin_id!r} is not registered.\")\n"
        "    return config\n"
        "\n"
        "\n"
        'SYSTEM_PROMPT = """\n'
        f"{prompt_body}\n"
        '"""\n'
        "\n"
        "\n"
        "ROUTER_SYSTEM = \"\"\"You are a strict intent classifier. Return ONLY valid JSON, no prose.\n"
        "\n"
        'Schema: {"intent": "tool_call"|"direct_answer"|"decline", "answer": "<string or null>"}\n'
        "\n"
        "- direct_answer: user asks who you are or what you can do\n"
        "- tool_call: user wants to use one of the agent tools — when in doubt, choose this\n"
        "- decline: ONLY if the request is completely unrelated to the agent domain\n"
        "\n"
        "Available tools:\n"
        f"{tool_desc_lines}\n"
        "\"\"\"\n"
        "\n"
        "\n"
        "DISPATCH_SYSTEM = \"\"\"You are a tool dispatcher. Return ONLY valid JSON, no prose.\n"
        "\n"
        'Schema: {"tool": "<tool_name>", "args": {"arg1": value1}}\n'
        "\n"
        "Available tools:\n"
        f"{dispatch_tool_lines}\n"
        "\n"
        "Rules:\n"
        "- Use exact tool names as listed above\n"
        "- Convert numeric strings to actual numbers\n"
        "\"\"\"\n"
        "\n"
        "\n"
        "NARRATE_SYSTEM = \"\"\"You are a narration assistant presenting tool results.\n"
        "STRICT RULES:\n"
        "- The tool result is ground truth. Do NOT correct, recompute, or second-guess any value.\n"
        "- Quote numbers and strings exactly as given.\n"
        "- If the result includes a count, lead with that number.\n"
        "- Keep it to 1-2 sentences.\"\"\"\n"
        "\n"
        "\n"
        "def _parse_json(raw: str) -> dict:\n"
        "    clean = raw.strip().lstrip(\"```json\").lstrip(\"```\").rstrip(\"```\").strip()\n"
        "    return json.loads(clean)\n"
        "\n"
        "\n"
        "def _format_result(result: dict) -> str:\n"
        "    \"\"\"Extract the most meaningful value from a tool result dict.\"\"\"\n"
        "    if \"expression\" in result:\n"
        "        return result[\"expression\"]\n"
        "    if \"reversed\" in result:\n"
        "        return result[\"reversed\"]\n"
        "    if \"files\" in result:\n"
        "        return f\"{result['count']} file(s) in {result['directory']}: {result['files']}\"\n"
        "    if \"error\" in result:\n"
        "        return f\"Error: {result['error']}\"\n"
        "    return json.dumps(result)\n"
        "\n"
        "\n"
        "def _error_response(detail: str, action: str = \"\") -> Dict[str, Any]:\n"
        "    return {\"success\": False, \"plugin_id\": PLUGIN_ID, \"action\": action,\n"
        "            \"answer\": f\"Error: {detail}\", \"results\": [], \"result_count\": 0, \"error\": detail}\n"
        "\n"
        "\n"
        "async def handle(req: Dict[str, Any]) -> Dict[str, Any]:\n"
        "    config  = get_config()\n"
        "    message = req.get(\"message\") or req.get(\"query\") or \"\"\n"
        "    action  = req.get(\"action\")\n"
        "\n"
        "    if action and not message:\n"
        "        return await _dispatch_action(action, req.get(\"params\") or {})\n"
        "    if not message:\n"
        "        return _error_response(\"No message or action provided\")\n"
        "\n"
        "    # 1. Classify intent\n"
        "    try:\n"
        "        raw      = await chat_completion(\n"
        "            f'User message: \"{message}\"\\n\\nClassify intent.',\n"
        "            system=ROUTER_SYSTEM, model=config.llm_model, temperature=0.0,\n"
        "        )\n"
        "        decision = _parse_json(raw)\n"
        "    except Exception:\n"
        "        decision = {\"intent\": \"tool_call\"}\n"
        "\n"
        "    intent = decision.get(\"intent\", \"tool_call\")\n"
        "\n"
        "    if intent in (\"direct_answer\", \"decline\") and decision.get(\"answer\"):\n"
        "        return {\"success\": True, \"plugin_id\": PLUGIN_ID, \"intent\": intent,\n"
        "                \"answer\": decision[\"answer\"], \"results\": [], \"result_count\": 0}\n"
        "\n"
        "    # 2. Dispatch to tool\n"
        "    try:\n"
        "        raw      = await chat_completion(\n"
        "            f'User message: \"{message}\"\\n\\nWhich tool and args?',\n"
        "            system=DISPATCH_SYSTEM, model=config.llm_model, temperature=0.0,\n"
        "        )\n"
        "        dispatch  = _parse_json(raw)\n"
        "        tool_name = dispatch.get(\"tool\", \"\")\n"
        "        args      = dispatch.get(\"args\", {})\n"
        "    except Exception as e:\n"
        "        return _error_response(f\"Dispatch failed: {e}\")\n"
        "\n"
        "    # 3. Execute — direct attribute lookup on TOOLS instance, no importlib\n"
        "    fn = getattr(TOOLS, tool_name, None)\n"
        "    if fn is None:\n"
        "        return _error_response(f\"Unknown tool: {tool_name!r}\")\n"
        "\n"
        "    try:\n"
        "        result = fn(**args)\n"
        "    except Exception as e:\n"
        "        return _error_response(f\"Tool error in {tool_name}: {e}\")\n"
        "\n"
        "    # Lock in canonical value before narration LLM runs\n"
        "    canonical = _format_result(result) if isinstance(result, dict) else str(result)\n"
        "\n"
        "    # 4. Narrate — wraps result, never replaces it\n"
        "    try:\n"
        "        narration = await chat_completion(\n"
        "            f'User asked: \"{message}\"\\n'\n"
        "            f'Tool {tool_name}({args}) returned (do not alter): \"{canonical}\"\\n\\n'\n"
        "            f'Write 1-2 sentences presenting that result.',\n"
        "            system=NARRATE_SYSTEM, model=config.llm_model, temperature=0.1,\n"
        "        )\n"
        "        answer = f\"{narration}\\n  \\u21b3 {canonical}\"\n"
        "    except Exception:\n"
        "        answer = f\"Tool result: {canonical}\"\n"
        "\n"
        "    return {\"success\": result.get(\"success\", True) if isinstance(result, dict) else True,\n"
        "            \"plugin_id\": PLUGIN_ID, \"intent\": \"tool_call\", \"tool\": tool_name,\n"
        "            \"answer\": answer, \"results\": [result], \"result_count\": 1}\n"
        "\n"
        "\n"
        "async def _dispatch_action(action: str, params: Dict[str, Any]) -> Dict[str, Any]:\n"
        "    \"\"\"Handle direct tool calls from the Tool Inspector.\"\"\"\n"
        "    fn = getattr(TOOLS, action, None)\n"
        "    if fn is None:\n"
        "        return _error_response(f\"Tool {action!r} not found\", action=action)\n"
        "    try:\n"
        "        result    = fn(**params)\n"
        "        canonical = _format_result(result) if isinstance(result, dict) else str(result)\n"
        "        return {\"success\": True, \"plugin_id\": PLUGIN_ID, \"intent\": \"action\",\n"
        "                \"action\": action, \"answer\": canonical,\n"
        "                \"results\": [result] if result is not None else [],\n"
        "                \"result_count\": 1 if result is not None else 0}\n"
        "    except Exception as e:\n"
        "        return _error_response(str(e), action=action)\n"
    )

    (d / "agent.py").write_text(agent_code)
    return  # end of new _write_agent_py

    plugin_id  = _slugify(m.id) or _slugify(m.name)  # DEAD CODE — safe to delete this block
    exec_tools = _code_tools(m)
    has_code   = bool(exec_tools)

    # Escape triple-quotes in the system prompt so it can't corrupt the file
    prompt_body = (m.system_prompt or "").strip().replace('"""', "'''")

    tool_list_lines = "\n".join(
        "- " + t.name + "("
        + ", ".join(f"{a}: {typ}" for a, typ in (t.arg_types or {}).items())
        + ")"
        for t in exec_tools
    )

    if has_code:
        agent_code = (
            "import json\n"
            "from typing import Any, Dict\n"
            "\n"
            f"PLUGIN_ID = {plugin_id!r}\n"
            "\n"
            'SYSTEM_PROMPT = """\n'
            f"{prompt_body}\n"
            '"""\n'
            "\n"
            "def get_config():\n"
            "    from plugins.base import PluginRegistry\n"
            "    config = PluginRegistry.get_config(PLUGIN_ID)\n"
            "    if not config:\n"
            "        raise RuntimeError(f'Plugin {PLUGIN_ID!r} is not registered.')\n"
            "    return config\n"
            "\n"
            "\n"
            'ROUTER_SYSTEM = """You are a strict intent classifier. Return ONLY a JSON object.\n'
            'Schema: {"intent": "direct_answer"|"tool_call"|"graph_query"|"decline", "confidence": 0.0-1.0, "reason": "<one sentence>", "answer": "<string or null>"}\n'
            "- direct_answer: user asks about agent identity or capabilities\n"
            "- tool_call: user wants to use one of the agent tools\n"
            "- graph_query: user asks about graph data\n"
            '- decline: outside domain"""\n'
            "\n"
            "\n"
            'DISPATCH_SYSTEM = """You are a tool dispatcher. Return ONLY a JSON object.\n'
            'Schema: {"tool": "tool_name", "args": {"arg1": "value1"}}\n'
            "Available tools:\n"
            f"{tool_list_lines}\n"
            'Return only the JSON object."""\n'
            "\n"
            "\n"
            "async def handle(req: Dict[str, Any]) -> Dict[str, Any]:\n"
            "    config = get_config()\n"
            "    message = req.get('message') or req.get('query') or ''\n"
            "    action  = req.get('action')\n"
            "\n"
            "    if action and not message:\n"
            "        return await _dispatch_action(action, req.get('params') or {}, config)\n"
            "    if not message:\n"
            "        return _error_response('No message or action provided')\n"
            "\n"
            "    from llm_client import chat_completion\n"
            "\n"
            "    # 1. Classify intent\n"
            "    try:\n"
            "        raw = await chat_completion(\n"
            "            f'User message: {json.dumps(message)}\\nAgent persona: {(config.system_prompt or \"\")[:200]}\\n\\nClassify intent.',\n"
            "            system=ROUTER_SYSTEM, model=config.llm_model, temperature=0.0,\n"
            "        )\n"
            "        decision = json.loads(raw.strip().lstrip('```json').lstrip('```').rstrip('```').strip())\n"
            "    except Exception:\n"
            "        decision = {'intent': 'tool_call'}\n"
            "\n"
            "    intent = decision.get('intent', 'tool_call')\n"
            "\n"
            "    if intent == 'direct_answer' and decision.get('answer'):\n"
            "        return {'success': True, 'plugin_id': PLUGIN_ID, 'intent': 'direct_answer',\n"
            "                'answer': decision['answer'], 'results': [], 'result_count': 0}\n"
            "\n"
            "    if intent == 'decline' and decision.get('answer'):\n"
            "        return {'success': True, 'plugin_id': PLUGIN_ID, 'intent': 'decline',\n"
            "                'answer': decision['answer'], 'results': [], 'result_count': 0}\n"
            "\n"
            "    if intent == 'graph_query':\n"
            "        return await _graph_query(message, config)\n"
            "\n"
            "    # 2. Dispatch to tool\n"
            "    try:\n"
            "        raw = await chat_completion(\n"
            "            f'User message: {json.dumps(message)}\\n\\nWhich tool and args?',\n"
            "            system=DISPATCH_SYSTEM, model=config.llm_model, temperature=0.0,\n"
            "        )\n"
            "        dispatch = json.loads(raw.strip().lstrip('```json').lstrip('```').rstrip('```').strip())\n"
            "        tool = dispatch.get('tool')\n"
            "        args = dispatch.get('args', {})\n"
            "    except Exception as e:\n"
            "        return _error_response(f'Dispatch failed: {e}')\n"
            "\n"
            "    import importlib\n"
            "    tools_mod = importlib.import_module(f'plugins.{PLUGIN_ID}.tools')\n"
            "    fn = getattr(tools_mod, tool, None)\n"
            "    if fn is None:\n"
            "        return _error_response(f'Tool {tool!r} not found in tools.py')\n"
            "\n"
            "    try:\n"
            "        result = fn(**args)\n"
            "    except NotImplementedError:\n"
            "        return {'success': False, 'plugin_id': PLUGIN_ID, 'intent': 'tool_call',\n"
            "                'answer': f'Tool {tool!r} is not yet implemented.', 'results': [], 'result_count': 0}\n"
            "    except Exception as e:\n"
            "        return _error_response(str(e))\n"
            "\n"
            "    narration = await chat_completion(\n"
            "        f'User asked: {json.dumps(message)}\\nTool {tool}({args}) returned: {json.dumps(result)}\\nWrite a brief friendly answer.',\n"
            "        system=config.system_prompt, model=config.llm_model, temperature=0.1,\n"
            "    )\n"
            "    return {'success': result.get('success', True) if isinstance(result, dict) else True,\n"
            "            'plugin_id': PLUGIN_ID, 'intent': 'tool_call', 'tool': tool,\n"
            "            'answer': narration, 'results': [result], 'result_count': 1}\n"
            "\n"
            "\n"
            "async def _graph_query(message: str, config) -> Dict[str, Any]:\n"
            "    try:\n"
            "        from nl_query_engine import natural_language_query, NaturalQueryRequest\n"
            "        from llm_client import chat_completion\n"
            "        result = await natural_language_query(NaturalQueryRequest(question=message, show_sparql=True))\n"
            "        result = result.dict()\n"
            "        if result.get('success') and result.get('results'):\n"
            "            narration = await chat_completion(\n"
            "                f'User asked: {json.dumps(message)}\\nGraph returned {result[\"result_count\"]} result(s):\\n{json.dumps(result[\"results\"][:20], indent=2)}\\nWrite a concise answer.',\n"
            "                system=config.system_prompt, model=config.llm_model, temperature=0.1,\n"
            "            )\n"
            "        else:\n"
            "            narration = result.get('answer', 'No results found.')\n"
            "        return {'success': result.get('success', False), 'plugin_id': PLUGIN_ID, 'intent': 'graph_query',\n"
            "                'answer': narration, 'sparql': result.get('sparql'), 'results': result.get('results', []),\n"
            "                'result_count': result.get('result_count', 0), 'timing_ms': result.get('timing_ms')}\n"
            "    except Exception as e:\n"
            "        return _error_response(str(e))\n"
            "\n"
            "\n"
            "async def _dispatch_action(action: str, params: Dict[str, Any], config) -> Dict[str, Any]:\n"
            "    \"\"\"Handle direct tool calls from the Tool Inspector.\"\"\"\n"
            "    import importlib\n"
            "    tools_mod = importlib.import_module(f'plugins.{PLUGIN_ID}.tools')\n"
            "    fn = getattr(tools_mod, action, None)\n"
            "    if fn is None:\n"
            "        return _error_response(f'Tool {action!r} not found', action=action)\n"
            "    try:\n"
            "        result = fn(**params)\n"
            "        return {'success': True, 'plugin_id': PLUGIN_ID, 'intent': 'action',\n"
            "                'action': action,\n"
            "                'answer': json.dumps(result, indent=2) if isinstance(result, dict) else str(result),\n"
            "                'results': [result] if result is not None else [], 'result_count': 1 if result is not None else 0}\n"
            "    except NotImplementedError:\n"
            "        return {'success': False, 'plugin_id': PLUGIN_ID, 'intent': 'action',\n"
            "                'action': action, 'answer': f'Tool {action!r} not yet implemented.',\n"
            "                'results': [], 'result_count': 0}\n"
            "    except Exception as e:\n"
            "        return _error_response(str(e), action=action)\n"
            "\n"
            "\n"
            "def _error_response(detail: str, action: str = '') -> Dict[str, Any]:\n"
            "    return {'success': False, 'plugin_id': PLUGIN_ID, 'action': action,\n"
            "            'answer': f'Error: {detail}', 'results': [], 'result_count': 0, 'error': detail}\n"
        )

    else:
        # No code upload — graph-query-only agent
        agent_code = (
            "import json\n"
            "from typing import Any, Dict\n"
            "\n"
            f"PLUGIN_ID = {plugin_id!r}\n"
            "\n"
            'SYSTEM_PROMPT = """\n'
            f"{prompt_body}\n"
            '"""\n'
            "\n"
            "def get_config():\n"
            "    from plugins.base import PluginRegistry\n"
            "    config = PluginRegistry.get_config(PLUGIN_ID)\n"
            "    if not config:\n"
            "        raise RuntimeError(f'Plugin {PLUGIN_ID!r} is not registered.')\n"
            "    return config\n"
            "\n"
            "\n"
            'ROUTER_SYSTEM = """You are a strict intent classifier. Return ONLY a JSON object.\n'
            'Schema: {"intent": "direct_answer"|"graph_query"|"decline", "confidence": 0.0-1.0, "reason": "<one sentence>", "answer": "<string or null>"}\n'
            "- direct_answer: user asks about agent identity or capabilities\n"
            "- graph_query: user asks about domain data\n"
            '- decline: outside domain"""\n'
            "\n"
            "\n"
            "async def handle(req: Dict[str, Any]) -> Dict[str, Any]:\n"
            "    config = get_config()\n"
            "    message = req.get('message') or req.get('query') or ''\n"
            "    action  = req.get('action')\n"
            "\n"
            "    if action and not message:\n"
            "        return _error_response(f'No conversational tools registered — action {action!r} not supported', action=action)\n"
            "    if not message:\n"
            "        return _error_response('No message provided')\n"
            "\n"
            "    from llm_client import chat_completion\n"
            "\n"
            "    try:\n"
            "        raw = await chat_completion(\n"
            "            f'User message: {json.dumps(message)}\\nAgent persona: {(config.system_prompt or \"\")[:200]}\\n\\nClassify intent.',\n"
            "            system=ROUTER_SYSTEM, model=config.llm_model, temperature=0.0,\n"
            "        )\n"
            "        decision = json.loads(raw.strip().lstrip('```json').lstrip('```').rstrip('```').strip())\n"
            "    except Exception:\n"
            "        decision = {'intent': 'graph_query'}\n"
            "\n"
            "    intent = decision.get('intent', 'graph_query')\n"
            "\n"
            "    if intent == 'direct_answer' and decision.get('answer'):\n"
            "        return {'success': True, 'plugin_id': PLUGIN_ID, 'intent': 'direct_answer',\n"
            "                'answer': decision['answer'], 'results': [], 'result_count': 0}\n"
            "    if intent == 'decline' and decision.get('answer'):\n"
            "        return {'success': True, 'plugin_id': PLUGIN_ID, 'intent': 'decline',\n"
            "                'answer': decision['answer'], 'results': [], 'result_count': 0}\n"
            "\n"
            "    return await _graph_query(message, config)\n"
            "\n"
            "\n"
            "async def _graph_query(message: str, config) -> Dict[str, Any]:\n"
            "    try:\n"
            "        from nl_query_engine import natural_language_query, NaturalQueryRequest\n"
            "        from llm_client import chat_completion\n"
            "        result = await natural_language_query(NaturalQueryRequest(question=message, show_sparql=True))\n"
            "        result = result.dict()\n"
            "        if result.get('success') and result.get('results'):\n"
            "            narration = await chat_completion(\n"
            "                f'User asked: {json.dumps(message)}\\nGraph returned {result[\"result_count\"]} result(s):\\n{json.dumps(result[\"results\"][:20], indent=2)}\\nWrite a concise answer.',\n"
            "                system=config.system_prompt, model=config.llm_model, temperature=0.1,\n"
            "            )\n"
            "        else:\n"
            "            narration = result.get('answer', 'No results found.')\n"
            "        return {'success': result.get('success', False), 'plugin_id': PLUGIN_ID, 'intent': 'graph_query',\n"
            "                'answer': narration, 'sparql': result.get('sparql'), 'results': result.get('results', []),\n"
            "                'result_count': result.get('result_count', 0), 'timing_ms': result.get('timing_ms')}\n"
            "    except Exception as e:\n"
            "        return _error_response(str(e))\n"
            "\n"
            "\n"
            "def _error_response(detail: str, action: str = '') -> Dict[str, Any]:\n"
            "    return {'success': False, 'plugin_id': PLUGIN_ID, 'action': action,\n"
            "            'answer': f'Error: {detail}', 'results': [], 'result_count': 0, 'error': detail}\n"
        )

    (d / "agent.py").write_text(agent_code)