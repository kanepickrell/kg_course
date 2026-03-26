import json
from typing import Any, Dict

PLUGIN_ID = "coverage_analyst"

def get_config():
    from plugins.base import PluginRegistry
    config = PluginRegistry.get_config(PLUGIN_ID)
    if not config:
        raise RuntimeError(f"Plugin '{PLUGIN_ID}' is not registered.")
    return config

ROUTER_SYSTEM = """You are a strict intent classifier. Return ONLY a JSON object.
Schema: {"intent": "direct_answer"|"graph_query"|"decline", "confidence": 0.0-1.0, "reason": "<one sentence>", "answer": "<string or null>"}
- direct_answer: user asks about agent identity or capabilities
- graph_query: user asks about TTPs, modules, sequences, coverage
- decline: outside domain — redirect to what you can help with"""

async def route_intent(message, config):
    from llm_client import chat_completion
    rules = config.get_intent_rules()
    trigger_block = ""
    if rules.direct_answer_triggers:
        trigger_block += f"\nDirect answer triggers: {rules.direct_answer_triggers}"
    if rules.decline_triggers:
        trigger_block += f"\nDecline triggers: {rules.decline_triggers}"
    persona = (config.system_prompt or "")[:300]
    prompt = f"User message: {json.dumps(message)}\n{trigger_block}\nAgent persona: {persona}\n\nClassify intent. Return only JSON."
    try:
        raw = await chat_completion(prompt, system=ROUTER_SYSTEM, model=config.llm_model, temperature=0.0)
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(clean)
    except Exception as e:
        print(f"Intent router failed: {e}")
        return {"intent": "graph_query", "confidence": 0.5, "reason": "router error", "answer": None}

async def handle(req: Dict[str, Any]) -> Dict[str, Any]:
    config = get_config()
    message = req.get("message") or req.get("query") or ""
    action = req.get("action")
    if action and not message:
        return await _dispatch_action(action, req.get("params") or {}, config)
    if not message:
        return _error_response("No message or action provided")
    decision = await route_intent(message, config)
    intent = decision.get("intent", "graph_query")
    answer = decision.get("answer")
    if intent == "direct_answer" and answer:
        return {"success": True, "plugin_id": PLUGIN_ID, "intent": "direct_answer", "answer": answer, "results": [], "result_count": 0}
    if intent == "decline" and answer:
        return {"success": True, "plugin_id": PLUGIN_ID, "intent": "decline", "answer": answer, "results": [], "result_count": 0}
    return await _graph_query(message, config)

async def _graph_query(message, config):
    try:
        from nl_query_engine import natural_language_query, NaturalQueryRequest
        from llm_client import chat_completion
        req = NaturalQueryRequest(question=message, show_sparql=True)
        result = await natural_language_query(req)
        result = result.dict()
        if result.get("success") and result.get("results"):
            narration_prompt = (
                f"The user asked: {json.dumps(message)}\n\n"
                f"Graph query returned {result['result_count']} result(s):\n"
                f"{json.dumps(result['results'][:20], indent=2)}\n\n"
                "Write a concise analyst answer. Use only these results — do not invent facts."
            )
            answer = await chat_completion(narration_prompt, system=config.system_prompt, model=config.llm_model, temperature=0.1)
        elif not result.get("success"):
            answer = f"No results found. Try asking about {', '.join(config.domain_classes or ['modules', 'TTPs'])}."
        else:
            answer = result.get("answer", "No results found.")
        return {"success": result.get("success", False), "plugin_id": PLUGIN_ID, "intent": "graph_query",
                "answer": answer, "sparql": result.get("sparql"), "results": result.get("results", []),
                "result_count": result.get("result_count", 0), "timing_ms": result.get("timing_ms"),
                "rag_context": result.get("rag_context"), "few_shot_examples": result.get("few_shot_examples")}
    except Exception as e:
        return _error_response(str(e))

async def _dispatch_action(action, params, config):
    try:
        import importlib
        tools_mod = importlib.import_module(f"plugins.{PLUGIN_ID}.tools")
        fn = getattr(tools_mod, action, None)
        if fn is None:
            return {"success": False, "plugin_id": PLUGIN_ID, "intent": "action", "action": action,
                    "answer": f"Tool '{action}' not found in tools.py", "results": [], "result_count": 0}
        result = await fn(**params) if callable(fn) else None
        return {"success": True, "plugin_id": PLUGIN_ID, "intent": "action", "action": action,
                "answer": str(result), "results": result if isinstance(result, list) else [result] if result else [],
                "result_count": len(result) if isinstance(result, list) else (1 if result else 0)}
    except NotImplementedError:
        return {"success": False, "plugin_id": PLUGIN_ID, "intent": "action", "action": action,
                "answer": f"Tool '{action}' not yet implemented.", "results": [], "result_count": 0}
    except Exception as e:
        return _error_response(str(e), action=action)

def _error_response(detail, action=""):
    return {"success": False, "plugin_id": PLUGIN_ID, "action": action,
            "answer": f"Error: {detail}", "results": [], "result_count": 0, "error": detail}
