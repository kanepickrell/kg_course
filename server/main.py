#!/usr/bin/env python3
"""
Unified ProtoGraph API
Integrates:
 - ArangoDB graph data
 - Ollama conversational AI
 - Power BI streaming analytics
 - Enhanced Search Functionality
 - Prospector Mode (Manual Graph Refinement)
 - JSON-based Connection Review (file-driven)
"""

import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from arango import ArangoClient
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from enum import Enum
import ollama

from analytics import calculate_team_coupling
from powerbi_stream import push_to_powerbi_stream
from ingestion_endpoint import router as ingest_router
from schema_registry import router as schema_router
from plugins.endpoints import router as plugin_router
from plugins.operator_plugin import operator_plugin 
from plugins.plugin_router import create_plugin_data_router
from neural_arango_integration import NeuralGraphRouter, create_neural_router_endpoints
from unified_search import create_unified_search_router
from neural_experiment_api import create_neural_experiment_router
from hybrid_cluster_router import HybridClusterRouter, create_hybrid_router_endpoints


from discovery_engine import (
    DiscoveryOrchestrator, 
    GraphHealthReport,
    DiscoveryTriggerResult
)

from pipeline_engine import PipelineEngine
from pipeline_router import create_pipeline_router

import ontology_api


# =====================================================
# ENVIRONMENT SETUP
# =====================================================
load_dotenv()

ARANGO_HOST = os.getenv("ARANGO_HOST", "http://localhost:8529")
ARANGO_USER = os.getenv("ARANGO_USER", "root")
ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD", "")
ARANGO_DB = os.getenv("ARANGO_DB", "AUTO_DB")
ARANGO_GRAPH = os.getenv("ARANGO_GRAPH", "protograph_kg")

# GraphDB Configuration (Primary backend)
GRAPHDB_ENABLED = os.getenv("GRAPHDB_ENABLED", "true").lower() == "true"
GRAPHDB_ENDPOINT = os.getenv("GRAPHDB_ENDPOINT", "http://localhost:7200")
GRAPHDB_REPO = os.getenv("GRAPHDB_REPO", "atlas")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://10.10.80.99:4001")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:120b")

JSON_PATH = "llm_edge_suggestions.json"

SCHEMA_COLLECTIONS = {
    'ontology_concepts', 'concepts', 'ontology_taxonomies', 
    'taxonomy_schemes', 'taxonomy_terms', 'taxonomies',
    'ontology_relationships', 'ontology_edges', 'relationship_types',
    'ontology_properties', 'schema_definitions',
}


# =====================================================
# FASTAPI APP
# =====================================================
app = FastAPI(
    title="ProtoGraph Unified API",
    description="ArangoDB + Ollama + Power BI integration backend with JSON-based Connection Review",
    version="4.0.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================================================
# DATABASE CONNECTION
# =====================================================
db = None
pipeline_engine = None  

if not GRAPHDB_ENABLED:
    # Only connect to ArangoDB if GraphDB is disabled
    try:
        client = ArangoClient(hosts=ARANGO_HOST)
        db = client.db(ARANGO_DB, username=ARANGO_USER, password=ARANGO_PASSWORD)
        db.collections()
        print(f"✓ Connected to ArangoDB: {ARANGO_DB}")
        
        import ingestion_endpoint
        import schema_registry
        ingestion_endpoint.db = db
        schema_registry.db = db
        ingestion_endpoint.init_ingestion(db)

        if db:
            try:
                pipeline_engine = PipelineEngine(db, payload_base_dir="./data/payloads")
                print(f"✓ Pipeline engine initialized")
            except Exception as e:
                print(f"⚠️ Pipeline engine failed: {e}")
                pipeline_engine = None
        
    except Exception as e:
        print(f"⚠️ ArangoDB not available: {e}")
        db = None
else:
    print(f"ℹ️ ArangoDB skipped — GraphDB is primary backend")

# =====================================================
# GRAPHDB CONNECTION (Phase 2 - alongside ArangoDB)
# =====================================================
gdb = None
if GRAPHDB_ENABLED:
    try:
        from graph_db import GraphDBAdapter
        gdb = GraphDBAdapter(endpoint=GRAPHDB_ENDPOINT, repo=GRAPHDB_REPO)
        health = gdb.health()
        if health["status"] == "connected":
            print(f"✓ GraphDB connected: {GRAPHDB_ENDPOINT}/repositories/{GRAPHDB_REPO}")
            print(f"  → {health.get('total_triples', '?')} triples, types: {health.get('artifact_counts', {})}")

            # Initialize GraphDB-native ingestion
            try:
                from ingestion_core import init_ingestion_core, router as ingest_core_router
                init_ingestion_core(gdb)
                app.include_router(ingest_core_router)
                print(f"✓ Ingestion core (GraphDB) loaded")
            except Exception as e:
                print(f"⚠️ Ingestion core init failed: {e}")
        else:
            print(f"⚠️ GraphDB connection unhealthy: {health.get('error', 'unknown')}")
            gdb = None
    except ImportError:
        print(f"⚠️ GraphDB enabled but graph_db.py not found — falling back to ArangoDB")
        gdb = None
    except Exception as e:
        print(f"⚠️ GraphDB initialization failed: {e} — falling back to ArangoDB")
        gdb = None
else:
    print(f"ℹ️ GraphDB disabled (set GRAPHDB_ENABLED=true to enable)")

# =====================================================
# OLLAMA CONFIGURATION
# =====================================================
ollama_client = None  # Initialize to None first

try:
    ollama_client = ollama.Client(host=OLLAMA_HOST)
    print(f"✓ Ollama connected: {OLLAMA_HOST}")
except TypeError:
    try:
        ollama_client = ollama
        ollama_client.list()
        print(f"✓ Ollama connected (legacy mode): {OLLAMA_HOST}")
    except Exception as fallback_error:
        print(f"⚠️ Ollama not available: {fallback_error}")
        ollama_client = None
except Exception as e:
    print(f"⚠️ Ollama not available: {e}")
    ollama_client = None

# =====================================================
# DISCOVERY ENGINE INITIALIZATION
# =====================================================
discovery_orchestrator = None
if db and ollama_client:
    try:
        discovery_orchestrator = DiscoveryOrchestrator(db, ollama_client)
        print(f"✓ Discovery orchestrator initialized")
    except Exception as e:
        print(f"⚠️ Discovery orchestrator failed: {e}")
        discovery_orchestrator = None
elif db:
    try:
        discovery_orchestrator = DiscoveryOrchestrator(db, None)
        print(f"✓ Discovery orchestrator initialized (health-only, no LLM)")
    except Exception as e:
        print(f"⚠️ Discovery orchestrator failed: {e}")
        discovery_orchestrator = None

# Inject into ingestion endpoint (ONLY HERE, after it's defined)
if discovery_orchestrator:
    ingestion_endpoint.discovery_orchestrator = discovery_orchestrator


# =====================================================
# ONTOLOGY API (ArangoDB fallback — only if no GraphDB)
# =====================================================
if db:
    ontology_api.db = db
    ontology_api.init_collections()
else:
    print(f"ℹ️ ArangoDB ontology API skipped (no connection)")


# =====================================================
# MODELS
# =====================================================
class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = None


# Prospector Mode Models
class CreateNodeRequest(BaseModel):
    label: str
    type: str
    cluster: str
    description: Optional[str] = None
    tags: Optional[List[str]] = []
    custom_fields: Optional[Dict[str, Any]] = {}


class UpdateNodeRequest(BaseModel):
    node_id: str
    label: Optional[str] = None
    type: Optional[str] = None
    cluster: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[Dict[str, Any]] = None


class CreateEdgeRequest(BaseModel):
    from_node: str  # format: "collection/key"
    to_node: str    # format: "collection/key"
    relationship_type: str
    weight: float = 1.0
    bidirectional: bool = False
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}


# =====================================================
# LIBRARY MODULE MODELS
# =====================================================
class LibraryModuleFilter(BaseModel):
    """Filter criteria for library module search"""
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tactic: Optional[str] = None
    execution_type: Optional[str] = None
    risk_level: Optional[str] = None
    tags: Optional[List[str]] = None
    search_text: Optional[str] = None

class ExecutionEnvironment(BaseModel):
    """Current execution environment state for validation"""
    has_c2_server: bool = False
    active_listeners: List[str] = []
    active_beacons: List[str] = []
    ssh_connections: List[str] = []
    available_payloads: List[str] = []
    external_tools: List[str] = []
    installed_libraries: List[str] = []


# =====================================================
# JSON REVIEW WORKFLOW MODELS
# =====================================================
class JSONUserReview(BaseModel):
    """Review decision from ConnectionReviewModal"""
    connectionId: str  # Changed from index to match frontend
    decision: str  # "approve" | "reject" | "modify"
    correctedRelationship: Optional[str] = None  # For modify decisions
    feedback: Optional[str] = None
    reviewedAt: str  # ISO timestamp
    reviewedBy: str  # User identifier


# =====================================================
# JSON UTILITIES
# =====================================================
def load_json():
    if not os.path.exists(JSON_PATH):
        return {"part1_responses": []}
    
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()
            
            # Handle empty file
            if not content:
                return {"part1_responses": []}
            
            data = json.loads(content)
            
            # Handle both formats: list or object with part1_responses
            if isinstance(data, list):
                return {"part1_responses": data}
            elif isinstance(data, dict) and "part1_responses" in data:
                return data
            else:
                return {"part1_responses": []}
                
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error in {JSON_PATH}: {e}")
        return {"part1_responses": []}
    except Exception as e:
        print(f"❌ Error loading {JSON_PATH}: {e}")
        return {"part1_responses": []}


def save_json(data):
    with open(JSON_PATH, "w") as f:
        json.dump(data, f, indent=2)


# =====================================================
# ROOT
# =====================================================
@app.get("/")
def root():
    return {
        "service": "ProtoGraph Unified API (JSON Review Mode)",
        "status": "running",
        "database": ARANGO_DB,
        "ollama_model": OLLAMA_MODEL,
        "endpoints": [
            "/graph",
            "/neighbors?node_id={node_id}&depth={depth}",
            "/search?q=",
            "/api/search/smart?q=",
            "/api/search/advanced?q=",
            "/chat",
            "/analytics/team-coupling-table",
            "/analytics/update-powerbi",
            "/analytics/notify-update",
            "/debug/edges",
            "/explore-db",
            "/health",
            # Prospector Mode endpoints
            "/prospector/node",
            "/prospector/edge",
            "/prospector/validate-nodes",
            "/prospector/bulk/nodes",
            # JSON-based Connection Review endpoints
            "/connections/pending",
            "/connections/review",
            "/connections/stats",
            "/api/artifact/{id}",
            "/api/ingest/analyze",
            "/api/ingest/commit",
            "/api/schemas/types",
            "/api/plugins",             
            "/api/plugins/{id}/data",    
        ],
    }


