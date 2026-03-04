#!/usr/bin/env python3
"""
ProtoGraph Database Setup - Interactive Version
Prompts for password instead of using .env file
"""

import sys
import getpass
from arango import ArangoClient

print("=" * 60)
print("🚀 ProtoGraph Database Setup")
print("=" * 60)
print()

# Get configuration from user
print("📝 Configuration")
print("-" * 60)

ARANGO_HOST = input("ArangoDB host [http://localhost:8529]: ").strip() or "http://localhost:8529"
ARANGO_USER = input("ArangoDB username [root]: ").strip() or "root"
ARANGO_PASSWORD = getpass.getpass("ArangoDB password: ")
DATABASE_NAME = input("Database name [protograph]: ").strip() or "protograph"
GRAPH_NAME = input("Graph name [protoGraph]: ").strip() or "protoGraph"

print()
print("✓ Configuration received")
print()

def setup_database():
    """Initialize ProtoGraph database structure in ArangoDB"""
    
    try:
        # Connect to ArangoDB
        print("🔌 Connecting to ArangoDB...")
        client = ArangoClient(hosts=ARANGO_HOST)
        sys_db = client.db("_system", username=ARANGO_USER, password=ARANGO_PASSWORD)
        print("✓ Connected successfully")
        
        # Create database if it doesn't exist
        print(f"\n📦 Setting up database: {DATABASE_NAME}")
        if not sys_db.has_database(DATABASE_NAME):
            sys_db.create_database(DATABASE_NAME)
            print(f"✓ Created database: {DATABASE_NAME}")
        else:
            print(f"✓ Database already exists: {DATABASE_NAME}")
        
        # Connect to our database
        db = client.db(DATABASE_NAME, username=ARANGO_USER, password=ARANGO_PASSWORD)
        
        # Create document collection for nodes
        print(f"\n📊 Setting up collections...")
        if not db.has_collection("nodes"):
            nodes_collection = db.create_collection("nodes")
            print("✓ Created collection: nodes")
        else:
            nodes_collection = db.collection("nodes")
            print("✓ Collection already exists: nodes")
        
        # Create edge collection for relationships
        if not db.has_collection("edges"):
            edges_collection = db.create_collection("edges", edge=True)
            print("✓ Created edge collection: edges")
        else:
            edges_collection = db.collection("edges")
            print("✓ Edge collection already exists: edges")
        
        # Create graph definition
        print(f"\n🕸️  Setting up graph: {GRAPH_NAME}")
        if not db.has_graph(GRAPH_NAME):
            graph = db.create_graph(GRAPH_NAME)
            
            # Define edge definition
            graph.create_edge_definition(
                edge_collection="edges",
                from_vertex_collections=["nodes"],
                to_vertex_collections=["nodes"]
            )
            print(f"✓ Created graph: {GRAPH_NAME}")
        else:
            graph = db.graph(GRAPH_NAME)
            print(f"✓ Graph already exists: {GRAPH_NAME}")
        
        # Create indexes for performance
        print(f"\n⚡ Creating indexes...")
        if not any(idx["fields"] == ["cluster"] for idx in nodes_collection.indexes()):
            nodes_collection.add_hash_index(fields=["cluster"])
            print("✓ Created cluster index on nodes")
        else:
            print("✓ Cluster index already exists")
        
        if not any(idx["fields"] == ["type"] for idx in nodes_collection.indexes()):
            nodes_collection.add_hash_index(fields=["type"])
            print("✓ Created type index on nodes")
        else:
            print("✓ Type index already exists")
        
        if not any(idx["fields"] == ["importance"] for idx in nodes_collection.indexes()):
            nodes_collection.add_skiplist_index(fields=["importance"])
            print("✓ Created importance index on nodes")
        else:
            print("✓ Importance index already exists")
        
        return db, graph
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


