import json
import os
import sys
from typing import Any, Dict

from llm_client import chat_completion

PLUGIN_ID = 'crypto'

# Direct import of the uploaded tool class — no importlib indirection.
# If you upload a different file, update the import and class name below.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crypto_tools import CryptoTools  # noqa: E402
TOOLS = CryptoTools()


def get_config():
    from plugins.base import PluginRegistry
    config = PluginRegistry.get_config(PLUGIN_ID)
    if not config:
        raise RuntimeError(f"Plugin 'crypto' is not registered.")
    return config

SYSTEM_PROMPT = """
You are Crypto Helper, a security utility agent.
You can hash strings, encode/decode base64, and generate secure passwords.
Always call a tool — never produce a hash, encoded value, or password yourself.

STRICT ROUTING RULES:
- Only respond to explicit requests to hash, encode, decode, or generate a password
- Anything that isnt related to hash strings, encode/decode base64, and generate secure passwords.  → decline
- Decline everything else with: "I can only hash strings, encode/decode base64, and generate passwords."
"""


ROUTER_SYSTEM = """You are a strict intent classifier. Return ONLY valid JSON, no prose.

Schema: {"intent": "tool_call"|"direct_answer"|"decline", "answer": "<string or null>"}

- direct_answer: user asks who you are or what you can do
- tool_call: user wants to use one of the agent tools — when in doubt, choose this
- decline: ONLY if the request is completely unrelated to the agent domain

Available tools:
  hash_string(text, algorithm)  - Hash a string using the specified algorithm.
  base64_encode(text)  - Encode a plain-text string to standard base64.
  base64_decode(text)  - Decode a base64 string back to plain text.
  generate_password(length)  - Generate a cryptographically secure random password.
"""


DISPATCH_SYSTEM = """You are a tool dispatcher. Return ONLY valid JSON, no prose.

Schema: {"tool": "<tool_name>", "args": {"arg1": value1}}

Available tools:
  hash_string(text (str), algorithm (str))
  base64_encode(text (str))
  base64_decode(text (str))
  generate_password(length (str))

Rules:
- Use exact tool names as listed above
- Convert numeric strings to actual numbers
"""


NARRATE_SYSTEM = """You are a narration assistant presenting tool results.
STRICT RULES:
- The tool result is ground truth. Do NOT correct, recompute, or second-guess any value.
- Quote numbers and strings exactly as given.
- If the result includes a count, lead with that number.
- Keep it to 1-2 sentences."""


def _parse_json(raw: str) -> dict:
    clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(clean)


def _format_result(result: dict) -> str:
    """Extract the most meaningful value from a tool result dict."""
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
    return {"success": False, "plugin_id": PLUGIN_ID, "action": action,
            "answer": f"Error: {detail}", "results": [], "result_count": 0, "error": detail}


async def handle(req: Dict[str, Any]) -> Dict[str, Any]:
    config  = get_config()
    message = req.get("message") or req.get("query") or ""
    action  = req.get("action")

    if action and not message:
        return await _dispatch_action(action, req.get("params") or {})
    if not message:
        return _error_response("No message or action provided")

    # 1. Classify intent
    try:
        raw      = await chat_completion(
            f'User message: "{message}"\n\nClassify intent.',
            system=ROUTER_SYSTEM, model=config.llm_model, temperature=0.0,
        )
        decision = _parse_json(raw)
    except Exception:
        decision = {"intent": "tool_call"}

    intent = decision.get("intent", "tool_call")

    if intent in ("direct_answer", "decline") and decision.get("answer"):
        return {"success": True, "plugin_id": PLUGIN_ID, "intent": intent,
                "answer": decision["answer"], "results": [], "result_count": 0}

    # 2. Dispatch to tool
    try:
        raw      = await chat_completion(
            f'User message: "{message}"\n\nWhich tool and args?',
            system=DISPATCH_SYSTEM, model=config.llm_model, temperature=0.0,
        )
        dispatch  = _parse_json(raw)
        tool_name = dispatch.get("tool", "")
        args      = dispatch.get("args", {})
    except Exception as e:
        return _error_response(f"Dispatch failed: {e}")

    # 3. Execute — direct attribute lookup on TOOLS instance, no importlib
    fn = getattr(TOOLS, tool_name, None)
    if fn is None:
        return _error_response(f"Unknown tool: {tool_name!r}")

    try:
        result = fn(**args)
    except Exception as e:
        return _error_response(f"Tool error in {tool_name}: {e}")

    # Lock in canonical value before narration LLM runs
    canonical = _format_result(result) if isinstance(result, dict) else str(result)

    # 4. Narrate — wraps result, never replaces it
    try:
        narration = await chat_completion(
            f'User asked: "{message}"\n'
            f'Tool {tool_name}({args}) returned (do not alter): "{canonical}"\n\n'
            f'Write 1-2 sentences presenting that result.',
            system=NARRATE_SYSTEM, model=config.llm_model, temperature=0.1,
        )
        answer = f"{narration}\n  \u21b3 {canonical}"
    except Exception:
        answer = f"Tool result: {canonical}"

    return {"success": result.get("success", True) if isinstance(result, dict) else True,
            "plugin_id": PLUGIN_ID, "intent": "tool_call", "tool": tool_name,
            "answer": answer, "results": [result], "result_count": 1}


async def _dispatch_action(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle direct tool calls from the Tool Inspector."""
    fn = getattr(TOOLS, action, None)
    if fn is None:
        return _error_response(f"Tool {action!r} not found", action=action)
    try:
        result    = fn(**params)
        canonical = _format_result(result) if isinstance(result, dict) else str(result)
        return {"success": True, "plugin_id": PLUGIN_ID, "intent": "action",
                "action": action, "answer": canonical,
                "results": [result] if result is not None else [],
                "result_count": 1 if result is not None else 0}
    except Exception as e:
        return _error_response(str(e), action=action)
