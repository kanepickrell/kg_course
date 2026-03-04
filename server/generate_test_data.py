"""
ProtoGraph Test Data Generator
==============================

Generates realistic test artifacts for testing the neural graph router.
Creates Library Modules, Robot Logs, Teams, and relationships between them.

Run with: python generate_test_data.py
"""

import requests
import random
import time

API_BASE = "http://localhost:8000"

# =============================================================================
# TEST DATA DEFINITIONS
# =============================================================================

# MITRE ATT&CK Tactics and Techniques
TACTICS = [
    ("TA0001", "Initial Access"),
    ("TA0002", "Execution"),
    ("TA0003", "Persistence"),
    ("TA0004", "Privilege Escalation"),
    ("TA0005", "Defense Evasion"),
    ("TA0006", "Credential Access"),
    ("TA0007", "Discovery"),
    ("TA0008", "Lateral Movement"),
    ("TA0009", "Collection"),
    ("TA0010", "Exfiltration"),
    ("TA0011", "Command and Control"),
]

TECHNIQUES = {
    "TA0001": [("T1566", "Phishing"), ("T1190", "Exploit Public-Facing Application")],
    "TA0002": [("T1059", "Command and Scripting Interpreter"), ("T1053", "Scheduled Task")],
    "TA0003": [("T1547", "Boot or Logon Autostart"), ("T1543", "Create or Modify System Process")],
    "TA0004": [("T1548", "Abuse Elevation Control"), ("T1134", "Access Token Manipulation")],
    "TA0005": [("T1070", "Indicator Removal"), ("T1562", "Impair Defenses")],
    "TA0006": [("T1003", "OS Credential Dumping"), ("T1110", "Brute Force"), ("T1558", "Steal or Forge Kerberos Tickets")],
    "TA0007": [("T1087", "Account Discovery"), ("T1083", "File and Directory Discovery")],
    "TA0008": [("T1021", "Remote Services"), ("T1550", "Use Alternate Authentication")],
    "TA0009": [("T1005", "Data from Local System"), ("T1113", "Screen Capture")],
    "TA0010": [("T1041", "Exfiltration Over C2"), ("T1048", "Exfiltration Over Alternative Protocol")],
    "TA0011": [("T1071", "Application Layer Protocol"), ("T1105", "Ingress Tool Transfer")],
}

# C2 Frameworks
C2_FRAMEWORKS = ["Cobalt Strike", "Sliver", "Metasploit"]

# Teams
TEAMS = [
    ("team_automation", "Automation", "automation"),
    ("team_opfor", "OPFOR", "opfor"),
    ("team_content", "Content Development", "content_dev"),
    ("team_range", "Range", "range"),
]

