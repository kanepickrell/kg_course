#!/usr/bin/env python3
"""
ProtoGraph Ontology Restoration Script
Restores ontology concepts and taxonomy terms to ArangoDB.

Usage:
    python restore_ontology.py --host localhost --port 8529 --db protograph --user root --password <password>
    
Or with environment variables:
    ARANGO_HOST=localhost ARANGO_PORT=8529 ARANGO_DB=protograph python restore_ontology.py
"""

import argparse
import os
import json
from typing import Dict, List, Any

try:
    from arango import ArangoClient
except ImportError:
    print("❌ python-arango not installed. Run: pip install python-arango")
    exit(1)


# ============================================================================
# ONTOLOGY CONCEPTS DATA
# ============================================================================

ONTOLOGY_CONCEPTS = {
    "ontology_id": "proto:ProtoGraphOntology",
    "ontology_label": "ProtoGraph Ontology",
    "description": "Core ontology for 318th RANS ProtoGraph knowledge graph",
    "namespace": "https://protograph.318rans.mil/ontology/",
    "version": "1.0.0",
    "last_updated": "2026-01-16",
    "concepts": [
        {
            "uri": "proto:concept/Thing",
            "label": "Thing",
            "definition": "Root concept - all entities in ProtoGraph are Things",
            "parent_uri": None,
            "abstract": True,
            "collection": None,
            "properties": [
                {"name": "id", "type": "string", "required": True, "description": "Unique identifier"},
                {"name": "created_at", "type": "datetime", "required": False, "description": "When this entity was created"},
                {"name": "updated_at", "type": "datetime", "required": False, "description": "When this entity was last modified"}
            ]
        },
        {
            "uri": "proto:concept/Agent",
            "label": "Agent",
            "definition": "An entity that can perform actions - people or teams",
            "parent_uri": "proto:concept/Thing",
            "abstract": True,
            "collection": None,
            "properties": [
                {"name": "name", "type": "string", "required": True, "description": "Display name of the agent"}
            ]
        },
        {
            "uri": "proto:concept/Person",
            "label": "Person",
            "definition": "An individual team member",
            "parent_uri": "proto:concept/Agent",
            "abstract": False,
            "collection": "Person",
            "taxonomy": "team_members",
            "properties": [
                {"name": "team", "type": "uri", "required": False, "taxonomy": "teams", "description": "Team this person belongs to"},
                {"name": "role", "type": "string", "required": False, "description": "Job title or role"},
                {"name": "email", "type": "string", "required": False, "description": "Email address"}
            ]
        },
        {
            "uri": "proto:concept/Team",
            "label": "Team",
            "definition": "An organizational team within 318th RANS",
            "parent_uri": "proto:concept/Agent",
            "abstract": False,
            "collection": "Team",
            "taxonomy": "teams",
            "properties": [
                {"name": "responsibilities", "type": "string[]", "required": False, "description": "List of team responsibilities"},
                {"name": "color", "type": "string", "required": False, "description": "UI color code for the team"}
            ]
        },
        {
            "uri": "proto:concept/Artifact",
            "label": "Artifact",
            "definition": "A work product created or used by teams - code, documents, logs, etc.",
            "parent_uri": "proto:concept/Thing",
            "abstract": True,
            "collection": None,
            "properties": [
                {"name": "name", "type": "string", "required": True, "description": "Display name of the artifact"},
                {"name": "description", "type": "string", "required": False, "description": "Detailed description"},
                {"name": "owner", "type": "uri", "required": False, "taxonomy": "teams", "description": "Team that owns this artifact"},
                {"name": "payload_url", "type": "string", "required": False, "description": "URL to full payload data"}
            ]
        },
        {
            "uri": "proto:concept/LibraryModule",
            "label": "Library Module",
            "definition": "An executable module in the Operator library - Cobalt Strike commands, Robot Framework keywords, scripts, etc.",
            "parent_uri": "proto:concept/Artifact",
            "abstract": False,
            "collection": "LibraryModule",
            "properties": [
                {"name": "category", "type": "string", "required": True, "taxonomy": "c2_frameworks", "description": "C2 framework this module belongs to (Cobalt Strike, Sliver, etc.)"},
                {"name": "tactic", "type": "string", "required": False, "taxonomy": "mitre_tactics", "description": "MITRE ATT&CK tactic ID (e.g., TA0006)"},
                {"name": "technique", "type": "string", "required": False, "taxonomy": "mitre_techniques", "description": "MITRE ATT&CK technique ID (e.g., T1003.001)"},
                {"name": "riskLevel", "type": "string", "required": False, "taxonomy": "risk_levels", "description": "Operational risk level"},
                {"name": "inputs", "type": "object[]", "required": False, "description": "Input parameters the module accepts"},
                {"name": "outputs", "type": "object[]", "required": False, "description": "Output data the module produces"},
                {"name": "requirements", "type": "object", "required": False, "description": "Execution requirements (elevated, arch, os)"},
                {"name": "confidence", "type": "number", "required": False, "description": "Classification confidence score (0-1)"}
            ]
        },
        {
            "uri": "proto:concept/RobotLog",
            "label": "Robot Log",
            "definition": "Execution log from Robot Framework test runs",
            "parent_uri": "proto:concept/Artifact",
            "abstract": False,
            "collection": "RobotLog",
            "properties": [
                {"name": "timestamp", "type": "datetime", "required": True, "description": "When the test was executed"},
                {"name": "scenario_id", "type": "string", "required": False, "description": "Reference to the execution plan/scenario"},
                {"name": "technique_id", "type": "string", "required": False, "taxonomy": "mitre_techniques", "description": "MITRE ATT&CK technique being tested (e.g., T1021.002)"},
                {"name": "command", "type": "string", "required": False, "description": "The command that was executed"},
                {"name": "result_status", "type": "string", "required": True, "taxonomy": "test_statuses", "description": "Test result (PASS or FAIL)"},
                {"name": "error_message", "type": "string", "required": False, "description": "Error message if test failed"},
                {"name": "duration_ms", "type": "integer", "required": False, "description": "Execution duration in milliseconds"}
            ]
        },
        {
            "uri": "proto:concept/WorkItem",
            "label": "Work Item",
            "definition": "A unit of work to be tracked - abstract base for stories, tasks, bugs",
            "parent_uri": "proto:concept/Thing",
            "abstract": True,
            "collection": None,
            "properties": [
                {"name": "title", "type": "string", "required": True, "description": "Title or name of the work item"},
                {"name": "description", "type": "string", "required": False, "description": "Detailed description"},
                {"name": "status", "type": "string", "required": True, "taxonomy": "work_statuses", "description": "Current workflow status"},
                {"name": "priority", "type": "string", "required": False, "taxonomy": "priority_levels", "description": "Priority level"},
                {"name": "assigned_to", "type": "uri", "required": False, "taxonomy": "team_members", "description": "Person assigned to this work"},
                {"name": "assigned_date", "type": "date", "required": False, "description": "Date work was assigned"},
                {"name": "due_date", "type": "date", "required": False, "description": "Target completion date"},
                {"name": "completed_date", "type": "date", "required": False, "description": "Actual completion date"}
            ]
        },
        {
            "uri": "proto:concept/DevelopmentStory",
            "label": "Development Story",
            "definition": "A development task to build, extend, or fix components - Jira-style work tracking",
            "parent_uri": "proto:concept/WorkItem",
            "abstract": False,
            "collection": "DevelopmentStory",
            "properties": [
                {"name": "story_name", "type": "string", "required": True, "description": "Name of the development story"},
                {"name": "story_type", "type": "string", "required": False, "taxonomy": "work_types", "description": "Type of work (Bug Fix, New Feature, Refactor, etc.)"},
                {"name": "requirements", "type": "string", "required": False, "description": "Technical requirements or acceptance criteria"},
                {"name": "sprint", "type": "string", "required": False, "description": "Sprint this story belongs to"},
                {"name": "related_artifacts", "type": "uri[]", "required": False, "range": "proto:concept/Artifact", "description": "Artifacts produced or modified by this story"},
                {"name": "story_points", "type": "integer", "required": False, "description": "Estimated effort in story points"}
            ]
        },
        {
            "uri": "proto:concept/Process",
            "label": "Process",
            "definition": "A multi-step workflow or procedure",
            "parent_uri": "proto:concept/Thing",
            "abstract": False,
            "collection": "Process",
            "properties": [
                {"name": "name", "type": "string", "required": True, "description": "Process name"},
                {"name": "description", "type": "string", "required": False, "description": "Process description"},
                {"name": "owner", "type": "uri", "required": False, "taxonomy": "teams", "description": "Team that owns this process"},
                {"name": "steps", "type": "uri[]", "required": False, "range": "proto:concept/Step", "description": "Ordered list of steps in this process"}
            ]
        },
        {
            "uri": "proto:concept/Step",
            "label": "Step",
            "definition": "A single step within a process",
            "parent_uri": "proto:concept/Thing",
            "abstract": True,
            "collection": None,
            "properties": [
                {"name": "name", "type": "string", "required": True, "description": "Step name"},
                {"name": "description", "type": "string", "required": False, "description": "What this step does"},
                {"name": "sequence", "type": "integer", "required": False, "description": "Order within the process"},
                {"name": "process", "type": "uri", "required": False, "range": "proto:concept/Process", "description": "Parent process this step belongs to"}
            ]
        },
        {
            "uri": "proto:concept/ExecutionStep",
            "label": "Execution Step",
            "definition": "A step that executes a Library Module or command",
            "parent_uri": "proto:concept/Step",
            "abstract": False,
            "collection": "ExecutionStep",
            "properties": [
                {"name": "module", "type": "uri", "required": False, "range": "proto:concept/LibraryModule", "description": "Library Module to execute"},
                {"name": "parameters", "type": "object", "required": False, "description": "Parameters to pass to the module"},
                {"name": "expected_outcome", "type": "string", "required": False, "description": "Expected result of this step"}
            ]
        }
    ]
}


