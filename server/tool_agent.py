#!/usr/bin/env python3
"""
agent_cli.py — Minimal CLI proof-of-concept for the ProtoGraph plugin agent loop.

Proves: user prompt → LLM classifies intent → LLM dispatches tool call →
        SimpleTools executes → LLM narrates result → back to prompt.

Drop this file into your server/ directory (same level as llm_client.py) and run:

    python agent_cli.py

It uses llm_client.chat_completion_sync so no event loop is needed.
Set OLLAMA_HOST / OPENAI_API_KEY in your environment or .env as usual.
"""

import json
import sys
import os

# ── Allow running from server/ directly ──────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm_client import chat_completion_sync, active_backend, active_model


# ── Tool library ──────────────────────────────────────────────────────────────

class SimpleTools:
    """The tool library the agent can call. Add methods freely."""

    def add_numbers(self, a: float, b: float) -> dict:
        """Add two numbers and return the result."""
        result = float(a) + float(b)
        return {"success": True, "result": result, "expression": f"{a} + {b} = {result}"}

    def reverse_text(self, text: str) -> dict:
        """Reverse a string of text."""
        return {"success": True, "original": text, "reversed": text[::-1]}

    def list_files(self, directory: str = ".") -> dict:
        """List files in a directory."""
        try:
            files = os.listdir(directory)
            return {"success": True, "directory": directory, "files": files, "count": len(files)}
        except Exception as e:
            return {"success": False, "error": str(e)}


TOOLS = SimpleTools()

# Build a tool schema string the LLM can read
TOOL_SCHEMA = """
Available tools (call by name):
  add_numbers(a, b)        — Add two numbers. Args: a (number), b (number)
  reverse_text(text)       — Reverse a string. Args: text (string)
  list_files(directory)    — List files. Args: directory (string, default ".")
"""

# ── System prompts ────────────────────────────────────────────────────────────

PERSONA = """You are Linux Helper, a friendly utility agent.
You can add numbers, reverse text, and list directory files.
Always use a tool to answer — never guess. Decline anything outside your tools."""

ROUTER_SYSTEM = f"""You are a strict intent classifier. Return ONLY valid JSON, no prose.

Schema: {{"intent": "tool_call"|"direct_answer"|"decline", "answer": "<string or null>"}}

- direct_answer: user asks who you are or what you can do → set answer to a brief description
- tool_call: user wants to use one of the tools
- decline: request is outside your tool set → set answer to a polite refusal

{TOOL_SCHEMA}"""

DISPATCH_SYSTEM = f"""You are a tool dispatcher. Return ONLY valid JSON, no prose.

Schema: {{"tool": "<tool_name>", "args": {{"arg1": value1, ...}}}}

{TOOL_SCHEMA}

Rules:
- Use exact tool names from the schema
- Convert numeric strings to numbers where appropriate
- For list_files, default directory to "." if not specified"""

# CRITICAL: The narration prompt explicitly forbids the LLM from second-guessing
# or correcting the tool result. The tool is the authority.
NARRATE_SYSTEM = """You are a narration assistant. Your only job is to present the
tool result to the user in a friendly sentence.

STRICT RULES:
- The tool result is ground truth. Do NOT correct, recompute, or second-guess any value in it.
- If the result contains a number, string, or list — quote it exactly as given.
- Do not perform any math or logic yourself. Just describe what the tool returned.
- Keep it to 1-2 sentences."""


# ── Agent loop ────────────────────────────────────────────────────────────────

def _llm(prompt: str, system: str) -> str:
    return chat_completion_sync(prompt, system=system, temperature=0.0)


def _parse_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON."""
    clean = raw.strip()
    for fence in ("```json", "```"):
        clean = clean.lstrip(fence)
    clean = clean.rstrip("```").strip()
    return json.loads(clean)


def _format_result(result: dict) -> str:
    """
    Pull the most meaningful field out of the tool result for display.
    The raw result is always printed too — LLM narration wraps it, never replaces it.
    """
    if "expression" in result:
        return result["expression"]
    if "reversed" in result:
        return result["reversed"]
    if "files" in result:
        return f"{result['count']} file(s) in {result['directory']}: {result['files']}"
    if "error" in result:
        return f"Error: {result['error']}"
    return json.dumps(result)


def handle(message: str) -> str:
    """Full agent turn: classify -> dispatch -> execute -> narrate."""

    # 1. Classify intent
    try:
        raw = _llm(f'User message: "{message}"\n\nClassify intent.', ROUTER_SYSTEM)
        decision = _parse_json(raw)
    except Exception as e:
        return f"[Router error: {e}]\nRaw: {raw}"

    intent = decision.get("intent", "tool_call")

    if intent in ("direct_answer", "decline"):
        return decision.get("answer") or "(no answer)"

    # 2. Dispatch to tool
    try:
        raw = _llm(f'User message: "{message}"\n\nWhich tool and args?', DISPATCH_SYSTEM)
        dispatch = _parse_json(raw)
        tool_name = dispatch.get("tool", "")
        args = dispatch.get("args", {})
    except Exception as e:
        return f"[Dispatch error: {e}]\nRaw: {raw}"

    fn = getattr(TOOLS, tool_name, None)
    if fn is None:
        return f"[Error] Unknown tool: {tool_name!r}"

    # 3. Execute — tool result is authoritative, captured before any LLM sees it
    try:
        result = fn(**args)
    except Exception as e:
        return f"[Tool error calling {tool_name}({args})]: {e}"

    # Lock in the canonical display value from the tool NOW,
    # before the narration LLM has any chance to touch it.
    canonical = _format_result(result)

    # 4. Narrate — LLM adds a friendly wrapper but the canonical value
    #    is injected verbatim into the prompt so it must repeat it as-is.
    try:
        narration = _llm(
            f'User asked: "{message}"\n'
            f'Tool called: {tool_name}({args})\n'
            f'Tool returned this exact value (do not alter it): "{canonical}"\n\n'
            f'Write 1-2 sentences presenting that result to the user.',
            NARRATE_SYSTEM,
        )
        # Always append the raw canonical value so the user sees it unambiguously.
        return f"{narration}\n  -> Tool result: {canonical}"
    except Exception:
        # Narration failed — fall back to raw, still correct.
        return f"Tool result: {canonical}"


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    print(f"\n🤖  Linux Helper — CLI Agent Proof-of-Concept")
    print(f"    Backend : {active_backend()}  |  Model: {active_model()}")
    print(f"    Tools   : add_numbers · reverse_text · list_files")
    print(f"    Type 'exit' or Ctrl-C to quit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            print("Bye.")
            break

        print("Agent: ", end="", flush=True)
        try:
            reply = handle(user_input)
        except Exception as e:
            reply = f"[Unhandled error: {e}]"
        print(reply)
        print()


if __name__ == "__main__":
    main()
