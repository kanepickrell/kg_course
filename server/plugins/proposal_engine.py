#!/usr/bin/env python3
"""
proposal_engine.py
==================
LLM-powered improvement proposal engine for ATLAS agents.

Three patterns from HyperAgents / ADAS
───────────────────────────────────────

1. META-AGENT PROMPT STRUCTURE (ADAS, Hu et al. 2024)
   Expertise claim first, then archive context, then task.
   The meta-agent sees the full interaction history before
   reasoning about what to change. It is told to propose
   something NOVEL — not a repeat of prior attempts.

2. SELF-REFLECTION PASS (HyperAgents, Zhang et al. 2026)
   After the meta-agent generates a proposal, a second LLM
   call critiques novelty and correctness. Up to 2 refinement
   passes on quality, up to 3 on JSON parse errors.
   Mirrors HyperAgents' refinement loop exactly.

3. PARENT SELECTION SCORING (HyperAgents archive scoring)
   Signals are scored before reaching the LLM. Higher-confidence
   signals get priority. Over-represented signal types are
   penalised so the meta-agent doesn't fixate on one category.
   Only signals above 0.3 are sent to the LLM.

How proposals are generated
────────────────────────────
  Step 1  Score all signals from interactions.jsonl +
          execution_log.jsonl. Filter below threshold.
  Step 2  For each high-confidence signal, call the meta-
          agent LLM to reason about root cause and propose
          a concrete fix with a before/after diff.
  Step 3  Run self-reflection pass. Refine if needed.
  Step 4  Deduplicate against existing proposals. Persist.

How proposals are applied
──────────────────────────
  prompt_revision  writes to agent.py + prompt_history.json
  tool_addition    appends stub to tools.py
  exec_fix         patches manifest start_command
  rule_rewrite     updates filters.intent_rules in registry
"""

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from math import log
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DATA_DIR    = Path(__file__).parent.parent / "data"
LOG_DIR     = DATA_DIR / "plugin_logs"
PLUGINS_DIR = Path(__file__).parent


# ── Paths ──────────────────────────────────────────────────────────────────────

def _log_dir(plugin_id: str) -> Path:
    d = LOG_DIR / plugin_id
    d.mkdir(parents=True, exist_ok=True)
    return d

def _proposals_path(plugin_id: str) -> Path:
    return _log_dir(plugin_id) / "proposals.json"

def _stable_id(text: str) -> str:
    return "prop_" + hashlib.sha1(text.encode()).hexdigest()[:8]


# ── Log readers ────────────────────────────────────────────────────────────────

def _read_jsonl(path: Path, days: int) -> List[Dict]:
    if not path.exists():
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                if e.get("ts", "") >= cutoff:
                    out.append(e)
            except Exception:
                pass
    return out

def _read_interactions(plugin_id: str, days: int) -> List[Dict]:
    return _read_jsonl(_log_dir(plugin_id) / "interactions.jsonl", days)

def _read_execution_log(plugin_id: str, days: int) -> List[Dict]:
    return _read_jsonl(_log_dir(plugin_id) / "execution_log.jsonl", days)

def _read_current_prompt(plugin_id: str) -> str:
    p = PLUGINS_DIR / plugin_id / "agent.py"
    if not p.exists():
        return ""
    m = re.search(r'SYSTEM_PROMPT\s*=\s*"""(.*?)"""', p.read_text(), re.DOTALL)
    return m.group(1).strip() if m else ""

def _read_manifest(plugin_id: str) -> Dict:
    p = DATA_DIR / "plugin_manifests" / f"{plugin_id}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}

def _read_tools_py(plugin_id: str) -> str:
    p = PLUGINS_DIR / plugin_id / "tools.py"
    return p.read_text() if p.exists() else ""


# ── Pattern 3: Signal scoring (HyperAgents parent selection) ──────────────────

