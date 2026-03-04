#!/usr/bin/env python3
"""
MAKER v4 vs v5 Comparison Tool

This script demonstrates the key differences between your original
v4 approach and the MAKER-compliant v5 approach.

Run this to see concrete examples of what changed.
"""

import json
from typing import List, Dict

# ============================================================================
# V4 STYLE (BROKEN)
# ============================================================================

V4_EXAMPLE_TASKS = [
    {
        "step": 1,
        "question": "Logs show DNS queries for 'mail.target-mil.gov' from IP 203.0.113.42 on March 15, 2024 at 14:32:18 UTC. What reconnaissance technique is this?",
        "issues": [
            "❌ Requires semantic inference (not just extraction)",
            "❌ Multiple correct answers possible",
            "❌ Natural language output (unbounded)",
            "❌ Includes narrative context (date, time, domain)"
        ]
    },
    {
        "step": 2,
        "question": "The same IP (203.0.113.42) then scanned ports 22, 80, 443, 3389, and 8443 on 'mail.target-mil.gov'. What tool signature does this port sequence match?",
        "issues": [
            "❌ Requires remembering previous step",
            "❌ Pattern matching across multiple values",
            "❌ Tool identification is subjective",
            "❌ Context pollution from 'same IP' reference"
        ]
    },
    {
        "step": 12,
        "question": "The mail server beacon (from 203.0.113.42 attack) uses interval 6 hours. The VPN server beacon uses interval 4 hours. Calculate: Over a 7-day period, how many MORE beacons does the VPN server send than the mail server?",
        "issues": [
            "❌ Multi-step: requires 3 calculations",
            "❌ Memory of previous steps (intervals from earlier)",
            "❌ Arithmetic reasoning",
            "❌ Could be decomposed into 3 atomic operations"
        ]
    }
]

# ============================================================================
# V5 STYLE (MAKER-COMPLIANT)
# ============================================================================

V5_EXAMPLE_TASKS = [
    {
        "task_id": 1,
        "operation": "EXTRACT_TIMESTAMP",
        "input": "2024-03-15T14:32:18Z 203.0.113.42:52341 -> 10.0.1.5:443 TCP ALLOW 1024B",
        "prompt": "Extract ONLY the timestamp.\nLog: 2024-03-15T14:32:18Z 203.0.113.42:52341 -> 10.0.1.5:443 TCP ALLOW 1024B\nFormat: YYYY-MM-DDTHH:MM:SSZ\nOutput:",
        "ground_truth": "2024-03-15T14:32:18Z",
        "output_type": "timestamp",
        "advantages": [
            "✅ Single primitive operation (extract one field)",
            "✅ Deterministic (no reasoning)",
            "✅ Discrete output (timestamp format)",
            "✅ Minimal context (just the log line)"
        ]
    },
    {
        "task_id": 2,
        "operation": "EXTRACT_SOURCE_IP",
        "input": "2024-03-15T14:32:18Z 203.0.113.42:52341 -> 10.0.1.5:443 TCP ALLOW 1024B",
        "prompt": "Extract ONLY the source IP.\nLog: 2024-03-15T14:32:18Z 203.0.113.42:52341 -> 10.0.1.5:443 TCP ALLOW 1024B\nFormat: X.X.X.X\nOutput:",
        "ground_truth": "203.0.113.42",
        "output_type": "ip_address",
        "advantages": [
            "✅ One extraction operation",
            "✅ Exact pattern matching",
            "✅ Normalized output via regex",
            "✅ No semantic ambiguity"
        ]
    },
    {
        "task_id": 3,
        "operation": "EXTRACT_PROTOCOL",
        "input": "2024-03-15T14:32:18Z 203.0.113.42:52341 -> 10.0.1.5:443 TCP ALLOW 1024B",
        "prompt": "Extract ONLY the protocol.\nLog: 2024-03-15T14:32:18Z 203.0.113.42:52341 -> 10.0.1.5:443 TCP ALLOW 1024B\nValid: TCP, UDP, ICMP\nOutput:",
        "ground_truth": "TCP",
        "output_type": "enum",
        "valid_values": ["TCP", "UDP", "ICMP"],
        "advantages": [
            "✅ Enum output (3 possible values)",
            "✅ Normalization maps variants to canonical form",
            "✅ Voting converges rapidly",
            "✅ Symbolic validation (exact match)"
        ]
    }
]

# ============================================================================
# VOTING COMPARISON
# ============================================================================

V4_VOTING_EXAMPLE = {
    "task": "What reconnaissance technique is this?",
    "raw_votes": {
        "subdomain enumeration": 1,
        "dns enumeration": 1,
        "subdomain discovery": 1,
        "dns reconnaissance": 1,
        "domain mapping": 1,
        "subdomain scanning": 1,
        "dns probing": 1
    },
    "problem": "❌ Vote splitting - 7 different strings, all semantically identical",
    "convergence": "NEVER (max samples reached, no clear winner)"
}

V5_VOTING_EXAMPLE = {
    "task": "Extract the protocol",
    "raw_outputs": [
        "TCP",
        "tcp",
        "The protocol is TCP",
        "It's TCP",
        "TCP protocol",
        "Protocol: TCP",
        "tcp"
    ],
    "normalized_votes": {
        "TCP": 7
    },
    "advantage": "✅ Normalization maps all variants to 'TCP' → instant convergence",
    "convergence": "After 3 samples (k=3 margin achieved)"
}

# ============================================================================
# DISPLAY FUNCTIONS
# ============================================================================

def print_section(title: str):
    print(f"\n{'='*80}")
    print(f"{title:^80}")
    print(f"{'='*80}\n")

