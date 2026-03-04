#!/usr/bin/env python3
"""
Reset and Seed AUTO_DB
- Drops and recreates AUTO_DB with proper user access
- Creates ontology collections (concepts, taxonomies, terms, relationship_types)
- Seeds the ProtoGraph ontology (concepts, taxonomies, terms, relationships)
- Creates document + edge collections for the knowledge graph
- Seeds 9 Operator LibraryModule nodes from the Neon Saguaro attack chain
- Creates the protograph_kg named graph
"""

from arango import ArangoClient
from datetime import datetime, timezone
from pathlib import Path
import json

# ─── Config ──────────────────────────────────────────────────
ARANGO_HOST = "http://localhost:8529"
DB_NAME = "AUTO_DB"
ROOT_USER = "root"
ROOT_PASS = "devpass"
PAYLOAD_STORAGE_DIR = Path("./data/payloads")

# ─── Connect ─────────────────────────────────────────────────
client = ArangoClient(hosts=ARANGO_HOST)
sys_db = client.db("_system", username=ROOT_USER, password=ROOT_PASS)

# ─── Drop & Recreate DB ─────────────────────────────────────
print("=" * 60)
print("RESETTING AUTO_DB")
print("=" * 60)

if sys_db.has_database(DB_NAME):
    sys_db.delete_database(DB_NAME)
    print(f"✗ Dropped {DB_NAME}")

sys_db.create_database(
    DB_NAME,
    users=[{"username": ROOT_USER, "password": ROOT_PASS, "active": True}],
)
print(f"✓ Created {DB_NAME} with user access")

db = client.db(DB_NAME, username=ROOT_USER, password=ROOT_PASS)

# ─── Ontology Collections ───────────────────────────────────
print("\n--- Ontology Collections ---")
ONTOLOGY_COLLECTIONS = {
    "ontology_concepts": False,
    "ontology_edges": True,  # edge collection
    "taxonomy_schemes": False,
    "taxonomy_terms": False,
    "relationship_types": False,
}

for name, is_edge in ONTOLOGY_COLLECTIONS.items():
    db.create_collection(name, edge=is_edge)
    print(f"  ✓ {name} {'(edge)' if is_edge else ''}")

# ─── Document Collections ───────────────────────────────────
print("\n--- Document Collections ---")
DOC_COLLECTIONS = [
    "LibraryModule",
    "ExecutionPlan",
    "Scenario",
    "RangeEnvironment",
    "IntelReport",
    "DevelopmentStory",
    "Process",
    "TTP",
    "MitreAttack",
    "Person",
    "Team",
    "RobotLog",
]

for name in DOC_COLLECTIONS:
    db.create_collection(name)
    print(f"  ✓ {name}")

# ─── Edge Collections ───────────────────────────────────────
print("\n--- Edge Collections ---")
EDGE_COLLECTIONS = [
    "CONTAINS",
    "PRODUCES",
    "REFERENCES",
    "LEADS_TO",
    "STARTS_WITH",
    "RELATED_TO",
    "ASSIGNED_TO",
    "BELONGS_TO",
    "DEPENDS_ON",
    "TESTS",
]

for name in EDGE_COLLECTIONS:
    db.create_collection(name, edge=True)
    print(f"  ✓ {name} (edge)")


# ═══════════════════════════════════════════════════════════════
# SEED ONTOLOGY
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("SEEDING ONTOLOGY")
print("=" * 60)

now = datetime.now(timezone.utc).isoformat()


def uri_to_key(uri):
    return uri.replace(":", "_").replace("/", "_").replace(" ", "_")


