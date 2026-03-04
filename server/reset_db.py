#!/usr/bin/env python3
"""
ProtoGraph Safe Reset - Clear Artifacts, Keep Ontology
Removes ingested data while preserving ontology structure (concepts, taxonomies, relationships)
"""

import sys
import getpass
from arango import ArangoClient
from datetime import datetime

print("=" * 60)
print("🧹 ProtoGraph Safe Reset")
print("   Clear artifacts, preserve ontology")
print("=" * 60)
print()

# Get configuration from user
print("📝 Configuration")
print("-" * 60)

ARANGO_HOST = input("ArangoDB host [http://localhost:8529]: ").strip() or "http://localhost:8529"
ARANGO_USER = input("ArangoDB username [root]: ").strip() or "root"
ARANGO_PASSWORD = getpass.getpass("ArangoDB password: ")
DATABASE_NAME = input("Database name [protograph]: ").strip() or "protograph"

print()
print("✓ Configuration received")
print()

# Collections to PRESERVE (ontology structure)
PROTECTED_COLLECTIONS = [
    '_ontology_concepts',
    '_ontology_edges', 
    '_taxonomies',
    '_taxonomy_terms',
    '_ontology_relationship_types',
]

# System collections (always protected)
SYSTEM_PREFIXES = ['_system', '_aqlfunctions', '_graphs', '_jobs']

def is_protected(collection_name: str) -> bool:
    """Check if a collection should be protected from deletion"""
    # Protect ontology collections
    if collection_name in PROTECTED_COLLECTIONS:
        return True
    # Protect ArangoDB system collections
    if collection_name.startswith('_') and collection_name not in PROTECTED_COLLECTIONS:
        # Allow clearing of edge collections that start with _ but aren't ontology
        if collection_name in ['_ontology_edges']:
            return True
        return True
    return False

