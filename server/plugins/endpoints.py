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
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .base import PluginRegistry

router = APIRouter(prefix="/api/plugins", tags=["plugins"])

PLUGINS_DIR = Path(__file__).parent
DATA_DIR    = Path(__file__).parent.parent / "data"


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


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


# ── Register (new) ─────────────────────────────────────────────────────────────

class GeneratedTool(BaseModel):
    name:            str
    signature:       str
    description:     Optional[str]          = None
    sparql_template: Optional[str]          = None
    arg_types:       Optional[Dict[str, str]] = None
    return_type:     Optional[str]          = None
    source:          Optional[str]          = "ontology"

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
    description:          Optional[str]                      = ""
    icon:                 Optional[str]                      = "⚙️"
    mode:                 Optional[str]                      = "action"
    domain_classes:       Optional[List[str]]                = []
    domain_relationships: Optional[List[str]]                = []
    write_permissions:    Optional[List[str]]                = []
    llm_model:            Optional[str]                      = "gpt-4o-mini"
    system_prompt:        Optional[str]                      = ""
    session_cache_ttl:    Optional[int]                      = 300
    generated_tools:      Optional[List[GeneratedTool]]      = []
    execution_context:    Optional[ExecutionContextManifest] = None
    improvement_policy:   Optional[ImprovementPolicyManifest] = None


@router.post("/register")
def register_plugin(manifest: RegisterManifest):
    """
    Register a new application from the AppOnboarding wizard manifest.
    1. Persists manifest to data/plugin_manifests/{id}.json
    2. Scaffolds plugins/{id}/ with domain.py, tools.py, agent.py
    3. Registers in live PluginRegistry
    4. Returns { id, success: true }
    Idempotent — re-registering overwrites scaffolded files and updates registry.
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
    _write_agent_py(plugin_dir, manifest)

    # 3. Register in live PluginRegistry
    # PluginConfig requires: id, name, description, endpoint, icon, active,
    # collections, field_mappings, filters, created_at, updated_at, created_by
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
        # Attach agent-specific fields dynamically so list_plugins can forward them
        cfg.mode               = manifest.mode
        cfg.llm_model          = manifest.llm_model
        cfg.domain_classes     = manifest.domain_classes or []
        cfg.domain_relationships = manifest.domain_relationships or []
        cfg.write_permissions  = manifest.write_permissions or []
        cfg.session_cache_ttl  = manifest.session_cache_ttl
        cfg.system_prompt      = manifest.system_prompt
        cfg.has_code           = manifest.execution_context is not None
        cfg.generated_tools    = [t.model_dump() for t in (manifest.generated_tools or [])]
        cfg.improvement_policy = manifest.improvement_policy.model_dump() if manifest.improvement_policy else None

        # PluginRegistry.register() expects a Plugin instance
        class _ScaffoldedPlugin(Plugin):
            def transform_data(self, nodes, payloads):
                return nodes

        PluginRegistry.register(_ScaffoldedPlugin(cfg))

    except Exception as e:
        # Scaffold succeeded but live registration failed — server reload will fix
        return {
            "success": True,
            "id": plugin_id,
            "scaffolded_at": str(plugin_dir),
            "registry_warning": f"Scaffolded OK. Live registration failed: {e}. Restart server to load.",
        }

    return {"success": True, "id": plugin_id, "scaffolded_at": str(plugin_dir)}


# ── Agent call (new) ───────────────────────────────────────────────────────────

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
    conversational: req.message             → forwarded to nl_query_engine
    hybrid:         supports both
    """
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    # Try domain-specific agent module if scaffolded
    agent_module_path = PLUGINS_DIR / plugin_id / "agent.py"
    if agent_module_path.exists():
        import importlib.util
        spec   = importlib.util.spec_from_file_location(f"plugins.{plugin_id}.agent", agent_module_path)
        module = importlib.util.module_from_spec(spec)          # type: ignore[arg-type]
        spec.loader.exec_module(module)                         # type: ignore[union-attr]
        if hasattr(module, "handle"):
            return await module.handle(req.dict())

    # Default placeholder
    name = getattr(plugin, "name", None) or getattr(getattr(plugin, "config", None), "name", plugin_id)
    return {
        "success":      True,
        "plugin_id":    plugin_id,
        "action":       req.action,
        "answer":       f"[{name}] Tool '{req.action}' received — implement handle() in plugins/{plugin_id}/agent.py",
        "results":      [],
        "result_count": 0,
    }


# ── Activate / Deactivate ──────────────────────────────────────────────────────

@router.post("/{plugin_id}/activate")
async def activate_plugin(plugin_id: str):
    """Activate a plugin by ID."""
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    PluginRegistry.activate(plugin_id)
    name = getattr(plugin, "name", None) or getattr(getattr(plugin, "config", None), "name", plugin_id)
    return {"success": True, "message": f"Plugin '{name}' activated"}


@router.post("/{plugin_id}/deactivate")
async def deactivate_plugin(plugin_id: str):
    """Deactivate a plugin by ID."""
    plugin = PluginRegistry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    PluginRegistry.deactivate(plugin_id)
    name = getattr(plugin, "name", None) or getattr(getattr(plugin, "config", None), "name", plugin_id)
    return {"success": True, "message": f"Plugin '{name}' deactivated"}


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


def _write_tools_py(d: Path, m: RegisterManifest):
    tool_fns: list = []
    for t in (m.generated_tools or []):
        arg_sig = ", ".join(f"{a}: {typ}" for a, typ in (t.arg_types or {}).items())
        body = textwrap.dedent(f"""\
            def {t.name}({arg_sig}):
                \"\"\"
                {t.description or t.name}
                Return type: {t.return_type or "Any"}
                \"\"\"
                # TODO: implement using gdb.sparql_query()
                raise NotImplementedError("Implement {t.name} in tools.py")
            """)
        tool_fns.append(body)

    header = textwrap.dedent(f"""\
        \"\"\"Typed tool set for {m.name}. Auto-generated — add domain logic here.\"\"\"
        from typing import Any, Dict, List, Optional

        """)
    (d / "tools.py").write_text(header + "\n\n".join(tool_fns))


def _write_agent_py(d: Path, m: RegisterManifest):
    exec_block = ""
    if m.execution_context:
        ec = m.execution_context
        ready = (
            f'stdout contains "{ec.ready_signal_value}"' if ec.ready_signal_type == "stdout_contains"
            else f"port {ec.ready_signal_value} available" if ec.ready_signal_type == "port_available"
            else "exit code 0"
        )
        exec_block = f'\nEXECUTION_CONTEXT = """\nStart: cd {ec.working_dir} && {ec.start_command}\nReady: {ready}\nStop:  {ec.stop_command}\n"""\n'

    content = textwrap.dedent(f"""\
        \"\"\"Agent config for {m.name}. Auto-generated — edit freely.\"\"\"
        from typing import Any, Dict, Optional

        PLUGIN_ID         = {m.id!r}
        LLM_MODEL         = {m.llm_model!r}
        SESSION_CACHE_TTL = {m.session_cache_ttl}

        SYSTEM_PROMPT = \"\"\"
        {(m.system_prompt or "").strip()}
        \"\"\"
        {exec_block}
        async def handle(req: Dict[str, Any]) -> Dict[str, Any]:
            action = req.get("action")
            params = req.get("params") or {{}}
            # TODO: route action → tool call
            return {{
                "success":      True,
                "plugin_id":    PLUGIN_ID,
                "action":       action,
                "answer":       f"[{m.name}] action={{action!r}} received — implement handle()",
                "results":      [],
                "result_count": 0,
            }}
        """)
    (d / "agent.py").write_text(content)