# ─── Concepts ────────────────────────────────────────────────
print("\n--- Concepts ---")
concepts = [
    {
        "uri": "proto:concept/Thing",
        "label": "Thing",
        "definition": "Root concept - everything in the knowledge graph",
        "parent_uri": None,
        "abstract": True,
        "collection": None,
        "properties": [],
    },
    {
        "uri": "proto:concept/Agent",
        "label": "Agent",
        "definition": "An entity that can perform actions - people, teams, systems",
        "parent_uri": "proto:concept/Thing",
        "abstract": True,
        "collection": None,
        "properties": [],
    },
    {
        "uri": "proto:concept/Person",
        "label": "Person",
        "definition": "An individual team member",
        "parent_uri": "proto:concept/Agent",
        "abstract": False,
        "collection": "Person",
        "properties": [
            {"name": "team", "type": "uri", "required": False, "taxonomy": "teams"},
            {"name": "role", "type": "string", "required": False},
            {"name": "email", "type": "string", "required": False},
        ],
    },
    {
        "uri": "proto:concept/Team",
        "label": "Team",
        "definition": "An organizational team within 318th RANS",
        "parent_uri": "proto:concept/Agent",
        "abstract": False,
        "collection": "Team",
        "properties": [
            {"name": "responsibilities", "type": "string[]", "required": False},
            {"name": "color", "type": "string", "required": False},
        ],
    },
    {
        "uri": "proto:concept/Artifact",
        "label": "Artifact",
        "definition": "A work product created or used by teams",
        "parent_uri": "proto:concept/Thing",
        "abstract": True,
        "collection": None,
        "properties": [
            {"name": "name", "type": "string", "required": True},
            {"name": "description", "type": "string", "required": False},
            {"name": "owner", "type": "uri", "required": False, "taxonomy": "teams"},
            {"name": "payload_url", "type": "string", "required": False},
        ],
    },
    {
        "uri": "proto:concept/LibraryModule",
        "label": "Library Module",
        "definition": "An executable module in the Operator library - Cobalt Strike commands, Robot Framework keywords, scripts",
        "parent_uri": "proto:concept/Artifact",
        "abstract": False,
        "collection": "LibraryModule",
        "properties": [
            {"name": "category", "type": "string", "required": True, "taxonomy": "c2_frameworks"},
            {"name": "tactic", "type": "string", "required": False, "taxonomy": "mitre_tactics"},
            {"name": "riskLevel", "type": "string", "required": False, "taxonomy": "risk_levels"},
            {"name": "icon", "type": "string", "required": False},
            {"name": "subcategory", "type": "string", "required": False},
            {"name": "estimatedDuration", "type": "integer", "required": False},
        ],
    },
    {
        "uri": "proto:concept/ExecutionPlan",
        "label": "Execution Plan",
        "definition": "A campaign plan that chains library modules into an attack workflow",
        "parent_uri": "proto:concept/Artifact",
        "abstract": False,
        "collection": "ExecutionPlan",
        "properties": [
            {"name": "status", "type": "string", "required": False},
            {"name": "target_network", "type": "string", "required": False},
        ],
    },
    {
        "uri": "proto:concept/Scenario",
        "label": "Scenario",
        "definition": "A training scenario or exercise definition",
        "parent_uri": "proto:concept/Artifact",
        "abstract": False,
        "collection": "Scenario",
        "properties": [
            {"name": "exercise_type", "type": "string", "required": False},
            {"name": "difficulty", "type": "string", "required": False},
        ],
    },
    {
        "uri": "proto:concept/RangeEnvironment",
        "label": "Range Environment",
        "definition": "A cyber range infrastructure environment",
        "parent_uri": "proto:concept/Artifact",
        "abstract": False,
        "collection": "RangeEnvironment",
        "properties": [
            {"name": "platform", "type": "string", "required": False},
            {"name": "network_topology", "type": "string", "required": False},
        ],
    },
    {
        "uri": "proto:concept/RobotLog",
        "label": "Robot Log",
        "definition": "Execution log from Robot Framework test runs",
        "parent_uri": "proto:concept/Artifact",
        "abstract": False,
        "collection": "RobotLog",
        "properties": [
            {"name": "status", "type": "string", "required": False},
            {"name": "execution_time", "type": "string", "required": False},
        ],
    },
    {
        "uri": "proto:concept/WorkItem",
        "label": "Work Item",
        "definition": "A trackable unit of work",
        "parent_uri": "proto:concept/Thing",
        "abstract": True,
        "collection": None,
        "properties": [
            {"name": "status", "type": "string", "required": False},
            {"name": "priority", "type": "string", "required": False},
            {"name": "assignee", "type": "uri", "required": False},
        ],
    },
    {
        "uri": "proto:concept/DevelopmentStory",
        "label": "Development Story",
        "definition": "A development task - Jira-style work tracking",
        "parent_uri": "proto:concept/WorkItem",
        "abstract": False,
        "collection": "DevelopmentStory",
        "properties": [
            {"name": "story_points", "type": "integer", "required": False},
            {"name": "sprint", "type": "string", "required": False},
        ],
    },
    {
        "uri": "proto:concept/TTP",
        "label": "TTP",
        "definition": "A MITRE ATT&CK Tactic, Technique, or Procedure",
        "parent_uri": "proto:concept/Thing",
        "abstract": False,
        "collection": "TTP",
        "properties": [
            {"name": "mitre_id", "type": "string", "required": True},
            {"name": "tactic", "type": "string", "required": False},
            {"name": "technique", "type": "string", "required": False},
        ],
    },
]

