"""
Neural Graph Routing - Ollama-Enabled Runner

Runs the simulation with real embeddings and SLM context generation via Ollama.

Usage:
    python -m simulation.runner_ollama --seed 42 --nodes 100 --queries 20
"""
import argparse
import time
from dataclasses import asdict
from typing import Dict, List, Tuple, Optional
import numpy as np

import sys
sys.path.insert(0, '.')

from config import (
    PROPAGATION_CONFIG, 
    AGENT_CONFIG, 
    EXPERIMENT_CONFIG,
    DOMAIN_HUBS,
    HUB_GOVERNANCE,
)
from core.propagation import PropagationEngine, PropagationResult
from core.cluster_agent import ClusterAgent, ClusterNode, DomainHub
from core.entry_selection import EntryPointSelector, EntryPointResult
from core.orchestrator import Orchestrator, update_propagation_result_with_contributions
from simulation.data_generator import SyntheticDataGenerator, SyntheticDataset, SyntheticQuery
from learning.activation_logger import ActivationLogger
from ollama_integration import OllamaClient, OllamaConfig, OLLAMA_CONFIG, embed_query


class OllamaAgentNetwork:
    """
    Agent network with Ollama-powered embeddings and context generation.
    """
    
    def __init__(self, dataset: SyntheticDataset, ollama_client: OllamaClient):
        self.dataset = dataset
        self.ollama = ollama_client
        
        # Build agents from clusters
        self.cluster_agents: Dict[str, ClusterAgent] = {}
        self.hub_agents: Dict[str, DomainHub] = {}
        
        # Agent adjacency (for propagation)
        self.agent_neighbors: Dict[str, List[Tuple[str, str]]] = {}
        
        # Indices for entry selection
        self.agent_centroids: Dict[str, np.ndarray] = {}
        self.agent_entities: Dict[str, set] = {}
        self.agent_techniques: Dict[str, set] = {}
        self.agent_terms: Dict[str, set] = {}
        
        self._build_network()
    
    def _build_network(self):
        """Build the complete agent network with Ollama embeddings."""
        node_map = {n.node_id: n for n in self.dataset.nodes}
        
        print("[Ollama] Computing embeddings for nodes...")
        
        # === STEP 1: Create cluster agents with real embeddings ===
        total_nodes = sum(len(nodes) for nodes in self.dataset.cluster_to_nodes.values())
        processed = 0
        
        for cluster_id, node_ids in self.dataset.cluster_to_nodes.items():
            agent_id = f"agent_{cluster_id}"
            
            # Build ClusterNode objects with real embeddings
            cluster_nodes = []
            cluster_embeddings = []
            
            for node_id in node_ids:
                syn_node = node_map[node_id]
                
                # Build text representation for embedding
                text_parts = [syn_node.name, syn_node.concept_type]
                if "description" in syn_node.properties:
                    text_parts.append(syn_node.properties["description"][:100])
                if "technique_id" in syn_node.properties:
                    text_parts.append(syn_node.properties["technique_id"])
                if "category" in syn_node.properties:
                    text_parts.append(syn_node.properties["category"])
                
                text = " ".join(text_parts)
                
                # Get embedding from Ollama
                embedding = self.ollama.get_embedding(text)
                
                if embedding is None:
                    # Fall back to synthetic
                    embedding = syn_node.properties.get("embedding")
                    if embedding:
                        embedding = np.array(embedding)
                
                if embedding is not None:
                    cluster_embeddings.append(embedding)
                
                cluster_nodes.append(ClusterNode(
                    node_id=syn_node.node_id,
                    concept_type=syn_node.concept_type,
                    name=syn_node.name,
                    properties=syn_node.properties,
                    embedding=embedding,
                ))
                
                processed += 1
            
            # Create agent
            agent = ClusterAgent(
                agent_id=agent_id,
                cluster_id=cluster_id,
                nodes=cluster_nodes,
            )
            self.cluster_agents[agent_id] = agent
            
            # Compute centroid from real embeddings
            if cluster_embeddings:
                centroid = np.mean(cluster_embeddings, axis=0)
                self.agent_centroids[agent_id] = centroid
                agent.centroid_embedding = centroid
            else:
                self.agent_centroids[agent_id] = agent.centroid_embedding
            
            # Store indices for entry selection
            self.agent_entities[agent_id] = set(agent.summary.top_entities)
            self.agent_techniques[agent_id] = set(agent.summary.top_techniques)
            self.agent_terms[agent_id] = set(agent.summary.top_terms)
            
            # Progress update
            if processed % 50 == 0:
                print(f"[Ollama] Processed {processed}/{total_nodes} nodes...")
        
        print(f"[Ollama] Computed embeddings for {len(self.cluster_agents)} cluster agents")
        
        # === STEP 2: Create hub agents ===
        for hub_id, domain in DOMAIN_HUBS.items():
            governed_concepts = HUB_GOVERNANCE.get(hub_id, set())
            
            governed_agents = []
            for agent_id, agent in self.cluster_agents.items():
                agent_concepts = set(agent.summary.concept_distribution.keys())
                if agent_concepts & governed_concepts:
                    governed_agents.append(agent_id)
            
            hub = DomainHub(
                hub_id=hub_id,
                domain=domain,
                governed_agents=governed_agents,
            )
            self.hub_agents[hub_id] = hub
            
            # Hub centroid = average of governed agents
            if governed_agents:
                gov_centroids = [
                    self.agent_centroids[a] for a in governed_agents 
                    if self.agent_centroids.get(a) is not None
                ]
                if gov_centroids:
                    self.agent_centroids[hub_id] = np.mean(gov_centroids, axis=0)
        
        # === STEP 3: Initialize neighbor lists ===
        for agent_id in self.cluster_agents:
            self.agent_neighbors[agent_id] = []
        for hub_id in self.hub_agents:
            self.agent_neighbors[hub_id] = []
        
        # === STEP 4: Build adjacency ===
        self._build_agent_adjacency()
    
    def _build_agent_adjacency(self):
        """Build agent-to-agent adjacency based on inter-cluster edges."""
        node_to_agent: Dict[str, str] = {}
        for agent_id, agent in self.cluster_agents.items():
            for node in agent.nodes:
                node_to_agent[node.node_id] = agent_id
        
        inter_cluster_edges: Dict[Tuple[str, str], Dict[str, int]] = {}
        
        for edge in self.dataset.edges:
            source_agent = node_to_agent.get(edge.source_id)
            target_agent = node_to_agent.get(edge.target_id)
            
            if source_agent and target_agent and source_agent != target_agent:
                key = (source_agent, target_agent)
                if key not in inter_cluster_edges:
                    inter_cluster_edges[key] = {}
                
                edge_type = edge.edge_type
                inter_cluster_edges[key][edge_type] = inter_cluster_edges[key].get(edge_type, 0) + 1
        
        for (source_agent, target_agent), edge_counts in inter_cluster_edges.items():
            dominant_type = max(edge_counts.items(), key=lambda x: x[1])[0]
            
            self.agent_neighbors[source_agent].append((target_agent, dominant_type))
            
            if (target_agent, dominant_type) not in [(n, t) for n, t in self.agent_neighbors.get(target_agent, [])]:
                self.agent_neighbors[target_agent].append((source_agent, dominant_type))
        
        # Connect hubs to governed agents
        for hub_id, hub in self.hub_agents.items():
            for governed_agent in hub.governed_agents:
                self.agent_neighbors[hub_id].append((governed_agent, "RELATED_TO"))
                self.agent_neighbors[governed_agent].append((hub_id, "RELATED_TO"))