def _score_signals(
    plugin_id:  str,
    entries:    List[Dict],
    exec_log:   List[Dict],
    policy:     Dict,
    existing:   List[Dict],
) -> List[Tuple[str, float, Dict]]:
    """
    Score candidate signals before sending to LLM.

    HyperAgents parent selection:
      base_score      = evidence strength (0.0 – 1.0)
      novelty_penalty = -log(1 + times_this_type_proposed) * 0.15
      final           = base_score + novelty_penalty
      threshold       = 0.3 (below this → skip LLM call)
    """
    threshold = policy.get("correction_threshold", 0.25)
    days      = policy.get("tool_usage_window_days", 7)
    type_counts: Dict[str, int] = Counter(p["type"] for p in existing)
    signals: List[Tuple[str, float, Dict]] = []

    # Signal A: correction rate above threshold
    if entries:
        total = len(entries)
        bad   = sum(1 for e in entries if e.get("outcome") in ("rejected", "auto"))
        rate  = bad / total
        if rate > threshold:
            base  = min(1.0, (rate - threshold) / max(threshold, 0.01))
            novel = -log(1 + type_counts.get("prompt_revision", 0)) * 0.15
            score = base + novel
            rejected_qs = [
                e.get("question", "")
                for e in entries
                if e.get("outcome") in ("rejected", "auto") and e.get("question")
            ]
            signals.append(("correction_rate", score, {
                "rate": rate, "threshold": threshold,
                "total": total, "bad": bad,
                "rejected_qs": rejected_qs, "days": days,
            }))

    # Signal B: repeated zero-result queries (tool gap)
    if policy.get("auto_propose_tool_additions", False):
        no_result = [
            e.get("question", "").strip().lower()
            for e in entries
            if e.get("result_count", -1) == 0
            and not e.get("tool_names")
            and e.get("question")
        ]
        for question, count in Counter(no_result).most_common(3):
            if count < 5:
                break
            base  = min(1.0, count / 20)
            novel = -log(1 + type_counts.get("tool_addition", 0)) * 0.2
            signals.append(("tool_gap", base + novel, {
                "question": question, "count": count,
            }))

    # Signal C: execution failures
    if policy.get("track_execution_failures", True) and exec_log:
        failures = [e for e in exec_log
                    if e.get("type") == "failure" and e.get("exit_code") not in (0, None)]
        if len(failures) >= 3:
            base  = min(1.0, len(failures) / 10)
            novel = -log(1 + type_counts.get("exec_fix", 0)) * 0.15
            signals.append(("exec_failure", base + novel, {
                "count":      len(failures),
                "recent_err": failures[-1].get("stderr_tail", ""),
                "exit_codes": [f.get("exit_code") for f in failures[-3:]],
            }))

    signals = [(t, s, p) for t, s, p in signals if s > 0.3]
    return sorted(signals, key=lambda x: x[1], reverse=True)


# ── Pattern 1: Meta-agent prompts (ADAS structure) ─────────────────────────────