concepts_coll = db.collection("ontology_concepts")
edges_coll = db.collection("ontology_edges")

for c in concepts:
    key = uri_to_key(c["uri"])
    doc = {
        "_key": key,
        "uri": c["uri"],
        "label": c["label"],
        "definition": c["definition"],
        "parent_uri": c["parent_uri"],
        "abstract": c["abstract"],
        "collection": c["collection"],
        "properties": c.get("properties", []),
        "created_at": now,
    }
    concepts_coll.insert(doc)
    print(f"  ✓ {c['label']}")

    # Create IS_A edge to parent
    if c["parent_uri"]:
        parent_key = uri_to_key(c["parent_uri"])
        edges_coll.insert({
            "_from": f"ontology_concepts/{key}",
            "_to": f"ontology_concepts/{parent_key}",
            "type": "IS_A",
            "created_at": now,
        })

print(f"  → {len(concepts)} concepts created")

# ─── Taxonomies ──────────────────────────────────────────────
print("\n--- Taxonomies ---")
taxonomies = [
    {"_key": "teams", "label": "Teams", "definition": "318th RANS organizational teams"},
    {"_key": "c2_frameworks", "label": "C2 Frameworks", "definition": "Command and control frameworks"},
    {"_key": "mitre_tactics", "label": "MITRE Tactics", "definition": "MITRE ATT&CK tactics"},
    {"_key": "risk_levels", "label": "Risk Levels", "definition": "Risk classification levels"},
    {"_key": "artifact_status", "label": "Artifact Status", "definition": "Status values for artifacts"},
]

tax_coll = db.collection("taxonomy_schemes")
for t in taxonomies:
    t["created_at"] = now
    tax_coll.insert(t)
    print(f"  ✓ {t['label']}")

