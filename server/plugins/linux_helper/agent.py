import json
from typing import Any, Dict

PLUGIN_ID = 'linux_helper'

SYSTEM_PROMPT = """
You are Linux Helper, a utility agent that can perform simple file and text operations.

You have access to three tools:
- add_numbers: add two numbers together
- reverse_text: reverse a string of text
- list_files: list files in a directory

Rules:
- Always call a tool to answer — never guess at results
- If a tool returns an error, report it clearly and suggest a fix
- Decline requests outside your tool set and explain what you can help with
"""

def get_config():
    from plugins.base import PluginRegistry
    config = PluginRegistry.get_config(PLUGIN_ID)
    if not config:
        raise RuntimeError(f'Plugin {PLUGIN_ID!r} is not registered.')
    return config


ROUTER_SYSTEM = """You are a strict intent classifier. Return ONLY a JSON object.
Schema: {"intent": "direct_answer"|"tool_call"|"graph_query"|"decline", "confidence": 0.0-1.0, "reason": "<one sentence>", "answer": "<string or null>"}
- direct_answer: user asks about agent identity or capabilities
- tool_call: user wants to use one of the agent tools
- graph_query: user asks about graph data
- decline: outside domain"""


DISPATCH_SYSTEM = """You are a tool dispatcher. Return ONLY a JSON object.
Schema: {"tool": "tool_name", "args": {"arg1": "value1"}}
Available tools:
- exec_add_numbers(a: str, b: str)
- exec_reverse_text(text: str)
- exec_list_files(directory: str)
Return only the JSON object."""


async def handle(req: Dict[str, Any]) -> Dict[str, Any]:
    config = get_config()
    message = req.get('message') or req.get('query') or ''
    action  = req.get('action')

    if action and not message:
        return await _dispatch_action(action, req.get('params') or {}, config)
    if not message:
        return _error_response('No message or action provided')

    from llm_client import chat_completion

    # 1. Classify intent
    try:
        raw = await chat_completion(
            f'User message: {json.dumps(message)}\nAgent persona: {(config.system_prompt or "")[:200]}\n\nClassify intent.',
            system=ROUTER_SYSTEM, model=config.llm_model, temperature=0.0,
        )
        decision = json.loads(raw.strip().lstrip('```json').lstrip('```').rstrip('```').strip())
    except Exception:
        decision = {'intent': 'tool_call'}

    intent = decision.get('intent', 'tool_call')

    if intent == 'direct_answer' and decision.get('answer'):
        return {'success': True, 'plugin_id': PLUGIN_ID, 'intent': 'direct_answer',
                'answer': decision['answer'], 'results': [], 'result_count': 0}

    if intent == 'decline' and decision.get('answer'):
        return {'success': True, 'plugin_id': PLUGIN_ID, 'intent': 'decline',
                'answer': decision['answer'], 'results': [], 'result_count': 0}

    if intent == 'graph_query':
        return await _graph_query(message, config)

    # 2. Dispatch to tool
    try:
        raw = await chat_completion(
            f'User message: {json.dumps(message)}\n\nWhich tool and args?',
            system=DISPATCH_SYSTEM, model=config.llm_model, temperature=0.0,
        )
        dispatch = json.loads(raw.strip().lstrip('```json').lstrip('```').rstrip('```').strip())
        tool = dispatch.get('tool')
        args = dispatch.get('args', {})
    except Exception as e:
        return _error_response(f'Dispatch failed: {e}')

    import importlib
    tools_mod = importlib.import_module(f'plugins.{PLUGIN_ID}.tools')
    fn = getattr(tools_mod, tool, None)
    if fn is None:
        return _error_response(f'Tool {tool!r} not found in tools.py')

    try:
        result = fn(**args)
    except NotImplementedError:
        return {'success': False, 'plugin_id': PLUGIN_ID, 'intent': 'tool_call',
                'answer': f'Tool {tool!r} is not yet implemented.', 'results': [], 'result_count': 0}
    except Exception as e:
        return _error_response(str(e))

    narration = await chat_completion(
        f'User asked: {json.dumps(message)}\nTool {tool}({args}) returned: {json.dumps(result)}\nWrite a brief friendly answer.',
        system=config.system_prompt, model=config.llm_model, temperature=0.1,
    )
    return {'success': result.get('success', True) if isinstance(result, dict) else True,
            'plugin_id': PLUGIN_ID, 'intent': 'tool_call', 'tool': tool,
            'answer': narration, 'results': [result], 'result_count': 1}


async def _graph_query(message: str, config) -> Dict[str, Any]:
    try:
        from nl_query_engine import natural_language_query, NaturalQueryRequest
        from llm_client import chat_completion
        result = await natural_language_query(NaturalQueryRequest(question=message, show_sparql=True))
        result = result.dict()
        if result.get('success') and result.get('results'):
            narration = await chat_completion(
                f'User asked: {json.dumps(message)}\nGraph returned {result["result_count"]} result(s):\n{json.dumps(result["results"][:20], indent=2)}\nWrite a concise answer.',
                system=config.system_prompt, model=config.llm_model, temperature=0.1,
            )
        else:
            narration = result.get('answer', 'No results found.')
        return {'success': result.get('success', False), 'plugin_id': PLUGIN_ID, 'intent': 'graph_query',
                'answer': narration, 'sparql': result.get('sparql'), 'results': result.get('results', []),
                'result_count': result.get('result_count', 0), 'timing_ms': result.get('timing_ms')}
    except Exception as e:
        return _error_response(str(e))


async def _dispatch_action(action: str, params: Dict[str, Any], config) -> Dict[str, Any]:
    """Handle direct tool calls from the Tool Inspector."""
    import importlib
    tools_mod = importlib.import_module(f'plugins.{PLUGIN_ID}.tools')
    fn = getattr(tools_mod, action, None)
    if fn is None:
        return _error_response(f'Tool {action!r} not found', action=action)
    try:
        result = fn(**params)
        return {'success': True, 'plugin_id': PLUGIN_ID, 'intent': 'action',
                'action': action,
                'answer': json.dumps(result, indent=2) if isinstance(result, dict) else str(result),
                'results': [result] if result is not None else [], 'result_count': 1 if result is not None else 0}
    except NotImplementedError:
        return {'success': False, 'plugin_id': PLUGIN_ID, 'intent': 'action',
                'action': action, 'answer': f'Tool {action!r} not yet implemented.',
                'results': [], 'result_count': 0}
    except Exception as e:
        return _error_response(str(e), action=action)


def _error_response(detail: str, action: str = '') -> Dict[str, Any]:
    return {'success': False, 'plugin_id': PLUGIN_ID, 'action': action,
            'answer': f'Error: {detail}', 'results': [], 'result_count': 0, 'error': detail}