class OllamaSimulationRunner:
    """
    Simulation runner with Ollama integration.
    """
    
    def __init__(
        self,
        seed: int = EXPERIMENT_CONFIG.random_seed,
        num_nodes: int = EXPERIMENT_CONFIG.num_nodes,
        num_queries: int = EXPERIMENT_CONFIG.num_queries,
        output_dir: str = "./logs",
        ollama_config: OllamaConfig = None,
    ):
        self.seed = seed
        self.num_nodes = num_nodes
        self.num_queries = num_queries
        self.ollama_config = ollama_config or OLLAMA_CONFIG
        
        # Components
        self.ollama = OllamaClient(self.ollama_config)
        self.dataset: Optional[SyntheticDataset] = None
        self.network: Optional[OllamaAgentNetwork] = None
        self.entry_selector: Optional[EntryPointSelector] = None
        self.propagation_engine: Optional[PropagationEngine] = None
        self.orchestrator: Optional[Orchestrator] = None
        self.logger: ActivationLogger = ActivationLogger(output_dir)
        
        # Track context generation for this query
        self._query_contexts: Dict[str, str] = {}
    
    def setup(self) -> str:
        """Initialize all components."""
        # Check Ollama health
        if self.ollama.check_health():
            print(f"[Setup] Ollama connected ({self.ollama_config.embedding_model}, {self.ollama_config.slm_model})")
        else:
            print("[Setup] WARNING: Ollama not available, using synthetic embeddings")
        
        print(f"[Setup] Generating synthetic data (seed={self.seed}, nodes={self.num_nodes})...")
        
        generator = SyntheticDataGenerator(seed=self.seed)
        self.dataset = generator.generate(
            num_nodes=self.num_nodes,
            num_queries=self.num_queries,
        )
        
        print(f"[Setup] Generated {len(self.dataset.nodes)} nodes, {len(self.dataset.edges)} edges")
        print(f"[Setup] Clusters: {len(self.dataset.cluster_to_nodes)}")
        
        # Build network with Ollama
        print("[Setup] Building agent network with Ollama embeddings...")
        self.network = OllamaAgentNetwork(self.dataset, self.ollama)
        print(f"[Setup] Created {len(self.network.cluster_agents)} cluster agents, "
              f"{len(self.network.hub_agents)} hub agents")
        
        # Initialize components
        self.entry_selector = EntryPointSelector(
            agent_centroids=self.network.agent_centroids,
            agent_entities=self.network.agent_entities,
            agent_techniques=self.network.agent_techniques,
            agent_terms=self.network.agent_terms,
            hub_agents={h: hub.domain for h, hub in self.network.hub_agents.items()},
        )
        
        self.propagation_engine = PropagationEngine(
            agent_neighbors=self.network.agent_neighbors,
            config=PROPAGATION_CONFIG,
        )
        
        self.orchestrator = Orchestrator(use_llm=False)
        
        # Start logging
        agent_to_cluster = {
            agent_id: agent.cluster_id 
            for agent_id, agent in self.network.cluster_agents.items()
        }
        
        run_id = self.logger.start_run(
            random_seed=self.seed,
            propagation_config=asdict(PROPAGATION_CONFIG),
            agent_config=asdict(AGENT_CONFIG),
            experiment_config=asdict(EXPERIMENT_CONFIG),
            num_nodes=len(self.dataset.nodes),
            num_edges=len(self.dataset.edges),
            num_clusters=len(self.dataset.cluster_to_nodes),
            num_agents=len(self.network.cluster_agents) + len(self.network.hub_agents),
            num_queries=len(self.dataset.queries),
            num_shared_entities=len(self.dataset.shared_entities),
            num_weak_bridges=len(self.dataset.weak_bridges),
            num_misleading_overlaps=len(self.dataset.misleading_overlaps),
            cluster_assignments=self.dataset.cluster_assignments,
            agent_to_cluster=agent_to_cluster,
        )
        
        print(f"[Setup] Run ID: {run_id}")
        return run_id
    
    def run_query(self, query: SyntheticQuery) -> Dict:
        """Run a single query with Ollama integration."""
        start_time = time.time()
        
        # Reset Ollama budgets for this query
        self.ollama.reset_budgets()
        self._query_contexts = {}
        
        # === STEP 1: Get real query embedding ===
        query_embedding = self.ollama.get_embedding(query.query_text)
        if query_embedding is None:
            # Fall back to synthetic
            query_embedding = self._get_synthetic_query_embedding(query)
        
        # === STEP 2: Entry point selection ===
        entry_result = self.entry_selector.select(
            query_text=query.query_text,
            query_embedding=query_embedding,
            top_k=PROPAGATION_CONFIG.top_k_entry_agents,
            include_hubs=PROPAGATION_CONFIG.include_hub_on_cold_start,
        )
        
        # === STEP 3: Propagation with Ollama context generation ===
        existing_contexts = []
        
        def relevance_fn(agent_id: str, signal: float) -> Tuple[bool, Optional[str]]:
            """Callback with Ollama context generation."""
            agent = self.network.cluster_agents.get(agent_id)
            if not agent:
                # Hub agent
                return signal >= PROPAGATION_CONFIG.activation_threshold, f"Hub: {agent_id}"
            
            # Check relevance using real embeddings
            is_relevant, score = agent.check_relevance(query_embedding, signal)
            
            if not is_relevant:
                return False, None
            
            # Generate context with Ollama SLM
            context = self.ollama.generate_context(
                cluster_summary=agent.summary.summary_text,
                query=query.query_text,
            )
            
            if context is None:
                # Fall back to deterministic
                context = agent._generate_deterministic_context(query.query_text)
            
            # Novelty check
            if not agent._passes_novelty_check(context, existing_contexts):
                return True, None  # Still activated, just no context
            
            existing_contexts.append(context)
            self._query_contexts[agent_id] = context
            
            return True, context
        
        prop_start = time.time()
        prop_result = self.propagation_engine.propagate(
            query_id=query.query_id,
            entry_agents=entry_result.selected_agents,
            entry_scores=entry_result.scores,
            relevance_fn=relevance_fn,
        )
        prop_time = (time.time() - prop_start) * 1000
        
        # === STEP 4: Collect contexts ===
        agent_contexts = {}
        for agent_id, record in prop_result.activation_records.items():
            if record.context_emitted:
                agent_contexts[agent_id] = record.context_emitted
        
        # === STEP 5: Synthesis ===
        synth_start = time.time()
        synth_result = self.orchestrator.synthesize(
            query=query.query_text,
            propagation_result=prop_result,
            agent_contexts=agent_contexts,
        )
        synth_time = (time.time() - synth_start) * 1000
        
        prop_result = update_propagation_result_with_contributions(
            prop_result, synth_result.contributing_agents
        )
        
        total_time = (time.time() - start_time) * 1000
        
        # === STEP 6: Log ===
        prop_paths = [
            {
                "source": p.source_agent,
                "target": p.target_agent,
                "strength": p.strength,
                "edge_type": p.edge_type,
                "hop": p.hop_count,
            }
            for p in prop_result.propagation_paths
        ]
        
        trace = self.logger.log_query(
            query_id=query.query_id,
            query_text=query.query_text,
            expected_clusters=query.expected_clusters,
            expected_agents=query.expected_agents,
            difficulty=query.difficulty,
            query_type=query.query_type,
            entry_method=entry_result.selection_method,
            entry_agents=entry_result.selected_agents,
            entry_scores=entry_result.scores,
            matched_entities=entry_result.matched_entities,
            activated_agents=prop_result.activated_agents,
            contributing_agents=synth_result.contributing_agents,
            dormant_agents=prop_result.dormant_agents,
            subthreshold_agents=prop_result.subthreshold_agents,
            propagation_paths=prop_paths,
            total_signals=prop_result.total_signals_sent,
            max_hop_reached=prop_result.max_hop_reached,
            propagation_time_ms=prop_time,
            synthesis_time_ms=synth_time,
            total_time_ms=total_time,
            truncated_by_max_agents=prop_result.truncated_by_max_agents,
            truncated_by_max_hops=prop_result.truncated_by_max_hops,
        )
        
        return {
            "query_id": query.query_id,
            "activated": len(prop_result.activated_agents),
            "contributed": len(synth_result.contributing_agents),
            "precision": trace.precision_at_k,
            "recall": trace.recall,
            "rescued": trace.propagation_rescued,
            "time_ms": total_time,
        }
    
    def _get_synthetic_query_embedding(self, query: SyntheticQuery) -> np.ndarray:
        """Fall back to synthetic embedding."""
        centroids = []
        for cluster_id in query.expected_clusters:
            agent_id = f"agent_{cluster_id}"
            centroid = self.network.agent_centroids.get(agent_id)
            if centroid is not None:
                centroids.append(centroid)
        
        if centroids:
            base = np.mean(centroids, axis=0)
            noise = np.random.randn(len(base)) * 0.1
            embedding = base + noise
            return embedding / np.linalg.norm(embedding)
        else:
            embedding = np.random.randn(768)
            return embedding / np.linalg.norm(embedding)
    
    def run(self) -> Dict:
        """Run the complete experiment."""
        run_id = self.setup()
        
        print(f"\n[Run] Starting {len(self.dataset.queries)} queries...")
        
        results = []
        for i, query in enumerate(self.dataset.queries):
            result = self.run_query(query)
            results.append(result)
            
            if (i + 1) % 10 == 0:
                avg_precision = np.mean([r["precision"] for r in results if r["precision"]])
                avg_recall = np.mean([r["recall"] for r in results if r["recall"]])
                avg_time = np.mean([r["time_ms"] for r in results])
                pct_rescued = sum(1 for r in results if r["rescued"]) / len(results)
                print(f"[Run] {i+1}/{len(self.dataset.queries)} - "
                      f"P@K: {avg_precision:.3f}, R: {avg_recall:.3f}, "
                      f"Rescued: {pct_rescued:.1%}, Time: {avg_time:.0f}ms")
        
        summary = self.logger.end_run()
        
        print(f"\n[Complete] Run {run_id} finished")
        print(f"  Mean activation sparsity: {summary.mean_activation_sparsity:.1%}")
        print(f"  Mean precision@K: {summary.mean_precision_at_k:.3f}")
        print(f"  Mean recall: {summary.mean_recall:.3f}")
        print(f"  Propagation rescued: {summary.pct_propagation_rescued:.1%}")
        print(f"  Mean time: {summary.mean_total_time_ms:.1f}ms")
        
        return asdict(summary)