def _build_meta_prompt(
    plugin_id:      str,
    signal_type:    str,
    signal_data:    Dict,
    current_prompt: str,
    tools_src:      str,
    manifest:       Dict,
    existing:       List[Dict],
) -> Tuple[str, str]:
    """
    ADAS pattern: expertise claim → archive context → task → schema.
    The meta-agent sees prior proposals so it does not repeat them.
    """
    resolved      = [p for p in existing if p.get("status") in ("approved", "rejected")]
    archive_lines = [
        f"  [{p['status'].upper()}] {p['type']}: {p['summary']}"
        for p in resolved[-5:]
    ]
    archive_str = "\n".join(archive_lines) if archive_lines else "  (no prior proposals)"

    system = (
        "You are an expert ML researcher and prompt engineer specializing in "
        "LLM-based agentic systems for cybersecurity and intelligence analysis.\n\n"
        "Your objective: analyze underperforming agents and propose concrete, "
        "targeted improvements. Reason carefully about root causes before proposing.\n\n"
        "IMPORTANT: Study prior proposals. Do NOT repeat rejected proposals. "
        "Propose something meaningfully different from anything already attempted.\n\n"
        f"PRIOR PROPOSALS FOR THIS AGENT:\n{archive_str}\n\n"
        "Return ONLY valid JSON — no prose, no markdown fences."
    )

    if signal_type == "correction_rate":
        rate      = signal_data["rate"]
        bad       = signal_data["bad"]
        total     = signal_data["total"]
        days      = signal_data["days"]
        bad_qs    = signal_data["rejected_qs"][:15]
        threshold = signal_data["threshold"]
        user = (
            "Analyze this underperforming agent and propose a prompt revision.\n\n"
            f"AGENT SYSTEM PROMPT (current):\n{current_prompt}\n\n"
            f"PERFORMANCE:\n"
            f"- Correction rate: {rate:.1%} over {days} days "
            f"(threshold: {threshold:.0%})\n"
            f"- {bad} of {total} interactions were rejected or unconfirmed\n\n"
            f"QUERIES THAT FAILED (sample of {len(bad_qs)}):\n"
            f"{json.dumps(bad_qs, indent=2)}\n\n"
            "Your task:\n"
            "1. Identify the specific root cause — what pattern in the failing "
            "queries reveals a gap in the prompt?\n"
            "2. Write a revised system prompt that addresses the root cause "
            "without over-constraining the agent.\n\n"
            'Return JSON: {"root_cause": "...", "summary": "...", '
            '"detail": "...", "proposed_prompt": "...", "confidence": 0.0}'
        )

    elif signal_type == "tool_gap":
        question = signal_data["question"]
        count    = signal_data["count"]
        user = (
            "An agent is missing a tool that operators repeatedly need.\n\n"
            f"AGENT TOOLS (current tools.py):\n"
            f"{tools_src[:2000] if tools_src else '(no tools.py found)'}\n\n"
            f"REPEATED UNRESOLVED QUERY ({count} times):\n\"{question}\"\n\n"
            "Your task:\n"
            "1. Understand what data or operation this query needs.\n"
            "2. Write a Python function stub for tools.py that would handle it.\n"
            "3. Include a SPARQL comment if data likely lives in the graph.\n\n"
            'Return JSON: {"summary": "...", "detail": "...", '
            '"function_name": "...", "stub_code": "...", "confidence": 0.0}'
        )

    elif signal_type == "exec_failure":
        count     = signal_data["count"]
        recent    = signal_data["recent_err"]
        exec_ctx  = manifest.get("execution_context", {})
        cmd       = exec_ctx.get("start_command", "")
        user = (
            "An agent's executable program is repeatedly failing to start.\n\n"
            f"CURRENT START COMMAND:\n{cmd}\n\n"
            f"EXECUTION CONTEXT:\n{json.dumps(exec_ctx, indent=2)}\n\n"
            f"FAILURE COUNT: {count}\n\n"
            f"MOST RECENT ERROR:\n{recent[:500]}\n\n"
            "Your task:\n"
            "1. Diagnose the failure from the error output.\n"
            "2. Propose a corrected start command.\n\n"
            'Return JSON: {"summary": "...", "detail": "...", '
            '"fixed_command": "...", "confidence": 0.0}'
        )
    else:
        user = "{}"

    return system, user


# ── Pattern 2: Self-reflection (HyperAgents refinement loop) ──────────────────

def _word_similarity(a: str, b: str) -> float:
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