# ─── Taxonomy Terms ──────────────────────────────────────────
print("\n--- Taxonomy Terms ---")
terms = [
    # Teams
    {"_key": "team_automation", "taxonomy_id": "teams", "uri": "proto:team/Automation", "label": "Automation", "aliases": ["Auto"]},
    {"_key": "team_opfor", "taxonomy_id": "teams", "uri": "proto:team/OPFOR", "label": "OPFOR", "aliases": ["Red Team"]},
    {"_key": "team_content", "taxonomy_id": "teams", "uri": "proto:team/ContentDevelopment", "label": "Content Development", "aliases": ["Content Dev"]},
    {"_key": "team_range", "taxonomy_id": "teams", "uri": "proto:team/RangeOperations", "label": "Range Operations", "aliases": ["Range Ops"]},
    # C2 Frameworks
    {"_key": "c2_cobalt_strike", "taxonomy_id": "c2_frameworks", "uri": "proto:c2/CobaltStrike", "label": "Cobalt Strike", "aliases": ["CS"]},
    {"_key": "c2_sliver", "taxonomy_id": "c2_frameworks", "uri": "proto:c2/Sliver", "label": "Sliver", "aliases": []},
    # Risk Levels
    {"_key": "risk_low", "taxonomy_id": "risk_levels", "uri": "proto:risk/Low", "label": "Low", "aliases": []},
    {"_key": "risk_medium", "taxonomy_id": "risk_levels", "uri": "proto:risk/Medium", "label": "Medium", "aliases": []},
    {"_key": "risk_high", "taxonomy_id": "risk_levels", "uri": "proto:risk/High", "label": "High", "aliases": []},
    {"_key": "risk_critical", "taxonomy_id": "risk_levels", "uri": "proto:risk/Critical", "label": "Critical", "aliases": []},
    # MITRE Tactics
    {"_key": "ta0001", "taxonomy_id": "mitre_tactics", "uri": "proto:mitre/TA0001", "label": "Initial Access", "aliases": []},
    {"_key": "ta0002", "taxonomy_id": "mitre_tactics", "uri": "proto:mitre/TA0002", "label": "Execution", "aliases": []},
    {"_key": "ta0003", "taxonomy_id": "mitre_tactics", "uri": "proto:mitre/TA0003", "label": "Persistence", "aliases": []},
    {"_key": "ta0004", "taxonomy_id": "mitre_tactics", "uri": "proto:mitre/TA0004", "label": "Privilege Escalation", "aliases": []},
    {"_key": "ta0005", "taxonomy_id": "mitre_tactics", "uri": "proto:mitre/TA0005", "label": "Defense Evasion", "aliases": []},
    {"_key": "ta0006", "taxonomy_id": "mitre_tactics", "uri": "proto:mitre/TA0006", "label": "Credential Access", "aliases": []},
    {"_key": "ta0007", "taxonomy_id": "mitre_tactics", "uri": "proto:mitre/TA0007", "label": "Discovery", "aliases": []},
    {"_key": "ta0008", "taxonomy_id": "mitre_tactics", "uri": "proto:mitre/TA0008", "label": "Lateral Movement", "aliases": []},
    {"_key": "ta0009", "taxonomy_id": "mitre_tactics", "uri": "proto:mitre/TA0009", "label": "Collection", "aliases": []},
    {"_key": "ta0011", "taxonomy_id": "mitre_tactics", "uri": "proto:mitre/TA0011", "label": "Command and Control", "aliases": ["C2"]},
    {"_key": "ta0042", "taxonomy_id": "mitre_tactics", "uri": "proto:mitre/TA0042", "label": "Resource Development", "aliases": []},
]

terms_coll = db.collection("taxonomy_terms")
for t in terms:
    t["created_at"] = now
    t.setdefault("definition", "")
    t.setdefault("aliases", [])
    t.setdefault("broader", None)
    t.setdefault("metadata", {})
    terms_coll.insert(t)

print(f"  → {len(terms)} terms created")

