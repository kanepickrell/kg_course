#!/usr/bin/env python3
"""
Add Extended ProtoGraph Dataset - 50+ Nodes
Realistic cyber range scenario nodes and relationships
"""

import sys
import getpass
from arango import ArangoClient

print("=" * 60)
print("🚀 ProtoGraph - Add Extended Dataset")
print("=" * 60)
print()

# Get configuration from user
ARANGO_HOST = input("ArangoDB host [http://localhost:8529]: ").strip() or "http://localhost:8529"
ARANGO_USER = input("ArangoDB username [root]: ").strip() or "root"
ARANGO_PASSWORD = getpass.getpass("ArangoDB password: ")
DATABASE_NAME = input("Database name [protograph]: ").strip() or "protograph"

print()
print("✓ Configuration received")
print()

try:
    # Connect to ArangoDB
    print("🔌 Connecting to ArangoDB...")
    client = ArangoClient(hosts=ARANGO_HOST)
    db = client.db(DATABASE_NAME, username=ARANGO_USER, password=ARANGO_PASSWORD)
    print("✓ Connected successfully")
    
    nodes_collection = db.collection("nodes")
    edges_collection = db.collection("edges")
    
    print("\n📥 Inserting extended dataset...")
    print("-" * 60)
    
    # Extended nodes (50+ total including original 11)
    extended_nodes = [
        # Content Development Cluster (15 nodes total)
        {"_key": "cd-threat-intel", "label": "Threat Intelligence Report", "type": "research", "cluster": "content_dev", "importance": 0.92, "size": 52},
        {"_key": "cd-ttps", "label": "TTP Mapping", "type": "analysis", "cluster": "content_dev", "importance": 0.88, "size": 49},
        {"_key": "cd-objectives", "label": "Learning Objectives", "type": "planning", "cluster": "content_dev", "importance": 0.9, "size": 51},
        {"_key": "cd-storyline", "label": "Attack Storyline", "type": "design", "cluster": "content_dev", "importance": 0.87, "size": 48},
        {"_key": "cd-personas", "label": "Adversary Personas", "type": "design", "cluster": "content_dev", "importance": 0.85, "size": 47},
        {"_key": "cd-handbook", "label": "Exercise Handbook", "type": "documentation", "cluster": "content_dev", "importance": 0.91, "size": 51},
        {"_key": "cd-briefing", "label": "Pre-Brief Materials", "type": "documentation", "cluster": "content_dev", "importance": 0.82, "size": 45},
        {"_key": "cd-debrief", "label": "After Action Template", "type": "documentation", "cluster": "content_dev", "importance": 0.84, "size": 46},
        {"_key": "cd-evaluation", "label": "Assessment Rubric", "type": "evaluation", "cluster": "content_dev", "importance": 0.86, "size": 47},
        {"_key": "cd-mitre", "label": "MITRE ATT&CK Mapping", "type": "reference", "cluster": "content_dev", "importance": 0.93, "size": 53},
        {"_key": "cd-ioc", "label": "IOC List", "type": "reference", "cluster": "content_dev", "importance": 0.88, "size": 49},
        {"_key": "cd-timeline", "label": "Event Timeline", "type": "planning", "cluster": "content_dev", "importance": 0.85, "size": 47},
        
        # Range Infrastructure Cluster (15 nodes total)
        {"_key": "rng-domain", "label": "Active Directory Setup", "type": "infrastructure", "cluster": "range", "importance": 0.94, "size": 54},
        {"_key": "rng-firewall", "label": "Firewall Configuration", "type": "security", "cluster": "range", "importance": 0.91, "size": 51},
        {"_key": "rng-ids", "label": "IDS/IPS Deployment", "type": "security", "cluster": "range", "importance": 0.89, "size": 50},
        {"_key": "rng-endpoints", "label": "Endpoint Configuration", "type": "infrastructure", "cluster": "range", "importance": 0.88, "size": 49},
        {"_key": "rng-servers", "label": "Server Deployment", "type": "infrastructure", "cluster": "range", "importance": 0.92, "size": 52},
        {"_key": "rng-workstations", "label": "Workstation Setup", "type": "infrastructure", "cluster": "range", "importance": 0.87, "size": 48},
        {"_key": "rng-dns", "label": "DNS Configuration", "type": "infrastructure", "cluster": "range", "importance": 0.86, "size": 47},
        {"_key": "rng-logging", "label": "SIEM Integration", "type": "monitoring", "cluster": "range", "importance": 0.93, "size": 53},
        {"_key": "rng-backups", "label": "Backup Systems", "type": "operations", "cluster": "range", "importance": 0.84, "size": 46},
        {"_key": "rng-vpn", "label": "VPN Access", "type": "security", "cluster": "range", "importance": 0.85, "size": 47},
        {"_key": "rng-segmentation", "label": "Network Segmentation", "type": "security", "cluster": "range", "importance": 0.9, "size": 50},
        {"_key": "rng-monitoring", "label": "Network Monitoring", "type": "monitoring", "cluster": "range", "importance": 0.91, "size": 51},
        {"_key": "rng-bastion", "label": "Bastion Hosts", "type": "security", "cluster": "range", "importance": 0.88, "size": 49},
        
        # OPFOR Cluster (18 nodes total)
        {"_key": "opfor-recon", "label": "Reconnaissance Phase", "type": "tactic", "cluster": "opfor", "importance": 0.89, "size": 50},
        {"_key": "opfor-weaponize", "label": "Weaponization", "type": "tactic", "cluster": "opfor", "importance": 0.87, "size": 48},
        {"_key": "opfor-delivery", "label": "Initial Access", "type": "tactic", "cluster": "opfor", "importance": 0.92, "size": 52},
        {"_key": "opfor-exploit", "label": "Exploitation", "type": "tactic", "cluster": "opfor", "importance": 0.91, "size": 51},
        {"_key": "opfor-persistence", "label": "Establish Persistence", "type": "tactic", "cluster": "opfor", "importance": 0.93, "size": 53},
        {"_key": "opfor-privilege", "label": "Privilege Escalation", "type": "tactic", "cluster": "opfor", "importance": 0.94, "size": 54},
        {"_key": "opfor-lateral", "label": "Lateral Movement", "type": "tactic", "cluster": "opfor", "importance": 0.95, "size": 55},
        {"_key": "opfor-discovery", "label": "Internal Discovery", "type": "tactic", "cluster": "opfor", "importance": 0.88, "size": 49},
        {"_key": "opfor-collection", "label": "Data Collection", "type": "tactic", "cluster": "opfor", "importance": 0.9, "size": 50},
        {"_key": "opfor-exfil", "label": "Data Exfiltration", "type": "tactic", "cluster": "opfor", "importance": 0.96, "size": 56},
        {"_key": "opfor-impact", "label": "Impact Operations", "type": "tactic", "cluster": "opfor", "importance": 0.89, "size": 50},
        {"_key": "opfor-c2", "label": "C2 Infrastructure", "type": "infrastructure", "cluster": "opfor", "importance": 0.94, "size": 54},
        {"_key": "opfor-payloads", "label": "Payload Development", "type": "development", "cluster": "opfor", "importance": 0.91, "size": 51},
        {"_key": "opfor-phishing", "label": "Phishing Campaign", "type": "technique", "cluster": "opfor", "importance": 0.87, "size": 48},
        {"_key": "opfor-password", "label": "Credential Harvesting", "type": "technique", "cluster": "opfor", "importance": 0.92, "size": 52},
        {"_key": "opfor-reporting", "label": "OPFOR Reporting", "type": "documentation", "cluster": "opfor", "importance": 0.86, "size": 47},
        {"_key": "opfor-deconflict", "label": "Deconfliction", "type": "coordination", "cluster": "opfor", "importance": 0.88, "size": 49},
        
        # Automation Cluster (14 nodes total)
        {"_key": "auto-ansible", "label": "Ansible Playbooks", "type": "automation", "cluster": "automation", "importance": 0.89, "size": 50},
        {"_key": "auto-terraform", "label": "Terraform IaC", "type": "automation", "cluster": "automation", "importance": 0.91, "size": 51},
        {"_key": "auto-cobalt", "label": "Cobalt Strike Profiles", "type": "tool", "cluster": "automation", "importance": 0.88, "size": 49},
        {"_key": "auto-metasploit", "label": "Metasploit Modules", "type": "tool", "cluster": "automation", "importance": 0.86, "size": 47},
        {"_key": "auto-bloodhound", "label": "BloodHound Collection", "type": "tool", "cluster": "automation", "importance": 0.87, "size": 48},
        {"_key": "auto-powershell", "label": "PowerShell Empire", "type": "tool", "cluster": "automation", "importance": 0.85, "size": 47},
        {"_key": "auto-mimikatz", "label": "Credential Dumping", "type": "technique", "cluster": "automation", "importance": 0.9, "size": 50},
        {"_key": "auto-impacket", "label": "Impacket Suite", "type": "tool", "cluster": "automation", "importance": 0.88, "size": 49},
        {"_key": "auto-responder", "label": "Responder LLMNR", "type": "tool", "cluster": "automation", "importance": 0.84, "size": 46},
        {"_key": "auto-proxychains", "label": "Proxy Configuration", "type": "technique", "cluster": "automation", "importance": 0.82, "size": 45},
        {"_key": "auto-empire", "label": "Empire Framework", "type": "tool", "cluster": "automation", "importance": 0.87, "size": 48},
        {"_key": "auto-logging", "label": "Attack Logging", "type": "monitoring", "cluster": "automation", "importance": 0.91, "size": 51},
        {"_key": "auto-orchestration", "label": "Attack Orchestration", "type": "coordination", "cluster": "automation", "importance": 0.93, "size": 53},
    ]
    
    # Insert extended nodes
    nodes_inserted = 0
    for node in extended_nodes:
        try:
            if not nodes_collection.has(node["_key"]):
                nodes_collection.insert(node)
                nodes_inserted += 1
        except Exception as e:
            print(f"   ⚠️  Skipped {node['_key']}: {e}")
    
    print(f"✓ Inserted {nodes_inserted} new nodes")
    
    # Extended edges - realistic relationships
    extended_edges = [
        # Content Dev relationships
        {"_from": "nodes/cd-threat-intel", "_to": "nodes/cd-apt", "type": "informs", "weight": 0.95},
        {"_from": "nodes/cd-ttps", "_to": "nodes/cd-narrative", "type": "defines", "weight": 0.9},
        {"_from": "nodes/cd-objectives", "_to": "nodes/cd-storyline", "type": "guides", "weight": 0.88},
        {"_from": "nodes/cd-personas", "_to": "nodes/opfor-obj", "type": "defines", "weight": 0.92},
        {"_from": "nodes/cd-mitre", "_to": "nodes/cd-ttps", "type": "references", "weight": 0.94},
        {"_from": "nodes/cd-handbook", "_to": "nodes/cd-briefing", "type": "includes", "weight": 0.87},
        {"_from": "nodes/cd-evaluation", "_to": "nodes/cd-debrief", "type": "uses", "weight": 0.85},
        {"_from": "nodes/cd-ioc", "_to": "nodes/rng-logging", "type": "generates", "weight": 0.91},
        {"_from": "nodes/cd-timeline", "_to": "nodes/opfor-campaign", "type": "defines", "weight": 0.89},
        
        # Range Infrastructure relationships
        {"_from": "nodes/rng-topo", "_to": "nodes/rng-domain", "type": "includes", "weight": 0.93},
        {"_from": "nodes/rng-domain", "_to": "nodes/rng-endpoints", "type": "manages", "weight": 0.91},
        {"_from": "nodes/rng-network", "_to": "nodes/rng-firewall", "type": "secures", "weight": 0.94},
        {"_from": "nodes/rng-firewall", "_to": "nodes/rng-ids", "type": "integrates", "weight": 0.88},
        {"_from": "nodes/rng-servers", "_to": "nodes/rng-workstations", "type": "serves", "weight": 0.86},
        {"_from": "nodes/rng-dns", "_to": "nodes/rng-domain", "type": "resolves", "weight": 0.92},
        {"_from": "nodes/rng-logging", "_to": "nodes/rng-monitoring", "type": "feeds", "weight": 0.95},
        {"_from": "nodes/rng-segmentation", "_to": "nodes/rng-firewall", "type": "enforces", "weight": 0.9},
        {"_from": "nodes/rng-bastion", "_to": "nodes/rng-vpn", "type": "controls", "weight": 0.87},
        {"_from": "nodes/rng-backups", "_to": "nodes/rng-servers", "type": "protects", "weight": 0.84},
        
        # OPFOR Kill Chain relationships
        {"_from": "nodes/opfor-obj", "_to": "nodes/opfor-recon", "type": "starts", "weight": 0.93},
        {"_from": "nodes/opfor-recon", "_to": "nodes/opfor-weaponize", "type": "leads-to", "weight": 0.91},
        {"_from": "nodes/opfor-weaponize", "_to": "nodes/opfor-delivery", "type": "enables", "weight": 0.92},
        {"_from": "nodes/opfor-delivery", "_to": "nodes/opfor-exploit", "type": "triggers", "weight": 0.94},
        {"_from": "nodes/opfor-exploit", "_to": "nodes/opfor-persistence", "type": "establishes", "weight": 0.95},
        {"_from": "nodes/opfor-persistence", "_to": "nodes/opfor-privilege", "type": "enables", "weight": 0.93},
        {"_from": "nodes/opfor-privilege", "_to": "nodes/opfor-lateral", "type": "facilitates", "weight": 0.96},
        {"_from": "nodes/opfor-lateral", "_to": "nodes/opfor-discovery", "type": "includes", "weight": 0.89},
        {"_from": "nodes/opfor-discovery", "_to": "nodes/opfor-collection", "type": "identifies", "weight": 0.91},
        {"_from": "nodes/opfor-collection", "_to": "nodes/opfor-exfil", "type": "prepares", "weight": 0.94},
        {"_from": "nodes/opfor-exfil", "_to": "nodes/opfor-impact", "type": "precedes", "weight": 0.87},
        
        # OPFOR Infrastructure
        {"_from": "nodes/opfor-c2", "_to": "nodes/opfor-persistence", "type": "maintains", "weight": 0.95},
        {"_from": "nodes/opfor-payloads", "_to": "nodes/opfor-delivery", "type": "enables", "weight": 0.93},
        {"_from": "nodes/opfor-phishing", "_to": "nodes/opfor-delivery", "type": "delivers", "weight": 0.91},
        {"_from": "nodes/opfor-password", "_to": "nodes/opfor-privilege", "type": "enables", "weight": 0.92},
        {"_from": "nodes/opfor-live", "_to": "nodes/opfor-reporting", "type": "documents", "weight": 0.88},
        {"_from": "nodes/opfor-deconflict", "_to": "nodes/rng-monitoring", "type": "coordinates", "weight": 0.86},
        
        # Automation relationships
        {"_from": "nodes/auto-terraform", "_to": "nodes/rng-network", "type": "deploys", "weight": 0.93},
        {"_from": "nodes/auto-ansible", "_to": "nodes/rng-endpoints", "type": "configures", "weight": 0.91},
        {"_from": "nodes/auto-sliver", "_to": "nodes/opfor-c2", "type": "provides", "weight": 0.94},
        {"_from": "nodes/auto-cobalt", "_to": "nodes/opfor-c2", "type": "alternative", "weight": 0.88},
        {"_from": "nodes/auto-metasploit", "_to": "nodes/opfor-exploit", "type": "executes", "weight": 0.9},
        {"_from": "nodes/auto-bloodhound", "_to": "nodes/opfor-discovery", "type": "enables", "weight": 0.92},
        {"_from": "nodes/auto-powershell", "_to": "nodes/opfor-lateral", "type": "facilitates", "weight": 0.91},
        {"_from": "nodes/auto-mimikatz", "_to": "nodes/opfor-password", "type": "performs", "weight": 0.93},
        {"_from": "nodes/auto-impacket", "_to": "nodes/opfor-lateral", "type": "enables", "weight": 0.89},
        {"_from": "nodes/auto-responder", "_to": "nodes/opfor-password", "type": "harvests", "weight": 0.87},
        {"_from": "nodes/auto-empire", "_to": "nodes/opfor-c2", "type": "alternative", "weight": 0.86},
        {"_from": "nodes/auto-orchestration", "_to": "nodes/opfor-campaign", "type": "executes", "weight": 0.95},
        {"_from": "nodes/auto-logging", "_to": "nodes/opfor-reporting", "type": "supports", "weight": 0.88},
        
        # Cross-cluster integration
        {"_from": "nodes/cd-narrative", "_to": "nodes/opfor-recon", "type": "defines", "weight": 0.89},
        {"_from": "nodes/rng-domain", "_to": "nodes/opfor-recon", "type": "target", "weight": 0.85},
        {"_from": "nodes/auto-ttp", "_to": "nodes/cd-ttps", "type": "implements", "weight": 0.91},
        {"_from": "nodes/rng-logging", "_to": "nodes/cd-evaluation", "type": "measures", "weight": 0.87},
        {"_from": "nodes/opfor-live", "_to": "nodes/rng-monitoring", "type": "monitored-by", "weight": 0.9},
        {"_from": "nodes/auto-playbook", "_to": "nodes/cd-timeline", "type": "follows", "weight": 0.88},
        {"_from": "nodes/cd-objectives", "_to": "nodes/cd-evaluation", "type": "measured-by", "weight": 0.92},
        {"_from": "nodes/rng-ids", "_to": "nodes/cd-ioc", "type": "detects", "weight": 0.9},
    ]
    
    # Insert extended edges
    edges_inserted = 0
    for edge in extended_edges:
        try:
            edges_collection.insert(edge)
            edges_inserted += 1
        except Exception as e:
            print(f"   ⚠️  Skipped edge: {e}")
    
    print(f"✓ Inserted {edges_inserted} new edges")
    
    # Final stats
    print("\n" + "=" * 60)
    print("✅ Extended dataset added successfully!")
    print("=" * 60)
    
    total_nodes = list(db.aql.execute("RETURN LENGTH(nodes)"))[0]
    total_edges = list(db.aql.execute("RETURN LENGTH(edges)"))[0]
    
    print(f"📊 Total nodes: {total_nodes}")
    print(f"🔗 Total edges: {total_edges}")
    print()
    print("Cluster breakdown:")
    
    cluster_query = """
    FOR node IN nodes
        COLLECT cluster = node.cluster WITH COUNT INTO count
        RETURN {cluster: cluster, count: count}
    """
    clusters = list(db.aql.execute(cluster_query))
    for cluster in clusters:
        print(f"  • {cluster['cluster']}: {cluster['count']} nodes")
    
    print()
    print("🎉 Refresh your ProtoGraph UI to see the new data!")
    print()
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    sys.exit(1)