"""
Diagnostic script to troubleshoot ArangoDB API issues
Run this on your machine to identify the problem
"""

import sys
import time

print("🔍 ProtoGraph API Diagnostics")
print("=" * 60)

# Test 1: Check if ArangoDB is accessible
print("\n📊 Test 1: ArangoDB Connection")
print("-" * 60)
try:
    from arango import ArangoClient
    import os
    
    ARANGO_HOST = os.getenv("ARANGO_HOST", "http://localhost:8529")
    ARANGO_USER = os.getenv("ARANGO_USER", "root")
    ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD")
    
    if not ARANGO_PASSWORD:
        print("⚠️  ARANGO_PASSWORD not set in environment")
        ARANGO_PASSWORD = input("Enter ArangoDB password: ")
    
    client = ArangoClient(hosts=ARANGO_HOST)
    db = client.db("protograph", username=ARANGO_USER, password=ARANGO_PASSWORD)
    
    # Try a simple query
    result = list(db.aql.execute("RETURN LENGTH(nodes)"))
    print(f"✅ ArangoDB connected successfully")
    print(f"   Nodes in database: {result[0]}")
    
except Exception as e:
    print(f"❌ ArangoDB connection failed: {e}")
    print("   Make sure ArangoDB is running on port 8529")
    sys.exit(1)

# Test 2: Check if FastAPI imports work
print("\n🚀 Test 2: FastAPI Dependencies")
print("-" * 60)
try:
    import fastapi
    import uvicorn
    from pydantic import BaseModel
    print("✅ All FastAPI dependencies installed")
except ImportError as e:
    print(f"❌ Missing dependency: {e}")
    print("   Run: pip install fastapi uvicorn python-arango python-dotenv")
    sys.exit(1)

# Test 3: Try to start the API
print("\n🌐 Test 3: API Service")
print("-" * 60)
print("Attempting to import api_service...")

try:
    # Try to import the API service
    import api_service
    print("✅ api_service.py imported successfully")
    
    if hasattr(api_service, 'app'):
        print("✅ FastAPI app found")
    else:
        print("❌ FastAPI app not found in api_service.py")
        
except Exception as e:
    print(f"❌ Failed to import api_service: {e}")
    print("\nPossible issues:")
    print("  1. api_service.py has syntax errors")
    print("  2. Missing dependencies")
    print("  3. Database connection failing during import")

# Test 4: Check if port 8000 is in use
print("\n🔌 Test 4: Port Availability")
print("-" * 60)
import socket

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

if is_port_in_use(8000):
    print("✅ Port 8000 is in use (API might be running)")
    print("   Try accessing: http://localhost:8000/")
    print("   Try accessing: http://localhost:8000/graph")
else:
    print("⚠️  Port 8000 is NOT in use")
    print("   The API server is not running")
    print("   Start it with: uvicorn api_service:app --reload")

# Test 5: Make a test request if port is in use
if is_port_in_use(8000):
    print("\n🧪 Test 5: API Request Test")
    print("-" * 60)
    try:
        import requests
        
        # Test root endpoint
        response = requests.get("http://localhost:8000/", timeout=10)
        print(f"✅ Root endpoint: {response.status_code}")
        print(f"   Response: {response.json()}")
        
        # Test graph endpoint
        response = requests.get("http://localhost:8000/graph", timeout=10)
        print(f"✅ Graph endpoint: {response.status_code}")
        data = response.json()
        print(f"   Nodes: {len(data.get('nodes', []))}")
        print(f"   Edges: {len(data.get('edges', []))}")
        
    except requests.exceptions.Timeout:
        print("❌ Request timed out (API is hanging)")
        print("\nPossible causes:")
        print("  1. Database query is taking too long")
        print("  2. Database connection is stuck")
        print("  3. Need to restart the API server")
        
    except Exception as e:
        print(f"❌ Request failed: {e}")

print("\n" + "=" * 60)
print("📝 Summary & Recommendations")
print("=" * 60)

if is_port_in_use(8000):
    print("\n⚠️  API server appears to be running but may be hanging")
    print("\nTry these steps:")
    print("  1. Stop the current API server (Ctrl+C)")
    print("  2. Check for any error messages in the terminal")
    print("  3. Restart: uvicorn api_service:app --reload --timeout-keep-alive 30")
    print("  4. Open http://localhost:8000/graph in browser")
else:
    print("\n✅ Database is working fine")
    print("\n🚀 Start the API server with:")
    print("     uvicorn api_service:app --reload --host 0.0.0.0 --port 8000")