# ============================================================================
# TAXONOMY DATA
# ============================================================================

TAXONOMIES = {
    "work_types": {
        "taxonomy_id": "proto:WorkTypes",
        "taxonomy_label": "Work Types",
        "description": "Types of development work for stories and tasks",
        "version": "1.0.0",
        "last_updated": "2026-01-16",
        "terms": [
            {"uri": "proto:work_type/bug_fix", "label": "Bug Fix", "aliases": ["bug", "Bug", "bugfix", "fix", "Fix", "defect", "Defect"], "definition": "Correcting an error or unexpected behavior in existing functionality", "broader": None, "icon": "🐛"},
            {"uri": "proto:work_type/new_feature", "label": "New Feature", "aliases": ["feature", "Feature", "new_feature", "enhancement", "Enhancement", "story", "Story"], "definition": "Developing new functionality or capability", "broader": None, "icon": "✨"},
            {"uri": "proto:work_type/refactor", "label": "Refactor", "aliases": ["refactor", "refactoring", "Refactoring", "tech_debt", "Tech Debt", "cleanup"], "definition": "Improving code structure or performance without changing functionality", "broader": None, "icon": "🔧"},
            {"uri": "proto:work_type/documentation", "label": "Documentation", "aliases": ["docs", "Docs", "doc", "documentation", "readme", "wiki"], "definition": "Creating or updating documentation, guides, or knowledge base articles", "broader": None, "icon": "📝"},
            {"uri": "proto:work_type/research", "label": "Research", "aliases": ["research", "spike", "Spike", "investigation", "Investigation", "POC", "poc", "proof_of_concept"], "definition": "Investigating technical approaches, feasibility studies, or proof of concepts", "broader": None, "icon": "🔬"}
        ]
    },
    "work_statuses": {
        "taxonomy_id": "proto:WorkStatuses",
        "taxonomy_label": "Work Statuses",
        "description": "Workflow states for development stories and tasks",
        "version": "1.0.0",
        "last_updated": "2026-01-16",
        "terms": [
            {"uri": "proto:work_status/backlog", "label": "backlog", "aliases": ["Backlog", "TODO", "to_do", "To Do", "queued"], "definition": "Work item is identified but not yet started", "broader": None, "sequence": 1, "color": "#6B7280"},
            {"uri": "proto:work_status/in_progress", "label": "in_progress", "aliases": ["In Progress", "in progress", "active", "working", "WIP"], "definition": "Work item is actively being worked on", "broader": None, "sequence": 2, "color": "#2563EB"},
            {"uri": "proto:work_status/review", "label": "review", "aliases": ["Review", "in_review", "In Review", "pending_review", "PR"], "definition": "Work is complete and awaiting review or approval", "broader": None, "sequence": 3, "color": "#CA8A04"},
            {"uri": "proto:work_status/complete", "label": "complete", "aliases": ["Complete", "done", "Done", "finished", "closed", "Closed"], "definition": "Work item has been completed and approved", "broader": None, "sequence": 4, "color": "#16A34A"}
        ]
    },
    "test_statuses": {
        "taxonomy_id": "proto:TestStatuses",
        "taxonomy_label": "Test Statuses",
        "description": "Result statuses for Robot Framework test execution",
        "version": "1.0.0",
        "last_updated": "2026-01-16",
        "terms": [
            {"uri": "proto:status/pass", "label": "PASS", "aliases": ["pass", "passed", "success", "SUCCESS"], "definition": "Test executed successfully and all assertions passed", "broader": None, "color": "#16A34A"},
            {"uri": "proto:status/fail", "label": "FAIL", "aliases": ["fail", "failed", "failure", "FAILURE"], "definition": "Test executed but one or more assertions failed", "broader": None, "color": "#DC2626"}
        ]
    },
    "teams": {
        "taxonomy_id": "proto:Teams",
        "taxonomy_label": "318th RANS Teams",
        "description": "Organizational teams within the 318th Range and Network Squadron",
        "version": "1.0.0",
        "last_updated": "2026-01-16",
        "terms": [
            {"uri": "proto:team/Automation", "label": "Automation", "aliases": ["Auto", "Automation Team", "AT"], "definition": "Responsible for attack automation scripts, C2 integration, orchestration frameworks, and execution pipelines.", "broader": None, "related": ["proto:team/OPFOR"], "responsibilities": ["Cobalt Strike automation", "Robot Framework test development", "C2 infrastructure scripting", "Payload deployment automation"], "color": "#B4A082"},
            {"uri": "proto:team/Range", "label": "Range", "aliases": ["Range Team", "Infrastructure", "RT", "Range Ops"], "definition": "Manages cyber range infrastructure, VM deployments, network configurations, and environment provisioning.", "broader": None, "related": ["proto:team/Automation"], "responsibilities": ["VM deployment and management", "Network topology configuration", "Range environment provisioning", "Infrastructure maintenance"], "color": "#8C8264"},
            {"uri": "proto:team/OPFOR", "label": "OPFOR", "aliases": ["Red Team", "Opposing Force", "Adversary Team", "Red"], "definition": "Executes adversary emulation operations, develops attack chains, and conducts red team activities during exercises.", "broader": None, "related": ["proto:team/Automation", "proto:team/ContentDev"], "responsibilities": ["Adversary emulation", "Attack chain execution", "TTP implementation", "Red team operations"], "color": "#64783C"},
            {"uri": "proto:team/ContentDev", "label": "Content Development", "aliases": ["ContentDev", "Content Dev", "Scenario Development", "CD", "Content"], "definition": "Develops training scenarios, threat intelligence products, exercise handbooks, and storyline narratives.", "broader": None, "related": ["proto:team/OPFOR"], "responsibilities": ["Scenario design", "Threat intelligence research", "Handbook creation", "Storyline development", "Intel product generation"], "color": "#829646"}
        ]
    },
    "team_members": {
        "taxonomy_id": "proto:TeamMembers",
        "taxonomy_label": "Team Members",
        "description": "Personnel within the 318th RANS Automation team",
        "version": "1.0.0",
        "last_updated": "2026-01-16",
        "terms": [
            {"uri": "proto:person/kane_pickrel", "label": "Kane Pickrel", "aliases": ["Kane", "KP"], "definition": "Ontology Architect on the Automation team", "broader": None, "team": "proto:team/Automation", "role": "Ontology Architect"},
            {"uri": "proto:person/hazel_cook", "label": "Hazel Cook", "aliases": ["Hazel", "HC"], "definition": "Software Engineer on the Automation team", "broader": None, "team": "proto:team/Automation", "role": "Software Engineer"},
            {"uri": "proto:person/ben_leedy", "label": "Ben Leedy", "aliases": ["Ben", "BL"], "definition": "DevOps Engineer on the Automation team", "broader": None, "team": "proto:team/Automation", "role": "DevOps Engineer"},
            {"uri": "proto:person/chris_kane", "label": "Chris Kane", "aliases": ["Chris K", "CK"], "definition": "Data Scientist on the Automation team", "broader": None, "team": "proto:team/Automation", "role": "Data Scientist"},
            {"uri": "proto:person/hank_schenk", "label": "Hank Schenk", "aliases": ["Hank", "HS"], "definition": "Software Engineer on the Automation team", "broader": None, "team": "proto:team/Automation", "role": "Software Engineer"},
            {"uri": "proto:person/qui_nguyen", "label": "Qui Nguyen", "aliases": ["Qui", "QN"], "definition": "Software Engineer on the Automation team", "broader": None, "team": "proto:team/Automation", "role": "Software Engineer"},
            {"uri": "proto:person/eduardo_calderon", "label": "Eduardo Calderon", "aliases": ["Eduardo", "EC"], "definition": "OPFOR Engineer on the Automation team", "broader": None, "team": "proto:team/Automation", "role": "OPFOR Engineer"}
        ]
    },
    "risk_levels": {
        "taxonomy_id": "proto:RiskLevels",
        "taxonomy_label": "Risk Levels",
        "description": "Risk classification for offensive operations",
        "version": "1.0.0",
        "last_updated": "2026-01-16",
        "terms": [
            {"uri": "proto:risk/critical", "label": "Critical", "aliases": ["crit", "critical-risk"], "definition": "High-impact actions that could cause significant damage or trigger alerts. Requires explicit approval before execution.", "broader": None, "color": "#DC2626", "approval_required": True, "reversible": False, "examples": ["Credential dumping (mimikatz)", "Domain admin escalation", "Data exfiltration", "Ransomware simulation", "Active Directory modification"]},
            {"uri": "proto:risk/high", "label": "High", "aliases": ["high-risk"], "definition": "Actions likely to trigger security monitoring or leave forensic artifacts. Requires team lead awareness.", "broader": None, "color": "#EA580C", "approval_required": True, "reversible": True, "examples": ["Lateral movement via PSExec", "Service installation", "Registry modification", "Scheduled task creation", "WMI execution"]},
            {"uri": "proto:risk/medium", "label": "Medium", "aliases": ["med", "medium-risk"], "definition": "Actions that may be detected but have limited blast radius and are typically reversible.", "broader": None, "color": "#CA8A04", "approval_required": False, "reversible": True, "examples": ["Network scanning", "File enumeration", "Process listing", "Share enumeration", "DNS queries"]},
            {"uri": "proto:risk/low", "label": "Low", "aliases": ["low-risk"], "definition": "Routine actions unlikely to trigger detection systems.", "broader": None, "color": "#16A34A", "approval_required": False, "reversible": True, "examples": ["Beacon check-in", "Sleep adjustment", "Screenshot capture", "Clipboard monitoring", "Current user enumeration"]},
            {"uri": "proto:risk/info", "label": "Informational", "aliases": ["informational", "none", "info-only"], "definition": "Passive information gathering or documentation with no operational impact on target systems.", "broader": None, "color": "#2563EB", "approval_required": False, "reversible": True, "examples": ["Documentation review", "Planning artifacts", "Configuration files", "Reference materials"]}
        ]
    },
    "priority_levels": {
        "taxonomy_id": "proto:PriorityLevels",
        "taxonomy_label": "Priority Levels",
        "description": "Priority classification for development stories and tasks",
        "version": "1.0.0",
        "last_updated": "2026-01-16",
        "terms": [
            {"uri": "proto:priority/critical", "label": "Critical", "aliases": ["critical", "P0", "p0", "urgent", "Urgent", "blocker", "Blocker"], "definition": "Highest priority - blocks other work or has immediate deadline", "broader": None, "sequence": 1, "color": "#DC2626", "sla_days": 1},
            {"uri": "proto:priority/high", "label": "High", "aliases": ["high", "P1", "p1", "important"], "definition": "High priority - should be addressed in current sprint", "broader": None, "sequence": 2, "color": "#EA580C", "sla_days": 7},
            {"uri": "proto:priority/medium", "label": "Medium", "aliases": ["medium", "med", "P2", "p2", "normal", "Normal"], "definition": "Standard priority - planned work for upcoming sprints", "broader": None, "sequence": 3, "color": "#CA8A04", "sla_days": 14},
            {"uri": "proto:priority/low", "label": "Low", "aliases": ["low", "P3", "p3", "minor", "Minor", "nice_to_have"], "definition": "Low priority - address when capacity allows", "broader": None, "sequence": 4, "color": "#16A34A", "sla_days": 30}
        ]
    },
    "c2_frameworks": {
        "taxonomy_id": "proto:C2Frameworks",
        "taxonomy_label": "C2 Frameworks",
        "description": "Command and Control frameworks used for adversary emulation",
        "version": "1.0.0",
        "last_updated": "2026-01-16",
        "terms": [
            {"uri": "proto:c2/cobalt_strike", "label": "Cobalt Strike", "aliases": ["CS", "Cobalt", "CobaltStrike"], "definition": "Commercial adversary simulation and red team operations software by Fortra (formerly HelpSystems)", "broader": None, "vendor": "Fortra", "beacon_types": ["HTTP", "HTTPS", "DNS", "SMB"], "documentation_url": "https://www.cobaltstrike.com/documentation"},
            {"uri": "proto:c2/sliver", "label": "Sliver", "aliases": ["sliver", "SliverC2"], "definition": "Open source cross-platform adversary emulation/red team framework by BishopFox", "broader": None, "vendor": "BishopFox", "beacon_types": ["HTTP", "HTTPS", "DNS", "mTLS", "WireGuard"], "documentation_url": "https://sliver.sh/"},
            {"uri": "proto:c2/powershell_empire", "label": "PowerShell Empire", "aliases": ["Empire", "PS Empire", "PSEmpire"], "definition": "Post-exploitation framework built on PowerShell and Python agents", "broader": None, "vendor": "BC Security", "beacon_types": ["HTTP", "HTTPS"], "documentation_url": "https://bc-security.gitbook.io/empire-wiki/"},
            {"uri": "proto:c2/covenant", "label": "Covenant C2", "aliases": ["Covenant", "CovenantC2"], "definition": ".NET based C2 framework with a web-based interface", "broader": None, "vendor": "Covenant Project", "beacon_types": ["HTTP", "HTTPS"], "documentation_url": "https://github.com/cobbr/Covenant"}
        ]
    },
    "mitre_tactics": {
        "taxonomy_id": "proto:MITRETactics",
        "taxonomy_label": "MITRE ATT&CK Tactics",
        "description": "Enterprise ATT&CK tactics used for adversary emulation classification",
        "version": "14.1",
        "source": "https://attack.mitre.org/tactics/enterprise/",
        "last_updated": "2026-01-16",
        "terms": [
            {"uri": "proto:tactic/TA0043", "mitre_id": "TA0043", "label": "Reconnaissance", "aliases": ["Recon"], "definition": "The adversary is trying to gather information they can use to plan future operations.", "broader": None, "phase": "pre-attack", "kill_chain_position": 1},
            {"uri": "proto:tactic/TA0042", "mitre_id": "TA0042", "label": "Resource Development", "aliases": ["Resource Dev", "Weaponization"], "definition": "The adversary is trying to establish resources they can use to support operations.", "broader": None, "phase": "pre-attack", "kill_chain_position": 2},
            {"uri": "proto:tactic/TA0001", "mitre_id": "TA0001", "label": "Initial Access", "aliases": ["IA", "Delivery"], "definition": "The adversary is trying to get into your network.", "broader": None, "phase": "attack", "kill_chain_position": 3},
            {"uri": "proto:tactic/TA0002", "mitre_id": "TA0002", "label": "Execution", "aliases": ["Exec", "Exploitation"], "definition": "The adversary is trying to run malicious code.", "broader": None, "phase": "attack", "kill_chain_position": 4},
            {"uri": "proto:tactic/TA0003", "mitre_id": "TA0003", "label": "Persistence", "aliases": ["Persist", "Installation"], "definition": "The adversary is trying to maintain their foothold.", "broader": None, "phase": "attack", "kill_chain_position": 5},
            {"uri": "proto:tactic/TA0004", "mitre_id": "TA0004", "label": "Privilege Escalation", "aliases": ["Priv Esc", "PrivEsc", "PE"], "definition": "The adversary is trying to gain higher-level permissions.", "broader": None, "phase": "attack", "kill_chain_position": 6},
            {"uri": "proto:tactic/TA0005", "mitre_id": "TA0005", "label": "Defense Evasion", "aliases": ["Evasion", "DefEvasion"], "definition": "The adversary is trying to avoid being detected.", "broader": None, "phase": "attack", "kill_chain_position": 7},
            {"uri": "proto:tactic/TA0006", "mitre_id": "TA0006", "label": "Credential Access", "aliases": ["Cred Access", "CredAccess", "Credentials"], "definition": "The adversary is trying to steal account names and passwords.", "broader": None, "phase": "attack", "kill_chain_position": 8},
            {"uri": "proto:tactic/TA0007", "mitre_id": "TA0007", "label": "Discovery", "aliases": ["Disco", "Enumeration"], "definition": "The adversary is trying to figure out your environment.", "broader": None, "phase": "attack", "kill_chain_position": 9},
            {"uri": "proto:tactic/TA0008", "mitre_id": "TA0008", "label": "Lateral Movement", "aliases": ["Lat Mov", "LatMov", "LM"], "definition": "The adversary is trying to move through your environment.", "broader": None, "phase": "attack", "kill_chain_position": 10},
            {"uri": "proto:tactic/TA0009", "mitre_id": "TA0009", "label": "Collection", "aliases": ["Collect"], "definition": "The adversary is trying to gather data of interest to their goal.", "broader": None, "phase": "attack", "kill_chain_position": 11},
            {"uri": "proto:tactic/TA0011", "mitre_id": "TA0011", "label": "Command and Control", "aliases": ["C2", "C&C", "CnC", "Command & Control"], "definition": "The adversary is trying to communicate with compromised systems to control them.", "broader": None, "phase": "attack", "kill_chain_position": 12},
            {"uri": "proto:tactic/TA0010", "mitre_id": "TA0010", "label": "Exfiltration", "aliases": ["Exfil", "Data Exfil"], "definition": "The adversary is trying to steal data.", "broader": None, "phase": "post-attack", "kill_chain_position": 13},
            {"uri": "proto:tactic/TA0040", "mitre_id": "TA0040", "label": "Impact", "aliases": ["Actions on Objectives", "AOO"], "definition": "The adversary is trying to manipulate, interrupt, or destroy your systems and data.", "broader": None, "phase": "post-attack", "kill_chain_position": 14}
        ]
    },
    "mitre_techniques": {
        "taxonomy_id": "proto:MITRETechniques",
        "taxonomy_label": "MITRE ATT&CK Techniques",
        "description": "Enterprise ATT&CK techniques and sub-techniques for adversary emulation",
        "version": "14.1",
        "source": "https://attack.mitre.org/techniques/enterprise/",
        "last_updated": "2026-01-16",
        "note": "This is a subset of commonly used techniques. Full ATT&CK has 200+ techniques.",
        "terms": [
            {"uri": "proto:technique/T1595", "label": "T1595", "aliases": ["Active Scanning", "t1595"], "definition": "Adversaries may execute active reconnaissance scans to gather information that can be used during targeting.", "broader": None, "tactic": "TA0043", "technique_name": "Active Scanning", "url": "https://attack.mitre.org/techniques/T1595/"},
            {"uri": "proto:technique/T1595.001", "label": "T1595.001", "aliases": ["Scanning IP Blocks", "t1595.001"], "definition": "Adversaries may scan victim IP blocks to gather information that can be used during targeting.", "broader": "proto:technique/T1595", "tactic": "TA0043", "technique_name": "Scanning IP Blocks", "url": "https://attack.mitre.org/techniques/T1595/001/"},
            {"uri": "proto:technique/T1595.002", "label": "T1595.002", "aliases": ["Vulnerability Scanning", "t1595.002"], "definition": "Adversaries may scan victims for vulnerabilities that can be used during targeting.", "broader": "proto:technique/T1595", "tactic": "TA0043", "technique_name": "Vulnerability Scanning", "url": "https://attack.mitre.org/techniques/T1595/002/"},
            {"uri": "proto:technique/T1592", "label": "T1592", "aliases": ["Gather Victim Host Information", "t1592"], "definition": "Adversaries may gather information about the victim's hosts that can be used during targeting.", "broader": None, "tactic": "TA0043", "technique_name": "Gather Victim Host Information", "url": "https://attack.mitre.org/techniques/T1592/"},
            {"uri": "proto:technique/T1589", "label": "T1589", "aliases": ["Gather Victim Identity Information", "t1589"], "definition": "Adversaries may gather information about the victim's identity that can be used during targeting.", "broader": None, "tactic": "TA0043", "technique_name": "Gather Victim Identity Information", "url": "https://attack.mitre.org/techniques/T1589/"},
            {"uri": "proto:technique/T1590", "label": "T1590", "aliases": ["Gather Victim Network Information", "t1590"], "definition": "Adversaries may gather information about the victim's networks that can be used during targeting.", "broader": None, "tactic": "TA0043", "technique_name": "Gather Victim Network Information", "url": "https://attack.mitre.org/techniques/T1590/"},
            {"uri": "proto:technique/T1587", "label": "T1587", "aliases": ["Develop Capabilities", "t1587"], "definition": "Adversaries may build capabilities that can be used during targeting.", "broader": None, "tactic": "TA0042", "technique_name": "Develop Capabilities", "url": "https://attack.mitre.org/techniques/T1587/"},
            {"uri": "proto:technique/T1587.001", "label": "T1587.001", "aliases": ["Malware", "t1587.001"], "definition": "Adversaries may develop malware and malware components that can be used during targeting.", "broader": "proto:technique/T1587", "tactic": "TA0042", "technique_name": "Malware", "url": "https://attack.mitre.org/techniques/T1587/001/"},
            {"uri": "proto:technique/T1588", "label": "T1588", "aliases": ["Obtain Capabilities", "t1588"], "definition": "Adversaries may buy and/or steal capabilities that can be used during targeting.", "broader": None, "tactic": "TA0042", "technique_name": "Obtain Capabilities", "url": "https://attack.mitre.org/techniques/T1588/"},
            {"uri": "proto:technique/T1583", "label": "T1583", "aliases": ["Acquire Infrastructure", "t1583"], "definition": "Adversaries may buy, lease, or rent infrastructure that can be used during targeting.", "broader": None, "tactic": "TA0042", "technique_name": "Acquire Infrastructure", "url": "https://attack.mitre.org/techniques/T1583/"},
            {"uri": "proto:technique/T1566", "label": "T1566", "aliases": ["Phishing", "t1566"], "definition": "Adversaries may send phishing messages to gain access to victim systems.", "broader": None, "tactic": "TA0001", "technique_name": "Phishing", "url": "https://attack.mitre.org/techniques/T1566/"},
            {"uri": "proto:technique/T1566.001", "label": "T1566.001", "aliases": ["Spearphishing Attachment", "t1566.001"], "definition": "Adversaries may send spearphishing emails with a malicious attachment.", "broader": "proto:technique/T1566", "tactic": "TA0001", "technique_name": "Spearphishing Attachment", "url": "https://attack.mitre.org/techniques/T1566/001/"},
            {"uri": "proto:technique/T1566.002", "label": "T1566.002", "aliases": ["Spearphishing Link", "t1566.002"], "definition": "Adversaries may send spearphishing emails with a malicious link.", "broader": "proto:technique/T1566", "tactic": "TA0001", "technique_name": "Spearphishing Link", "url": "https://attack.mitre.org/techniques/T1566/002/"},
            {"uri": "proto:technique/T1190", "label": "T1190", "aliases": ["Exploit Public-Facing Application", "t1190"], "definition": "Adversaries may attempt to exploit a weakness in an Internet-facing host or system.", "broader": None, "tactic": "TA0001", "technique_name": "Exploit Public-Facing Application", "url": "https://attack.mitre.org/techniques/T1190/"},
            {"uri": "proto:technique/T1133", "label": "T1133", "aliases": ["External Remote Services", "t1133"], "definition": "Adversaries may leverage external-facing remote services to initially access a network.", "broader": None, "tactic": "TA0001", "technique_name": "External Remote Services", "url": "https://attack.mitre.org/techniques/T1133/"},
            {"uri": "proto:technique/T1078", "label": "T1078", "aliases": ["Valid Accounts", "t1078"], "definition": "Adversaries may obtain and abuse credentials of existing accounts as a means of gaining Initial Access.", "broader": None, "tactic": "TA0001", "technique_name": "Valid Accounts", "url": "https://attack.mitre.org/techniques/T1078/"},
            {"uri": "proto:technique/T1078.001", "label": "T1078.001", "aliases": ["Default Accounts", "t1078.001"], "definition": "Adversaries may obtain and abuse credentials of a default account.", "broader": "proto:technique/T1078", "tactic": "TA0001", "technique_name": "Default Accounts", "url": "https://attack.mitre.org/techniques/T1078/001/"},
            {"uri": "proto:technique/T1078.002", "label": "T1078.002", "aliases": ["Domain Accounts", "t1078.002"], "definition": "Adversaries may obtain and abuse credentials of a domain account.", "broader": "proto:technique/T1078", "tactic": "TA0001", "technique_name": "Domain Accounts", "url": "https://attack.mitre.org/techniques/T1078/002/"},
            {"uri": "proto:technique/T1078.003", "label": "T1078.003", "aliases": ["Local Accounts", "t1078.003"], "definition": "Adversaries may obtain and abuse credentials of a local account.", "broader": "proto:technique/T1078", "tactic": "TA0001", "technique_name": "Local Accounts", "url": "https://attack.mitre.org/techniques/T1078/003/"},
            {"uri": "proto:technique/T1059", "label": "T1059", "aliases": ["Command and Scripting Interpreter", "t1059"], "definition": "Adversaries may abuse command and script interpreters to execute commands, scripts, or binaries.", "broader": None, "tactic": "TA0002", "technique_name": "Command and Scripting Interpreter", "url": "https://attack.mitre.org/techniques/T1059/"},
            {"uri": "proto:technique/T1059.001", "label": "T1059.001", "aliases": ["PowerShell", "t1059.001"], "definition": "Adversaries may abuse PowerShell commands and scripts for execution.", "broader": "proto:technique/T1059", "tactic": "TA0002", "technique_name": "PowerShell", "url": "https://attack.mitre.org/techniques/T1059/001/"},
            {"uri": "proto:technique/T1059.003", "label": "T1059.003", "aliases": ["Windows Command Shell", "cmd", "t1059.003"], "definition": "Adversaries may abuse the Windows command shell for execution.", "broader": "proto:technique/T1059", "tactic": "TA0002", "technique_name": "Windows Command Shell", "url": "https://attack.mitre.org/techniques/T1059/003/"},
            {"uri": "proto:technique/T1059.004", "label": "T1059.004", "aliases": ["Unix Shell", "bash", "t1059.004"], "definition": "Adversaries may abuse Unix shell commands and scripts for execution.", "broader": "proto:technique/T1059", "tactic": "TA0002", "technique_name": "Unix Shell", "url": "https://attack.mitre.org/techniques/T1059/004/"},
            {"uri": "proto:technique/T1059.005", "label": "T1059.005", "aliases": ["Visual Basic", "VBS", "t1059.005"], "definition": "Adversaries may abuse Visual Basic for execution.", "broader": "proto:technique/T1059", "tactic": "TA0002", "technique_name": "Visual Basic", "url": "https://attack.mitre.org/techniques/T1059/005/"},
            {"uri": "proto:technique/T1059.006", "label": "T1059.006", "aliases": ["Python", "t1059.006"], "definition": "Adversaries may abuse Python commands and scripts for execution.", "broader": "proto:technique/T1059", "tactic": "TA0002", "technique_name": "Python", "url": "https://attack.mitre.org/techniques/T1059/006/"},
            {"uri": "proto:technique/T1047", "label": "T1047", "aliases": ["Windows Management Instrumentation", "WMI", "t1047"], "definition": "Adversaries may abuse Windows Management Instrumentation (WMI) to execute malicious commands.", "broader": None, "tactic": "TA0002", "technique_name": "Windows Management Instrumentation", "url": "https://attack.mitre.org/techniques/T1047/"},
            {"uri": "proto:technique/T1053", "label": "T1053", "aliases": ["Scheduled Task/Job", "t1053"], "definition": "Adversaries may abuse task scheduling functionality to facilitate initial or recurring execution.", "broader": None, "tactic": "TA0002", "technique_name": "Scheduled Task/Job", "url": "https://attack.mitre.org/techniques/T1053/"},
            {"uri": "proto:technique/T1053.005", "label": "T1053.005", "aliases": ["Scheduled Task", "t1053.005"], "definition": "Adversaries may abuse the Windows Task Scheduler to perform task scheduling for execution.", "broader": "proto:technique/T1053", "tactic": "TA0002", "technique_name": "Scheduled Task", "url": "https://attack.mitre.org/techniques/T1053/005/"},
            {"uri": "proto:technique/T1543", "label": "T1543", "aliases": ["Create or Modify System Process", "t1543"], "definition": "Adversaries may create or modify system-level processes to repeatedly execute malicious payloads.", "broader": None, "tactic": "TA0003", "technique_name": "Create or Modify System Process", "url": "https://attack.mitre.org/techniques/T1543/"},
            {"uri": "proto:technique/T1543.003", "label": "T1543.003", "aliases": ["Windows Service", "t1543.003"], "definition": "Adversaries may create or modify Windows services to repeatedly execute malicious payloads.", "broader": "proto:technique/T1543", "tactic": "TA0003", "technique_name": "Windows Service", "url": "https://attack.mitre.org/techniques/T1543/003/"},
            {"uri": "proto:technique/T1547", "label": "T1547", "aliases": ["Boot or Logon Autostart Execution", "t1547"], "definition": "Adversaries may configure system settings to automatically execute a program during system boot or logon.", "broader": None, "tactic": "TA0003", "technique_name": "Boot or Logon Autostart Execution", "url": "https://attack.mitre.org/techniques/T1547/"},
            {"uri": "proto:technique/T1547.001", "label": "T1547.001", "aliases": ["Registry Run Keys / Startup Folder", "t1547.001"], "definition": "Adversaries may achieve persistence by adding a program to a startup folder or referencing it with a Registry run key.", "broader": "proto:technique/T1547", "tactic": "TA0003", "technique_name": "Registry Run Keys / Startup Folder", "url": "https://attack.mitre.org/techniques/T1547/001/"},
            {"uri": "proto:technique/T1548", "label": "T1548", "aliases": ["Abuse Elevation Control Mechanism", "t1548"], "definition": "Adversaries may circumvent mechanisms designed to control elevate privileges to gain higher-level permissions.", "broader": None, "tactic": "TA0004", "technique_name": "Abuse Elevation Control Mechanism", "url": "https://attack.mitre.org/techniques/T1548/"},
            {"uri": "proto:technique/T1548.002", "label": "T1548.002", "aliases": ["Bypass User Account Control", "UAC Bypass", "t1548.002"], "definition": "Adversaries may bypass UAC mechanisms to elevate process privileges on system.", "broader": "proto:technique/T1548", "tactic": "TA0004", "technique_name": "Bypass User Account Control", "url": "https://attack.mitre.org/techniques/T1548/002/"},
            {"uri": "proto:technique/T1134", "label": "T1134", "aliases": ["Access Token Manipulation", "t1134"], "definition": "Adversaries may modify access tokens to operate under a different user or system security context.", "broader": None, "tactic": "TA0004", "technique_name": "Access Token Manipulation", "url": "https://attack.mitre.org/techniques/T1134/"},
            {"uri": "proto:technique/T1055", "label": "T1055", "aliases": ["Process Injection", "t1055"], "definition": "Adversaries may inject code into processes in order to evade process-based defenses as well as possibly elevate privileges.", "broader": None, "tactic": "TA0005", "technique_name": "Process Injection", "url": "https://attack.mitre.org/techniques/T1055/"},
            {"uri": "proto:technique/T1055.001", "label": "T1055.001", "aliases": ["Dynamic-link Library Injection", "DLL Injection", "t1055.001"], "definition": "Adversaries may inject dynamic-link libraries (DLLs) into processes in order to evade process-based defenses.", "broader": "proto:technique/T1055", "tactic": "TA0005", "technique_name": "Dynamic-link Library Injection", "url": "https://attack.mitre.org/techniques/T1055/001/"},
            {"uri": "proto:technique/T1070", "label": "T1070", "aliases": ["Indicator Removal", "t1070"], "definition": "Adversaries may delete or modify artifacts generated within systems to remove evidence of their presence.", "broader": None, "tactic": "TA0005", "technique_name": "Indicator Removal", "url": "https://attack.mitre.org/techniques/T1070/"},
            {"uri": "proto:technique/T1070.001", "label": "T1070.001", "aliases": ["Clear Windows Event Logs", "t1070.001"], "definition": "Adversaries may clear Windows Event Logs to hide the activity of an intrusion.", "broader": "proto:technique/T1070", "tactic": "TA0005", "technique_name": "Clear Windows Event Logs", "url": "https://attack.mitre.org/techniques/T1070/001/"},
            {"uri": "proto:technique/T1562", "label": "T1562", "aliases": ["Impair Defenses", "t1562"], "definition": "Adversaries may maliciously modify components of a victim environment in order to hinder or disable defensive mechanisms.", "broader": None, "tactic": "TA0005", "technique_name": "Impair Defenses", "url": "https://attack.mitre.org/techniques/T1562/"},
            {"uri": "proto:technique/T1562.001", "label": "T1562.001", "aliases": ["Disable or Modify Tools", "t1562.001"], "definition": "Adversaries may modify and/or disable security tools to avoid possible detection.", "broader": "proto:technique/T1562", "tactic": "TA0005", "technique_name": "Disable or Modify Tools", "url": "https://attack.mitre.org/techniques/T1562/001/"},
            {"uri": "proto:technique/T1003", "label": "T1003", "aliases": ["OS Credential Dumping", "Credential Dumping", "t1003"], "definition": "Adversaries may attempt to dump credentials to obtain account login and credential material.", "broader": None, "tactic": "TA0006", "technique_name": "OS Credential Dumping", "url": "https://attack.mitre.org/techniques/T1003/"},
            {"uri": "proto:technique/T1003.001", "label": "T1003.001", "aliases": ["LSASS Memory", "mimikatz", "t1003.001"], "definition": "Adversaries may attempt to access credential material stored in the process memory of the LSASS.", "broader": "proto:technique/T1003", "tactic": "TA0006", "technique_name": "LSASS Memory", "url": "https://attack.mitre.org/techniques/T1003/001/"},
            {"uri": "proto:technique/T1003.002", "label": "T1003.002", "aliases": ["Security Account Manager", "SAM", "t1003.002"], "definition": "Adversaries may attempt to extract credential material from the SAM database.", "broader": "proto:technique/T1003", "tactic": "TA0006", "technique_name": "Security Account Manager", "url": "https://attack.mitre.org/techniques/T1003/002/"},
            {"uri": "proto:technique/T1003.003", "label": "T1003.003", "aliases": ["NTDS", "t1003.003"], "definition": "Adversaries may attempt to access or create a copy of the Active Directory domain database NTDS.dit.", "broader": "proto:technique/T1003", "tactic": "TA0006", "technique_name": "NTDS", "url": "https://attack.mitre.org/techniques/T1003/003/"},
            {"uri": "proto:technique/T1003.006", "label": "T1003.006", "aliases": ["DCSync", "t1003.006"], "definition": "Adversaries may attempt to access credentials and other sensitive information by abusing a Windows Domain Controller's API.", "broader": "proto:technique/T1003", "tactic": "TA0006", "technique_name": "DCSync", "url": "https://attack.mitre.org/techniques/T1003/006/"},
            {"uri": "proto:technique/T1110", "label": "T1110", "aliases": ["Brute Force", "t1110"], "definition": "Adversaries may use brute force techniques to gain access to accounts when passwords are unknown.", "broader": None, "tactic": "TA0006", "technique_name": "Brute Force", "url": "https://attack.mitre.org/techniques/T1110/"},
            {"uri": "proto:technique/T1110.001", "label": "T1110.001", "aliases": ["Password Guessing", "t1110.001"], "definition": "Adversaries may guess passwords to attempt access to accounts.", "broader": "proto:technique/T1110", "tactic": "TA0006", "technique_name": "Password Guessing", "url": "https://attack.mitre.org/techniques/T1110/001/"},
            {"uri": "proto:technique/T1110.003", "label": "T1110.003", "aliases": ["Password Spraying", "t1110.003"], "definition": "Adversaries may use a single or small list of commonly used passwords against many different accounts.", "broader": "proto:technique/T1110", "tactic": "TA0006", "technique_name": "Password Spraying", "url": "https://attack.mitre.org/techniques/T1110/003/"},
            {"uri": "proto:technique/T1558", "label": "T1558", "aliases": ["Steal or Forge Kerberos Tickets", "t1558"], "definition": "Adversaries may attempt to subvert Kerberos authentication by stealing or forging Kerberos tickets.", "broader": None, "tactic": "TA0006", "technique_name": "Steal or Forge Kerberos Tickets", "url": "https://attack.mitre.org/techniques/T1558/"},
            {"uri": "proto:technique/T1558.003", "label": "T1558.003", "aliases": ["Kerberoasting", "t1558.003"], "definition": "Adversaries may abuse a valid Kerberos ticket-granting ticket (TGT) or sniff network traffic to obtain a TGS.", "broader": "proto:technique/T1558", "tactic": "TA0006", "technique_name": "Kerberoasting", "url": "https://attack.mitre.org/techniques/T1558/003/"},
            {"uri": "proto:technique/T1087", "label": "T1087", "aliases": ["Account Discovery", "t1087"], "definition": "Adversaries may attempt to get a listing of valid accounts, usernames, or email addresses on a system or within a compromised environment.", "broader": None, "tactic": "TA0007", "technique_name": "Account Discovery", "url": "https://attack.mitre.org/techniques/T1087/"},
            {"uri": "proto:technique/T1087.001", "label": "T1087.001", "aliases": ["Local Account", "t1087.001"], "definition": "Adversaries may attempt to get a listing of local system accounts.", "broader": "proto:technique/T1087", "tactic": "TA0007", "technique_name": "Local Account", "url": "https://attack.mitre.org/techniques/T1087/001/"},
            {"uri": "proto:technique/T1087.002", "label": "T1087.002", "aliases": ["Domain Account", "t1087.002"], "definition": "Adversaries may attempt to get a listing of domain accounts.", "broader": "proto:technique/T1087", "tactic": "TA0007", "technique_name": "Domain Account", "url": "https://attack.mitre.org/techniques/T1087/002/"},
            {"uri": "proto:technique/T1083", "label": "T1083", "aliases": ["File and Directory Discovery", "t1083"], "definition": "Adversaries may enumerate files and directories or may search in specific locations of a host or network share.", "broader": None, "tactic": "TA0007", "technique_name": "File and Directory Discovery", "url": "https://attack.mitre.org/techniques/T1083/"},
            {"uri": "proto:technique/T1046", "label": "T1046", "aliases": ["Network Service Discovery", "Network Scanning", "t1046"], "definition": "Adversaries may attempt to get a listing of services running on remote hosts and local network infrastructure devices.", "broader": None, "tactic": "TA0007", "technique_name": "Network Service Discovery", "url": "https://attack.mitre.org/techniques/T1046/"},
            {"uri": "proto:technique/T1057", "label": "T1057", "aliases": ["Process Discovery", "t1057"], "definition": "Adversaries may attempt to get information about running processes on a system.", "broader": None, "tactic": "TA0007", "technique_name": "Process Discovery", "url": "https://attack.mitre.org/techniques/T1057/"},
            {"uri": "proto:technique/T1082", "label": "T1082", "aliases": ["System Information Discovery", "t1082"], "definition": "An adversary may attempt to get detailed information about the operating system and hardware.", "broader": None, "tactic": "TA0007", "technique_name": "System Information Discovery", "url": "https://attack.mitre.org/techniques/T1082/"},
            {"uri": "proto:technique/T1016", "label": "T1016", "aliases": ["System Network Configuration Discovery", "t1016"], "definition": "Adversaries may look for details about the network configuration and settings.", "broader": None, "tactic": "TA0007", "technique_name": "System Network Configuration Discovery", "url": "https://attack.mitre.org/techniques/T1016/"},
            {"uri": "proto:technique/T1049", "label": "T1049", "aliases": ["System Network Connections Discovery", "t1049"], "definition": "Adversaries may attempt to get a listing of network connections to or from the compromised system.", "broader": None, "tactic": "TA0007", "technique_name": "System Network Connections Discovery", "url": "https://attack.mitre.org/techniques/T1049/"},
            {"uri": "proto:technique/T1021", "label": "T1021", "aliases": ["Remote Services", "t1021"], "definition": "Adversaries may use Valid Accounts to log into a service that accepts remote connections.", "broader": None, "tactic": "TA0008", "technique_name": "Remote Services", "url": "https://attack.mitre.org/techniques/T1021/"},
            {"uri": "proto:technique/T1021.001", "label": "T1021.001", "aliases": ["Remote Desktop Protocol", "RDP", "t1021.001"], "definition": "Adversaries may use Valid Accounts to log into a computer using the Remote Desktop Protocol (RDP).", "broader": "proto:technique/T1021", "tactic": "TA0008", "technique_name": "Remote Desktop Protocol", "url": "https://attack.mitre.org/techniques/T1021/001/"},
            {"uri": "proto:technique/T1021.002", "label": "T1021.002", "aliases": ["SMB/Windows Admin Shares", "PSExec", "t1021.002"], "definition": "Adversaries may use Valid Accounts to interact with a remote network share using SMB.", "broader": "proto:technique/T1021", "tactic": "TA0008", "technique_name": "SMB/Windows Admin Shares", "url": "https://attack.mitre.org/techniques/T1021/002/"},
            {"uri": "proto:technique/T1021.003", "label": "T1021.003", "aliases": ["Distributed Component Object Model", "DCOM", "t1021.003"], "definition": "Adversaries may use Valid Accounts to interact with remote machines by taking advantage of DCOM.", "broader": "proto:technique/T1021", "tactic": "TA0008", "technique_name": "Distributed Component Object Model", "url": "https://attack.mitre.org/techniques/T1021/003/"},
            {"uri": "proto:technique/T1021.004", "label": "T1021.004", "aliases": ["SSH", "t1021.004"], "definition": "Adversaries may use Valid Accounts to log into remote machines using Secure Shell (SSH).", "broader": "proto:technique/T1021", "tactic": "TA0008", "technique_name": "SSH", "url": "https://attack.mitre.org/techniques/T1021/004/"},
            {"uri": "proto:technique/T1021.006", "label": "T1021.006", "aliases": ["Windows Remote Management", "WinRM", "t1021.006"], "definition": "Adversaries may use Valid Accounts to interact with remote systems using WinRM.", "broader": "proto:technique/T1021", "tactic": "TA0008", "technique_name": "Windows Remote Management", "url": "https://attack.mitre.org/techniques/T1021/006/"},
            {"uri": "proto:technique/T1550", "label": "T1550", "aliases": ["Use Alternate Authentication Material", "t1550"], "definition": "Adversaries may use alternate authentication material to move laterally within an environment.", "broader": None, "tactic": "TA0008", "technique_name": "Use Alternate Authentication Material", "url": "https://attack.mitre.org/techniques/T1550/"},
            {"uri": "proto:technique/T1550.002", "label": "T1550.002", "aliases": ["Pass the Hash", "PtH", "t1550.002"], "definition": "Adversaries may pass the hash using stolen password hashes to move laterally.", "broader": "proto:technique/T1550", "tactic": "TA0008", "technique_name": "Pass the Hash", "url": "https://attack.mitre.org/techniques/T1550/002/"},
            {"uri": "proto:technique/T1550.003", "label": "T1550.003", "aliases": ["Pass the Ticket", "PtT", "t1550.003"], "definition": "Adversaries may pass the ticket using stolen Kerberos tickets to move laterally.", "broader": "proto:technique/T1550", "tactic": "TA0008", "technique_name": "Pass the Ticket", "url": "https://attack.mitre.org/techniques/T1550/003/"},
            {"uri": "proto:technique/T1560", "label": "T1560", "aliases": ["Archive Collected Data", "t1560"], "definition": "Adversaries may compress and/or encrypt data that is collected prior to exfiltration.", "broader": None, "tactic": "TA0009", "technique_name": "Archive Collected Data", "url": "https://attack.mitre.org/techniques/T1560/"},
            {"uri": "proto:technique/T1005", "label": "T1005", "aliases": ["Data from Local System", "t1005"], "definition": "Adversaries may search local system sources to find files of interest and sensitive data.", "broader": None, "tactic": "TA0009", "technique_name": "Data from Local System", "url": "https://attack.mitre.org/techniques/T1005/"},
            {"uri": "proto:technique/T1039", "label": "T1039", "aliases": ["Data from Network Shared Drive", "t1039"], "definition": "Adversaries may search network shares on computers they have compromised to find files of interest.", "broader": None, "tactic": "TA0009", "technique_name": "Data from Network Shared Drive", "url": "https://attack.mitre.org/techniques/T1039/"},
            {"uri": "proto:technique/T1113", "label": "T1113", "aliases": ["Screen Capture", "Screenshot", "t1113"], "definition": "Adversaries may attempt to take screen captures of the desktop to gather information.", "broader": None, "tactic": "TA0009", "technique_name": "Screen Capture", "url": "https://attack.mitre.org/techniques/T1113/"},
            {"uri": "proto:technique/T1071", "label": "T1071", "aliases": ["Application Layer Protocol", "t1071"], "definition": "Adversaries may communicate using OSI application layer protocols to avoid detection.", "broader": None, "tactic": "TA0011", "technique_name": "Application Layer Protocol", "url": "https://attack.mitre.org/techniques/T1071/"},
            {"uri": "proto:technique/T1071.001", "label": "T1071.001", "aliases": ["Web Protocols", "HTTP C2", "t1071.001"], "definition": "Adversaries may communicate using application layer protocols associated with web traffic.", "broader": "proto:technique/T1071", "tactic": "TA0011", "technique_name": "Web Protocols", "url": "https://attack.mitre.org/techniques/T1071/001/"},
            {"uri": "proto:technique/T1071.004", "label": "T1071.004", "aliases": ["DNS", "DNS C2", "t1071.004"], "definition": "Adversaries may communicate using the DNS application layer protocol to avoid detection.", "broader": "proto:technique/T1071", "tactic": "TA0011", "technique_name": "DNS", "url": "https://attack.mitre.org/techniques/T1071/004/"},
            {"uri": "proto:technique/T1105", "label": "T1105", "aliases": ["Ingress Tool Transfer", "t1105"], "definition": "Adversaries may transfer tools or other files from an external system into a compromised environment.", "broader": None, "tactic": "TA0011", "technique_name": "Ingress Tool Transfer", "url": "https://attack.mitre.org/techniques/T1105/"},
            {"uri": "proto:technique/T1572", "label": "T1572", "aliases": ["Protocol Tunneling", "t1572"], "definition": "Adversaries may tunnel network communications to and from a victim system within a separate protocol.", "broader": None, "tactic": "TA0011", "technique_name": "Protocol Tunneling", "url": "https://attack.mitre.org/techniques/T1572/"},
            {"uri": "proto:technique/T1041", "label": "T1041", "aliases": ["Exfiltration Over C2 Channel", "t1041"], "definition": "Adversaries may steal data by exfiltrating it over an existing command and control channel.", "broader": None, "tactic": "TA0010", "technique_name": "Exfiltration Over C2 Channel", "url": "https://attack.mitre.org/techniques/T1041/"},
            {"uri": "proto:technique/T1048", "label": "T1048", "aliases": ["Exfiltration Over Alternative Protocol", "t1048"], "definition": "Adversaries may steal data by exfiltrating it over a different protocol than the existing C2 channel.", "broader": None, "tactic": "TA0010", "technique_name": "Exfiltration Over Alternative Protocol", "url": "https://attack.mitre.org/techniques/T1048/"},
            {"uri": "proto:technique/T1567", "label": "T1567", "aliases": ["Exfiltration Over Web Service", "t1567"], "definition": "Adversaries may use an existing, legitimate external Web service to exfiltrate data.", "broader": None, "tactic": "TA0010", "technique_name": "Exfiltration Over Web Service", "url": "https://attack.mitre.org/techniques/T1567/"},
            {"uri": "proto:technique/T1486", "label": "T1486", "aliases": ["Data Encrypted for Impact", "Ransomware", "t1486"], "definition": "Adversaries may encrypt data on target systems or on large numbers of systems to interrupt availability.", "broader": None, "tactic": "TA0040", "technique_name": "Data Encrypted for Impact", "url": "https://attack.mitre.org/techniques/T1486/"},
            {"uri": "proto:technique/T1489", "label": "T1489", "aliases": ["Service Stop", "t1489"], "definition": "Adversaries may stop or disable services on a system to render those services unavailable.", "broader": None, "tactic": "TA0040", "technique_name": "Service Stop", "url": "https://attack.mitre.org/techniques/T1489/"},
            {"uri": "proto:technique/T1490", "label": "T1490", "aliases": ["Inhibit System Recovery", "t1490"], "definition": "Adversaries may delete or remove built-in data and turn off services designed to aid in recovery.", "broader": None, "tactic": "TA0040", "technique_name": "Inhibit System Recovery", "url": "https://attack.mitre.org/techniques/T1490/"},
            {"uri": "proto:technique/T1529", "label": "T1529", "aliases": ["System Shutdown/Reboot", "t1529"], "definition": "Adversaries may shutdown/reboot systems to interrupt access to, or aid in the destruction of, those systems.", "broader": None, "tactic": "TA0040", "technique_name": "System Shutdown/Reboot", "url": "https://attack.mitre.org/techniques/T1529/"}
        ]
    }
}