def safe_reset():
    """Reset artifact data while preserving ontology"""
    
    try:
        # Connect to ArangoDB
        print("🔌 Connecting to ArangoDB...")
        client = ArangoClient(hosts=ARANGO_HOST)
        
        # Check if database exists
        sys_db = client.db("_system", username=ARANGO_USER, password=ARANGO_PASSWORD)
        if not sys_db.has_database(DATABASE_NAME):
            print(f"❌ Database '{DATABASE_NAME}' does not exist!")
            sys.exit(1)
        
        db = client.db(DATABASE_NAME, username=ARANGO_USER, password=ARANGO_PASSWORD)
        print(f"✓ Connected to database: {DATABASE_NAME}")
        
        # Get all collections
        all_collections = db.collections()
        
        # Categorize collections
        protected = []
        artifact_collections = []
        edge_collections = []
        
        for coll in all_collections:
            name = coll['name']
            is_edge = coll.get('type') == 3  # Edge collection type
            
            if is_protected(name):
                protected.append(name)
            elif is_edge and not name.startswith('_'):
                edge_collections.append(name)
            elif not name.startswith('_'):
                artifact_collections.append(name)
        
        # Display what will happen
        print()
        print("=" * 60)
        print("📋 RESET PLAN")
        print("=" * 60)
        print()
        print("🛡️  PROTECTED (will NOT be touched):")
        for name in sorted(protected):
            coll = db.collection(name)
            count = coll.count()
            print(f"   • {name} ({count} documents)")
        
        print()
        print("🗑️  ARTIFACT COLLECTIONS (will be EMPTIED):")
        total_artifacts = 0
        for name in sorted(artifact_collections):
            coll = db.collection(name)
            count = coll.count()
            total_artifacts += count
            print(f"   • {name} ({count} documents)")
        
        if not artifact_collections:
            print("   (none found)")
        
        print()
        print("🔗 EDGE COLLECTIONS (will be EMPTIED):")
        total_edges = 0
        for name in sorted(edge_collections):
            coll = db.collection(name)
            count = coll.count()
            total_edges += count
            print(f"   • {name} ({count} edges)")
        
        if not edge_collections:
            print("   (none found)")
        
        print()
        print(f"📊 Summary: {total_artifacts} artifacts + {total_edges} edges will be deleted")
        print(f"           {len(protected)} collections will be preserved")
        print()
        
        # Confirmation
        print("⚠️  WARNING: This action cannot be undone!")
        confirm = input("Proceed with safe reset? [y/N]: ").strip().lower()
        if confirm != 'y':
            print("❌ Reset cancelled")
            sys.exit(0)
        
        print()
        print("=" * 60)
        print("🧹 EXECUTING SAFE RESET")
        print("=" * 60)
        print()
        
        # Clear artifact collections (truncate, don't delete)
        print("📄 Clearing artifact collections...")
        for name in artifact_collections:
            try:
                coll = db.collection(name)
                count_before = coll.count()
                coll.truncate()
                print(f"   ✓ {name}: cleared {count_before} documents")
            except Exception as e:
                print(f"   ⚠️  {name}: {e}")
        
        # Clear edge collections
        print()
        print("🔗 Clearing edge collections...")
        for name in edge_collections:
            try:
                coll = db.collection(name)
                count_before = coll.count()
                coll.truncate()
                print(f"   ✓ {name}: cleared {count_before} edges")
            except Exception as e:
                print(f"   ⚠️  {name}: {e}")
        
        # Verify ontology is intact
        print()
        print("🔍 Verifying ontology integrity...")
        
        ontology_ok = True
        for name in PROTECTED_COLLECTIONS:
            if db.has_collection(name):
                coll = db.collection(name)
                count = coll.count()
                print(f"   ✓ {name}: {count} documents (intact)")
                if count == 0 and name in ['_ontology_concepts', '_taxonomies']:
                    print(f"      ⚠️  Warning: {name} is empty!")
            else:
                print(f"   ℹ️  {name}: collection doesn't exist")
        
        return db
        
    except Exception as e:
        print(f"\n❌ Error during reset: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def show_ontology_summary(db):
    """Display summary of preserved ontology"""
    
    print()
    print("=" * 60)
    print("📊 ONTOLOGY SUMMARY (Preserved)")
    print("=" * 60)
    
    # Concepts
    if db.has_collection('_ontology_concepts'):
        concepts = list(db.aql.execute("""
            FOR c IN _ontology_concepts
            FILTER c.abstract != true
            RETURN {label: c.label, collection: c.collection}
        """))
        print(f"\n📦 Artifact Types ({len(concepts)} concrete concepts):")
        for c in concepts:
            print(f"   • {c['label']} → {c.get('collection', 'N/A')}")
    
    # Taxonomies
    if db.has_collection('_taxonomies'):
        taxonomies = list(db.aql.execute("""
            FOR t IN _taxonomies
            RETURN {id: t.taxonomy_id, name: t.name}
        """))
        print(f"\n🏷️  Taxonomies ({len(taxonomies)}):")
        for t in taxonomies:
            # Count terms
            term_count = list(db.aql.execute("""
                FOR term IN _taxonomy_terms
                FILTER term.taxonomy_id == @tax_id
                RETURN 1
            """, bind_vars={'tax_id': t['id']}))
            print(f"   • {t['name']} ({len(term_count)} terms)")
    
    # Relationship types
    if db.has_collection('_ontology_relationship_types'):
        rel_types = list(db.aql.execute("""
            FOR r IN _ontology_relationship_types
            RETURN r.label
        """))
        print(f"\n🔗 Relationship Types ({len(rel_types)}):")
        for r in rel_types:
            print(f"   • {r}")


def optional_seed_data(db):
    """Optionally insert minimal seed data for testing"""
    
    print()
    response = input("Insert sample test data? [y/N]: ").strip().lower()
    if response != 'y':
        return
    
    print()
    print("📥 Inserting sample data...")
    
    # Get concrete concepts to know what collections exist
    concepts = list(db.aql.execute("""
        FOR c IN _ontology_concepts
        FILTER c.abstract != true AND c.collection != null
        RETURN {label: c.label, collection: c.collection}
    """))
    
    collection_map = {c['label']: c['collection'] for c in concepts}
    
    # Insert a sample Library Module if that type exists
    if 'Library Module' in collection_map:
        coll_name = collection_map['Library Module']
        if db.has_collection(coll_name):
            coll = db.collection(coll_name)
            sample = {
                "_key": "sample_mimikatz",
                "id": "sample_mimikatz",
                "name": "Mimikatz Credential Dump",
                "description": "Sample module for credential dumping using Mimikatz",
                "category": "Cobalt Strike",
                "tactic": "TA0006",
                "technique": "T1003.001",
                "owner": "OPFOR",
                "riskLevel": "High",
                "_artifact_type": "Library Module",
                "_ingested_at": datetime.now().isoformat()
            }
            try:
                coll.insert(sample)
                print(f"   ✓ Inserted sample Library Module")
            except Exception as e:
                print(f"   ⚠️  Could not insert sample: {e}")
    
    # Insert a sample Development Story if that type exists
    if 'Development Story' in collection_map:
        coll_name = collection_map['Development Story']
        if db.has_collection(coll_name):
            coll = db.collection(coll_name)
            sample = {
                "_key": "sample_story_001",
                "id": "sample_story_001",
                "title": "Implement Kerberoasting Module",
                "description": "Build a new module for Kerberoasting attacks",
                "status": "Backlog",
                "priority": "High",
                "sprint": "Sprint 25",
                "assigned_to": "Kane Pickrel",
                "_artifact_type": "Development Story",
                "_ingested_at": datetime.now().isoformat()
            }
            try:
                coll.insert(sample)
                print(f"   ✓ Inserted sample Development Story")
            except Exception as e:
                print(f"   ⚠️  Could not insert sample: {e}")
    
    print("   Done!")


if __name__ == "__main__":
    try:
        # Run safe reset
        db = safe_reset()
        
        # Show ontology summary
        show_ontology_summary(db)
        
        # Optional seed data
        optional_seed_data(db)
        
        print()
        print("=" * 60)
        print("✅ Safe reset complete!")
        print("=" * 60)
        print()
        print("Your ontology (concepts, taxonomies, relationships) is intact.")
        print("All artifact data has been cleared.")
        print()
        print("📋 Next steps:")
        print("  1. Restart the API server: python main.py")
        print("  2. Use the Ingest button to add new data")
        print("  3. Data will be validated against your existing ontology")
        print()
        
    except KeyboardInterrupt:
        print("\n\n❌ Reset cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)