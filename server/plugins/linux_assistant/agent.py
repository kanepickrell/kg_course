"""
plugins/linux_assistant/agent.py
=================================
Drop this file into server/plugins/linux_assistant/agent.py

Key differences from the generated version:
- SimpleTools is imported directly at the top — no importlib, no dynamic module loading
- tools.py is not involved at all; the class instance is held in TOOLS
- _format_result() locks in the canonical value before narration LLM runs
- Narration system prompt forbids recomputing or correcting tool output
"""

import json
from typing import Any, Dict

from llm_client import chat_completion

PLUGIN_ID = "linux_assistant"

# ── Tool library (direct import — no indirection) ─────────────────────────────
# SimpleTools lives right here in the same directory.
# If you uploaded a different file, import that class instead.

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simple_tools import SimpleTools  # noqa: E402

TOOLS = SimpleTools()


# ── Config helper ─────────────────────────────────────────────────────────────

def get_config():
    from plugins.base import PluginRegistry
    config = PluginRegistry.get_config(PLUGIN_ID)
    if not config:
        raise RuntimeError(f"Plugin {PLUGIN_ID!r} is not registered.")
    return config


# ── System prompts ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
You are Linux Helper, a friendly utility agent for the 318th RANS ATLAS system.
You can add numbers, reverse text, and list directory files.
Always use a tool to answer — never guess. Decline anything outside your tools.
"""

ROUTER_SYSTEM = """You are a strict intent classifier. Return ONLY valid JSON, no prose.

Schema: {"intent": "tool_call"|"direct_answer"|"decline", "answer": "<string or null>"}

- direct_answer: user asks who you are or what you can do → set answer to a brief description
- tool_call: user wants to use one of the agent tools — when in doubt, choose this
- decline: ONLY use this if the request is completely unrelated to numbers, text, or files

Available tools:
  add_numbers(a, b)      — Add two numbers (any request involving math or sums)
  reverse_text(text)     — Reverse a string (any request involving flipping/reversing text)
  list_files(directory)  — List OR count files in a directory (use this for ANY request
                           about files, directories, how many files, what files exist, etc.)

IMPORTANT: Requests like "how many files", "count files", "what's in this folder" all map
to list_files — they are tool_call, not decline."""

DISPATCH_SYSTEM = """You are a tool dispatcher. Return ONLY valid JSON, no prose.

Schema: {"tool": "<tool_name>", "args": {"arg1": value1, ...}}

Available tools:
  add_numbers(a, b)      — Add two numbers. Args: a (number), b (number)
  reverse_text(text)     — Reverse a string. Args: text (string)
  list_files(directory)  — List files. Args: directory (string, default ".")

Rules:
- Use exact tool names
- Convert numeric strings to actual numbers
- Default directory to "." if not specified"""

NARRATE_SYSTEM = """You are a narration assistant presenting tool results to a user.

STRICT RULES:
- The tool result is ground truth. Do NOT correct, recompute, or second-guess any value.
- Quote numbers, strings, and lists exactly as given to you.
- Do not perform any math or logic yourself.
- If the result includes a count, lead with that number.
- Keep it to 1-2 sentences."""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_json(raw: str) -> dict:
    clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(clean)


def _format_result(result: dict) -> str:
    """Extract the canonical display value from the tool result dict."""
    if "expression" in result:
        return result["expression"]
    if "reversed" in result:
        return result["reversed"]
    if "files" in result:
        return f"{result['count']} file(s) in {result['directory']}: {result['files']}"
    if "error" in result:
        return f"Error: {result['error']}"
    return json.dumps(result)


def _error_response(detail: str, action: str = "") -> Dict[str, Any]:
    return {
        "success": False,
        "plugin_id": PLUGIN_ID,
        "action": action,
        "answer": f"Error: {detail}",
        "results": [],
        "result_count": 0,
        "error": detail,
    }


# ── Main handler ──────────────────────────────────────────────────────────────

async def handle(req: Dict[str, Any]) -> Dict[str, Any]:
    config  = get_config()
    message = req.get("message") or req.get("query") or ""
    action  = req.get("action")

    # Direct tool call from Tool Inspector (action-based)
    if action and not message:
        return await _dispatch_action(action, req.get("params") or {})

    if not message:
        return _error_response("No message or action provided")

    # 1. Classify intent
    try:
        raw      = await chat_completion(
            f'User message: "{message}"\n\nClassify intent.',
            system=ROUTER_SYSTEM,
            model=config.llm_model,
            temperature=0.0,
        )
        decision = _parse_json(raw)
    except Exception as e:
        decision = {"intent": "tool_call"}

    intent = decision.get("intent", "tool_call")

    if intent in ("direct_answer", "decline") and decision.get("answer"):
        return {
            "success":      True,
            "plugin_id":    PLUGIN_ID,
            "intent":       intent,
            "answer":       decision["answer"],
            "results":      [],
            "result_count": 0,
        }

    # 2. Dispatch to tool
    try:
        raw      = await chat_completion(
            f'User message: "{message}"\n\nWhich tool and args?',
            system=DISPATCH_SYSTEM,
            model=config.llm_model,
            temperature=0.0,
        )
        dispatch  = _parse_json(raw)
        tool_name = dispatch.get("tool", "")
        args      = dispatch.get("args", {})
    except Exception as e:
        return _error_response(f"Dispatch failed: {e}")

    # 3. Execute — direct attribute lookup on the class instance
    fn = getattr(TOOLS, tool_name, None)
    if fn is None:
        return _error_response(f"Unknown tool: {tool_name!r}")

    try:
        result = fn(**args)
    except Exception as e:
        return _error_response(f"Tool error in {tool_name}({args}): {e}")

    # Lock in canonical value before narration LLM runs
    canonical = _format_result(result)

    # 4. Narrate — wraps the result, never replaces it
    try:
        narration = await chat_completion(
            f'User asked: "{message}"\n'
            f'Tool {tool_name}({args}) returned this exact value (do not alter it): "{canonical}"\n\n'
            f'Write 1-2 sentences presenting that result.',
            system=NARRATE_SYSTEM,
            model=config.llm_model,
            temperature=0.1,
        )
        answer = f"{narration}\n  ↳ {canonical}"
    except Exception:
        answer = f"Tool result: {canonical}"

    return {
        "success":      result.get("success", True) if isinstance(result, dict) else True,
        "plugin_id":    PLUGIN_ID,
        "intent":       "tool_call",
        "tool":         tool_name,
        "answer":       answer,
        "results":      [result],
        "result_count": 1,
    }


# ── Direct action dispatch (Tool Inspector) ───────────────────────────────────

async def _dispatch_action(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    fn = getattr(TOOLS, action, None)
    if fn is None:
        return _error_response(f"Tool {action!r} not found", action=action)
    try:
        result    = fn(**params)
        canonical = _format_result(result) if isinstance(result, dict) else str(result)
        return {
            "success":      True,
            "plugin_id":    PLUGIN_ID,
            "intent":       "action",
            "action":       action,
            "answer":       canonical,
            "results":      [result] if result is not None else [],
            "result_count": 1 if result is not None else 0,
        }
    except Exception as e:
        return _error_response(str(e), action=action)