# ============================================================================
# RESTORATION FUNCTIONS
# ============================================================================

def create_collections_if_not_exist(db, collections: List[str]):
    """Ensure collections exist"""
    for coll_name in collections:
        if not db.has_collection(coll_name):
            db.create_collection(coll_name)
            print(f"  ✓ Created collection: {coll_name}")
        else:
            print(f"  • Collection exists: {coll_name}")


def clear_collection(db, coll_name: str):
    """Remove all documents from a collection"""
    if db.has_collection(coll_name):
        db.collection(coll_name).truncate()
        print(f"  🗑️  Cleared: {coll_name}")


def restore_ontology_concepts(db):
    """Restore ontology concept definitions"""
    print("\n📦 Restoring ontology concepts...")
    
    coll = db.collection('ontology_concepts')
    
    for concept in ONTOLOGY_CONCEPTS['concepts']:
        # Use URI as document key (sanitized)
        key = concept['uri'].replace(':', '_').replace('/', '_')
        doc = {
            '_key': key,
            **concept
        }
        
        try:
            coll.insert(doc, overwrite=True)
            print(f"  ✓ {concept['label']}")
        except Exception as e:
            print(f"  ❌ {concept['label']}: {e}")
    
    print(f"  → Restored {len(ONTOLOGY_CONCEPTS['concepts'])} concepts")