# ─── Relationship Types ─────────────────────────────────────
print("\n--- Relationship Types ---")
rel_types = [
    {
        "_key": "rel_CONTAINS",
        "uri": "proto:rel/CONTAINS",
        "label": "CONTAINS",
        "definition": "Parent contains child element",
        "domain": ["proto:concept/ExecutionPlan", "proto:concept/Scenario"],
        "range": ["proto:concept/LibraryModule", "proto:concept/Artifact"],
    },
    {
        "_key": "rel_PRODUCES",
        "uri": "proto:rel/PRODUCES",
        "label": "PRODUCES",
        "definition": "Source produces target as output",
        "domain": ["proto:concept/LibraryModule", "proto:concept/Agent"],
        "range": ["proto:concept/Artifact", "proto:concept/RobotLog"],
    },
    {
        "_key": "rel_REFERENCES",
        "uri": "proto:rel/REFERENCES",
        "label": "REFERENCES",
        "definition": "Source references or cites target",
        "domain": ["proto:concept/Artifact"],
        "range": ["proto:concept/TTP", "proto:concept/Artifact"],
    },
    {
        "_key": "rel_LEADS_TO",
        "uri": "proto:rel/LEADS_TO",
        "label": "LEADS_TO",
        "definition": "Source leads to or enables target in a workflow",
        "domain": ["proto:concept/LibraryModule"],
        "range": ["proto:concept/LibraryModule"],
    },
    {
        "_key": "rel_ASSIGNED_TO",
        "uri": "proto:rel/ASSIGNED_TO",
        "label": "ASSIGNED_TO",
        "definition": "Work item assigned to an agent",
        "domain": ["proto:concept/WorkItem"],
        "range": ["proto:concept/Agent"],
    },
    {
        "_key": "rel_BELONGS_TO",
        "uri": "proto:rel/BELONGS_TO",
        "label": "BELONGS_TO",
        "definition": "Agent belongs to a team",
        "domain": ["proto:concept/Person"],
        "range": ["proto:concept/Team"],
    },
    {
        "_key": "rel_DEPENDS_ON",
        "uri": "proto:rel/DEPENDS_ON",
        "label": "DEPENDS_ON",
        "definition": "Source depends on target",
        "domain": ["proto:concept/Artifact"],
        "range": ["proto:concept/Artifact"],
    },
    {
        "_key": "rel_TESTS",
        "uri": "proto:rel/TESTS",
        "label": "TESTS",
        "definition": "Test validates or exercises target",
        "domain": ["proto:concept/RobotLog"],
        "range": ["proto:concept/LibraryModule", "proto:concept/ExecutionPlan"],
    },
    {
        "_key": "rel_RELATED_TO",
        "uri": "proto:rel/RELATED_TO",
        "label": "RELATED_TO",
        "definition": "General semantic relationship",
        "domain": ["proto:concept/Thing"],
        "range": ["proto:concept/Thing"],
        "symmetric": True,
    },
]

rel_coll = db.collection("relationship_types")
for r in rel_types:
    r["created_at"] = now
    r.setdefault("inverse", None)
    r.setdefault("symmetric", False)
    r.setdefault("transitive", False)
    rel_coll.insert(r)
    print(f"  ✓ {r['label']}")


# ═══════════════════════════════════════════════════════════════
# SEED OPERATOR LIBRARY MODULES (Neon Saguaro Chain)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("SEEDING OPERATOR LIBRARY MODULES")
print("=" * 60)

