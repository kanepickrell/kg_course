import json
import os
import sys
from typing import Any, Dict, Optional

from llm_client import chat_completion
from plugins.proposal_engine import log_interaction as _log_interaction

PLUGIN_ID = 'crypto'
ACCEPTS_DELEGATION = False

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from crypto_tools import CryptoTools  # noqa: E402
TOOLS = CryptoTools()


def get_config():
    from plugins.base import PluginRegistry
    config = PluginRegistry.get_config(PLUGIN_ID)
    if not config:
        raise RuntimeError(f"Plugin {PLUGIN_ID!r} is not registered.")
    return config


SYSTEM_PROMPT = """
You are Crypto Helper, a security utility agent for ATLAS. Your primary functions are to hash strings, encode/decode base64, and generate secure passwords. You can also provide guidance on security-related topics. If a query is outside your expertise, politely inform the user and suggest they ask about hashing, encoding, or password generation. Always call a tool for hashing, encoding, or password generation tasks. Additionally, consider providing brief explanations or resources related to security topics to enhance user engagement.
"""


ROUTER_SYSTEM = """
You are an expert intent classifier for the Crypto Helper agent.
This agent specialises in: Thing.

Return ONLY valid JSON matching this schema:
{"intent": "tool_call"|"direct_answer"|"decline", "answer": "<string or null>"}

- direct_answer: the user is asking who you are or what you can do
- tool_call: the user wants to use the agent tools — default when in doubt
- decline: ONLY if the request is completely outside the domain above

Available tools:
  hash_string(text (str), algorithm (str)) - Hash a string using the specified algorithm.
  base64_encode(text (str)) - Encode a plain-text string to standard base64.
  base64_decode(text (str)) - Decode a base64 string back to plain text.
  generate_password(length (str)) - Generate a cryptographically secure random password.
"""


DISPATCH_SYSTEM = """
You are a tool dispatcher for the Crypto Helper agent.
Return ONLY valid JSON:
{"tool": "<tool_name>", "args": {"arg1": value1}}

Available tools:
  hash_string(text (str), algorithm (str))
  base64_encode(text (str))
  base64_decode(text (str))
  generate_password(length (str))

Rules:
- Use exact tool names as listed
- Convert numeric strings to actual numbers
"""


NARRATE_SYSTEM = """
You are a narration assistant for the Crypto Helper agent.
The tool result is ground truth. Do NOT correct or recompute any value.
Quote numbers and strings exactly as given. Keep it to 1-2 sentences.
"""


def _parse_json(raw: str) -> dict:
    clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(clean)


def _format_result(result) -> str:
    if not isinstance(result, dict):
        return str(result)
    for key in ("hash", "encoded", "decoded", "password", "result", "reversed"):
        if key in result:
            return str(result[key])
    if "files" in result:
        count = result.get('count', 0)
        directory = result.get('directory', '.')
        files = result['files']
        return f"{count} file(s) in {directory}: {files}"
    if "error" in result:
        error = result['error']
        return f"Error: {error}"
    return json.dumps(result)


def _error_response(detail: str, action: str = "") -> Dict[str, Any]:
    return {
        "success": False, "plugin_id": PLUGIN_ID, "action": action,
        "answer": f"Error: {detail}", "results": [], "result_count": 0,
        "error": detail,
    }


async def forward(req: Dict[str, Any]) -> Dict[str, Any]:
    """
    DELEGATED mode entry point.
    Called by the Orchestrator — routing has already happened.
    Executes the task directly without intent classification.
    """
    if not ACCEPTS_DELEGATION:
        return _error_response("This agent does not accept delegated tasks")

    task    = req.get("task") or req.get("message") or ""
    context = req.get("context") or {}

    if True:
        return await _tool_call(task, get_config(), context=context)
    return await _graph_query(task, get_config())