def restore_taxonomy_schemes(db):
    """Restore taxonomy scheme metadata"""
    print("\n📋 Restoring taxonomy schemes...")
    
    coll = db.collection('taxonomy_schemes')
    
    for scheme_id, taxonomy in TAXONOMIES.items():
        doc = {
            '_key': scheme_id,
            'scheme_id': scheme_id,
            'taxonomy_id': taxonomy.get('taxonomy_id', ''),
            'taxonomy_label': taxonomy.get('taxonomy_label', ''),
            'description': taxonomy.get('description', ''),
            'version': taxonomy.get('version', '1.0.0'),
            'last_updated': taxonomy.get('last_updated', ''),
            'source': taxonomy.get('source', ''),
            'note': taxonomy.get('note', '')
        }
        
        try:
            coll.insert(doc, overwrite=True)
            print(f"  ✓ {scheme_id}: {taxonomy.get('taxonomy_label', '')}")
        except Exception as e:
            print(f"  ❌ {scheme_id}: {e}")
    
    print(f"  → Restored {len(TAXONOMIES)} taxonomy schemes")


def restore_taxonomy_terms(db):
    """Restore taxonomy terms"""
    print("\n🏷️  Restoring taxonomy terms...")
    
    coll = db.collection('taxonomy_terms')
    total_terms = 0
    
    for scheme_id, taxonomy in TAXONOMIES.items():
        terms = taxonomy.get('terms', [])
        print(f"\n  [{scheme_id}] - {len(terms)} terms")
        
        for term in terms:
            # Generate key from URI
            key = term['uri'].replace(':', '_').replace('/', '_')
            
            doc = {
                '_key': key,
                'scheme_id': scheme_id,
                **term
            }
            
            try:
                coll.insert(doc, overwrite=True)
                total_terms += 1
            except Exception as e:
                print(f"    ❌ {term.get('label', 'unknown')}: {e}")
    
    print(f"\n  → Restored {total_terms} total terms")