async def _reflect_and_refine(
    raw_json:    Dict,
    existing:    List[Dict],
    llm_fn,
) -> Dict:
    """
    Two refinement passes on novelty + correctness.
    Mirrors HyperAgents: 2 passes on quality, up to 3 on errors.
    """
    existing_summaries = [
        p.get("summary", "") for p in existing
        if p.get("status") != "rejected"
    ]

    reflection_system = (
        "You are a rigorous peer reviewer evaluating an improvement proposal "
        "for an AI agent. Check for novelty, feasibility, and correctness. "
        "Return ONLY valid JSON matching the exact schema of the input."
    )

    for _ in range(2):
        summary    = raw_json.get("summary", "")
        is_dup     = any(_word_similarity(summary, s) > 0.7 for s in existing_summaries)
        dup_note   = "WARNING: This proposal is too similar to an existing one. Revise substantially." if is_dup else "Appears novel."

        reflection_user = (
            f"Review this proposal:\n\n{json.dumps(raw_json, indent=2)}\n\n"
            f"Already proposed (do not repeat):\n{json.dumps(existing_summaries, indent=2)}\n\n"
            f"Novelty check: {dup_note}\n\n"
            "Is this proposal:\n"
            "1. NOVEL — meaningfully different from prior proposals?\n"
            "2. CORRECT — will the change plausibly fix the described problem?\n"
            "3. SPECIFIC — does it make a concrete reviewable change?\n\n"
            "Return the original JSON if all YES, or a revised version if any NO. "
            "Schema must match exactly."
        )

        try:
            raw = await llm_fn(reflection_user, system=reflection_system, temperature=0.1)
            clean   = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            refined = json.loads(clean)
            if "summary" in refined and "detail" in refined:
                raw_json = refined
        except Exception:
            break

    return raw_json


# ── Main engine ────────────────────────────────────────────────────────────────

async def run_analysis(plugin_id: str, policy: Dict) -> List[Dict]:
    """
    Full LLM-powered analysis pipeline.
    Returns complete proposal list (existing + new).
    """
    if not policy.get("enabled", False):
        return load_proposals(plugin_id)

    days     = policy.get("tool_usage_window_days", 7)
    entries  = _read_interactions(plugin_id, days)
    exec_log = _read_execution_log(plugin_id, days)
    existing = load_proposals(plugin_id)
    existing_ids = {p["id"] for p in existing}

    try:
        from llm_client import chat_completion as _llm
    except ImportError:
        return existing

    async def llm_fn(user_msg: str, system: str = "", temperature: float = 0.2) -> str:
        return await _llm(user_msg, system=system, temperature=temperature)

    # Step 1: Score signals
    signals = _score_signals(plugin_id, entries, exec_log, policy, existing)
    if not signals:
        return existing

    current_prompt = _read_current_prompt(plugin_id)
    tools_src      = _read_tools_py(plugin_id)
    manifest       = _read_manifest(plugin_id)
    new_proposals  = []

    for signal_type, score, signal_data in signals[:3]:
        # Step 2: Meta-agent call
        system_prompt, user_msg = _build_meta_prompt(
            plugin_id, signal_type, signal_data,
            current_prompt, tools_src, manifest, existing,
        )

        raw_json    = None
        error_count = 0
        while error_count < 3:
            try:
                raw   = await llm_fn(user_msg, system=system_prompt, temperature=0.3)
                clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
                raw_json = json.loads(clean)
                break
            except Exception:
                error_count += 1

        if raw_json is None:
            continue

        # Step 3: Self-reflection
        raw_json = await _reflect_and_refine(raw_json, existing, llm_fn)

        # Step 4: Build record
        proposal = _build_proposal_record(
            plugin_id, signal_type, signal_data, raw_json, score
        )
        if not proposal or proposal["id"] in existing_ids:
            continue

        new_proposals.append(proposal)
        existing_ids.add(proposal["id"])

    all_proposals = existing + new_proposals
    if new_proposals:
        _save_proposals(plugin_id, all_proposals)

    return all_proposals


