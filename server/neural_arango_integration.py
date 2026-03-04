"""
Neural Graph Router - ArangoDB Integration
==========================================

Integrates the neural graph routing system with ProtoGraph's ArangoDB backend.

This module:
1. Fetches real graph data from ArangoDB
2. Runs community detection to identify natural clusters
3. Spawns cluster agents for each community
4. Provides neural search capabilities

Add to your unified_api.py or run standalone.
"""

import os
import json
import hashlib
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import numpy as np

# ArangoDB
from arango import ArangoClient

# For embeddings
import requests

# =============================================================================
# CONFIGURATION
# =============================================================================

ARANGO_HOST = os.getenv("ARANGO_HOST", "http://localhost:8529")
ARANGO_DB = os.getenv("ARANGO_DB", "AUTO_DB")
ARANGO_USER = os.getenv("ARANGO_USER", "root")
ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD", "devpass")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://10.10.80.99:4001")
EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text:latest")
SLM_MODEL = os.getenv("OLLAMA_SLM_MODEL", "gemma2:2b")

# Schema collections to exclude from neural routing
SCHEMA_COLLECTIONS = {
    'ontology_concepts', 'concepts', 'ontology_taxonomies',
    'taxonomy_schemes', 'taxonomy_terms', 'taxonomies',
    'ontology_relationships', 'ontology_edges', 'relationship_types',
    'ontology_properties', 'schema_definitions', 'system_config', 'meta',
}

# Edge collections
EDGE_COLLECTIONS = {
    'CONTAINS', 'PRODUCES', 'REFERENCES', 'LEADS_TO', 'STARTS_WITH',
    'IMPLEMENTS', 'TESTED_BY', 'AUTHORED', 'OWNED_BY', 'USES',
    'DEPENDS_ON', 'RELATES_TO', 'SUBTECHNIQUE_OF', 'ontology_edges',
}

# Propagation weights by relationship type
PROPAGATION_WEIGHTS = {
    'IMPLEMENTS': 0.9,
    'SUBTECHNIQUE_OF': 0.95,
    'TESTED_BY': 0.8,
    'USES': 0.7,
    'DEPENDS_ON': 0.7,
    'REFERENCES': 0.6,
    'RELATES_TO': 0.5,
    'AUTHORED': 0.4,
    'OWNED_BY': 0.3,
    'CONTAINS': 0.6,
    'PRODUCES': 0.7,
    'LEADS_TO': 0.5,
    'STARTS_WITH': 0.4,
}

# Neural routing thresholds
ACTIVATION_THRESHOLD = 0.3
MAX_HOPS = 4
MAX_ACTIVE_AGENTS = 15
MAX_OUTGOING_PER_AGENT = 5
SIGNAL_DECAY = 0.7
ACCUMULATION_CEILING = 2.0

# Minimum cluster size to spawn an agent
MIN_CLUSTER_SIZE = 2


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class GraphNode:
    """Node from ArangoDB"""
    id: str
    label: str
    type: str
    cluster: str
    properties: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[np.ndarray] = None


@dataclass
class GraphEdge:
    """Edge from ArangoDB"""
    id: str
    source: str
    target: str
    edge_type: str
    weight: float = 1.0


@dataclass
class ClusterSummary:
    """Summary of a cluster for agent context"""
    cluster_id: str
    node_count: int
    node_types: Dict[str, int]
    sample_labels: List[str]
    keywords: List[str]
    summary_text: str
    centroid_embedding: Optional[np.ndarray] = None


@dataclass
class ClusterAgent:
    """Agent responsible for a cluster of nodes"""
    agent_id: str
    cluster_id: str
    node_ids: Set[str]
    summary: ClusterSummary
    neighbor_agents: Set[str] = field(default_factory=set)
    activation_count: int = 0
    
    def is_relevant(self, query_embedding: np.ndarray, threshold: float = ACTIVATION_THRESHOLD) -> Tuple[bool, float]:
        """Check if this agent's cluster is relevant to the query"""
        if self.summary.centroid_embedding is None:
            return False, 0.0
        
        # Cosine similarity
        dot = np.dot(query_embedding, self.summary.centroid_embedding)
        norm = np.linalg.norm(query_embedding) * np.linalg.norm(self.summary.centroid_embedding)
        similarity = dot / norm if norm > 0 else 0.0
        
        return similarity >= threshold, float(similarity)