# Library Module Templates
LIBRARY_MODULES = [
    # Credential Access modules
    {"name": "mimikatz_sekurlsa", "desc": "Dump credentials from LSASS using sekurlsa", "tactic": "TA0006", "technique": "T1003"},
    {"name": "mimikatz_kerberos", "desc": "Kerberos ticket extraction and manipulation", "tactic": "TA0006", "technique": "T1558"},
    {"name": "lazagne_browser", "desc": "Extract saved passwords from browsers", "tactic": "TA0006", "technique": "T1003"},
    {"name": "pypykatz_memory", "desc": "Python implementation of mimikatz for memory analysis", "tactic": "TA0006", "technique": "T1003"},
    
    # Lateral Movement modules
    {"name": "psexec_beacon", "desc": "PsExec-style lateral movement via SMB", "tactic": "TA0008", "technique": "T1021"},
    {"name": "wmi_exec", "desc": "WMI-based remote execution", "tactic": "TA0008", "technique": "T1021"},
    {"name": "winrm_shell", "desc": "WinRM remote shell execution", "tactic": "TA0008", "technique": "T1021"},
    {"name": "dcom_exec", "desc": "DCOM-based lateral movement", "tactic": "TA0008", "technique": "T1021"},
    {"name": "pth_attack", "desc": "Pass-the-hash authentication attack", "tactic": "TA0008", "technique": "T1550"},
    
    # Discovery modules
    {"name": "bloodhound_collector", "desc": "Active Directory enumeration for BloodHound", "tactic": "TA0007", "technique": "T1087"},
    {"name": "ad_recon", "desc": "Active Directory reconnaissance scripts", "tactic": "TA0007", "technique": "T1087"},
    {"name": "network_scanner", "desc": "Internal network scanning and mapping", "tactic": "TA0007", "technique": "T1083"},
    {"name": "share_finder", "desc": "Network share enumeration", "tactic": "TA0007", "technique": "T1083"},
    
    # Execution modules
    {"name": "powershell_runner", "desc": "PowerShell script execution framework", "tactic": "TA0002", "technique": "T1059"},
    {"name": "csharp_loader", "desc": "In-memory C# assembly loader", "tactic": "TA0002", "technique": "T1059"},
    {"name": "bof_loader", "desc": "Beacon Object File loader for Cobalt Strike", "tactic": "TA0002", "technique": "T1059"},
    
    # Persistence modules
    {"name": "scheduled_task_persist", "desc": "Persistence via scheduled tasks", "tactic": "TA0003", "technique": "T1053"},
    {"name": "registry_persist", "desc": "Registry-based persistence mechanisms", "tactic": "TA0003", "technique": "T1547"},
    {"name": "service_persist", "desc": "Windows service persistence", "tactic": "TA0003", "technique": "T1543"},
    
    # Defense Evasion modules
    {"name": "amsi_bypass", "desc": "AMSI bypass techniques", "tactic": "TA0005", "technique": "T1562"},
    {"name": "etw_patch", "desc": "ETW patching for logging evasion", "tactic": "TA0005", "technique": "T1562"},
    {"name": "log_cleaner", "desc": "Windows event log manipulation", "tactic": "TA0005", "technique": "T1070"},
    
    # C2 modules
    {"name": "dns_beacon", "desc": "DNS-based C2 communication", "tactic": "TA0011", "technique": "T1071"},
    {"name": "https_beacon", "desc": "HTTPS-based C2 with domain fronting", "tactic": "TA0011", "technique": "T1071"},
    {"name": "smb_beacon", "desc": "SMB-based peer-to-peer C2", "tactic": "TA0011", "technique": "T1071"},
    
    # Collection modules
    {"name": "keylogger", "desc": "Keystroke logging module", "tactic": "TA0009", "technique": "T1005"},
    {"name": "screenshot_capture", "desc": "Periodic screenshot capture", "tactic": "TA0009", "technique": "T1113"},
    {"name": "clipboard_monitor", "desc": "Clipboard content monitoring", "tactic": "TA0009", "technique": "T1005"},
]

# Robot Log Templates
ROBOT_LOG_TEMPLATES = [
    {"name": "test_credential_dump_{n}", "desc": "Automated test of credential dumping module"},
    {"name": "test_lateral_movement_{n}", "desc": "Automated lateral movement test"},
    {"name": "test_discovery_{n}", "desc": "Automated discovery module test"},
    {"name": "test_persistence_{n}", "desc": "Persistence mechanism validation"},
    {"name": "test_evasion_{n}", "desc": "Defense evasion technique test"},
    {"name": "test_c2_comms_{n}", "desc": "C2 communication channel test"},
    {"name": "integration_test_{n}", "desc": "Full attack chain integration test"},
    {"name": "regression_test_{n}", "desc": "Regression test suite execution"},
]


# =============================================================================
# DATA GENERATION FUNCTIONS
# =============================================================================

def create_node(label: str, node_type: str, cluster: str, description: str, tags: list) -> dict:
    """Create a node via Prospector API"""
    payload = {
        "label": label,
        "type": node_type,
        "cluster": cluster,
        "description": description,
        "tags": tags
    }
    
    try:
        response = requests.post(
            f"{API_BASE}/prospector/node",
            json=payload,
            timeout=10
        )
        if response.status_code == 200:
            result = response.json()
            return result.get("node", {})
        else:
            print(f"  ⚠️ Failed to create {label}: {response.text[:100]}")
    except Exception as e:
        print(f"  ❌ Error creating {label}: {e}")
    
    return {}