@app.get("/debug/edges")
def debug_edges():
    """Debug edge collections to see what's actually connected"""
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    try:
        # edge_collections = ['CONTAINS', 'PRODUCES', 'REFERENCES', 'LEADS_TO', 'STARTS_WITH']
        edge_collections = ['CONTAINS', 'PRODUCES', 'REFERENCES', 'LEADS_TO', 'STARTS_WITH', 'COLLABORATION_WITH']                                                                                                
        result = {}
        
        for edge_coll in edge_collections:
            try:
                coll = db.collection(edge_coll)
                count = coll.count()
                samples = list(coll.all(limit=5))
                result[edge_coll] = {
                    "count": count,
                    "samples": samples
                }
            except Exception as e:
                result[edge_coll] = {"error": str(e)}
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# DATABASE EXPLORATION
# =====================================================
@app.get("/explore-db")
def explore_db():
    """See what collections and graphs exist"""
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    try:
        collections = [c['name'] for c in db.collections() if not c['name'].startswith('_')]
        graphs = [g['name'] for g in db.graphs()]
        
        # Sample a document from each collection
        samples = {}
        for coll_name in collections[:5]:  # First 5 collections
            coll = db.collection(coll_name)
            sample = list(coll.all(limit=1))
            samples[coll_name] = sample[0] if sample else None
        
        return {
            "collections": collections,
            "graphs": graphs,
            "samples": samples
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# GRAPH ENDPOINTS
# =====================================================
@app.get("/graph")
def get_graph(include_schema: bool = False):
    """Fetch all artifact nodes and relationship edges from ArangoDB
    
    Args:
        include_schema: If True, include ontology/schema nodes. Default False.
    
    Returns nodes with:
        - type: Human-readable artifact type (from _artifact_type or collection name)
        - cluster: Team ownership (from owner, assigned_to, or inferred from collaboration_with)
    """
    # =====================================================
    # GRAPHDB PATH (Phase 2)
    # =====================================================
    if gdb:
        try:
            result = gdb.get_full_graph(include_schema=include_schema)
            print(f"✅ [GraphDB] Returning {result['count']} nodes and {len(result['edges'])} edges")
            return result
        except Exception as e:
            print(f"⚠️ [GraphDB] Failed, falling back to ArangoDB: {e}")
            # Fall through to ArangoDB path

    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")

    try:
        # =====================================================
        # DYNAMIC EDGE COLLECTION DISCOVERY (THE FIX!)
        # =====================================================
        # Discover edge collections from ArangoDB metadata
        # This ensures newly created collections like RELATED_TO are found
        
        all_collections_info = list(db.collections())
        all_collection_names = [c['name'] for c in all_collections_info if not c['name'].startswith('_')]
        
        edge_collections = set()
        
        # Method 1: Query ArangoDB for all edge collections (type=3)
        for coll_name in all_collection_names:
            try:
                coll = db.collection(coll_name)
                props = coll.properties()
                # Edge collections have type=3, document collections have type=2
                if props.get('type') == 3:
                    edge_collections.add(coll_name)
            except:
                continue
        
        # Method 2: Also get relationship types from ontology
        try:
            if db.has_collection('relationship_types'):
                cursor = db.aql.execute("FOR r IN relationship_types RETURN r.label")
                for label in cursor:
                    if label:
                        # Add both uppercase and as-is versions
                        edge_collections.add(label)
                        edge_collections.add(label.upper())
        except Exception as e:
            print(f"⚠️ Could not query relationship_types: {e}")
        
        # Fallback: Always include these known edge collections
        edge_collections.update({
            'CONTAINS', 'PRODUCES', 'REFERENCES', 'LEADS_TO', 'STARTS_WITH',
            'RELATED_TO', 'ASSIGNED_TO', 'TESTED_BY', 'OWNED_BY',
            'ontology_edges'
        })
        
        # Only keep collections that actually exist
        edge_collections = {ec for ec in edge_collections if ec in all_collection_names}
        
        print(f"🔗 Discovered edge collections: {sorted(edge_collections)}")
        
        # =====================================================
        # REST OF THE FUNCTION (mostly unchanged)
        # =====================================================
        
        # Build exclusion set for document collections
        excluded = set(edge_collections)
        if not include_schema:
            excluded = excluded.union(SCHEMA_COLLECTIONS)
        
        # Filter to only data collections
        doc_collections = [c for c in all_collection_names if c not in excluded]
        
        print(f"📊 Querying {len(doc_collections)} document collections")
        
        # Fetch all documents from artifact collections
        nodes = []
        for coll_name in doc_collections:
            try:
                query = f"FOR doc IN `{coll_name}` RETURN doc"
                docs = list(db.aql.execute(query))
                for doc in docs:
                    # === Determine cluster/team from actual document fields ===
                    cluster = None
                    
                    # 1. Check explicit owner field
                    owner = doc.get("owner")
                    if owner:
                        owner_lower = owner.lower()
                        if "automation" in owner_lower:
                            cluster = "Automation"
                        elif "range" in owner_lower:
                            cluster = "Range"
                        elif "content" in owner_lower:
                            cluster = "Content Development"
                        elif "opfor" in owner_lower:
                            cluster = "OPFOR"
                        else:
                            cluster = owner
                    
                    # 2. Check assigned_to field
                    if not cluster:
                        assigned_to = doc.get("assigned_to")
                        if assigned_to:
                            cluster = "Development"
                    
                    # 3. Check collaboration_with array
                    if not cluster:
                        collaboration = doc.get("collaboration_with", [])
                        if "Automation" in collaboration:
                            cluster = "Automation"
                        elif "Range" in collaboration:
                            cluster = "Range"
                        elif "ContentDev" in collaboration or "Content Development" in collaboration:
                            cluster = "Content Development"
                        elif "OPFOR" in collaboration:
                            cluster = "OPFOR"
                    
                    # 4. Infer from collection name (fallback)
                    if not cluster:
                        if "Execution" in coll_name or "Orchestration" in coll_name:
                            cluster = "Automation"
                        elif "Range" in coll_name or "Network" in coll_name:
                            cluster = "Range"
                        elif "Content" in coll_name or "Intel" in coll_name:
                            cluster = "Content Development"
                        elif "OPFOR" in coll_name or "Red" in coll_name:
                            cluster = "OPFOR"
                        else:
                            cluster = "Unassigned"
                    
                    # Use _artifact_type for human-readable type
                    artifact_type = doc.get("_artifact_type")
                    if not artifact_type:
                        artifact_type = _camel_to_title(coll_name)
                    
                    nodes.append({
                        "id": doc["_id"],
                        "label": doc.get("name", doc.get("label", doc.get("title", doc.get("_key")))),
                        "cluster": cluster,
                        "type": artifact_type,
                        "_artifact_type": artifact_type,
                        "owner": doc.get("owner", doc.get("assigned_to", "")),
                        "scenario_id": doc.get("scenario_id", "unknown"),
                        "status": doc.get("status", ""),
                        "importance": doc.get("importance", 0.5),
                        "description": doc.get("description", "")[:200] if doc.get("description") else ""
                    })
            except Exception as e:
                print(f"⚠️ Error fetching collection {coll_name}: {e}")
                continue
        
        # =====================================================
        # FETCH EDGES FROM ALL DISCOVERED EDGE COLLECTIONS
        # =====================================================
        edges = []
        node_ids = set(n["id"] for n in nodes)
        
        # Filter to collections that exist and aren't ontology (unless include_schema)
        edge_colls_to_query = [
            ec for ec in edge_collections 
            if ec in all_collection_names
            and (include_schema or ec != 'ontology_edges')
        ]
        
        print(f"📊 Querying {len(edge_colls_to_query)} edge collections: {sorted(edge_colls_to_query)}")
        
        for edge_coll in edge_colls_to_query:
            try:
                query = f"FOR edge IN `{edge_coll}` RETURN edge"
                edge_docs = list(db.aql.execute(query))
                
                matched_count = 0
                for e in edge_docs:
                    # Only include edges where both nodes are in our result set
                    if e["_from"] in node_ids and e["_to"] in node_ids:
                        edges.append({
                            "id": e["_id"],
                            "source": e["_from"],
                            "target": e["_to"],
                            "type": edge_coll.lower(),
                            "relationship_type": e.get("relationship_type", edge_coll),
                            "weight": e.get("weight", 1.0),
                            "confidence": e.get("confidence", 0)
                        })
                        matched_count += 1
                
                if matched_count > 0:
                    print(f"  ✅ {edge_coll}: {matched_count} edges")
                    
            except Exception as e:
                print(f"  ⚠️ Error fetching edge collection {edge_coll}: {e}")
                continue
        
        print(f"✅ Returning {len(nodes)} nodes and {len(edges)} edges")
        return {"nodes": nodes, "edges": edges, "count": len(nodes)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching graph: {str(e)}")


def _camel_to_title(name: str) -> str:
    """Convert CamelCase to Title Case with spaces.
    
    Examples:
        LibraryModule -> Library Module
        DevelopmentStory -> Development Story
        RobotLog -> Robot Log
    """
    import re
    # Insert space before capitals (but not at start)
    spaced = re.sub(r'(?<!^)(?=[A-Z])', ' ', name)
    return spaced


@app.get("/neighbors")
def get_neighbors(node_id: str = Query(..., description="Full node ID like 'Collection/key'"), depth: int = Query(1, ge=1, le=5)):
    """Fetch connected nodes within N hops using edge collections"""
    # =====================================================
    # GRAPHDB PATH (Phase 2)
    # =====================================================
    if gdb:
        try:
            result = gdb.get_neighbors(node_id, depth=depth)
            if result is None:
                raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")
            print(f"✅ [GraphDB] Neighbors for {node_id}: {result['count']} nodes")
            return result
        except HTTPException:
            raise
        except Exception as e:
            print(f"⚠️ [GraphDB] Neighbors failed, falling back to ArangoDB: {e}")
            # Fall through to ArangoDB path

    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")

    try:
        print(f"🔍 Fetching neighbors for: {node_id} at depth {depth}")
        
        # Start with the center node
        center_query = f"RETURN DOCUMENT('{node_id}')"
        center_result = list(db.aql.execute(center_query))
        
        if not center_result or not center_result[0]:
            raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")
        
        center_node = center_result[0]
        print(f"✓ Center node found: {center_node.get('_key', 'unknown')}")
        
        # Use a unified traversal query that can cross all edge types
        edge_collections = ['CONTAINS', 'PRODUCES', 'REFERENCES', 'LEADS_TO', 'STARTS_WITH']
        
        # Build query with proper collection references
        try:
            # Use OUTBOUND/INBOUND separately and combine results
            all_neighbors = []
            all_edges = []
            
            for direction in ['OUTBOUND', 'INBOUND']:
                for edge_coll in edge_collections:
                    try:
                        query = f"""
                            FOR v, e, p IN 1..{depth} {direction} @start_vertex {edge_coll}
                                OPTIONS {{uniqueVertices: "path", bfs: true}}
                                RETURN {{node: v, edge: e}}
                        """
                        
                        results = list(db.aql.execute(
                            query, 
                            bind_vars={"start_vertex": node_id}
                        ))
                        
                        for r in results:
                            if r.get('node'):
                                all_neighbors.append(r['node'])
                            if r.get('edge'):
                                all_edges.append(r['edge'])
                    
                    except Exception as coll_error:
                        print(f"⚠️ Error with {edge_coll} {direction}: {coll_error}")
                        continue
            
            # Deduplicate
            seen_nodes = set()
            seen_edges = set()
            neighbors = []
            edges = []
            
            for n in all_neighbors:
                node_id_str = n['_id']
                if node_id_str not in seen_nodes:
                    seen_nodes.add(node_id_str)
                    neighbors.append(n)
            
            for e in all_edges:
                edge_id_str = e['_id']
                if edge_id_str not in seen_edges:
                    seen_edges.add(edge_id_str)
                    edges.append(e)
            
            print(f"✓ Found {len(neighbors)} unique neighbors and {len(edges)} edges at depth {depth}")
            
            return {
                "center": center_node,
                "depth": depth,
                "nodes": neighbors,
                "edges": edges,
                "count": len(neighbors)
            }
            
        except Exception as query_error:
            print(f"❌ Query execution error: {query_error}")
            raise HTTPException(status_code=500, detail=f"Query failed: {str(query_error)}")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Neighbor fetch failed: {str(e)}")


# =====================================================
# ENHANCED SEARCH ENDPOINTS
# =====================================================
@app.get("/api/search/smart")
async def smart_search(
    q: str = Query(..., min_length=1, description="Natural language search query"),
    limit: int = Query(20, le=100, description="Max results to return")
):
    """
    SMART SEARCH - Uses Ollama to understand intent and search intelligently
    This endpoint powers the "Ask me anything about your data" search bar
    
    Examples:
    - "find TTPs related to PowerShell"
    - "show me OPFOR artifacts"
    - "what automation failures happened recently"
    """
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    try:
        print(f"\n{'='*80}")
        print(f"🔍 SMART SEARCH: '{q}'")
        print(f"{'='*80}")
        
        # =====================================================
        # GRAPHDB PATH (Phase 2) - simple keyword search
        # =====================================================
        if gdb:
            try:
                gdb_results = gdb.search(q, limit=limit)
                if gdb_results:
                    print(f"✅ [GraphDB] Search returned {len(gdb_results)} results")
                    return {
                        "query": q,
                        "extracted_intent": {
                            "search_terms": [q],
                            "collections": [],
                            "clusters": []
                        },
                        "count": len(gdb_results),
                        "results": [{
                            "id": r["_id"],
                            "label": r.get("name", r["_key"]),
                            "type": r.get("_artifact_type", "Unknown"),
                            "cluster": "Unassigned",
                            "scenario_id": "unknown",
                            "description": r.get("description", ""),
                            "status": "",
                            "relevance_score": 0,
                            "collaboration_with": []
                        } for r in gdb_results]
                    }
            except Exception as e:
                print(f"⚠️ [GraphDB] Search failed, falling back to ArangoDB: {e}")
        
        # Step 1: Extract search terms (but don't trust collection/cluster guesses)
        search_terms = []
        collections_filter = []
        clusters_filter = []
        
        # Simple keyword extraction as fallback
        keywords = [term.strip() for term in q.lower().split() if len(term.strip()) > 2]
        
        # Try Ollama for search terms ONLY
        if ollama_client:
            try:
                intent_prompt = f"""Given this search query: "{q}"

Extract ONLY the search terms (keywords to search for).
Return a simple JSON array of strings.

Example: ["PowerShell", "T1059"]
For "{q}": """
                
                intent_response = ollama_client.chat(
                    model=OLLAMA_MODEL,
                    messages=[{"role": "user", "content": intent_prompt}]
                )
                intent_text = intent_response["message"]["content"].strip()
                
                # Parse JSON from response
                if intent_text.startswith("```"):
                    intent_text = intent_text.split("```")[1]
                    if intent_text.startswith("json"):
                        intent_text = intent_text[4:]
                intent_text = intent_text.strip()
                
                # Try to parse as array
                if intent_text.startswith("["):
                    search_terms = json.loads(intent_text)
                else:
                    # Fallback if not array
                    search_terms = keywords
                    
                print(f"✅ Ollama extracted terms: {search_terms}")
            except Exception as e:
                print(f"⚠️  Ollama failed, using keywords: {e}")
                search_terms = keywords
        else:
            search_terms = keywords
        
        # Step 2: Manually infer clusters from search terms
        # Only add cluster filter if we're VERY confident
        query_lower = q.lower()
        
        if query_lower == "opfor" or "show me opfor" in query_lower or "opfor content" in query_lower:
            clusters_filter = ["OPFOR"]
            print(f"🎯 Detected explicit OPFOR search")
        elif query_lower == "automation" or "show me automation" in query_lower:
            clusters_filter = ["Automation"]
            print(f"🎯 Detected explicit Automation search")
        elif query_lower == "range" or "show me range" in query_lower:
            clusters_filter = ["Range"]
            print(f"🎯 Detected explicit Range search")
        elif "contentdev" in query_lower or "content dev" in query_lower:
            clusters_filter = ["ContentDev"]
            print(f"🎯 Detected explicit ContentDev search")
        else:
            # Don't filter by cluster - search everything
            print(f"🌐 Searching all clusters")
        
        # Step 3: Get ALL collections (don't trust Ollama's guesses)
        edge_collections = ['CONTAINS', 'PRODUCES', 'REFERENCES', 'LEADS_TO', 'STARTS_WITH']
        
        # Always get all collections
        all_collections = [c['name'] for c in db.collections() 
                          if not c['name'].startswith('_') 
                          and c['name'] not in edge_collections]
        
        print(f"🔑 Search terms: {search_terms}")
        print(f"📦 Searching ALL collections (found {len(all_collections)})")
        if clusters_filter:
            print(f"🎯 Cluster filter: {clusters_filter}")
        else:
            print(f"🎯 No cluster filter (searching all)")
        
        # Step 4: Search each collection
        results = []
        collections_searched = 0
        collections_with_results = 0
        
        for coll_name in all_collections:
            try:
                # Check collection has documents
                coll = db.collection(coll_name)
                doc_count = coll.count()
                
                if doc_count == 0:
                    continue
                
                collections_searched += 1
                
                # Build FILTER conditions for text search
                filter_conditions = []
                for term in search_terms:
                    filter_conditions.append(
                        f"LIKE(LOWER(doc.name), '%{term.lower()}%', true) OR "
                        f"LIKE(LOWER(doc._key), '%{term.lower()}%', true) OR "
                        f"LIKE(LOWER(doc.description), '%{term.lower()}%', true)"
                    )
                
                if not filter_conditions:
                    combined_filter = "true"
                else:
                    combined_filter = " OR ".join([f"({cond})" for cond in filter_conditions])
                
                # Add cluster filtering if specified
                if clusters_filter:
                    collab_conditions = []
                    for cluster in clusters_filter:
                        collab_conditions.append(f"'{cluster}' IN doc.collaboration_with")
                    
                    collab_filter = " OR ".join(collab_conditions)
                    
                    # Use OR - match text OR cluster membership
                    combined_filter = f"({combined_filter}) OR ({collab_filter})"
                
                # Try query WITH graph traversal for relevance scoring
                try:
                    query_with_graph = f"""
                        FOR doc IN {coll_name}
                            FILTER {combined_filter}
                            LIMIT {limit}
                            
                            LET outbound_count = LENGTH(
                                FOR v IN 1..1 OUTBOUND doc._id CONTAINS, PRODUCES, REFERENCES, LEADS_TO, STARTS_WITH
                                    RETURN 1
                            )
                            
                            LET inbound_count = LENGTH(
                                FOR v IN 1..1 INBOUND doc._id CONTAINS, PRODUCES, REFERENCES, LEADS_TO, STARTS_WITH
                                    RETURN 1
                            )
                            
                            RETURN {{
                                doc: doc,
                                relevance_score: outbound_count + inbound_count
                            }}
                    """
                    
                    docs_with_scores = list(db.aql.execute(query_with_graph))
                    
                    if len(docs_with_scores) > 0:
                        collections_with_results += 1
                        print(f"  ✅ {coll_name}: {len(docs_with_scores)} results")
                    
                    for item in docs_with_scores:
                        doc = item['doc']
                        collaboration = doc.get("collaboration_with", [])
                        
                        if "Automation" in collaboration:
                            cluster = "automation"
                        elif "Range" in collaboration:
                            cluster = "range"
                        elif "ContentDev" in collaboration:
                            cluster = "content"
                        elif "OPFOR" in collaboration:
                            cluster = "opfor"
                        else:
                            cluster = "planning"
                        
                        results.append({
                            "id": doc["_id"],
                            "label": doc.get("name", doc.get("_key", "Unnamed")),
                            "type": coll_name,
                            "cluster": cluster,
                            "scenario_id": doc.get("scenario_id", "unknown"),
                            "description": doc.get("description", ""),
                            "status": doc.get("status", ""),
                            "relevance_score": item['relevance_score'],
                            "collaboration_with": doc.get("collaboration_with", [])
                        })
                
                except Exception as graph_error:
                    # Fallback: simple query without graph traversal
                    simple_query = f"""
                        FOR doc IN {coll_name}
                            FILTER {combined_filter}
                            LIMIT {limit}
                            RETURN doc
                    """
                    
                    docs = list(db.aql.execute(simple_query))
                    
                    if len(docs) > 0:
                        collections_with_results += 1
                        print(f"  ✅ {coll_name}: {len(docs)} results (simple)")
                    
                    for doc in docs:
                        collaboration = doc.get("collaboration_with", [])
                        
                        if "Automation" in collaboration:
                            cluster = "automation"
                        elif "Range" in collaboration:
                            cluster = "range"
                        elif "ContentDev" in collaboration:
                            cluster = "content"
                        elif "OPFOR" in collaboration:
                            cluster = "opfor"
                        else:
                            cluster = "planning"
                        
                        results.append({
                            "id": doc["_id"],
                            "label": doc.get("name", doc.get("_key", "Unnamed")),
                            "type": coll_name,
                            "cluster": cluster,
                            "scenario_id": doc.get("scenario_id", "unknown"),
                            "description": doc.get("description", ""),
                            "status": doc.get("status", ""),
                            "relevance_score": 0,
                            "collaboration_with": doc.get("collaboration_with", [])
                        })
                    
            except Exception as coll_error:
                # Silently skip collections that error
                continue
        
        # Step 5: Sort and return
        results.sort(key=lambda x: x['relevance_score'], reverse=True)
        results = results[:limit]
        
        print(f"\n{'='*80}")
        print(f"✅ SEARCHED: {collections_searched} collections")
        print(f"✅ FOUND RESULTS IN: {collections_with_results} collections")
        print(f"✅ TOTAL RESULTS: {len(results)}")
        print(f"{'='*80}\n")
        
        return {
            "query": q,
            "extracted_intent": {
                "search_terms": search_terms,
                "collections": [],  # Not used anymore
                "clusters": clusters_filter
            },
            "count": len(results),
            "results": results
        }
        
    except Exception as e:
        print(f"\n❌ SEARCH FAILED: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Smart search failed: {str(e)}")


@app.get("/api/search/advanced")
def advanced_search(
    q: str = Query(..., min_length=1),
    collections: Optional[List[str]] = Query(None, description="Filter by collections"),
    clusters: Optional[List[str]] = Query(None, description="Filter by clusters"),
    scenario_id: Optional[str] = Query(None, description="Filter by scenario"),
    status: Optional[str] = Query(None, description="Filter by status"),
    include_related: bool = Query(False, description="Include connected nodes"),
    depth: int = Query(1, ge=1, le=3, description="Depth for related nodes"),
    limit: int = Query(50, le=200)
):
    """
    ADVANCED SEARCH - Full control with filters and graph traversal
    
    Examples:
    - /api/search/advanced?q=mimikatz&clusters=Automation&clusters=OPFOR
    - /api/search/advanced?q=OBAP&scenario_id=OBAP&include_related=true&depth=2
    - /api/search/advanced?q=test&collections=TestLogArtifact&status=failed
    """
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    try:
        edge_collections = ['CONTAINS', 'PRODUCES', 'REFERENCES', 'LEADS_TO', 'STARTS_WITH']
        
        if collections:
            search_collections = collections
        else:
            search_collections = [c['name'] for c in db.collections() 
                                 if not c['name'].startswith('_') 
                                 and c['name'] not in edge_collections]
        
        results = []
        
        for coll_name in search_collections:
            try:
                # Build dynamic filter
                filters = [
                    "LIKE(LOWER(doc.name), @pattern, true) OR "
                    "LIKE(LOWER(doc._key), @pattern, true) OR "
                    "LIKE(LOWER(doc.description), @pattern, true)"
                ]
                
                bind_vars = {"pattern": f"%{q.lower()}%"}
                
                # Add cluster filter
                if clusters:
                    cluster_conditions = []
                    for i, cluster in enumerate(clusters):
                        cluster_conditions.append(f"@cluster{i} IN doc.collaboration_with")
                        bind_vars[f"cluster{i}"] = cluster
                    filters.append(f"({' OR '.join(cluster_conditions)})")
                
                # Add scenario filter
                if scenario_id:
                    filters.append("doc.scenario_id == @scenario_id")
                    bind_vars["scenario_id"] = scenario_id
                
                # Add status filter
                if status:
                    filters.append("doc.status == @status")
                    bind_vars["status"] = status
                
                combined_filter = " AND ".join([f"({f})" for f in filters])
                
                query = f"""
                    FOR doc IN {coll_name}
                        FILTER {combined_filter}
                        LIMIT @limit
                        RETURN doc
                """
                
                bind_vars["limit"] = limit
                
                docs = list(db.aql.execute(query, bind_vars=bind_vars))
                
                for doc in docs:
                    collaboration = doc.get("collaboration_with", [])
                    if "Automation" in collaboration:
                        cluster = "automation"
                    elif "Range" in collaboration:
                        cluster = "range"
                    elif "ContentDev" in collaboration:
                        cluster = "content"
                    elif "OPFOR" in collaboration:
                        cluster = "opfor"
                    else:
                        cluster = "planning"
                    
                    result_item = {
                        "id": doc["_id"],
                        "label": doc.get("name", doc["_key"]),
                        "type": coll_name,
                        "cluster": cluster,
                        "scenario_id": doc.get("scenario_id", "unknown"),
                        "description": doc.get("description", ""),
                        "status": doc.get("status", ""),
                        "collaboration_with": doc.get("collaboration_with", [])
                    }
                    
                    # Optionally include related nodes
                    if include_related:
                        related_nodes = []
                        for direction in ['OUTBOUND', 'INBOUND']:
                            for edge_coll in edge_collections:
                                try:
                                    traversal_query = f"""
                                        FOR v IN 1..@depth {direction} @start_node {edge_coll}
                                            RETURN {{
                                                id: v._id,
                                                label: v.name,
                                                type: PARSE_IDENTIFIER(v._id).collection
                                            }}
                                    """
                                    related = list(db.aql.execute(
                                        traversal_query,
                                        bind_vars={
                                            "start_node": doc["_id"],
                                            "depth": depth
                                        }
                                    ))
                                    related_nodes.extend(related)
                                except:
                                    continue
                        
                        result_item["related_nodes"] = related_nodes[:10]  # Limit related
                    
                    results.append(result_item)
                    
            except Exception as e:
                print(f"Error in advanced search for {coll_name}: {e}")
                continue
        
        return {
            "query": q,
            "filters": {
                "collections": collections,
                "clusters": clusters,
                "scenario_id": scenario_id,
                "status": status,
                "include_related": include_related
            },
            "count": len(results),
            "results": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Advanced search failed: {str(e)}")


@app.get("/api/artifact/{doc_id}")
def get_artifact(doc_id: str):
    try:
        # URL-decoded already because FastAPI handles %2F correctly
        if "/" not in doc_id:
            raise HTTPException(status_code=400, detail="Invalid doc_id format")

        collection, key = doc_id.split("/", 1)

        # =====================================================
        # GRAPHDB PATH (Phase 2)
        # =====================================================
        if gdb:
            try:
                doc = gdb.get_artifact(collection, key)
                if doc is None:
                    raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
                return {"success": True, "data": doc}
            except HTTPException:
                raise
            except Exception as e:
                print(f"⚠️ [GraphDB] Artifact fetch failed, falling back to ArangoDB: {e}")

        coll = db.collection(collection)
        if not coll.has(key):
            raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

        doc = coll.get(key)
        return {"success": True, "data": doc}

    except Exception as e:
        print("Error fetching artifact:", e)
        raise HTTPException(status_code=500, detail=str(e))


# Alternative endpoint with explicit collection/key separation
@app.get("/api/artifact/{collection}/{key:path}")
def get_artifact_by_parts(collection: str, key: str):
    """
    Fetch artifact with explicit collection and key path parameters.
    This handles cases where the key itself might contain slashes.
    """
    try:
        # =====================================================
        # GRAPHDB PATH (Phase 2)
        # =====================================================
        if gdb:
            try:
                doc = gdb.get_artifact(collection, key)
                if doc is None:
                    raise HTTPException(
                        status_code=404, 
                        detail=f"Document {collection}/{key} not found"
                    )
                return {"success": True, "data": doc}
            except HTTPException:
                raise
            except Exception as e:
                print(f"⚠️ [GraphDB] Artifact fetch failed, falling back to ArangoDB: {e}")

        coll = db.collection(collection)
        if not coll.has(key):
            raise HTTPException(
                status_code=404, 
                detail=f"Document {collection}/{key} not found in database"
            )

        doc = coll.get(key)
        return {"success": True, "data": doc}

    except Exception as e:
        print(f"Error fetching artifact {collection}/{key}:", e)
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# CHAT ASSISTANT (Enhanced with search context)
# =====================================================
@app.post("/chat")
def chat(req: ChatRequest):
    """Chat with Ollama AI using optional graph context"""
    if not ollama_client:
        raise HTTPException(status_code=500, detail="Ollama client unavailable")

    try:
        # Enhanced system prompt with formatting constraints
        system_prompt = """You are ProtoGraph's AI assistant for the 318th RANS. 
You help analyze cyber operations artifacts, automation workflows, and range configurations.

You have access to a knowledge graph with these types of nodes:
- TTPs (MITRE ATT&CK techniques)
- Processes (team workflows)
- Artifacts (campaign plans, test logs, configurations)
- Steps (planning, development, execution)

RESPONSE RULES:
- NEVER use markdown formatting (**, ||, ---, tables, etc.)
- Keep responses concise - match the length to the question
- For simple questions, give brief 1-2 sentence answers
- For complex questions, provide detailed explanations in plain paragraphs
- Use bullet points with simple dashes (-) only when listing is absolutely necessary
- Write naturally as if speaking to a colleague

When users ask questions, help them find relevant nodes, understand relationships, and identify patterns."""

        context_text = f"Current graph context: {req.context or 'No specific nodes selected'}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{context_text}\n\nQuestion: {req.message}"},
        ]
        
        response = ollama_client.chat(model=OLLAMA_MODEL, messages=messages)
        return {"reply": response["message"]["content"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ollama chat failed: {str(e)}")


# =====================================================
# ANALYTICS → POWER BI STREAM
# =====================================================
@app.post("/analytics/update-powerbi")
def update_powerbi():
    """Push current coupling data to Power BI Streaming Dataset"""
    rows = calculate_team_coupling()
    if not rows:
        raise HTTPException(status_code=400, detail="No data to push")

    print(f"🚀 Pushing {len(rows)} rows to Power BI…")
    if push_to_powerbi_stream(rows):
        return {"status": "pushed", "rows": len(rows)}

    raise HTTPException(status_code=500, detail="Power BI push failed")


@app.post("/analytics/notify-update")
def notify_update():
    """Frontend notification that graph state changed (for Power BI sync)"""
    # This is called when user interacts with graph
    # You can trigger analytics recalculation here if needed
    return {"status": "acknowledged", "message": "Graph update noted"}


@app.get("/analytics/team-coupling-table")
def get_team_coupling_table():
    """Return team coupling data for Power BI to consume"""
    rows = calculate_team_coupling()
    if not rows:
        return {"rows": []}
    
    return {"rows": rows}


# =====================================================
# PROSPECTOR MODE ENDPOINTS
# =====================================================

@app.post("/prospector/node")
async def prospector_create_node(request: CreateNodeRequest):
    """
    Create a new node in the graph
    """
    # =====================================================
    # GRAPHDB PATH (Phase 2)
    # =====================================================
    if gdb:
        try:
            # Map type string to an ontology class, default to LibraryModule
            type_to_class = {
                "library_module": "LibraryModule",
                "librarymodule": "LibraryModule",
                "ttp": "TTP",
                "person": "Person",
                "team": "Team",
                "execution_plan": "ExecutionPlan",
                "scenario": "Scenario",
                "development_story": "DevelopmentStory",
                "range_environment": "RangeEnvironment",
                "robot_log": "RobotLog",
            }
            artifact_type = type_to_class.get(request.type.lower(), "LibraryModule")
            
            # Generate a key from the label
            import re
            key = re.sub(r'[^a-zA-Z0-9_-]', '_', request.label.lower()).strip('_')
            
            properties = {
                "name": request.label,
                "description": request.description or "",
            }
            if request.custom_fields:
                properties.update(request.custom_fields)
            
            result = gdb.create_node(key, artifact_type, properties)
            
            print(f"✅ [GraphDB] Created node: {result['_id']}")
            return {
                "success": True,
                "message": "Node created successfully",
                "node": {
                    "_id": result["_id"],
                    "_key": key,
                    "name": request.label,
                    "label": request.label,
                    "type": request.type,
                    "cluster": request.cluster,
                    "description": request.description or "",
                    "tags": request.tags or [],
                    "created_by": "prospector",
                    "created_at": datetime.utcnow().isoformat(),
                }
            }
        except Exception as e:
            print(f"⚠️ [GraphDB] Create node failed, falling back to ArangoDB: {e}")

    if not db:
        raise HTTPException(status_code=503, detail="Database connection not available")
    
    try:
        # Determine which collection to use based on type
        # You can customize this logic based on your schema
        collection_name = "nodes"  # Default collection
        
        # Check if collection exists, create if not
        if not db.has_collection(collection_name):
            db.create_collection(collection_name)
        
        nodes_collection = db.collection(collection_name)
        
        # Prepare node document
        node_doc = {
            "name": request.label,  # Use 'name' to match your existing schema
            "label": request.label,
            "type": request.type,
            "cluster": request.cluster,
            "description": request.description or "",
            "tags": request.tags or [],
            "importance": 0.5,
            "size": 20,
            "created_by": "prospector",
            "created_at": datetime.utcnow().isoformat(),
            **request.custom_fields
        }
        
        # Insert into database
        result = nodes_collection.insert(node_doc)
        
        print(f"✅ Created node: {result['_id']}")
        
        return {
            "success": True,
            "message": "Node created successfully",
            "node": {
                "_id": result["_id"],
                "_key": result["_key"],
                "_rev": result["_rev"],
                **node_doc
            }
        }
        
    except Exception as e:
        print(f"❌ Failed to create node: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create node: {str(e)}")


@app.put("/prospector/node")
async def prospector_update_node(request: UpdateNodeRequest):
    """
    Update an existing node's properties
    """
    # =====================================================
    # GRAPHDB PATH (Phase 2)
    # =====================================================
    if gdb:
        try:
            if "/" not in request.node_id:
                raise HTTPException(status_code=400, detail="Invalid node_id format. Expected 'collection/key'")
            
            collection_name, key = request.node_id.split("/", 1)
            
            updates = {}
            if request.label is not None:
                updates["name"] = request.label
            if request.description is not None:
                updates["description"] = request.description
            if request.custom_fields:
                updates.update(request.custom_fields)
            
            result = gdb.update_node(collection_name, key, updates)
            
            print(f"✅ [GraphDB] Updated node: {result['_id']}")
            return {
                "success": True,
                "message": "Node updated successfully",
                "node_id": result["_id"],
            }
        except HTTPException:
            raise
        except Exception as e:
            print(f"⚠️ [GraphDB] Update node failed, falling back to ArangoDB: {e}")

    if not db:
        raise HTTPException(status_code=503, detail="Database connection not available")
    
    try:
        # Extract collection and key from node_id
        if "/" not in request.node_id:
            raise HTTPException(status_code=400, detail="Invalid node_id format. Expected 'collection/key'")
        
        collection_name, key = request.node_id.split("/", 1)
        nodes_collection = db.collection(collection_name)
        
        # Build update document
        update_doc = {
            "updated_by": "prospector",
            "updated_at": datetime.utcnow().isoformat()
        }
        
        if request.label is not None:
            update_doc["label"] = request.label
            update_doc["name"] = request.label  # Update both for consistency
        if request.type is not None:
            update_doc["type"] = request.type
        if request.cluster is not None:
            update_doc["cluster"] = request.cluster
        if request.description is not None:
            update_doc["description"] = request.description
        if request.tags is not None:
            update_doc["tags"] = request.tags
        if request.custom_fields:
            update_doc.update(request.custom_fields)
        
        # Update the document
        result = nodes_collection.update({"_key": key, **update_doc})
        
        print(f"✅ Updated node: {result['_id']}")
        
        return {
            "success": True,
            "message": "Node updated successfully",
            "node_id": result["_id"],
            "rev": result["_rev"]
        }
        
    except Exception as e:
        print(f"❌ Failed to update node: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update node: {str(e)}")


@app.delete("/prospector/node/{node_id:path}")
async def prospector_delete_node(node_id: str):
    """
    Delete a node and all its connected edges
    """
    # =====================================================
    # GRAPHDB PATH (Phase 2)
    # =====================================================
    if gdb:
        try:
            if "/" not in node_id:
                raise HTTPException(status_code=400, detail="Invalid node_id format. Expected 'collection/key'")
            
            collection_name, key = node_id.split("/", 1)
            gdb.delete_node(collection_name, key)
            
            print(f"✅ [GraphDB] Deleted node: {node_id}")
            return {
                "success": True,
                "message": "Node deleted successfully",
                "deleted_node_id": node_id
            }
        except HTTPException:
            raise
        except Exception as e:
            print(f"⚠️ [GraphDB] Delete node failed, falling back to ArangoDB: {e}")

    if not db:
        raise HTTPException(status_code=503, detail="Database connection not available")
    
    try:
        # Extract collection and key
        if "/" not in node_id:
            raise HTTPException(status_code=400, detail="Invalid node_id format. Expected 'collection/key'")
        
        collection_name, key = node_id.split("/", 1)
        
        # Try to use graph API if graph exists (this auto-deletes edges)
        try:
            graph = db.graph(ARANGO_GRAPH)
            graph.delete_vertex(node_id)
            print(f"✅ Deleted node via graph API: {node_id}")
        except:
            # Fallback: just delete the document
            # Note: This won't auto-delete edges, but safer if graph doesn't exist
            nodes_collection = db.collection(collection_name)
            nodes_collection.delete(key)
            print(f"✅ Deleted node via collection: {node_id}")
        
        return {
            "success": True,
            "message": "Node deleted successfully",
            "deleted_node_id": node_id
        }
        
    except Exception as e:
        print(f"❌ Failed to delete node: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete node: {str(e)}")
    

@app.delete("/api/artifact/{collection}/{key}")
async def delete_artifact(collection: str, key: str):
    """
    Delete an artifact node from the graph.
    """
    # =====================================================
    # GRAPHDB PATH (Phase 2)
    # =====================================================
    if gdb:
        try:
            if not gdb.has_artifact(key):
                raise HTTPException(status_code=404, detail=f"Document '{collection}/{key}' not found")
            
            gdb.delete_node(collection, key)
            
            print(f"✅ [GraphDB] Deleted artifact: {collection}/{key}")
            return {
                "success": True,
                "message": f"Artifact {collection}/{key} deleted successfully",
                "deleted_id": f"{collection}/{key}"
            }
        except HTTPException:
            raise
        except Exception as e:
            print(f"⚠️ [GraphDB] Delete artifact failed, falling back to ArangoDB: {e}")

    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        # Check if collection exists
        if not db.has_collection(collection):
            raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")
        
        coll = db.collection(collection)
        
        # Check if document exists
        if not coll.has(key):
            raise HTTPException(status_code=404, detail=f"Document '{collection}/{key}' not found")
        
        # Delete the document
        coll.delete(key)
        
        print(f"✅ Deleted artifact: {collection}/{key}")
        
        return {
            "success": True,
            "message": f"Artifact {collection}/{key} deleted successfully",
            "deleted_id": f"{collection}/{key}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to delete artifact: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete artifact: {str(e)}")


@app.post("/prospector/edge")
async def prospector_create_edge(request: CreateEdgeRequest):
    """
    Create a new edge between two nodes
    """
    # =====================================================
    # GRAPHDB PATH (Phase 2)
    # =====================================================
    if gdb:
        try:
            # Parse from_node and to_node ("Collection/key" format)
            if "/" not in request.from_node or "/" not in request.to_node:
                raise HTTPException(status_code=400, detail="Invalid node ID format. Expected 'collection/key'")
            
            from_coll, from_key = request.from_node.split("/", 1)
            to_coll, to_key = request.to_node.split("/", 1)
            
            # Normalize relationship type to uppercase
            rel_type = request.relationship_type.upper()
            
            result = gdb.create_edge(from_coll, from_key, to_coll, to_key, rel_type)
            
            print(f"✅ [GraphDB] Created edge: {request.from_node} --{rel_type}--> {request.to_node}")
            
            # Handle bidirectional
            reverse_result = None
            if request.bidirectional:
                reverse_result = gdb.create_edge(to_coll, to_key, from_coll, from_key, rel_type)
                print(f"✅ [GraphDB] Created reverse edge")
            
            return {
                "success": True,
                "message": "Edge created successfully" + (" (bidirectional)" if request.bidirectional else ""),
                "edge": {
                    "_id": result["_id"],
                    "_key": f"{from_key}-{to_key}",
                    "_from": request.from_node,
                    "_to": request.to_node,
                    "type": request.relationship_type,
                    "weight": request.weight,
                    "description": request.description or "",
                    "created_by": "prospector",
                    "created_at": datetime.utcnow().isoformat(),
                },
                "reverse_edge": {
                    "_id": reverse_result["_id"],
                } if reverse_result else None
            }
        except HTTPException:
            raise
        except Exception as e:
            print(f"⚠️ [GraphDB] Create edge failed, falling back to ArangoDB: {e}")

    if not db:
        raise HTTPException(status_code=503, detail="Database connection not available")
    
    try:
        # Use existing edge collections or create new one
        # You can customize which edge collection to use based on relationship_type
        edge_collection_name = "REFERENCES"  # Default to REFERENCES
        
        # Map relationship types to your existing edge collections
        relationship_mapping = {
            "depends_on": "REFERENCES",
            "uses": "REFERENCES",
            "imports": "REFERENCES",
            "calls": "REFERENCES",
            "contains": "CONTAINS",
            "produces": "PRODUCES",
            "leads_to": "LEADS_TO",
            "starts_with": "STARTS_WITH"
        }
        
        edge_collection_name = relationship_mapping.get(
            request.relationship_type.lower(), 
            "REFERENCES"
        )
        
        # Check if edge collection exists
        if not db.has_collection(edge_collection_name):
            # Create as edge collection
            db.create_collection(edge_collection_name, edge=True)
        
        edges_collection = db.collection(edge_collection_name)
        
        # Prepare edge document
        edge_doc = {
            "_from": request.from_node,
            "_to": request.to_node,
            "type": request.relationship_type,
            "weight": request.weight,
            "description": request.description or "",
            "created_by": "prospector",
            "created_at": datetime.utcnow().isoformat(),
            **(request.metadata or {})
        }
        
        # Insert edge
        result = edges_collection.insert(edge_doc)
        
        print(f"✅ Created edge: {result['_id']} ({request.from_node} -> {request.to_node})")
        
        # If bidirectional, create reverse edge
        reverse_result = None
        if request.bidirectional:
            reverse_doc = {
                "_from": request.to_node,
                "_to": request.from_node,
                "type": f"{request.relationship_type}_reverse",
                "weight": request.weight,
                "description": f"Reverse of: {request.description}" if request.description else "",
                "created_by": "prospector",
                "created_at": datetime.utcnow().isoformat(),
                "bidirectional_pair": result["_id"],
                **(request.metadata or {})
            }
            reverse_result = edges_collection.insert(reverse_doc)
            print(f"✅ Created reverse edge: {reverse_result["_id"]}")
        
        return {
            "success": True,
            "message": "Edge created successfully" + (" (bidirectional)" if request.bidirectional else ""),
            "edge": {
                "_id": result["_id"],
                "_key": result["_key"],
                "_rev": result["_rev"],
                **edge_doc
            },
            "reverse_edge": {
                "_id": reverse_result["_id"],
                "_key": reverse_result["_key"],
                "_rev": reverse_result["_rev"]
            } if reverse_result else None
        }
        
    except Exception as e:
        print(f"❌ Failed to create edge: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create edge: {str(e)}")


@app.delete("/prospector/edge/{edge_id:path}")
async def prospector_delete_edge(edge_id: str):
    """
    Delete a specific edge
    """
    # =====================================================
    # GRAPHDB PATH (Phase 2)
    # =====================================================
    if gdb:
        try:
            if "/" not in edge_id:
                raise HTTPException(status_code=400, detail="Invalid edge_id format. Expected 'collection/key'")
            
            # edge_id format from frontend: "LEADS_TO/from_key-to_key"
            rel_type, key_pair = edge_id.split("/", 1)
            
            # Parse the key pair to get from/to keys
            if "-" in key_pair:
                from_key, to_key = key_pair.split("-", 1)
                gdb.delete_edge(from_key, to_key, rel_type)
            else:
                # Fallback: try to delete by brute force query
                gdb.sparql_update(f"""
                    DELETE WHERE {{
                        ?s <https://proto.atlas/relationship/{rel_type}> ?o .
                        FILTER(STRENDS(STR(?s), "{key_pair}") || STRENDS(STR(?o), "{key_pair}"))
                    }}
                """)
            
            print(f"✅ [GraphDB] Deleted edge: {edge_id}")
            return {
                "success": True,
                "message": "Edge deleted successfully",
                "deleted_edge_id": edge_id
            }
        except HTTPException:
            raise
        except Exception as e:
            print(f"⚠️ [GraphDB] Delete edge failed, falling back to ArangoDB: {e}")

    if not db:
        raise HTTPException(status_code=503, detail="Database connection not available")
    
    try:
        # Extract collection and key
        if "/" not in edge_id:
            raise HTTPException(status_code=400, detail="Invalid edge_id format. Expected 'collection/key'")
        
        collection_name, key = edge_id.split("/", 1)
        edges_collection = db.collection(collection_name)
        
        # Delete the edge
        edges_collection.delete(key)
        
        print(f"✅ Deleted edge: {edge_id}")
        
        return {
            "success": True,
            "message": "Edge deleted successfully",
            "deleted_edge_id": edge_id
        }
        
    except Exception as e:
        print(f"❌ Failed to delete edge: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete edge: {str(e)}")


@app.get("/prospector/validate-nodes")
async def prospector_validate_nodes(node_ids: str):
    """
    Validate that nodes exist before creating edges
    """
    # =====================================================
    # GRAPHDB PATH (Phase 2)
    # =====================================================
    if gdb:
        try:
            node_id_list = node_ids.split(',')
            results = {}
            
            for node_id in node_id_list:
                node_id = node_id.strip()
                if "/" not in node_id:
                    results[node_id] = False
                    continue
                collection_name, key = node_id.split("/", 1)
                results[node_id] = gdb.has_artifact(key)
            
            return {
                "success": True,
                "all_nodes_exist": all(results.values()),
                "nodes": results
            }
        except Exception as e:
            print(f"⚠️ [GraphDB] Validate nodes failed, falling back to ArangoDB: {e}")

    if not db:
        raise HTTPException(status_code=503, detail="Database connection not available")
    
    try:
        node_id_list = node_ids.split(',')
        results = {}
        
        for node_id in node_id_list:
            node_id = node_id.strip()
            
            if "/" not in node_id:
                results[node_id] = False
                continue
            
            collection_name, key = node_id.split("/", 1)
            
            try:
                collection = db.collection(collection_name)
                exists = collection.has(key)
                results[node_id] = exists
            except:
                results[node_id] = False
        
        all_exist = all(results.values())
        
        return {
            "success": True,
            "all_nodes_exist": all_exist,
            "nodes": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to validate nodes: {str(e)}")


@app.post("/prospector/bulk/nodes")
async def prospector_bulk_create_nodes(nodes: List[CreateNodeRequest]):
    """
    Create multiple nodes in one operation
    
    Example:
    POST /prospector/bulk/nodes
    [
      {"label": "Node 1", "type": "script", "cluster": "automation"},
      {"label": "Node 2", "type": "tool", "cluster": "range"}
    ]
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database connection not available")
    
    try:
        collection_name = "nodes"
        
        if not db.has_collection(collection_name):
            db.create_collection(collection_name)
        
        nodes_collection = db.collection(collection_name)
        
        node_docs = []
        for node_req in nodes:
            node_doc = {
                "name": node_req.label,
                "label": node_req.label,
                "type": node_req.type,
                "cluster": node_req.cluster,
                "description": node_req.description or "",
                "tags": node_req.tags or [],
                "importance": 0.5,
                "size": 20,
                "created_by": "prospector",
                "created_at": datetime.utcnow().isoformat(),
                **node_req.custom_fields
            }
            node_docs.append(node_doc)
        
        # Bulk insert
        results = nodes_collection.insert_many(node_docs)
        
        print(f"✅ Bulk created {len(results)} nodes")
        
        return {
            "success": True,
            "message": f"Created {len(results)} nodes",
            "created_count": len(results),
            "nodes": results
        }
        
    except Exception as e:
        print(f"❌ Failed to bulk create nodes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to bulk create nodes: {str(e)}")


# =====================================================
# JSON-BASED CONNECTION REVIEW SYSTEM
# =====================================================
@app.get("/connections/pending")
def get_pending_json():
    """
    Get pending LLM-suggested connections for review.
    
    Reads from llm_edge_suggestions.json and formats for ConnectionReviewModal.
    Extracts real node data including cluster, type, metadata, and confidence.
    """
    data = load_json()

    formatted = []
    for idx, item in enumerate(data.get("part1_responses", [])):
        # Skip already reviewed items
        if "user_decision" in item:
            continue
            
        src = item.get("src_node", {})
        tgt = item.get("pair_node", {})
        
        # Extract node type from collection (e.g., "Process/key" -> "Process")
        src_type = src.get("_id", "").split("/")[0] if "/" in src.get("_id", "") else "Unknown"
        tgt_type = tgt.get("_id", "").split("/")[0] if "/" in tgt.get("_id", "") else "Unknown"
        
        # Try to determine cluster from node attributes
        # Priority: cluster > team > owner > default based on type
        def get_cluster(node, node_type):
            """Intelligently determine node cluster"""
            if node.get("cluster"):
                return node["cluster"]
            if node.get("team"):
                return node["team"]
            if node.get("owner"):
                owner = node["owner"].lower()
                if "automation" in owner:
                    return "automation"
                elif "range" in owner:
                    return "range"
                elif "opfor" in owner:
                    return "opfor"
            # Default cluster based on type
            if "automation" in node_type.lower():
                return "automation"
            elif "execution" in node_type.lower() or "live" in node_type.lower():
                return "range"
            elif "planning" in node_type.lower() or "development" in node_type.lower():
                return "content"
            return "unknown"
        
        src_cluster = get_cluster(src, src_type)
        tgt_cluster = get_cluster(tgt, tgt_type)
        
        # Extract metadata (exclude internal ArangoDB fields)
        excluded_fields = ["_id", "_key", "_rev", "name", "description", "label"]
        src_metadata = {k: v for k, v in src.items() if k not in excluded_fields}
        tgt_metadata = {k: v for k, v in tgt.items() if k not in excluded_fields}
        
        formatted.append({
            "id": f"json_{idx}",
            "sourceNode": {
                "id": src.get("_id"),
                "label": src.get("name", src.get("label", src.get("_key", "Unknown"))),
                "type": src_type,
                "cluster": src_cluster,
                "description": src.get("description", ""),
                "importance": src.get("importance", 0.5),
                "metadata": src_metadata
            },
            "targetNode": {
                "id": tgt.get("_id"),
                "label": tgt.get("name", tgt.get("label", tgt.get("_key", "Unknown"))),
                "type": tgt_type,
                "cluster": tgt_cluster,
                "description": tgt.get("description", ""),
                "importance": tgt.get("importance", 0.5),
                "metadata": tgt_metadata
            },
            "proposedRelationship": item.get("type", "RELATED_TO"),
            "confidence": item.get("conn_strength", 5) / 10.0,  # Convert 1-10 scale to 0.0-1.0
            "reasoning": item.get("explanation", "No explanation provided"),
            "llmModel": item.get("model", "unknown"),
            "createdAt": item.get("created_at", datetime.utcnow().isoformat())
        })

    return {"connections": formatted, "count": len(formatted)}



@app.post("/connections/review")
async def review_json(review: JSONUserReview):
    """
    Process user review decision and auto-create edges in ArangoDB if approved.
    
    Workflow:
    1. Save review decision to JSON
    2. If approved/modified, create edge in ArangoDB
    3. Return success with edge details
    
    Args:
        review: Review decision from ConnectionReviewModal
        
    Returns:
        Success status and edge details if created
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database connection not available")
    
    data = load_json()

    # Parse connectionId (format: "json_0") to get array index
    try:
        index = int(review.connectionId.split("_")[1])
        entry = data["part1_responses"][index]
    except (IndexError, ValueError, KeyError) as e:
        raise HTTPException(status_code=404, detail=f"Invalid connectionId: {review.connectionId}")

    # Save review metadata to JSON
    entry["user_decision"] = review.decision
    entry["corrected_relationship"] = review.correctedRelationship
    entry["feedback"] = review.feedback
    entry["reviewed_at"] = review.reviewedAt
    entry["reviewed_by"] = review.reviewedBy
    
    save_json(data)
    
    print(f"📝 Review saved: {review.connectionId} -> {review.decision}")

    # ⭐ AUTO-CREATE EDGE IF APPROVED OR MODIFIED
    edge_result = None
    if review.decision in ["approve", "modify"]:
        try:
            # Determine final relationship type
            relationship_type = (
                review.correctedRelationship.upper() 
                if review.decision == "modify" and review.correctedRelationship
                else entry.get("type", "RELATED_TO").upper()
            )
            
            # Extract node IDs
            src_id = entry["src_node"]["_id"]
            tgt_id = entry["pair_node"]["_id"]
            
            # Calculate weight from confidence (1-10 scale -> 0.0-1.0)
            confidence_raw = entry.get("conn_strength", 5)
            weight = confidence_raw / 10.0
            
            # Generate edge key (format: sourceKey_to_targetKey)
            src_key = src_id.split("/")[-1] if "/" in src_id else src_id
            tgt_key = tgt_id.split("/")[-1] if "/" in tgt_id else tgt_id
            edge_key = f"{src_key}_to_{tgt_key}"
            
            # Build edge document with comprehensive metadata
            edge_doc = {
                "_key": edge_key,
                "_from": src_id,
                "_to": tgt_id,
                "relationship_type": relationship_type,
                "weight": weight,
                "confidence": confidence_raw,
                
                # LLM Discovery Metadata
                "discovered_by": "llm_ensemble",
                "llm_model": entry.get("model", "unknown"),
                "llm_explanation": entry.get("explanation", ""),
                "discovery_stage": "3-stage-ensemble",
                
                # Review Metadata
                "reviewed": True,
                "review_decision": review.decision,
                "reviewed_at": review.reviewedAt,
                "reviewed_by": review.reviewedBy,
                "user_feedback": review.feedback or "",
                
                # Original vs Corrected (for modify decisions)
                "original_relationship": entry.get("type", "RELATED_TO").upper() if review.decision == "modify" else None,
                "corrected_relationship": review.correctedRelationship.upper() if review.decision == "modify" else None,
                
                # Timestamps
                "created_at": datetime.utcnow().isoformat(),
                "discovered_at": entry.get("created_at", datetime.utcnow().isoformat())
            }
            
            # Create edge collection if it doesn't exist
            collection_name = relationship_type
            if not db.has_collection(collection_name):
                print(f"📦 Creating new edge collection: {collection_name}")
                db.create_collection(collection_name, edge=True)
            
            edges_collection = db.collection(collection_name)
            
            # Try update first (in case edge exists), then insert
            try:
                existing = edges_collection.get(edge_key)
                if existing:
                    # Update existing edge
                    result = edges_collection.update({
                        "_key": edge_key,
                        **edge_doc
                    })
                    print(f"🔄 Updated existing edge: {result['_id']}")
                    edge_result = {
                        "action": "updated",
                        "edge_id": result["_id"],
                        "edge_key": result["_key"]
                    }
                else:
                    raise Exception("Edge not found, will insert")
            except Exception:
                # Insert new edge
                result = edges_collection.insert(edge_doc)
                print(f"✅ Created new edge: {result['_id']}")
                edge_result = {
                    "action": "created",
                    "edge_id": result["_id"],
                    "edge_key": result["_key"]
                }
            
            # Log to edge tracking file
            with open('new_edge_keys.txt', 'a') as f:
                f.write(f"{result['_id']}\n")
            
            return {
                "success": True,
                "message": f"Review saved and edge {edge_result['action']}",
                "review_saved": True,
                "edge_created": True,
                "edge": edge_result
            }
            
        except Exception as e:
            print(f"❌ Failed to create edge from review: {e}")
            import traceback
            traceback.print_exc()
            
            # Still return success for review, but note edge creation failure
            return {
                "success": True,
                "message": "Review saved, but edge creation failed",
                "review_saved": True,
                "edge_created": False,
                "error": str(e)
            }
    
    # Rejected - no edge creation
    return {
        "success": True,
        "message": "Review saved (rejected, no edge created)",
        "review_saved": True,
        "edge_created": False
    }


@app.get("/connections/stats")
def get_json_review_stats():
    """
    Get statistics about connection review process.
    
    Returns counts and accuracy metrics for dashboard display.
    """
    data = load_json()
    items = data.get("part1_responses", [])

    reviewed = [i for i in items if "user_decision" in i]
    approved = [i for i in reviewed if i.get("user_decision") == "approve"]
    modified = [i for i in reviewed if i.get("user_decision") == "modify"]
    rejected = [i for i in reviewed if i.get("user_decision") == "reject"]
    
    # Calculate average confidence of approved edges
    if approved or modified:
        approved_confidences = [i.get("conn_strength", 5) for i in approved + modified]
        avg_approved_confidence = sum(approved_confidences) / len(approved_confidences) / 10.0
    else:
        avg_approved_confidence = 0.0
    
    # Calculate precision (approved / (approved + rejected))
    total_decided = len(approved) + len(rejected)
    precision = len(approved) / total_decided if total_decided > 0 else 0.0

    return {
        "total_pending": len(items) - len(reviewed),
        "total_reviewed": len(reviewed),
        "approved_count": len(approved),
        "rejected_count": len(rejected),
        "modified_count": len(modified),
        "accuracy_rate": precision,
        "avg_confidence": avg_approved_confidence,
        "precision": precision,
        "avg_approved_confidence": avg_approved_confidence
    }

@app.post("/connections/batch-approve")
async def batch_approve_connections(
    confidence_threshold: float = 0.8,
    max_count: int = 10,
    reviewed_by: str = "batch_automation"
):
    """
    Batch approve high-confidence connections above threshold.
    
    Useful for auto-approving very confident LLM suggestions.
    
    Args:
        confidence_threshold: Minimum confidence (0.0-1.0) to auto-approve
        max_count: Maximum number to approve in one batch
        reviewed_by: Identifier for batch reviewer
        
    Returns:
        List of approved edges with creation status
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database connection not available")
    
    data = load_json()
    items = data.get("part1_responses", [])
    
    # Filter high-confidence, unreviewed items
    candidates = [
        (idx, item) for idx, item in enumerate(items)
        if "user_decision" not in item
        and item.get("conn_strength", 0) / 10.0 >= confidence_threshold
    ][:max_count]
    
    results = []
    
    for idx, item in candidates:
        # Create fake review object
        review = JSONUserReview(
            connectionId=f"json_{idx}",
            decision="approve",
            correctedRelationship=None,
            feedback=f"Auto-approved: confidence {item.get('conn_strength', 0)/10.0:.2f}",
            reviewedAt=datetime.utcnow().isoformat(),
            reviewedBy=reviewed_by
        )
        
        # Use existing review logic
        result = await review_json(review)
        results.append({
            "connectionId": f"json_{idx}",
            "confidence": item.get("conn_strength", 0) / 10.0,
            **result
        })
    
    return {
        "success": True,
        "approved_count": len(results),
        "results": results
    }

@app.post("/connections/{connection_id}/re-analyze")
async def reanalyze_connection(connection_id: str):
    """
    Re-run LLM analysis on a specific connection.
    
    Useful when user wants a second opinion or more context.
    """
    # This would call the LLM ensemble again on the specific node pair
    # Implementation depends on whether you want to keep Ollama client available
    raise HTTPException(status_code=501, detail="Re-analysis not yet implemented")

# =====================================================
# LIBRARY MODULE ENDPOINTS
# =====================================================

@app.get("/api/library-modules")
async def get_library_modules_for_operator(
    category: Optional[str] = None,
    tactic: Optional[str] = None,
    execution_type: Optional[str] = None,
    risk_level: Optional[str] = None,
    search: Optional[str] = Query(None, description="Search term for name/description"),
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    limit: int = 100
):
    """
    Get library modules with optional filtering and search.
    
    FIXED: Now properly merges data from both ArangoDB documents AND payload files.
    Handles case-insensitive field names (inputs vs Inputs) from both sources.
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        # Build dynamic query with filters
        filters = []
        bind_vars = {"limit": limit}
        
        if category:
            filters.append("doc.category == @category")
            bind_vars["category"] = category
            
        if tactic:
            filters.append("doc.tactic == @tactic")
            bind_vars["tactic"] = tactic
        
        if execution_type:
            filters.append("doc.executionType == @execution_type")
            bind_vars["execution_type"] = execution_type
            
        if risk_level:
            filters.append("doc.riskLevel == @risk_level")
            bind_vars["risk_level"] = risk_level
            
        if search:
            filters.append(
                "(CONTAINS(LOWER(doc.name), LOWER(@search)) OR "
                "CONTAINS(LOWER(doc.description), LOWER(@search)) OR "
                "CONTAINS(LOWER(doc._key), LOWER(@search)))"
            )
            bind_vars["search"] = search
            
        if tags:
            # Handle comma-separated tags
            tag_list = [t.strip() for t in tags.split(",")]
            tag_conditions = []
            for i, tag in enumerate(tag_list):
                tag_conditions.append(f"@tag{i} IN doc.metadata.tags")
                bind_vars[f"tag{i}"] = tag
            if tag_conditions:
                filters.append(f"({' OR '.join(tag_conditions)})")
        
        filter_clause = " AND ".join(filters) if filters else "true"
        
        query = f"""
            FOR doc IN LibraryModule
                FILTER {filter_clause}
                SORT doc.name ASC
                LIMIT @limit
                RETURN doc
        """
        
        modules = list(db.aql.execute(query, bind_vars=bind_vars))
        
        print(f"📦 Found {len(modules)} modules in ArangoDB")
        
        # Payload directory
        payload_dir = os.getenv("PAYLOAD_STORAGE_DIR", "./data/payloads")
        
        enriched_modules = []
        for module in modules:
            # Start with a copy of the module
            enriched = dict(module)
            artifact_key = module.get("_key", "")
            
            # Helper function to get field with case-insensitive fallback
            def get_field(source: dict, field: str, default=None):
                """Get field checking both lowercase and capitalized versions"""
                return (
                    source.get(field) or 
                    source.get(field.capitalize()) or 
                    source.get(field[0].upper() + field[1:]) or  # Handle 'inputs' -> 'Inputs'
                    default
                )
            
            # Check what's already in the ArangoDB document
            has_inputs = bool(get_field(module, 'inputs'))
            has_outputs = bool(get_field(module, 'outputs'))
            has_parameters = bool(get_field(module, 'parameters'))
            
            # If module already has complete data, use it directly
            if has_inputs and has_outputs and has_parameters:
                print(f"  ✅ {module.get('name', artifact_key)}: Complete data in ArangoDB")
                
                # Normalize field names (ensure lowercase)
                enriched["inputs"] = get_field(module, 'inputs', [])
                enriched["outputs"] = get_field(module, 'outputs', [])
                enriched["parameters"] = get_field(module, 'parameters', [])
                enriched["requirements"] = get_field(module, 'requirements', {})
                enriched["executionType"] = get_field(module, 'executionType', 'shell_command')
                enriched["cobaltStrikeCommand"] = get_field(module, 'cobaltStrikeCommand')
                enriched["robotKeyword"] = get_field(module, 'robotKeyword')
                enriched["robotTemplate"] = get_field(module, 'robotTemplate')
                enriched["shellCommand"] = get_field(module, 'shellCommand')
                enriched["estimatedDuration"] = get_field(module, 'estimatedDuration', '1-5 min')
                enriched["subcategory"] = get_field(module, 'subcategory', '')
                enriched["icon"] = get_field(module, 'icon', '⚡')
                
            else:
                # Try to load from payload file
                payload_path = os.path.join(payload_dir, f"{artifact_key}.json")
                
                if os.path.exists(payload_path):
                    try:
                        with open(payload_path, 'r', encoding='utf-8') as f:
                            payload_data = json.load(f)
                        
                        print(f"  📄 {module.get('name', artifact_key)}: Loaded from payload file")
                        
                        # Merge payload data (payload takes precedence for these fields)
                        enriched["inputs"] = get_field(payload_data, 'inputs', [])
                        enriched["outputs"] = get_field(payload_data, 'outputs', [])
                        enriched["parameters"] = get_field(payload_data, 'parameters', [])
                        enriched["requirements"] = get_field(payload_data, 'requirements', {})
                        enriched["executionType"] = get_field(payload_data, 'executionType') or get_field(module, 'executionType', 'shell_command')
                        enriched["cobaltStrikeCommand"] = get_field(payload_data, 'cobaltStrikeCommand') or get_field(module, 'cobaltStrikeCommand')
                        enriched["robotKeyword"] = get_field(payload_data, 'robotKeyword') or get_field(module, 'robotKeyword')
                        enriched["robotTemplate"] = get_field(payload_data, 'robotTemplate') or get_field(module, 'robotTemplate')
                        enriched["shellCommand"] = get_field(payload_data, 'shellCommand') or get_field(module, 'shellCommand')
                        enriched["estimatedDuration"] = get_field(payload_data, 'estimatedDuration') or get_field(module, 'estimatedDuration', '1-5 min')
                        enriched["subcategory"] = get_field(payload_data, 'subcategory') or get_field(module, 'subcategory', '')
                        enriched["icon"] = get_field(payload_data, 'icon') or get_field(module, 'icon', '⚡')
                        
                    except Exception as e:
                        print(f"  ⚠️ {module.get('name', artifact_key)}: Payload load failed - {e}")
                        # Use defaults
                        enriched["inputs"] = []
                        enriched["outputs"] = []
                        enriched["parameters"] = []
                        enriched["requirements"] = {}
                else:
                    print(f"  ⚠️ {module.get('name', artifact_key)}: No payload file, no embedded data")
                    # No payload and no embedded data - use empty defaults
                    enriched["inputs"] = get_field(module, 'inputs', [])
                    enriched["outputs"] = get_field(module, 'outputs', [])
                    enriched["parameters"] = get_field(module, 'parameters', [])
                    enriched["requirements"] = get_field(module, 'requirements', {})
                    enriched["executionType"] = get_field(module, 'executionType', 'shell_command')
                    enriched["estimatedDuration"] = get_field(module, 'estimatedDuration', '1-5 min')
                    enriched["icon"] = get_field(module, 'icon', '⚡')
            
            enriched_modules.append(enriched)
        
        # Summary
        complete_count = sum(1 for m in enriched_modules if m.get('parameters'))
        print(f"\n✅ Returning {len(enriched_modules)} modules ({complete_count} with parameters)")
        
        return {
            "success": True,
            "count": len(enriched_modules),
            "modules": enriched_modules
        }
        
    except Exception as e:
        print(f"❌ Failed to fetch modules: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))





@app.get("/api/library-modules/{module_key}")
async def get_library_module(module_key: str):
    """
    Get a specific library module by key.
    
    Example:
    - /api/library-modules/lib_cs_mimikatz
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        collection = db.collection("LibraryModule")
        
        if not collection.has(module_key):
            raise HTTPException(status_code=404, detail=f"Module '{module_key}' not found")
        
        module = collection.get(module_key)
        
        return {
            "success": True,
            "module": module
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to fetch module: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch module: {str(e)}")


@app.get("/api/library-modules/categories")
async def get_library_module_categories():
    """
    Get all unique categories and their counts.
    
    Useful for building filter dropdowns in Operator UI.
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        query = """
            FOR doc IN LibraryModule
                COLLECT category = doc.category WITH COUNT INTO count
                SORT category
                RETURN {category: category, count: count}
        """
        
        categories = list(db.aql.execute(query))
        
        return {
            "success": True,
            "categories": categories
        }
        
    except Exception as e:
        print(f"❌ Failed to fetch categories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/library-modules/tactics")
async def get_library_module_tactics():
    """
    Get all MITRE ATT&CK tactics and their counts.
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        query = """
            FOR doc IN LibraryModule
                FILTER doc.tactic != null AND doc.tactic != 'control'
                COLLECT tactic = doc.tactic WITH COUNT INTO count
                SORT tactic
                RETURN {tactic: tactic, count: count}
        """
        
        tactics = list(db.aql.execute(query))
        
        return {
            "success": True,
            "tactics": tactics
        }
        
    except Exception as e:
        print(f"❌ Failed to fetch tactics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/library-modules/validate-requirements")
async def validate_module_requirements(
    module_key: str,
    environment: ExecutionEnvironment
):
    """
    Validate if a library module can execute in the current environment.
    
    Checks:
    - C2 server availability
    - Required listeners
    - SSH connections
    - External tools
    - Robot Framework libraries
    
    Example:
    POST /api/library-modules/validate-requirements?module_key=lib_cs_mimikatz
    {
      "has_c2_server": true,
      "active_listeners": ["http-listener-01"],
      "active_beacons": ["beacon_123"],
      "ssh_connections": [],
      "available_payloads": [],
      "external_tools": [],
      "installed_libraries": []
    }
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        collection = db.collection("LibraryModule")
        
        if not collection.has(module_key):
            raise HTTPException(status_code=404, detail=f"Module '{module_key}' not found")
        
        module = collection.get(module_key)
        requirements = module.get("requirements", {})
        
        validation_results = {
            "can_execute": True,
            "missing_requirements": [],
            "warnings": []
        }
        
        # Check C2 server
        if requirements.get("c2Server") and not environment.has_c2_server:
            validation_results["can_execute"] = False
            validation_results["missing_requirements"].append({
                "type": "c2_server",
                "message": "C2 server not connected"
            })
        
        # Check listeners
        required_listeners = requirements.get("listeners", [])
        missing_listeners = set(required_listeners) - set(environment.active_listeners)
        if missing_listeners:
            validation_results["can_execute"] = False
            validation_results["missing_requirements"].append({
                "type": "listeners",
                "message": f"Missing listeners: {', '.join(missing_listeners)}"
            })
        
        # Check SSH connections
        required_ssh = requirements.get("sshConnections", [])
        missing_ssh = set(required_ssh) - set(environment.ssh_connections)
        if missing_ssh:
            validation_results["can_execute"] = False
            validation_results["missing_requirements"].append({
                "type": "ssh_connections",
                "message": f"Missing SSH connections: {', '.join(missing_ssh)}"
            })
        
        # Check external tools
        required_tools = requirements.get("externalTools", [])
        missing_tools = set(required_tools) - set(environment.external_tools)
        if missing_tools:
            validation_results["can_execute"] = False
            validation_results["missing_requirements"].append({
                "type": "external_tools",
                "message": f"Missing tools: {', '.join(missing_tools)}"
            })
        
        # Check Robot Framework libraries
        required_libs = requirements.get("libraries", [])
        missing_libs = set(required_libs) - set(environment.installed_libraries)
        if missing_libs:
            validation_results["warnings"].append({
                "type": "libraries",
                "message": f"Missing Robot libraries: {', '.join(missing_libs)}"
            })
        
        # Check beacons for Cobalt Strike modules
        if module.get("executionType") == "cobalt_strike" and not environment.active_beacons:
            validation_results["warnings"].append({
                "type": "beacons",
                "message": "No active beacons available"
            })
        
        return {
            "success": True,
            "module_key": module_key,
            "module_name": module.get("name"),
            "validation": validation_results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to validate requirements: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/library-modules/by-execution-type/{execution_type}")
async def get_modules_by_execution_type(
    execution_type: str,
    limit: int = Query(100, le=500)
):
    """
    Get all modules of a specific execution type.
    
    Examples:
    - /api/library-modules/by-execution-type/cobalt_strike
    - /api/library-modules/by-execution-type/robot_utility
    - /api/library-modules/by-execution-type/shell_command
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        query = """
            FOR doc IN LibraryModule
                FILTER doc.executionType == @execution_type
                LIMIT @limit
                RETURN doc
        """
        
        modules = list(db.aql.execute(query, bind_vars={
            "execution_type": execution_type,
            "limit": limit
        }))
        
        return {
            "success": True,
            "execution_type": execution_type,
            "count": len(modules),
            "modules": modules
        }
        
    except Exception as e:
        print(f"❌ Failed to fetch modules by execution type: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/library-modules/stats")
async def get_library_module_stats():
    """
    Get statistics about library modules.
    
    Returns:
    - Total count
    - Count by category
    - Count by execution type
    - Count by risk level
    - Count by tactic
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        # Total count
        total_query = "RETURN LENGTH(LibraryModule)"
        total = list(db.aql.execute(total_query))[0]
        
        # By category
        category_query = """
            FOR doc IN LibraryModule
                COLLECT category = doc.category WITH COUNT INTO count
                RETURN {category: category, count: count}
        """
        by_category = list(db.aql.execute(category_query))
        
        # By execution type
        exec_type_query = """
            FOR doc IN LibraryModule
                COLLECT execType = doc.executionType WITH COUNT INTO count
                RETURN {executionType: execType, count: count}
        """
        by_execution_type = list(db.aql.execute(exec_type_query))
        
        # By risk level
        risk_query = """
            FOR doc IN LibraryModule
                COLLECT risk = doc.riskLevel WITH COUNT INTO count
                RETURN {riskLevel: risk, count: count}
        """
        by_risk_level = list(db.aql.execute(risk_query))
        
        # By tactic
        tactic_query = """
            FOR doc IN LibraryModule
                FILTER doc.tactic != null
                COLLECT tactic = doc.tactic WITH COUNT INTO count
                RETURN {tactic: tactic, count: count}
        """
        by_tactic = list(db.aql.execute(tactic_query))
        
        return {
            "success": True,
            "stats": {
                "total": total,
                "by_category": by_category,
                "by_execution_type": by_execution_type,
                "by_risk_level": by_risk_level,
                "by_tactic": by_tactic
            }
        }
        
    except Exception as e:
        print(f"❌ Failed to fetch stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Add to the root endpoint's list of endpoints
@app.get("/")
def root():
    return {
        "service": "ProtoGraph Unified API (JSON Review Mode)",
        "status": "running",
        "database": ARANGO_DB,
        "ollama_model": OLLAMA_MODEL,
        "endpoints": [
            # ... existing endpoints ...
            # Library Module endpoints
            "/api/library-modules",
            "/api/library-modules/{module_key}",
            "/api/library-modules/categories",
            "/api/library-modules/tactics",
            "/api/library-modules/validate-requirements",
            "/api/library-modules/by-execution-type/{execution_type}",
            "/api/library-modules/stats",
        ],
    }

# =====================================================
# GRAPH HEALTH & DISCOVERY ENDPOINTS
# =====================================================

@app.get("/api/graph/health")
async def get_graph_health():
    """
    Get current graph health statistics.
    
    Returns comprehensive metrics including:
    - Node/edge counts
    - Connectivity metrics (density, avg degree)
    - Clustering coefficient
    - Component analysis
    - Health status and issues
    """
    if not discovery_orchestrator:
        raise HTTPException(status_code=503, detail="Discovery engine not initialized")
    
    try:
        health = discovery_orchestrator.get_health()
        return {
            "success": True,
            "health": health.to_dict()
        }
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/discovery/check")
async def check_discovery_trigger(artifact_id: str):
    """
    Check if LLM discovery should run for a specific artifact.
    
    Returns trigger decision, reason, and candidate nodes.
    """
    if not discovery_orchestrator:
        raise HTTPException(status_code=503, detail="Discovery engine not initialized")
    
    try:
        result = discovery_orchestrator.check_discovery_needed(artifact_id)
        return {
            "success": True,
            "should_trigger": result.should_trigger,
            "reason": result.reason,
            "priority": result.priority,
            "candidates_count": len(result.candidates),
            "candidates": result.candidates,
            "health_snapshot": result.health_snapshot
        }
    except Exception as e:
        print(f"❌ Discovery check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/discovery/run")
async def run_discovery(artifact_id: str, max_candidates: int = 10):
    """
    Run LLM edge discovery for a specific artifact.
    
    This triggers the 3-stage ensemble:
    1. Binary classification
    2. Edge type classification  
    3. Confidence rating
    
    Results are returned directly (not queued).
    """
    if not discovery_orchestrator:
        raise HTTPException(status_code=503, detail="Discovery engine not initialized")
    
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama not available")
    
    try:
        result = discovery_orchestrator.process_new_artifact(artifact_id)
        
        # Also save suggestions to the pending queue (JSON file)
        if result["suggestions"]:
            _save_suggestions_to_pending(artifact_id, result["suggestions"])
        
        return {
            "success": True,
            **result
        }
    except Exception as e:
        print(f"❌ Discovery run failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def _save_suggestions_to_pending(artifact_id: str, suggestions: List[Dict]):
    """Save suggestions to pending queue for review"""
    try:
        # Load existing
        if os.path.exists(JSON_PATH):
            with open(JSON_PATH, 'r') as f:
                data = json.load(f)
        else:
            data = {"part1_responses": []}
        
        # Convert suggestions to pending format
        for sugg in suggestions:
            pending_entry = {
                "src_node": {"_id": sugg["source_id"], "name": sugg["source_label"]},
                "pair_node": {"_id": sugg["target_id"], "name": sugg["target_label"]},
                "type": sugg["relationship_type"],
                "explanation": sugg["explanation"],
                "conn_strength": int(sugg["confidence"] * 10),
                "model": sugg["model_used"],
                "created_at": sugg["discovered_at"],
                "triggered_by": artifact_id
            }
            data["part1_responses"].append(pending_entry)
        
        # Save
        with open(JSON_PATH, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"✅ Saved {len(suggestions)} suggestions to pending queue")
        
    except Exception as e:
        print(f"⚠️ Failed to save suggestions: {e}")


@app.get("/api/discovery/stats")
async def get_discovery_stats():
    """
    Get discovery system statistics.
    
    Combines graph health with pending review stats.
    """
    if not discovery_orchestrator:
        raise HTTPException(status_code=503, detail="Discovery engine not initialized")
    
    try:
        health = discovery_orchestrator.get_health()
        review_stats = get_json_review_stats()  # Existing function
        
        return {
            "success": True,
            "graph_health": {
                "status": health.status,
                "num_nodes": health.num_nodes,
                "num_edges": health.num_edges,
                "edge_density": health.edge_density,
                "clustering": health.clustering_coefficient,
                "orphans": health.num_orphan_nodes,
                "components": health.num_weakly_connected_components,
                "issues": health.issues
            },
            "review_queue": review_stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# HEALTH
# =====================================================
@app.get("/health")
def health():
    health_info = {
        "status": "ok", 
        "time": datetime.utcnow().isoformat(),
        "arango_connected": db is not None,
        "graphdb_enabled": GRAPHDB_ENABLED,
        "graphdb_connected": gdb is not None,
    }
    if gdb:
        try:
            gdb_health = gdb.health()
            health_info["graphdb"] = gdb_health
        except:
            health_info["graphdb"] = {"status": "error"}
    return health_info

# =====================================================
# MAIN ENTRYPOINT
# =====================================================
# Only include old ArangoDB ingestion router if GraphDB ingestion core is not loaded
if not GRAPHDB_ENABLED or gdb is None:
    app.include_router(ingest_router)
app.include_router(schema_router)
app.include_router(plugin_router)
plugin_data_router = create_plugin_data_router(db, "./data/payloads", gdb)
app.include_router(plugin_data_router)
# Mount ontology API — GraphDB version if available, ArangoDB fallback
if gdb:
    try:
        from ontology_graphdb import init_ontology_graphdb, router as ontology_gdb_router
        init_ontology_graphdb(gdb)
        app.include_router(ontology_gdb_router)
        print(f"✓ Ontology API (GraphDB) mounted")
    except Exception as e:
        print(f"⚠️ Ontology GraphDB API failed, falling back to ArangoDB: {e}")
        app.include_router(ontology_api.router)
else:
    app.include_router(ontology_api.router)

# Mount natural language query engine
if gdb:
    try:
        from nl_query_engine import init_query_engine, router as nl_query_router
        init_query_engine(gdb)
        app.include_router(nl_query_router)
        print(f"✓ Natural language query engine mounted at /api/query/*")
    except Exception as e:
        print(f"⚠️ NL query engine failed to load: {e}")

neural_router = NeuralGraphRouter()
create_neural_router_endpoints(app, neural_router)

try:
    hybrid_router = HybridClusterRouter()
    create_hybrid_router_endpoints(app, hybrid_router)
    print(f"✓ Hybrid cluster router v3 mounted at /api/neural-v3/*")
except Exception as e:
    print(f"⚠️ Hybrid cluster router failed to initialize: {e}")

unified_search_router = create_unified_search_router(
    db=db,
    neural_router=neural_router,
    ollama_client=ollama_client,
    ollama_model=OLLAMA_MODEL
)
app.include_router(unified_search_router)
print(f"✓ Unified search router mounted at /api/search/unified")

experiment_router = create_neural_experiment_router(neural_router)
app.include_router(experiment_router)

# Include pipeline router
if pipeline_engine:
    pipeline_router = create_pipeline_router(pipeline_engine)
    app.include_router(pipeline_router)
    print(f"✓ Pipeline router mounted at /api/pipelines")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)