def insert_sample_data(db):
    """Insert sample ProtoGraph data"""
    
    nodes_collection = db.collection("nodes")
    edges_collection = db.collection("edges")
    
    print(f"\n📥 Inserting sample data...")
    
    # Sample nodes (matching your domain)
    sample_nodes = [
        {
            "_key": "cd-dlo",
            "label": "DLO Requirements",
            "type": "requirement",
            "cluster": "content_dev",
            "importance": 0.95,
            "size": 55
        },
        {
            "_key": "cd-apt",
            "label": "APT Profile (APT29)",
            "type": "profile",
            "cluster": "content_dev",
            "importance": 0.9,
            "size": 50
        },
        {
            "_key": "cd-narrative",
            "label": "Scenario Narrative",
            "type": "design",
            "cluster": "content_dev",
            "importance": 0.85,
            "size": 48
        },
        {
            "_key": "rng-topo",
            "label": "Network Topology",
            "type": "infrastructure",
            "cluster": "range",
            "importance": 0.9,
            "size": 50
        },
        {
            "_key": "rng-network",
            "label": "Network Build",
            "type": "infrastructure",
            "cluster": "range",
            "importance": 0.9,
            "size": 50
        },
        {
            "_key": "opfor-obj",
            "label": "Adversarial Objectives",
            "type": "planning",
            "cluster": "opfor",
            "importance": 0.9,
            "size": 50
        },
        {
            "_key": "opfor-campaign",
            "label": "Campaign Plan",
            "type": "planning",
            "cluster": "opfor",
            "importance": 0.9,
            "size": 50
        },
        {
            "_key": "opfor-live",
            "label": "Live Range Execution",
            "type": "execution",
            "cluster": "opfor",
            "importance": 0.95,
            "size": 55
        },
        {
            "_key": "auto-sliver",
            "label": "Sliver C2 Library",
            "type": "development",
            "cluster": "automation",
            "importance": 0.85,
            "size": 48
        },
        {
            "_key": "auto-ttp",
            "label": "TTP Automation Scripts",
            "type": "script",
            "cluster": "automation",
            "importance": 0.9,
            "size": 50
        },
        {
            "_key": "auto-playbook",
            "label": "Attack Playbook",
            "type": "delivery",
            "cluster": "automation",
            "importance": 0.9,
            "size": 50
        }
    ]
    
    # Insert nodes
    nodes_inserted = 0
    for node in sample_nodes:
        if not nodes_collection.has(node["_key"]):
            nodes_collection.insert(node)
            nodes_inserted += 1
    
    print(f"✓ Inserted {nodes_inserted} nodes")
    
    # Sample edges (relationships)
    sample_edges = [
        {"_from": "nodes/cd-dlo", "_to": "nodes/cd-apt", "type": "defines", "weight": 0.9},
        {"_from": "nodes/cd-apt", "_to": "nodes/cd-narrative", "type": "informs", "weight": 0.9},
        {"_from": "nodes/cd-narrative", "_to": "nodes/rng-topo", "type": "requires", "weight": 0.9},
        {"_from": "nodes/rng-topo", "_to": "nodes/rng-network", "type": "defines", "weight": 0.95},
        {"_from": "nodes/cd-apt", "_to": "nodes/opfor-obj", "type": "defines", "weight": 0.95},
        {"_from": "nodes/opfor-obj", "_to": "nodes/opfor-campaign", "type": "drives", "weight": 0.9},
        {"_from": "nodes/opfor-campaign", "_to": "nodes/opfor-live", "type": "executes", "weight": 0.95},
        {"_from": "nodes/auto-sliver", "_to": "nodes/auto-ttp", "type": "enables", "weight": 0.85},
        {"_from": "nodes/auto-ttp", "_to": "nodes/auto-playbook", "type": "finalizes", "weight": 0.9},
        {"_from": "nodes/auto-playbook", "_to": "nodes/opfor-live", "type": "enables", "weight": 0.95}
    ]
    
    # Insert edges
    edges_inserted = 0
    for edge in sample_edges:
        edges_collection.insert(edge)
        edges_inserted += 1
    
    print(f"✓ Inserted {edges_inserted} edges")


def test_queries(db):
    """Test some basic AQL queries"""
    
    print(f"\n🧪 Testing queries...")
    
    # Query 1: Count nodes
    query1 = "RETURN LENGTH(nodes)"
    result = list(db.aql.execute(query1))
    print(f"✓ Total nodes: {result[0]}")
    
    # Query 2: Count edges
    query2 = "RETURN LENGTH(edges)"
    result = list(db.aql.execute(query2))
    print(f"✓ Total edges: {result[0]}")
    
    # Query 3: Get clusters
    query3 = """
    FOR node IN nodes
        COLLECT cluster = node.cluster WITH COUNT INTO count
        RETURN {cluster: cluster, count: count}
    """
    result = list(db.aql.execute(query3))
    print(f"✓ Clusters found:")
    for cluster in result:
        print(f"  • {cluster['cluster']}: {cluster['count']} nodes")


if __name__ == "__main__":
    try:
        print("=" * 60)
        print("SETUP PROCESS")
        print("=" * 60)
        
        # Setup database structure
        db, graph = setup_database()
        
        # Ask if user wants to insert sample data
        print()
        response = input("Insert sample data? [Y/n]: ").strip().lower()
        if response != 'n':
            insert_sample_data(db)
            test_queries(db)
        
        print()
        print("=" * 60)
        print("✅ ProtoGraph database setup complete!")
        print("=" * 60)
        print(f"📊 Database: {DATABASE_NAME}")
        print(f"🕸️  Graph: {GRAPH_NAME}")
        print(f"🔗 Web UI: {ARANGO_HOST}")
        print()
        print("Next steps:")
        print("  1. Start the API: uvicorn api_service:app --reload")
        print("  2. Test the API: curl http://localhost:8000/graph")
        print("  3. Update your frontend code (see FRONTEND_MIGRATION_GUIDE.md)")
        print()
        
    except KeyboardInterrupt:
        print("\n\n❌ Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        sys.exit(1)