@dataclass
class ActivationResult:
    """Result of neural routing activation"""
    query: str
    entry_agents: List[str]
    activated_agents: List[str]
    contributing_agents: List[str]
    propagation_path: List[Dict[str, Any]]
    contexts: Dict[str, str]
    total_time_ms: float


# =============================================================================
# OLLAMA CLIENT
# =============================================================================

class OllamaClient:
    """Client for Ollama embeddings and SLM generation"""
    
    def __init__(self, host: str = OLLAMA_HOST):
        self.host = host.rstrip('/')
        self.embedding_cache: Dict[str, np.ndarray] = {}
    
    def health_check(self) -> bool:
        """Check if Ollama is available"""
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def get_embedding(self, text: str, model: str = EMBEDDING_MODEL) -> Optional[np.ndarray]:
        """Get embedding for text"""
        # Check cache
        cache_key = hashlib.md5(f"{model}:{text}".encode()).hexdigest()
        if cache_key in self.embedding_cache:
            return self.embedding_cache[cache_key]
        
        try:
            response = requests.post(
                f"{self.host}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=30
            )
            if response.status_code == 200:
                embedding = np.array(response.json()["embedding"])
                self.embedding_cache[cache_key] = embedding
                return embedding
        except Exception as e:
            print(f"⚠️ Embedding error: {e}")
        
        return None
    
    def generate_context(self, cluster_summary: str, query: str, model: str = SLM_MODEL) -> str:
        """Generate context statement for a cluster given a query"""
        prompt = f"""You are an expert on this knowledge cluster:
{cluster_summary}

Query: {query}

In ONE sentence (max 25 words), explain how this cluster relates to the query.
If not relevant, respond with exactly: NOT_RELEVANT"""

        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 60, "temperature": 0.3}
                },
                timeout=60
            )
            if response.status_code == 200:
                return response.json().get("response", "").strip()
        except Exception as e:
            print(f"⚠️ Generation error: {e}")
        
        return "NOT_RELEVANT"


# =============================================================================
# ARANGO GRAPH LOADER
# =============================================================================

class ArangoGraphLoader:
    """Loads graph data from ArangoDB"""
    
    def __init__(self):
        self.client = ArangoClient(hosts=ARANGO_HOST)
        self.db = self.client.db(ARANGO_DB, username=ARANGO_USER, password=ARANGO_PASSWORD)
        print(f"✓ Connected to ArangoDB: {ARANGO_DB}")
    
    def load_data_nodes(self) -> List[GraphNode]:
        """Load all data nodes (excluding schema)"""
        nodes = []
        
        all_collections = [c['name'] for c in self.db.collections() 
                          if not c['name'].startswith('_')]
        
        # Filter to data collections only
        data_collections = [c for c in all_collections 
                           if c not in SCHEMA_COLLECTIONS 
                           and c not in EDGE_COLLECTIONS]
        
        print(f"📊 Loading nodes from {len(data_collections)} data collections...")
        
        for coll_name in data_collections:
            try:
                query = f"FOR doc IN `{coll_name}` RETURN doc"
                docs = list(self.db.aql.execute(query))
                
                for doc in docs:
                    nodes.append(GraphNode(
                        id=doc["_id"],
                        label=doc.get("name", doc.get("label", doc.get("_key", ""))),
                        type=coll_name,
                        cluster=doc.get("cluster", "unknown"),
                        properties={k: v for k, v in doc.items() 
                                   if k not in ['_id', '_key', '_rev']}
                    ))
            except Exception as e:
                print(f"⚠️ Error loading {coll_name}: {e}")
        
        print(f"✓ Loaded {len(nodes)} data nodes")
        return nodes
    
    def load_edges(self, node_ids: Set[str]) -> List[GraphEdge]:
        """Load edges between the given nodes"""
        edges = []
        
        all_collections = [c['name'] for c in self.db.collections() 
                          if not c['name'].startswith('_')]
        
        edge_colls = [c for c in EDGE_COLLECTIONS if c in all_collections and c != 'ontology_edges']
        
        print(f"📊 Loading edges from {len(edge_colls)} edge collections...")
        
        for edge_coll in edge_colls:
            try:
                query = f"FOR e IN `{edge_coll}` RETURN e"
                edge_docs = list(self.db.aql.execute(query))
                
                for e in edge_docs:
                    if e["_from"] in node_ids and e["_to"] in node_ids:
                        edges.append(GraphEdge(
                            id=e["_id"],
                            source=e["_from"],
                            target=e["_to"],
                            edge_type=edge_coll,
                            weight=e.get("weight", 1.0)
                        ))
            except Exception as e:
                print(f"⚠️ Error loading edges from {edge_coll}: {e}")
        
        print(f"✓ Loaded {len(edges)} edges")
        return edges