modules = [
    {
        "_key": "cs-start-c2",
        "name": "Start C2",
        "description": "Start the Cobalt Strike team server",
        "icon": "🚀",
        "tactic": "Resource Development",
        "category": "Cobalt Strike",
        "subcategory": "Infrastructure",
        "riskLevel": "low",
        "estimatedDuration": 10,
        "owner": "Automation",
        "_artifact_type": "Library Module",
    },
    {
        "_key": "cs-create-listener",
        "name": "Create Listener",
        "description": "Create a C2 listener for beacon callbacks",
        "icon": "📡",
        "tactic": "Resource Development",
        "category": "Cobalt Strike",
        "subcategory": "Infrastructure",
        "riskLevel": "medium",
        "estimatedDuration": 5,
        "owner": "Automation",
        "_artifact_type": "Library Module",
    },
    {
        "_key": "cs-create-payload",
        "name": "Create Payload",
        "description": "Generate a beacon payload for the specified listener",
        "icon": "💣",
        "tactic": "Resource Development",
        "category": "Cobalt Strike",
        "subcategory": "Payload",
        "riskLevel": "high",
        "estimatedDuration": 10,
        "owner": "Automation",
        "_artifact_type": "Library Module",
    },
    {
        "_key": "cs-initial-access",
        "name": "Initial Access (SCP/SSH)",
        "description": "Deploy and execute beacon on target via SCP file transfer and SSH execution",
        "icon": "🚀",
        "tactic": "Initial Access",
        "category": "Cobalt Strike",
        "subcategory": "Access",
        "riskLevel": "high",
        "estimatedDuration": 30,
        "owner": "OPFOR",
        "_artifact_type": "Library Module",
    },
    {
        "_key": "cs-get-session-by-ip",
        "name": "Get Session By IP",
        "description": "Retrieve an active beacon session by target IP address",
        "icon": "🎯",
        "tactic": "Execution",
        "category": "Cobalt Strike",
        "subcategory": "Session Management",
        "riskLevel": "low",
        "estimatedDuration": 15,
        "owner": "Automation",
        "_artifact_type": "Library Module",
    },
    {
        "_key": "cs-getuid",
        "name": "Get User Identity",
        "description": "Retrieve current user identity and privilege context from beacon",
        "icon": "👤",
        "tactic": "Discovery",
        "category": "Cobalt Strike",
        "subcategory": "Reconnaissance",
        "riskLevel": "low",
        "estimatedDuration": 5,
        "owner": "OPFOR",
        "_artifact_type": "Library Module",
    },
    {
        "_key": "cs-dump-credentials",
        "name": "Dump Credentials",
        "description": "Dump credentials using Mimikatz",
        "icon": "🔑",
        "tactic": "Credential Access",
        "category": "Cobalt Strike",
        "subcategory": "Credentials",
        "riskLevel": "critical",
        "estimatedDuration": 15,
        "owner": "OPFOR",
        "_artifact_type": "Library Module",
    },
    {
        "_key": "cs-lateral-psexec",
        "name": "Lateral Move (PsExec)",
        "description": "Lateral movement using PsExec64 via beacon",
        "icon": "🔀",
        "tactic": "Lateral Movement",
        "category": "Cobalt Strike",
        "subcategory": "Movement",
        "riskLevel": "high",
        "estimatedDuration": 30,
        "owner": "OPFOR",
        "_artifact_type": "Library Module",
    },
    {
        "_key": "cs-stop-c2",
        "name": "Stop C2",
        "description": "Disconnect from the Cobalt Strike teamserver",
        "icon": "🛑",
        "tactic": "Cleanup",
        "category": "Cobalt Strike",
        "subcategory": "C2 Management",
        "riskLevel": "low",
        "estimatedDuration": 5,
        "owner": "Automation",
        "_artifact_type": "Library Module",
    },
]

lib_coll = db.collection("LibraryModule")