def create_edge(from_node: str, to_node: str, rel_type: str, weight: float = 0.8) -> dict:
    """Create an edge via Prospector API"""
    payload = {
        "from_node": from_node,
        "to_node": to_node,
        "relationship_type": rel_type,
        "weight": weight,
        "bidirectional": False
    }
    
    try:
        response = requests.post(
            f"{API_BASE}/prospector/edge",
            json=payload,
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        else:
            print(f"  ⚠️ Failed to create edge: {response.text[:100]}")
    except Exception as e:
        print(f"  ❌ Error creating edge: {e}")
    
    return {}


def generate_test_data():
    """Generate comprehensive test data"""
    
    print("="*60)
    print("PROTOGRAPH TEST DATA GENERATOR")
    print("="*60)
    
    created_nodes = {
        "teams": [],
        "modules": [],
        "logs": [],
    }
    
    # 1. Create Teams
    print("\n📁 Creating Teams...")
    for team_id, team_name, cluster in TEAMS:
        node = create_node(
            label=team_name,
            node_type="team",
            cluster=cluster,
            description=f"{team_name} team for cyber range operations",
            tags=[cluster, "team", team_id]
        )
        if node:
            created_nodes["teams"].append(node)
            print(f"  ✓ {team_name}")
    
    # 2. Create Library Modules
    print("\n📦 Creating Library Modules...")
    for module in LIBRARY_MODULES:
        c2 = random.choice(C2_FRAMEWORKS)
        cluster = "opfor" if module["tactic"] in ["TA0006", "TA0008"] else random.choice(["automation", "opfor"])
        
        node = create_node(
            label=module["name"],
            node_type="library_module",
            cluster=cluster,
            description=module["desc"],
            tags=[module["tactic"], module["technique"], c2.lower().replace(" ", "_"), cluster]
        )
        if node:
            node["_meta"] = {"tactic": module["tactic"], "technique": module["technique"], "c2": c2}
            created_nodes["modules"].append(node)
            print(f"  ✓ {module['name']} ({module['tactic']})")
    
    # 3. Create Robot Logs
    print("\n🤖 Creating Robot Logs...")
    statuses = ["PASS", "FAIL", "PASS", "PASS", "PASS"]  # 80% pass rate
    
    for i, template in enumerate(ROBOT_LOG_TEMPLATES * 3):  # Create 24 logs
        log_name = template["name"].format(n=i+1)
        status = random.choice(statuses)
        
        # Associate with a random module
        if created_nodes["modules"]:
            associated_module = random.choice(created_nodes["modules"])
            tags = ["robot_framework", "automated_test", status.lower()]
            if "_meta" in associated_module:
                tags.extend([associated_module["_meta"]["tactic"], associated_module["_meta"]["technique"]])
        else:
            tags = ["robot_framework", "automated_test", status.lower()]
        
        node = create_node(
            label=log_name,
            node_type="robot_log",
            cluster="automation",
            description=f"{template['desc']} - Status: {status}",
            tags=tags
        )
        if node:
            node["_associated_module"] = associated_module["_id"] if created_nodes["modules"] else None
            created_nodes["logs"].append(node)
            print(f"  ✓ {log_name} [{status}]")
    
    # 4. Create Relationships
    print("\n🔗 Creating Relationships...")
    edge_count = 0
    
    # Team -> Module (AUTHORED)
    if created_nodes["teams"] and created_nodes["modules"]:
        opfor_team = next((t for t in created_nodes["teams"] if "OPFOR" in t.get("label", "")), None)
        automation_team = next((t for t in created_nodes["teams"] if "Automation" in t.get("label", "")), None)
        
        for module in created_nodes["modules"]:
            # Assign to appropriate team
            team = opfor_team if module.get("cluster") == "opfor" else automation_team
            if team:
                result = create_edge(team["_id"], module["_id"], "authored", 0.9)
                if result:
                    edge_count += 1
    
    # Module -> Log (TESTED_BY)
    for log in created_nodes["logs"]:
        if log.get("_associated_module"):
            result = create_edge(log["_associated_module"], log["_id"], "tested_by", 0.85)
            if result:
                edge_count += 1
    
    # Module -> Module (USES/DEPENDS_ON) - Create attack chains
    if len(created_nodes["modules"]) > 5:
        # Group modules by tactic
        by_tactic = {}
        for m in created_nodes["modules"]:
            if "_meta" in m:
                tactic = m["_meta"]["tactic"]
                if tactic not in by_tactic:
                    by_tactic[tactic] = []
                by_tactic[tactic].append(m)
        
        # Create attack chain: Discovery -> Credential Access -> Lateral Movement
        chains = [
            ("TA0007", "TA0006", "uses"),      # Discovery -> Credential Access
            ("TA0006", "TA0008", "uses"),      # Credential Access -> Lateral Movement
            ("TA0002", "TA0003", "uses"),      # Execution -> Persistence
            ("TA0003", "TA0005", "depends_on"), # Persistence -> Defense Evasion
            ("TA0008", "TA0011", "uses"),      # Lateral Movement -> C2
        ]
        
        for source_tactic, target_tactic, rel_type in chains:
            if source_tactic in by_tactic and target_tactic in by_tactic:
                for src in by_tactic[source_tactic][:2]:  # Limit connections
                    for tgt in by_tactic[target_tactic][:2]:
                        result = create_edge(src["_id"], tgt["_id"], rel_type, 0.7)
                        if result:
                            edge_count += 1
    
    print(f"  ✓ Created {edge_count} relationships")
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"  Teams:          {len(created_nodes['teams'])}")
    print(f"  Library Modules: {len(created_nodes['modules'])}")
    print(f"  Robot Logs:      {len(created_nodes['logs'])}")
    print(f"  Relationships:   {edge_count}")
    print(f"  TOTAL NODES:     {sum(len(v) for v in created_nodes.values())}")
    
    return created_nodes