# =============================================================================
# COMMUNITY DETECTION
# =============================================================================

class CommunityDetector:
    """Detects communities/clusters in the graph using label propagation"""
    
    def detect_communities(self, nodes: List[GraphNode], edges: List[GraphEdge]) -> Dict[str, str]:
        """
        Detect communities and return node_id -> community_id mapping.
        Uses a simple label propagation algorithm.
        """
        if not nodes:
            return {}
        
        # Build adjacency list
        adjacency: Dict[str, Set[str]] = defaultdict(set)
        for edge in edges:
            adjacency[edge.source].add(edge.target)
            adjacency[edge.target].add(edge.source)
        
        # Initialize each node with its own community
        communities = {node.id: node.id for node in nodes}
        
        # Label propagation iterations
        max_iterations = 10
        for iteration in range(max_iterations):
            changed = False
            
            # Process nodes in random order
            node_ids = list(communities.keys())
            np.random.shuffle(node_ids)
            
            for node_id in node_ids:
                neighbors = adjacency.get(node_id, set())
                if not neighbors:
                    continue
                
                # Count neighbor community labels
                label_counts: Dict[str, int] = defaultdict(int)
                for neighbor in neighbors:
                    label_counts[communities[neighbor]] += 1
                
                # Adopt most common neighbor label
                if label_counts:
                    best_label = max(label_counts, key=label_counts.get)
                    if communities[node_id] != best_label:
                        communities[node_id] = best_label
                        changed = True
            
            if not changed:
                print(f"   Community detection converged at iteration {iteration + 1}")
                break
        
        # Normalize community IDs to sequential integers
        unique_communities = list(set(communities.values()))
        community_map = {old: f"cluster_{i}" for i, old in enumerate(unique_communities)}
        
        normalized = {node_id: community_map[comm] for node_id, comm in communities.items()}
        
        # Count communities
        comm_sizes = defaultdict(int)
        for comm in normalized.values():
            comm_sizes[comm] += 1
        
        print(f"✓ Detected {len(unique_communities)} communities")
        print(f"   Sizes: {dict(sorted(comm_sizes.items(), key=lambda x: -x[1])[:10])}")
        
        return normalized


# =============================================================================
# NEURAL GRAPH ROUTER
# =============================================================================