async def handle(req: Dict[str, Any]) -> Dict[str, Any]:
    """
    STANDALONE mode entry point.
    Called by humans via the API or dashboard.
    Runs full intent classification before execution.
    """
    # If the orchestrator is calling handle() (e.g. agent has no forward yet),
    # skip classification and go straight to execution.
    if req.get("delegated"):
        return await forward(req)

    config  = get_config()
    message = req.get("message") or req.get("query") or ""
    action  = req.get("action")

    if action and not message:
        return await _dispatch_action(action, req.get("params") or {})
    if not message:
        return _error_response("No message or action provided")

    # Intent classification — STANDALONE only
    try:
        raw = await chat_completion(
            f"User message: {message!r}\n\nClassify intent.",
            system=ROUTER_SYSTEM,
            model=config.llm_model,
            temperature=0.0,
        )
        decision = _parse_json(raw)
    except Exception:
        decision = {"intent": 'tool_call'}

    intent = decision.get("intent", 'tool_call')

    if intent in ("direct_answer", "decline") and decision.get("answer"):
        _log_interaction(PLUGIN_ID, {
            "question": message, "outcome": "auto",
            "tool_names": [], "result_count": 0,
        })
        return {
            "success": True, "plugin_id": PLUGIN_ID, "intent": intent,
            "answer": decision["answer"], "results": [], "result_count": 0,
        }

    if True:
        result = await _tool_call(message, config)
    else:
        result = await _graph_query(message, config)

    _log_interaction(PLUGIN_ID, {
        "question":     message,
        "outcome":      "auto",
        "tool_names":   [result.get("tool")] if result.get("tool") else [],
        "result_count": result.get("result_count", 0),
        "error":        result.get("error"),
        "timing_ms":    result.get("timing_ms"),
    })
    return result


async def _tool_call(message: str, config, context: dict = {}) -> Dict[str, Any]:
    try:
        raw = await chat_completion(
            f"User message: {message!r}\n\nContext: {context!r}\n\nWhich tool and args?",
            system=DISPATCH_SYSTEM,
            model=config.llm_model,
            temperature=0.0,
        )
        dispatch  = _parse_json(raw)
        tool_name = dispatch.get("tool", "")
        args      = dispatch.get("args", {})
    except Exception as e:
        return _error_response(f"Dispatch failed: {e}")

    fn = getattr(TOOLS, tool_name, None)
    if fn is None:
        return _error_response(f"Unknown tool: {tool_name!r}")

    try:
        result = fn(**args)
    except Exception as e:
        return _error_response(f"Tool error in {tool_name}: {e}")

    canonical = _format_result(result)

    try:
        narration = await chat_completion(
            (
                f"User asked: {message!r}\n"
                f"Tool {tool_name}({args}) returned: {canonical!r}\n\n"
                "Write 1-2 sentences presenting that result."
            ),
            system=NARRATE_SYSTEM,
            model=config.llm_model,
            temperature=0.1,
        )
        answer = f"{narration}\n  \u21b3 {canonical}"
    except Exception:
        answer = f"Tool result: {canonical}"

    success = result.get('success', True) if isinstance(result, dict) else True
    return {
        "success": success, "plugin_id": PLUGIN_ID, "intent": "tool_call",
        "tool": tool_name, "answer": answer,
        "results": [result], "result_count": 1,
    }


async def _graph_query(message: str, config) -> Dict[str, Any]:
    try:
        from nl_query_engine import natural_language_query, NaturalQueryRequest
        result = await natural_language_query(NaturalQueryRequest(question=message, show_sparql=True))
        result = result.dict()
        if result.get("success") and result.get("results"):
            narration = await chat_completion(
                (
                    f"User asked: {message!r}\n"
                    f"Graph returned {result['result_count']} result(s):\n"
                    f"{json.dumps(result['results'][:20], indent=2)}\n"
                    "Write a concise answer."
                ),
                system=config.system_prompt,
                model=config.llm_model,
                temperature=0.1,
            )
        else:
            narration = result.get("answer", "No results found.")
        return {
            "success": result.get("success", False), "plugin_id": PLUGIN_ID,
            "intent": "graph_query", "answer": narration,
            "sparql": result.get("sparql"), "results": result.get("results", []),
            "result_count": result.get("result_count", 0),
            "timing_ms": result.get("timing_ms"),
        }
    except Exception as e:
        return _error_response(str(e))


async def _dispatch_action(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle direct tool calls from the Tool Inspector."""
    fn = getattr(TOOLS, action, None) if True else None
    if fn is None:
        return _error_response(f"Tool {action!r} not found", action=action)
    try:
        result    = fn(**params)
        canonical = _format_result(result)
        return {
            "success": True, "plugin_id": PLUGIN_ID, "intent": "action",
            "action": action, "answer": canonical,
            "results": [result] if result is not None else [],
            "result_count": 1 if result is not None else 0,
        }
    except Exception as e:
        return _error_response(str(e), action=action)