def verify_restoration(db):
    """Verify data was restored correctly"""
    print("\n🔍 Verifying restoration...")
    
    collections = ['ontology_concepts', 'taxonomy_schemes', 'taxonomy_terms']
    
    for coll_name in collections:
        if db.has_collection(coll_name):
            count = db.collection(coll_name).count()
            print(f"  • {coll_name}: {count} documents")
        else:
            print(f"  ❌ {coll_name}: collection not found!")


def main():
    parser = argparse.ArgumentParser(description='Restore ProtoGraph ontology to ArangoDB')
    parser.add_argument('--host', default=os.environ.get('ARANGO_HOST', 'localhost'),
                        help='ArangoDB host (default: localhost)')
    parser.add_argument('--port', type=int, default=int(os.environ.get('ARANGO_PORT', '8529')),
                        help='ArangoDB port (default: 8529)')
    parser.add_argument('--db', default=os.environ.get('ARANGO_DB', 'protograph'),
                        help='Database name (default: protograph)')
    parser.add_argument('--user', default=os.environ.get('ARANGO_USER', 'root'),
                        help='Username (default: root)')
    parser.add_argument('--password', default=os.environ.get('ARANGO_PASSWORD', ''),
                        help='Password')
    parser.add_argument('--clear', action='store_true',
                        help='Clear existing data before restoring')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without making changes')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("ProtoGraph Ontology Restoration")
    print("=" * 60)
    print(f"Host: {args.host}:{args.port}")
    print(f"Database: {args.db}")
    print(f"User: {args.user}")
    
    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made")
        print(f"\nWould restore:")
        print(f"  • {len(ONTOLOGY_CONCEPTS['concepts'])} ontology concepts")
        print(f"  • {len(TAXONOMIES)} taxonomy schemes")
        total_terms = sum(len(t.get('terms', [])) for t in TAXONOMIES.values())
        print(f"  • {total_terms} taxonomy terms")
        return
    
    # Connect to ArangoDB
    try:
        client = ArangoClient(hosts=f'http://{args.host}:{args.port}')
        db = client.db(args.db, username=args.user, password=args.password)
        print(f"\n✓ Connected to ArangoDB")
    except Exception as e:
        print(f"\n❌ Failed to connect: {e}")
        return 1
    
    # Create collections
    print("\n📁 Ensuring collections exist...")
    create_collections_if_not_exist(db, ['ontology_concepts', 'taxonomy_schemes', 'taxonomy_terms'])
    
    # Clear if requested
    if args.clear:
        print("\n🗑️  Clearing existing data...")
        clear_collection(db, 'ontology_concepts')
        clear_collection(db, 'taxonomy_schemes')
        clear_collection(db, 'taxonomy_terms')
    
    # Restore data
    restore_ontology_concepts(db)
    restore_taxonomy_schemes(db)
    restore_taxonomy_terms(db)
    
    # Verify
    verify_restoration(db)
    
    print("\n" + "=" * 60)
    print("✅ Restoration complete!")
    print("=" * 60)
    
    return 0


if __name__ == '__main__':
    exit(main())