#!/usr/bin/env python3
"""
Test script for ProtoGraph depth exploration feature
Run this to verify your API endpoints are working correctly
"""

import requests
import json
from typing import Dict, Any

API_BASE = "http://localhost:8000"

def test_api_status() -> bool:
    """Test if API is running"""
    print("\n🧪 Testing API Status...")
    try:
        response = requests.get(f"{API_BASE}/")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API is running: {data['service']}")
            print(f"   Database: {data['database']}")
            print(f"   Graph: {data['graph']}")
            print(f"   Connected: {data['connected']}")
            return data['connected']
        else:
            print(f"❌ API returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Could not connect to {API_BASE}")
        print("   Make sure your backend is running:")
        print("   uvicorn api_service:app --reload")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_full_graph() -> Dict[str, Any]:
    """Test fetching full graph"""
    print("\n🧪 Testing Full Graph Endpoint...")
    try:
        response = requests.get(f"{API_BASE}/graph")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Full graph loaded")
            print(f"   Nodes: {len(data['nodes'])}")
            print(f"   Edges: {len(data['edges'])}")
            
            # Show some node IDs
            if data['nodes']:
                print(f"   Sample nodes:")
                for node in data['nodes'][:3]:
                    print(f"     - {node['id']}: {node['label']}")
            
            return data
        else:
            print(f"❌ Failed to fetch graph: {response.status_code}")
            print(f"   {response.text}")
            return {}
    except Exception as e:
        print(f"❌ Error: {e}")
        return {}


def test_neighbors(node_key: str, depth: int = 1) -> Dict[str, Any]:
    """Test neighbor exploration at specific depth"""
    print(f"\n🧪 Testing Neighbors Endpoint: {node_key} at depth {depth}...")
    try:
        response = requests.get(f"{API_BASE}/neighbors/{node_key}?depth={depth}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Neighbors found")
            print(f"   Center: {data['center']}")
            print(f"   Depth: {data['depth']}")
            print(f"   Total nodes: {data['count']}")
            print(f"   Edges: {len(data['edges'])}")
            
            # Show nodes by distance
            nodes_by_distance = {}
            for node in data['nodes']:
                dist = node.get('distance', 0)
                if dist not in nodes_by_distance:
                    nodes_by_distance[dist] = []
                nodes_by_distance[dist].append(node['label'])
            
            print(f"   Nodes by distance:")
            for dist in sorted(nodes_by_distance.keys()):
                print(f"     Distance {dist}: {len(nodes_by_distance[dist])} nodes")
                if dist <= 1:  # Show details for close nodes
                    for label in nodes_by_distance[dist][:5]:
                        print(f"       - {label}")
            
            return data
        else:
            print(f"❌ Failed to fetch neighbors: {response.status_code}")
            print(f"   {response.text}")
            return {}
    except Exception as e:
        print(f"❌ Error: {e}")
        return {}


def test_depth_comparison(node_key: str):
    """Compare results at different depths"""
    print(f"\n🧪 Testing Depth Comparison for: {node_key}")
    print("=" * 60)
    
    results = {}
    for depth in [1, 2, 3]:
        data = test_neighbors(node_key, depth)
        if data:
            results[depth] = {
                'nodes': data['count'],
                'edges': len(data['edges'])
            }
    
    if results:
        print("\n📊 Depth Comparison:")
        print(f"{'Depth':<10} {'Nodes':<10} {'Edges':<10}")
        print("-" * 30)
        for depth in [1, 2, 3]:
            if depth in results:
                r = results[depth]
                print(f"{depth:<10} {r['nodes']:<10} {r['edges']:<10}")


def test_search(query: str):
    """Test search functionality"""
    print(f"\n🧪 Testing Search: '{query}'...")
    try:
        response = requests.get(f"{API_BASE}/search?q={query}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Search results: {len(data['results'])} matches")
            for result in data['results'][:5]:
                print(f"   - {result['id']}: {result['label']} ({result['cluster']})")
            return data
        else:
            print(f"❌ Search failed: {response.status_code}")
            return {}
    except Exception as e:
        print(f"❌ Error: {e}")
        return {}


def run_all_tests():
    """Run complete test suite"""
    print("\n" + "=" * 60)
    print("🚀 ProtoGraph API Test Suite")
    print("=" * 60)
    
    # Test 1: API Status
    if not test_api_status():
        print("\n❌ Cannot proceed - API is not running")
        return
    
    # Test 2: Full Graph
    graph_data = test_full_graph()
    if not graph_data or not graph_data.get('nodes'):
        print("\n❌ Cannot proceed - No graph data available")
        return
    
    # Get a sample node for testing
    sample_node = graph_data['nodes'][0]
    node_key = sample_node['id'].replace('nodes/', '')
    print(f"\n📝 Using test node: {sample_node['label']} ({node_key})")
    
    # Test 3: Neighbor exploration at different depths
    test_depth_comparison(node_key)
    
    # Test 4: Try with APT29 specifically (if it exists)
    apt_nodes = [n for n in graph_data['nodes'] if 'apt' in n['label'].lower()]
    if apt_nodes:
        apt_key = apt_nodes[0]['id'].replace('nodes/', '')
        print(f"\n📝 Testing with APT node: {apt_nodes[0]['label']} ({apt_key})")
        test_depth_comparison(apt_key)
    
    # Test 5: Search
    test_search("APT")
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ Test Suite Complete!")
    print("=" * 60)
    print("\n💡 Next Steps:")
    print("1. If all tests passed, your backend is working correctly")
    print("2. Check your frontend is connecting to http://localhost:8000")
    print("3. Open browser DevTools to see API calls in action")
    print("4. Double-click nodes in Discovery mode to test depth exploration")
    print("\n📖 See DEPTH_FEATURE_GUIDE.md for detailed usage instructions")


if __name__ == "__main__":
    run_all_tests()