def reinitialize_neural_router():
    """Reinitialize the neural router after data generation"""
    print("\n🧠 Reinitializing Neural Router...")
    try:
        response = requests.post(f"{API_BASE}/api/neural/initialize?force=true", timeout=60)
        if response.status_code == 200:
            result = response.json()
            stats = result.get("stats", {})
            print(f"  ✓ Nodes: {stats.get('total_nodes', 0)}")
            print(f"  ✓ Edges: {stats.get('total_edges', 0)}")
            print(f"  ✓ Agents: {stats.get('total_agents', 0)}")
            return True
        else:
            print(f"  ⚠️ Failed: {response.text[:100]}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    return False


def test_neural_search():
    """Test neural search with sample queries"""
    print("\n🔍 Testing Neural Search...")
    
    test_queries = [
        "credential dumping mimikatz",
        "lateral movement remote execution",
        "active directory enumeration",
        "persistence scheduled task",
        "defense evasion amsi bypass",
    ]
    
    for query in test_queries:
        try:
            response = requests.get(
                f"{API_BASE}/api/neural/search",
                params={"q": query},
                timeout=30
            )
            if response.status_code == 200:
                result = response.json()
                print(f"\n  Query: '{query}'")
                print(f"    Entry agents: {len(result.get('entry_agents', []))}")
                print(f"    Activated: {len(result.get('activated_agents', []))}")
                print(f"    Contributing: {len(result.get('contributing_agents', []))}")
                print(f"    Time: {result.get('time_ms', 0):.1f}ms")
                
                contexts = result.get("contexts", {})
                if contexts:
                    print(f"    Contexts:")
                    for agent_id, ctx in list(contexts.items())[:2]:
                        print(f"      [{agent_id}]: {ctx[:80]}...")
        except Exception as e:
            print(f"  ❌ Error searching '{query}': {e}")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    # Check API is running
    try:
        response = requests.get(f"{API_BASE}/", timeout=5)
        print(f"✓ API is running at {API_BASE}")
    except:
        print(f"❌ Cannot connect to API at {API_BASE}")
        print("   Make sure unified_api.py is running")
        exit(1)
    
    # Generate test data
    created = generate_test_data()
    
    # Reinitialize neural router
    if reinitialize_neural_router():
        # Test search
        time.sleep(2)  # Wait for embeddings
        test_neural_search()
    
    print("\n✅ Done!")
