#!/usr/bin/env python3
"""
Insert sample data into ProtoGraph database
"""

import getpass
from arango import ArangoClient
from datetime import datetime

print("🔐 Enter ArangoDB credentials")
ARANGO_HOST = input("Host [http://localhost:8529]: ").strip() or "http://localhost:8529"
ARANGO_USER = input("Username [root]: ").strip() or "root"
ARANGO_PASSWORD = getpass.getpass("Password: ")
DATABASE_NAME = input("Database [DB_318]: ").strip() or "DB_318"

print("\n🔌 Connecting...")
client = ArangoClient(hosts=ARANGO_HOST)
db = client.db(DATABASE_NAME, username=ARANGO_USER, password=ARANGO_PASSWORD)
print("✓ Connected\n")

# Create document collections
print("📦 Creating document collections...")
doc_collections = ['Playbook', 'Script', 'Runbook', 'TestPlan', 'PolicyDocument']

for coll_name in doc_collections:
    if not db.has_collection(coll_name):
        db.create_collection(coll_name)
        print(f"  ✓ Created {coll_name}")
    else:
        print(f"  ✓ {coll_name} exists")

# Insert sample Playbook
print("\n📥 Inserting sample data...")
playbooks = db.collection('Playbook')

sample_playbook = {
    "_key": "sample_obap_playbook",
    "name": "OBAP Attack Playbook",
    "type": "Playbook",
    "cluster": "automation",
    "collaboration_with": ["Automation", "OPFOR"],
    "description": "Automated playbook for OBAP scenario execution",
    "canonical_theme": "Adversarial Emulation",
    "themes": ["C2", "Persistence", "Lateral Movement"],
    "categories": ["Offensive", "Automation"],
    "tags": ["obap", "sliver", "c2", "apt"],
    "source_filename": "OBAP_Playbook.pdf",
    "ingested_at": datetime.now().isoformat(),
    "confidence": 0.95,
    "importance": 0.9
}

if playbooks.has("sample_obap_playbook"):
    playbooks.update(sample_playbook)
    print("  ✓ Updated sample Playbook")
else:
    playbooks.insert(sample_playbook)
    print("  ✓ Inserted sample Playbook")

# Insert sample Script
scripts = db.collection('Script')

sample_script = {
    "_key": "sample_sliver_setup",
    "name": "Sliver C2 Setup Script",
    "type": "Script",
    "cluster": "automation",
    "collaboration_with": ["Automation"],
    "description": "Automated setup for Sliver C2 infrastructure",
    "canonical_theme": "Infrastructure Setup",
    "themes": ["C2", "Infrastructure", "Automation"],
    "categories": ["Setup", "C2"],
    "tags": ["sliver", "c2", "setup", "automation"],
    "source_filename": "sliver_setup.py",
    "ingested_at": datetime.now().isoformat(),
    "confidence": 0.92,
    "importance": 0.85
}

if scripts.has("sample_sliver_setup"):
    scripts.update(sample_script)
    print("  ✓ Updated sample Script")
else:
    scripts.insert(sample_script)
    print("  ✓ Inserted sample Script")

# Insert sample edge
print("\n🔗 Inserting sample edge...")
references = db.collection('REFERENCES')

sample_edge = {
    "_key": "playbook_to_script",
    "_from": "Playbook/sample_obap_playbook",
    "_to": "Script/sample_sliver_setup",
    "relationship_type": "REFERENCES",
    "weight": 0.9,
    "confidence": 9,
    "discovered_by": "manual_sample",
    "discovered_at": datetime.now().isoformat(),
    "explanation": "OBAP playbook references Sliver setup script for C2 initialization"
}

if references.has("playbook_to_script"):
    references.update(sample_edge)
    print("  ✓ Updated sample edge")
else:
    references.insert(sample_edge)
    print("  ✓ Inserted sample edge")

# Verify
print("\n🔍 Verification:")
print(f"  Playbook count: {playbooks.count()}")
print(f"  Script count: {scripts.count()}")
print(f"  REFERENCES count: {references.count()}")

print("\n✅ Sample data inserted successfully!")
print(f"\n🚀 Test it:")
print(f"   curl http://localhost:8000/graph")