def main():
    import os
    
    parser = argparse.ArgumentParser(description="Run neural graph routing with Ollama")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--nodes", type=int, default=100, help="Number of nodes")
    parser.add_argument("--queries", type=int, default=20, help="Number of queries")
    parser.add_argument("--output", type=str, default="./logs", help="Output directory")
    parser.add_argument("--ollama-url", type=str, 
                       default=os.getenv("OLLAMA_HOST", "http://10.10.80.99:4001"), 
                       help="Ollama URL")
    parser.add_argument("--embedding-model", type=str, 
                       default=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text:latest"), 
                       help="Embedding model")
    parser.add_argument("--slm-model", type=str, 
                       default=os.getenv("OLLAMA_SLM_MODEL", "gemma2:2b"), 
                       help="SLM model")
    
    args = parser.parse_args()
    
    # Configure Ollama
    config = OllamaConfig(
        base_url=args.ollama_url,
        embedding_model=args.embedding_model,
        slm_model=args.slm_model,
    )
    
    runner = OllamaSimulationRunner(
        seed=args.seed,
        num_nodes=args.nodes,
        num_queries=args.queries,
        output_dir=args.output,
        ollama_config=config,
    )
    
    summary = runner.run()
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    print(f"\nBy Difficulty:")
    for diff, metrics in summary.get("metrics_by_difficulty", {}).items():
        print(f"  {diff}: P@K={metrics['mean_precision']:.3f}, "
              f"R={metrics['mean_recall']:.3f}, "
              f"Rescued={metrics['pct_propagation_rescued']:.1%}")


if __name__ == "__main__":
    main()