def print_v4_task(task: Dict):
    print(f"Step {task['step']}:")
    print(f"  Question: {task['question'][:80]}...")
    print(f"\n  Issues:")
    for issue in task['issues']:
        print(f"    {issue}")
    print()

def print_v5_task(task: Dict):
    print(f"Task {task['task_id']}: {task['operation']}")
    print(f"  Input:  {task['input']}")
    print(f"  Prompt: {task['prompt'][:80]}...")
    print(f"  Ground truth: {task['ground_truth']}")
    print(f"  Output type:  {task['output_type']}")
    if 'valid_values' in task:
        print(f"  Valid values: {task['valid_values']}")
    print(f"\n  Advantages:")
    for adv in task['advantages']:
        print(f"    {adv}")
    print()

def print_voting_comparison():
    print_section("VOTING COMPARISON")
    
    print("V4 VOTING (BROKEN):")
    print(f"  Task: {V4_VOTING_EXAMPLE['task']}")
    print(f"\n  Raw votes:")
    for answer, count in V4_VOTING_EXAMPLE['raw_votes'].items():
        print(f"    '{answer}': {count}")
    print(f"\n  {V4_VOTING_EXAMPLE['problem']}")
    print(f"  Convergence: {V4_VOTING_EXAMPLE['convergence']}")
    
    print("\n" + "-"*80 + "\n")
    
    print("V5 VOTING (FIXED):")
    print(f"  Task: {V5_VOTING_EXAMPLE['task']}")
    print(f"\n  Raw outputs:")
    for i, output in enumerate(V5_VOTING_EXAMPLE['raw_outputs'], 1):
        print(f"    Sample {i}: '{output}'")
    print(f"\n  After normalization:")
    for answer, count in V5_VOTING_EXAMPLE['normalized_votes'].items():
        print(f"    '{answer}': {count} votes")
    print(f"\n  {V5_VOTING_EXAMPLE['advantage']}")
    print(f"  Convergence: {V5_VOTING_EXAMPLE['convergence']}")

def print_scale_comparison():
    print_section("SCALE COMPARISON")
    
    print("V4 APPROACH:")
    print("  Chain length: 25 steps")
    print("  Expected divergence: NONE (too short)")
    print("  Why: Monolithic models can handle 25 steps without catastrophic failure")
    print()
    
    print("V5 APPROACH:")
    print("  Chain lengths:")
    print("    - v5 (basic):   500 atomic operations")
    print("    - v5b (extreme): 2000 atomic operations")
    print("    - v5b (massive): 5000-10000 atomic operations (configurable)")
    print()
    print("  Expected divergence: MASSIVE")
    print("  Why: At 1000+ steps, monolithic error accumulation becomes exponential")
    print()
    print("  Predicted results at 2000 steps:")
    print("    Monolithic: 40-50% (catastrophic collapse)")
    print("    Atomic:     75-85% (stable via voting + isolation)")
    print("    Gap:        25-35 percentage points")

def print_key_principles():
    print_section("KEY PRINCIPLES")
    
    principles = [
        ("Atomicity", 
         "V4: Multi-step reasoning required",
         "V5: ONE primitive operation per task"),
        
        ("Action Space",
         "V4: Unbounded natural language",
         "V5: Discrete values (enums, integers, IPs)"),
        
        ("Voting",
         "V4: Vote splitting on semantic equivalents",
         "V5: Normalization before voting → convergence"),
        
        ("Context",
         "V4: Full scenario + narrative + multi-step history",
         "V5: Minimal (just the input for THIS operation)"),
        
        ("Validation",
         "V4: Fuzzy substring matching",
         "V5: Symbolic exact match"),
        
        ("Decomposition",
         "V4: Medium-level tasks (still complex)",
         "V5: Maximal decomposition (m=1)"),
        
        ("Scale",
         "V4: 25 steps (insufficient)",
         "V5: 500-2000+ steps (exponential regime)")
    ]
    
    for principle, v4, v5 in principles:
        print(f"{principle}:")
        print(f"  ❌ {v4}")
        print(f"  ✅ {v5}")
        print()

def main():
    print("\n" + "="*80)
    print(" "*20 + "MAKER v4 vs v5 COMPARISON")
    print("="*80)
    
    print_section("V4 TASK EXAMPLES (PROBLEMATIC)")
    for task in V4_EXAMPLE_TASKS:
        print_v4_task(task)
    
    print_section("V5 TASK EXAMPLES (MAKER-COMPLIANT)")
    for task in V5_EXAMPLE_TASKS:
        print_v5_task(task)
    
    print_voting_comparison()
    print_scale_comparison()
    print_key_principles()
    
    print_section("SUMMARY")
    print("""
V4 Implementation Issues:
  1. Tasks not atomic (multi-step reasoning)
  2. Voting broken (natural language vote splitting)
  3. Context pollution (narrative + history)
  4. Fuzzy validation (substring matching)
  5. Not maximally decomposed
  6. Chain too short (25 vs 2000+ needed)
  7. No output normalization

V5 Improvements:
  1. ✅ TRUE atomicity (one extraction per task)
  2. ✅ Normalized voting (maps variants to canonical form)
  3. ✅ Minimal context (just log line)
  4. ✅ Symbolic validation (exact match)
  5. ✅ Maximal decomposition (m=1)
  6. ✅ Long chains (500-2000+ steps)
  7. ✅ Discrete action space (enums, integers, IPs)

Expected Result:
  At 2000 steps, you should see 25-40 point gap favoring atomic approach.
  This is the MAKER thesis: exponential divergence at scale.

Next Steps:
  1. Run: python maker_demo_v5_atomic.py (500 steps)
  2. Run: python maker_demo_v5b_extreme.py (2000 steps)
  3. For massive scale, edit v5b and set NUM_LOGS = 2000 (10k steps)
    """)

if __name__ == "__main__":
    main()