class NeuralGraphRouter:
    """
    Main neural graph routing system.
    Manages cluster agents and handles query routing.
    """
    
    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        self.ollama = ollama_client or OllamaClient()
        self.loader = ArangoGraphLoader()
        self.detector = CommunityDetector()
        
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[GraphEdge] = []
        self.agents: Dict[str, ClusterAgent] = {}
        self.node_to_agent: Dict[str, str] = {}
        self.agent_adjacency: Dict[str, Set[str]] = defaultdict(set)
        
        self._initialized = False
    
    def initialize(self, force_reload: bool = False) -> bool:
        """Initialize the router by loading data and creating agents"""
        if self._initialized and not force_reload:
            return True
        
        print("\n" + "="*60)
        print("NEURAL GRAPH ROUTER - INITIALIZATION")
        print("="*60)
        
        # Check Ollama
        if not self.ollama.health_check():
            print("⚠️ Ollama not available - using synthetic embeddings")
        
        # Load nodes
        nodes = self.loader.load_data_nodes()
        if not nodes:
            print("⚠️ No data nodes found - router will be empty")
            self._initialized = True
            return True
        
        self.nodes = {n.id: n for n in nodes}
        
        # Load edges
        node_ids = set(self.nodes.keys())
        self.edges = self.loader.load_edges(node_ids)
        
        # Detect communities
        print("\n🔍 Detecting communities...")
        communities = self.detector.detect_communities(nodes, self.edges)
        
        # Group nodes by community
        community_nodes: Dict[str, List[GraphNode]] = defaultdict(list)
        for node_id, comm_id in communities.items():
            community_nodes[comm_id].append(self.nodes[node_id])
        
        # Create agents for each community
        print(f"\n🤖 Creating cluster agents...")
        for comm_id, comm_nodes in community_nodes.items():
            if len(comm_nodes) < MIN_CLUSTER_SIZE:
                continue
            
            agent = self._create_agent(comm_id, comm_nodes)
            self.agents[agent.agent_id] = agent
            
            for node in comm_nodes:
                self.node_to_agent[node.id] = agent.agent_id
        
        print(f"✓ Created {len(self.agents)} cluster agents")
        
        # Build agent adjacency (agents are neighbors if their clusters share edges)
        self._build_agent_adjacency()
        
        self._initialized = True
        print("\n✅ Neural Graph Router initialized")
        print(f"   Nodes: {len(self.nodes)}")
        print(f"   Edges: {len(self.edges)}")
        print(f"   Agents: {len(self.agents)}")
        
        return True
    
    def _create_agent(self, cluster_id: str, nodes: List[GraphNode]) -> ClusterAgent:
        """Create a cluster agent for the given nodes"""
        # Build summary
        node_types: Dict[str, int] = defaultdict(int)
        for node in nodes:
            node_types[node.type] += 1
        
        sample_labels = [n.label for n in nodes[:10] if n.label]
        
        # Extract keywords from labels and properties
        keywords = set()
        for node in nodes:
            if node.label:
                keywords.update(node.label.lower().split('_'))
                keywords.update(node.label.lower().split())
            for key, value in node.properties.items():
                if isinstance(value, str) and len(value) < 50:
                    keywords.add(value.lower())
        
        keywords = [k for k in keywords if len(k) > 2][:20]
        
        # Generate summary text
        type_str = ", ".join([f"{count} {t}" for t, count in sorted(node_types.items(), key=lambda x: -x[1])[:3]])
        summary_text = f"Cluster with {len(nodes)} nodes: {type_str}. Sample items: {', '.join(sample_labels[:5])}. Keywords: {', '.join(keywords[:10])}"
        
        # Compute centroid embedding
        centroid = None
        if self.ollama.health_check():
            embeddings = []
            for node in nodes[:20]:  # Sample for efficiency
                text = f"{node.label} {node.type} {' '.join(str(v) for v in node.properties.values() if isinstance(v, str))}"
                emb = self.ollama.get_embedding(text[:500])
                if emb is not None:
                    embeddings.append(emb)
            
            if embeddings:
                centroid = np.mean(embeddings, axis=0)
        
        summary = ClusterSummary(
            cluster_id=cluster_id,
            node_count=len(nodes),
            node_types=dict(node_types),
            sample_labels=sample_labels,
            keywords=keywords,
            summary_text=summary_text,
            centroid_embedding=centroid
        )
        
        return ClusterAgent(
            agent_id=f"agent_{cluster_id}",
            cluster_id=cluster_id,
            node_ids={n.id for n in nodes},
            summary=summary
        )
    
    def _build_agent_adjacency(self):
        """Build adjacency map between agents based on inter-cluster edges"""
        self.agent_adjacency.clear()
        
        for edge in self.edges:
            source_agent = self.node_to_agent.get(edge.source)
            target_agent = self.node_to_agent.get(edge.target)
            
            if source_agent and target_agent and source_agent != target_agent:
                self.agent_adjacency[source_agent].add(target_agent)
                self.agent_adjacency[target_agent].add(source_agent)
        
        print(f"✓ Built agent adjacency graph")
        for agent_id, neighbors in self.agent_adjacency.items():
            if neighbors:
                print(f"   {agent_id} -> {len(neighbors)} neighbors")
    
    def search(self, query: str, top_k: int = 5) -> ActivationResult:
        """
        Execute neural search with sparse activation and propagation.
        
        Args:
            query: The search query
            top_k: Number of entry agents to select
        
        Returns:
            ActivationResult with contexts and paths
        """
        import time
        start_time = time.time()
        
        if not self._initialized:
            self.initialize()
        
        if not self.agents:
            return ActivationResult(
                query=query,
                entry_agents=[],
                activated_agents=[],
                contributing_agents=[],
                propagation_path=[],
                contexts={},
                total_time_ms=0
            )
        
        print(f"\n🔍 Neural search: '{query[:50]}...'")
        
        # Get query embedding
        query_embedding = self.ollama.get_embedding(query)
        if query_embedding is None:
            print("⚠️ Could not get query embedding")
            # Fall back to keyword matching
            return self._keyword_search(query)
        
        # STAGE 1: Entry point selection (top-K by embedding similarity)
        agent_scores: List[Tuple[str, float]] = []
        for agent_id, agent in self.agents.items():
            relevant, score = agent.is_relevant(query_embedding, threshold=0.0)
            agent_scores.append((agent_id, score))
        
        agent_scores.sort(key=lambda x: -x[1])
        entry_agents = [aid for aid, score in agent_scores[:top_k] if score >= ACTIVATION_THRESHOLD]
        
        if not entry_agents:
            # Take top agent even if below threshold
            entry_agents = [agent_scores[0][0]] if agent_scores else []
        
        print(f"   Entry agents: {entry_agents}")
        
        # STAGE 2: Propagation
        activated_agents: Set[str] = set(entry_agents)
        propagation_path: List[Dict[str, Any]] = []
        agent_signals: Dict[str, float] = {aid: agent_scores[i][1] for i, (aid, _) in enumerate(agent_scores) if aid in entry_agents}
        
        # BFS propagation with signal decay
        queue = [(aid, 0, agent_signals.get(aid, 0.5)) for aid in entry_agents]
        visited_at_depth: Dict[str, int] = {aid: 0 for aid in entry_agents}
        
        while queue and len(activated_agents) < MAX_ACTIVE_AGENTS:
            current_agent, depth, incoming_signal = queue.pop(0)
            
            if depth >= MAX_HOPS:
                continue
            
            # Get neighbors
            neighbors = self.agent_adjacency.get(current_agent, set())
            propagations = 0
            
            for neighbor in neighbors:
                if propagations >= MAX_OUTGOING_PER_AGENT:
                    break
                
                if neighbor in visited_at_depth and visited_at_depth[neighbor] <= depth:
                    continue
                
                # Calculate propagated signal
                # Use edge weight if available (simplified: use default)
                edge_weight = PROPAGATION_WEIGHTS.get('RELATES_TO', 0.5)
                propagated_signal = min(incoming_signal * edge_weight * SIGNAL_DECAY, ACCUMULATION_CEILING)
                
                if propagated_signal >= ACTIVATION_THRESHOLD:
                    if neighbor not in activated_agents:
                        activated_agents.add(neighbor)
                        visited_at_depth[neighbor] = depth + 1
                        agent_signals[neighbor] = propagated_signal
                        
                        propagation_path.append({
                            "from": current_agent,
                            "to": neighbor,
                            "depth": depth + 1,
                            "signal": propagated_signal
                        })
                        
                        queue.append((neighbor, depth + 1, propagated_signal))
                        propagations += 1
        
        print(f"   Activated: {len(activated_agents)} agents")
        
        # STAGE 3: Generate contexts from activated agents
        contexts: Dict[str, str] = {}
        contributing_agents: List[str] = []
        
        for agent_id in activated_agents:
            agent = self.agents[agent_id]
            agent.activation_count += 1
            
            context = self.ollama.generate_context(agent.summary.summary_text, query)
            
            if context and context != "NOT_RELEVANT":
                contexts[agent_id] = context
                contributing_agents.append(agent_id)
        
        print(f"   Contributing: {len(contributing_agents)} agents")
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        return ActivationResult(
            query=query,
            entry_agents=entry_agents,
            activated_agents=list(activated_agents),
            contributing_agents=contributing_agents,
            propagation_path=propagation_path,
            contexts=contexts,
            total_time_ms=elapsed_ms
        )
    
    def _keyword_search(self, query: str) -> ActivationResult:
        """Fallback keyword-based search when embeddings unavailable"""
        query_terms = set(query.lower().split())
        
        matches: List[Tuple[str, int]] = []
        for agent_id, agent in self.agents.items():
            score = len(query_terms.intersection(set(agent.summary.keywords)))
            if score > 0:
                matches.append((agent_id, score))
        
        matches.sort(key=lambda x: -x[1])
        entry_agents = [aid for aid, _ in matches[:3]]
        
        return ActivationResult(
            query=query,
            entry_agents=entry_agents,
            activated_agents=entry_agents,
            contributing_agents=entry_agents,
            propagation_path=[],
            contexts={aid: self.agents[aid].summary.summary_text for aid in entry_agents},
            total_time_ms=0
        )
    
    def get_agent_info(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific agent"""
        agent = self.agents.get(agent_id)
        if not agent:
            return None
        
        return {
            "agent_id": agent.agent_id,
            "cluster_id": agent.cluster_id,
            "node_count": len(agent.node_ids),
            "node_ids": list(agent.node_ids)[:20],
            "summary": agent.summary.summary_text,
            "keywords": agent.summary.keywords,
            "node_types": agent.summary.node_types,
            "neighbor_agents": list(self.agent_adjacency.get(agent_id, set())),
            "activation_count": agent.activation_count,
        }
    
    def get_all_agents(self) -> List[Dict[str, Any]]:
        """Get summary of all agents"""
        return [
            {
                "agent_id": agent.agent_id,
                "cluster_id": agent.cluster_id,
                "node_count": len(agent.node_ids),
                "keywords": agent.summary.keywords[:5],
                "activation_count": agent.activation_count,
            }
            for agent in self.agents.values()
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get router statistics"""
        return {
            "initialized": self._initialized,
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "total_agents": len(self.agents),
            "agent_stats": {
                aid: {
                    "nodes": len(a.node_ids),
                    "activations": a.activation_count
                }
                for aid, a in self.agents.items()
            }
        }


# =============================================================================
# FASTAPI ENDPOINTS
# =============================================================================

def create_neural_router_endpoints(app, router: NeuralGraphRouter):
    """
    Add neural router endpoints to a FastAPI app.
    
    Usage:
        from neural_arango_integration import NeuralGraphRouter, create_neural_router_endpoints
        
        router = NeuralGraphRouter()
        create_neural_router_endpoints(app, router)
    """
    from fastapi import Query
    
    @app.get("/api/neural/health")
    def neural_health():
        """Check neural router health"""
        return {
            "status": "ok",
            "initialized": router._initialized,
            "agents": len(router.agents),
            "nodes": len(router.nodes),
        }
    
    @app.post("/api/neural/initialize")
    def neural_initialize(force: bool = False):
        """Initialize or reinitialize the neural router"""
        success = router.initialize(force_reload=force)
        return {
            "success": success,
            "stats": router.get_stats()
        }
    
    @app.get("/api/neural/search")
    def neural_search(
        q: str = Query(..., description="Search query"),
        top_k: int = Query(5, description="Number of entry agents")
    ):
        """Execute neural search"""
        result = router.search(q, top_k=top_k)
        return {
            "query": result.query,
            "entry_agents": result.entry_agents,
            "activated_agents": result.activated_agents,
            "contributing_agents": result.contributing_agents,
            "propagation_path": result.propagation_path,
            "contexts": result.contexts,
            "time_ms": result.total_time_ms,
        }
    
    @app.get("/api/neural/agents")
    def neural_agents():
        """Get all agents"""
        return {
            "agents": router.get_all_agents(),
            "total": len(router.agents)
        }
    
    @app.get("/api/neural/agent/{agent_id}")
    def neural_agent_info(agent_id: str):
        """Get info about a specific agent"""
        info = router.get_agent_info(agent_id)
        if not info:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        return info
    
    @app.get("/api/neural/stats")
    def neural_stats():
        """Get router statistics"""
        return router.get_stats()
    
    print("✓ Neural router endpoints registered at /api/neural/*")


# =============================================================================
# STANDALONE TEST
# =============================================================================

if __name__ == "__main__":
    print("Testing Neural Graph Router with ArangoDB...")
    
    # Create router
    router = NeuralGraphRouter()
    
    # Initialize
    router.initialize()
    
    # Print stats
    stats = router.get_stats()
    print(f"\n📊 Router Stats:")
    print(f"   Nodes: {stats['total_nodes']}")
    print(f"   Edges: {stats['total_edges']}")
    print(f"   Agents: {stats['total_agents']}")
    
    if stats['total_agents'] > 0:
        # Test search
        test_query = "credential dumping mimikatz"
        print(f"\n🔍 Test search: '{test_query}'")
        
        result = router.search(test_query)
        print(f"   Entry agents: {result.entry_agents}")
        print(f"   Activated: {len(result.activated_agents)}")
        print(f"   Contributing: {len(result.contributing_agents)}")
        print(f"   Time: {result.total_time_ms:.1f}ms")
        
        if result.contexts:
            print(f"\n   Contexts:")
            for agent_id, context in result.contexts.items():
                print(f"   [{agent_id}]: {context[:100]}...")
    else:
        print("\n⚠️ No agents created - ingest some data first!")