# Ensure payload directory exists
PAYLOAD_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Load full payload data from existing payload files (if they exist)
# These contain the rich data (inputs, outputs, parameters, robotFramework)
def load_payload(key: str) -> dict | None:
    """Load existing payload file for a module key."""
    payload_path = PAYLOAD_STORAGE_DIR / f"{key}.json"
    if payload_path.exists():
        with open(payload_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def save_payload(key: str, full_data: dict):
    """Write full payload to ./data/payloads/{key}.json"""
    payload_path = PAYLOAD_STORAGE_DIR / f"{key}.json"
    payload = {
        "_payload_version": "2.0",
        "_saved_at": now,
        "_artifact_key": key,
        **full_data,
    }
    with open(payload_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"    📄 Payload saved: {payload_path}")

for m in modules:
    key = m["_key"]
    m["_ingested_at"] = now
    m["payload_url"] = f"/api/ingest/payloads/{key}.json"
    
    # Check if a rich payload file already exists
    existing_payload = load_payload(key)
    if existing_payload:
        # Payload file already has full data — leave it as-is
        print(f"    📄 Existing payload found for {key}")
    else:
        # No payload file yet — write the metadata as the payload
        # (you can later enrich these with inputs/outputs/parameters)
        save_payload(key, {k: v for k, v in m.items() if not k.startswith("_") or k == "_artifact_type"})
    
    lib_coll.insert(m)
    print(f"  ✓ {m['name']} ({key})")

print(f"  → {len(modules)} modules created")

# ─── LEADS_TO Edges (Attack Chain) ──────────────────────────
print("\n--- Attack Chain Edges (LEADS_TO) ---")
chain = [
    ("cs-start-c2", "cs-create-listener", "C2 ready, create listener"),
    ("cs-create-listener", "cs-create-payload", "Listener active, generate payload"),
    ("cs-create-payload", "cs-initial-access", "Payload ready, deploy to target"),
    ("cs-initial-access", "cs-get-session-by-ip", "Beacon deployed, retrieve session"),
    ("cs-get-session-by-ip", "cs-getuid", "Session acquired, identify user"),
    ("cs-getuid", "cs-dump-credentials", "User identified, harvest credentials"),
    ("cs-dump-credentials", "cs-lateral-psexec", "Credentials harvested, pivot to next target"),
    ("cs-lateral-psexec", "cs-stop-c2", "Lateral movement complete, clean up"),
]

leads_to = db.collection("LEADS_TO")
for src, tgt, desc in chain:
    leads_to.insert({
        "_from": f"LibraryModule/{src}",
        "_to": f"LibraryModule/{tgt}",
        "relationship_type": "LEADS_TO",
        "description": desc,
        "weight": 1.0,
        "confidence": 1.0,
        "created_at": now,
    })
    print(f"  ✓ {src} → {tgt}")

# ─── REFERENCES Edges (MITRE ATT&CK) ────────────────────────
print("\n--- MITRE ATT&CK References ---")
ttp_refs = [
    ("cs-initial-access", "T1105", "Ingress Tool Transfer"),
    ("cs-getuid", "T1033", "System Owner/User Discovery"),
    ("cs-dump-credentials", "T1003.001", "LSASS Memory"),
    ("cs-lateral-psexec", "T1569.002", "Service Execution"),
]

ttp_coll = db.collection("TTP")
refs_coll = db.collection("REFERENCES")

for mod_key, mitre_id, technique_name in ttp_refs:
    ttp_key = mitre_id.replace(".", "_")
    # Create TTP node if needed
    if not ttp_coll.has(ttp_key):
        ttp_coll.insert({
            "_key": ttp_key,
            "mitre_id": mitre_id,
            "name": technique_name,
            "tactic": "",
            "_artifact_type": "TTP",
            "_ingested_at": now,
        })
    # Create edge
    refs_coll.insert({
        "_from": f"LibraryModule/{mod_key}",
        "_to": f"TTP/{ttp_key}",
        "relationship_type": "REFERENCES",
        "description": f"Implements {mitre_id}: {technique_name}",
        "created_at": now,
    })
    print(f"  ✓ {mod_key} → {mitre_id} ({technique_name})")


# ─── Seed Teams ──────────────────────────────────────────────
print("\n--- Teams ---")
teams = [
    {"_key": "automation", "name": "Automation", "color": "#3B82F6"},
    {"_key": "opfor", "name": "OPFOR", "color": "#EF4444"},
    {"_key": "content_dev", "name": "Content Development", "color": "#10B981"},
    {"_key": "range_ops", "name": "Range Operations", "color": "#F59E0B"},
]

team_coll = db.collection("Team")
for t in teams:
    t["_ingested_at"] = now
    t["_artifact_type"] = "Team"
    team_coll.insert(t)
    print(f"  ✓ {t['name']}")


# ─── Named Graph ────────────────────────────────────────────
print("\n--- Named Graph ---")
if db.has_graph("protograph_kg"):
    db.delete_graph("protograph_kg")

edge_definitions = [
    {
        "edge_collection": ec,
        "from_vertex_collections": DOC_COLLECTIONS,
        "to_vertex_collections": DOC_COLLECTIONS,
    }
    for ec in EDGE_COLLECTIONS
]

db.create_graph("protograph_kg", edge_definitions=edge_definitions)
print("  ✓ protograph_kg graph created")


# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("DONE!")
print("=" * 60)
print(f"  Database:     {DB_NAME}")
print(f"  Ontology:     {len(concepts)} concepts, {len(taxonomies)} taxonomies, {len(terms)} terms, {len(rel_types)} rel types")
print(f"  Modules:      {len(modules)} LibraryModule documents")
print(f"  Chain edges:  {len(chain)} LEADS_TO")
print(f"  TTP refs:     {len(ttp_refs)} REFERENCES")
print(f"  Teams:        {len(teams)}")
print(f"  Graph:        protograph_kg")
print()
print("Restart your FastAPI server and the Ontology Manager should load!")