def _build_proposal_record(
    plugin_id:   str,
    signal_type: str,
    signal_data: Dict,
    llm_output:  Dict,
    score:       float,
) -> Optional[Dict]:
    now = datetime.now(timezone.utc).isoformat()

    if signal_type == "correction_rate":
        if "proposed_prompt" not in llm_output:
            return None
        return {
            "id":      _stable_id(f"{plugin_id}prompt{llm_output.get('summary','')}"),
            "type":    "prompt_revision",
            "status":  "pending",
            "summary": llm_output.get("summary", "Prompt revision")[:120],
            "detail":  llm_output.get("detail", ""),
            "root_cause": llm_output.get("root_cause", ""),
            "triggered_by": (
                f"Correction rate {signal_data['rate']:.1%} over {signal_data['days']}d "
                f"(threshold {signal_data['threshold']:.0%}, n={signal_data['total']})"
            ),
            "created_at": now,
            "score":      round(score, 3),
            "confidence": llm_output.get("confidence", 0.5),
            "correction_rate_at_trigger": round(signal_data["rate"], 3),
            "diff": {
                "before": _read_current_prompt(plugin_id),
                "after":  llm_output["proposed_prompt"],
            },
        }

    if signal_type == "tool_gap":
        if "stub_code" not in llm_output:
            return None
        return {
            "id":      _stable_id(f"{plugin_id}tool{llm_output.get('function_name','')}"),
            "type":    "tool_addition",
            "status":  "pending",
            "summary": llm_output.get("summary", "Add tool")[:120],
            "detail":  llm_output.get("detail", ""),
            "triggered_by": (
                f"\"{signal_data['question'][:60]}\" repeated "
                f"{signal_data['count']} times with no tool match"
            ),
            "created_at": now,
            "score":      round(score, 3),
            "confidence": llm_output.get("confidence", 0.5),
            "function_name": llm_output.get("function_name", ""),
            "diff": {
                "before": "# No matching tool",
                "after":  llm_output["stub_code"],
            },
        }

    if signal_type == "exec_failure":
        if "fixed_command" not in llm_output:
            return None
        old_cmd = _read_manifest(plugin_id).get("execution_context", {}).get("start_command", "")
        return {
            "id":      _stable_id(f"{plugin_id}exec{llm_output.get('fixed_command','')}"),
            "type":    "exec_fix",
            "status":  "pending",
            "summary": llm_output.get("summary", "Fix execution")[:120],
            "detail":  llm_output.get("detail", ""),
            "triggered_by": f"program_start failed {signal_data['count']} times",
            "created_at": now,
            "score":      round(score, 3),
            "confidence": llm_output.get("confidence", 0.5),
            "diff": {
                "before": old_cmd,
                "after":  llm_output["fixed_command"],
            },
        }

    return None


# ── Persistence ────────────────────────────────────────────────────────────────

def load_proposals(plugin_id: str) -> List[Dict]:
    path = _proposals_path(plugin_id)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []

def _save_proposals(plugin_id: str, proposals: List[Dict]) -> None:
    _proposals_path(plugin_id).write_text(json.dumps(proposals, indent=2))


# ── Apply approved proposals ───────────────────────────────────────────────────

def apply_proposal(plugin_id: str, proposal: Dict) -> Dict[str, Any]:
    ptype = proposal.get("type")
    after = proposal.get("diff", {}).get("after", "")
    try:
        if ptype == "prompt_revision":  return _apply_prompt_revision(plugin_id, after, proposal)
        if ptype == "tool_addition":    return _apply_tool_addition(plugin_id, after, proposal)
        if ptype == "exec_fix":         return _apply_exec_fix(plugin_id, after, proposal)
        if ptype == "rule_rewrite":     return _apply_rule_rewrite(plugin_id, after, proposal)
        return {"success": False, "applied": False, "message": f"Unknown type: {ptype}"}
    except Exception as e:
        return {"success": False, "applied": False, "message": str(e)}


def _apply_prompt_revision(plugin_id: str, new_prompt: str, proposal: Dict) -> Dict:
    from .endpoints import _write_system_prompt_to_agent, _update_live_config
    agent_path = PLUGINS_DIR / plugin_id / "agent.py"
    changed    = _write_system_prompt_to_agent(agent_path, new_prompt)
    _update_live_config(plugin_id, system_prompt=new_prompt)

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
        "version":                version,
        "approved_at":            datetime.now(timezone.utc).isoformat(),
        "approved_by":            "improvement_policy",
        "prompt":                 new_prompt,
        "old_prompt":             proposal.get("diff", {}).get("before", ""),
        "summary":                proposal.get("summary", ""),
        "root_cause":             proposal.get("root_cause", ""),
        "correction_rate_before": proposal.get("correction_rate_at_trigger"),
        "correction_rate_after":  None,
        "proposal_id":            proposal.get("id"),
        "score":                  proposal.get("score"),
    })
    history_path.write_text(json.dumps(history, indent=2))
    return {"success": True, "applied": changed, "message": f"Prompt updated (v{version})"}


def _apply_tool_addition(plugin_id: str, stub_code: str, proposal: Dict) -> Dict:
    tools_path = PLUGINS_DIR / plugin_id / "tools.py"
    if not tools_path.exists():
        return {"success": False, "applied": False, "message": "tools.py not found"}
    current = tools_path.read_text()
    fn_name = proposal.get("function_name", "")
    if fn_name and f"def {fn_name}" in current:
        return {"success": True, "applied": False, "message": "Stub already exists"}
    tools_path.write_text(current.rstrip() + "\n\n\n" + stub_code + "\n")
    return {"success": True, "applied": True, "message": "Stub added to tools.py"}


def _apply_exec_fix(plugin_id: str, new_command: str, proposal: Dict) -> Dict:
    manifest_path = DATA_DIR / "plugin_manifests" / f"{plugin_id}.json"
    if not manifest_path.exists():
        return {"success": False, "applied": False, "message": "Manifest not found"}
    data = json.loads(manifest_path.read_text())
    if "execution_context" not in data:
        return {"success": False, "applied": False, "message": "No execution_context"}
    data["execution_context"]["start_command"] = new_command
    manifest_path.write_text(json.dumps(data, indent=2))
    return {"success": True, "applied": True, "message": f"start_command updated"}


def _apply_rule_rewrite(plugin_id: str, new_rules_json: str, proposal: Dict) -> Dict:
    try:
        new_rules = json.loads(new_rules_json)
    except Exception:
        return {"success": False, "applied": False, "message": "Invalid rules JSON"}
    from .base import PluginRegistry, IntentRules
    config = PluginRegistry.get_config(plugin_id)
    if not config:
        return {"success": False, "applied": False, "message": "Plugin not found"}
    config.set_intent_rules(IntentRules(**new_rules))
    PluginRegistry.update_config(plugin_id, {"filters": config.filters})
    return {"success": True, "applied": True, "message": "Intent rules updated"}


# ── Interaction logging (called directly from agent.py) ────────────────────────

def log_interaction(plugin_id: str, entry: Dict) -> None:
    """Write one interaction to interactions.jsonl. No HTTP round-trip."""
    entry["ts"] = datetime.now(timezone.utc).isoformat()
    with open(_log_dir(plugin_id) / "interactions.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


def log_execution_event(plugin_id: str, event_type: str, **kwargs) -> None:
    """Write a program lifecycle event to execution_log.jsonl."""
    entry = {
        "ts":   datetime.now(timezone.utc).isoformat(),
        "id":   _stable_id(f"{plugin_id}{event_type}{datetime.now().isoformat()}"),
        "type": event_type,
        **kwargs,
    }
    with open(_log_dir(plugin_id) / "execution_log.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


def update_interaction_outcome(plugin_id: str, question: str, outcome: str) -> bool:
    """
    Upgrade the most recent matching 'auto' interaction to confirmed/rejected.
    Called when operator clicks thumbs-up in the Console.
    """
    log_path = _log_dir(plugin_id) / "interactions.jsonl"
    if not log_path.exists():
        return False
    lines   = log_path.read_text().splitlines()
    target  = question.strip().lower()
    updated = False
    new_lines = []
    for line in reversed(lines):
        if not updated:
            try:
                e = json.loads(line)
                if (e.get("question", "").strip().lower() == target
                        and e.get("outcome") == "auto"):
                    e["outcome"] = outcome
                    line = json.dumps(e)
                    updated = True
            except Exception:
                pass
        new_lines.append(line)
    if updated:
        log_path.write_text("\n".join(reversed(new_lines)) + "\n")
    return updated