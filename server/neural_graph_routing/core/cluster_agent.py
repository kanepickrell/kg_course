"""
Neural Graph Routing - Cluster Agent

Each agent owns a cluster of nodes and decides:
1. Is a query relevant to my cluster? (gated by incoming signal)
2. If yes, emit a concise context statement

PHASE 1: Deterministic summaries from node fields
PHASE 2: SLM-generated summaries (only after routing is proven)

ENFORCEMENT:
- No compute unless incoming_signal >= activation_threshold
- Context must be concise (max_context_tokens)
- Novelty check prevents duplicate/near-duplicate emissions
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
import numpy as np
from collections import Counter

from config import AGENT_CONFIG, PROPAGATION_CONFIG, AgentConfig


@dataclass
class ClusterNode:
    """A node belonging to a cluster."""
    node_id: str
    concept_type: str
    name: str
    properties: Dict[str, any]
    embedding: Optional[np.ndarray] = None


@dataclass
class ClusterSummary:
    """Deterministic summary of a cluster's contents."""
    total_nodes: int
    concept_distribution: Dict[str, int]  # concept_type -> count
    top_entities: List[str]               # Most frequent named entities
    top_techniques: List[str]             # MITRE technique IDs if present
    top_terms: List[str]                  # High-frequency terms
    summary_text: str                     # Human-readable summary


class ClusterAgent:
    """
    An agent responsible for a cluster of graph nodes.
    
    RULES:
    1. Cannot compute (embedding similarity, context generation) unless
       incoming signal meets activation threshold.
    2. Must emit concise context (< max_context_tokens).
    3. Must pass novelty check before emitting.
    """
    
    def __init__(
        self,
        agent_id: str,
        cluster_id: str,
        nodes: List[ClusterNode],
        config: AgentConfig = AGENT_CONFIG,
    ):
        self.agent_id = agent_id
        self.cluster_id = cluster_id
        self.nodes = nodes
        self.config = config
        
        # Build deterministic summary (Phase 1)
        self.summary = self._build_deterministic_summary()
        
        # Compute cluster centroid embedding
        self.centroid_embedding = self._compute_centroid()
        
        # For novelty checking
        self._emitted_contexts: List[str] = []
    
    def _build_deterministic_summary(self) -> ClusterSummary:
        """
        Build summary from node fields. No LLM.
        This is Phase 1 - deterministic and fast.
        """
        # Concept type distribution
        concept_counts = Counter(n.concept_type for n in self.nodes)
        
        # Extract entities (names)
        all_names = [n.name for n in self.nodes if n.name]
        name_counts = Counter(all_names)
        top_entities = [name for name, _ in name_counts.most_common(5)]
        
        # Extract techniques (if present in properties)
        techniques = []
        for n in self.nodes:
            if "technique_id" in n.properties:
                techniques.append(n.properties["technique_id"])
            if "tactic" in n.properties:
                techniques.append(n.properties["tactic"])
        technique_counts = Counter(techniques)
        top_techniques = [t for t, _ in technique_counts.most_common(5)]
        
        # Extract common terms from names and descriptions
        all_terms = []
        for n in self.nodes:
            if n.name:
                all_terms.extend(n.name.lower().split())
            if "description" in n.properties:
                all_terms.extend(n.properties["description"].lower().split()[:20])
        
        # Filter stopwords
        stopwords = {"the", "a", "an", "is", "are", "for", "to", "of", "and", "in", "on", "with"}
        filtered_terms = [t for t in all_terms if t not in stopwords and len(t) > 2]
        term_counts = Counter(filtered_terms)
        top_terms = [t for t, _ in term_counts.most_common(10)]
        
        # Build summary text
        concept_str = ", ".join(f"{count} {ctype}" for ctype, count in concept_counts.most_common(3))
        entity_str = ", ".join(top_entities[:3]) if top_entities else "various items"
        technique_str = f" Techniques: {', '.join(top_techniques[:3])}." if top_techniques else ""
        
        summary_text = f"Cluster with {concept_str}. Key items: {entity_str}.{technique_str}"
        
        return ClusterSummary(
            total_nodes=len(self.nodes),
            concept_distribution=dict(concept_counts),
            top_entities=top_entities,
            top_techniques=top_techniques,
            top_terms=top_terms,
            summary_text=summary_text,
        )
    
    def _compute_centroid(self) -> Optional[np.ndarray]:
        """Compute mean embedding of all nodes with embeddings."""
        embeddings = [n.embedding for n in self.nodes if n.embedding is not None]
        if not embeddings:
            return None
        return np.mean(embeddings, axis=0)
    
    def check_relevance(
        self,
        query_embedding: np.ndarray,
        incoming_signal: float,
    ) -> Tuple[bool, float]:
        """
        Check if query is relevant to this cluster.
        
        ENFORCEMENT: Returns (False, 0) if incoming_signal < threshold.
        No embedding computation happens in that case.
        
        Args:
            query_embedding: Query vector.
            incoming_signal: Propagated signal strength.
            
        Returns:
            (is_relevant, relevance_score)
        """
        # === HARD GATE: No compute below threshold ===
        if incoming_signal < PROPAGATION_CONFIG.activation_threshold:
            return False, 0.0
        
        if self.centroid_embedding is None:
            # Can't compute similarity, fall back to signal strength
            return incoming_signal >= PROPAGATION_CONFIG.activation_threshold, incoming_signal
        
        # Cosine similarity
        dot = np.dot(query_embedding, self.centroid_embedding)
        norm_q = np.linalg.norm(query_embedding)
        norm_c = np.linalg.norm(self.centroid_embedding)
        
        if norm_q == 0 or norm_c == 0:
            return False, 0.0
        
        similarity = dot / (norm_q * norm_c)
        
        # Combine signal strength with embedding similarity
        combined_score = (incoming_signal * 0.6) + (similarity * 0.4)
        
        # Threshold for relevance
        is_relevant = combined_score >= PROPAGATION_CONFIG.activation_threshold
        
        return is_relevant, combined_score
    
    def emit_context(
        self,
        query_text: str,
        incoming_signal: float,
        existing_contexts: List[str],
    ) -> Optional[str]:
        """
        Emit a concise context statement about how this cluster relates to the query.
        
        ENFORCEMENT:
        - Returns None if incoming_signal < threshold (no compute)
        - Returns None if context would be too similar to existing (novelty check)
        - Context is deterministic in Phase 1 (no SLM)
        
        Args:
            query_text: The original query.
            incoming_signal: Signal strength (must be >= threshold).
            existing_contexts: Contexts already emitted by other agents.
            
        Returns:
            Context string or None if gated/filtered.
        """
        # === HARD GATE: No compute below threshold ===
        assert incoming_signal >= PROPAGATION_CONFIG.activation_threshold, \
            f"emit_context called with signal {incoming_signal} below threshold {PROPAGATION_CONFIG.activation_threshold}"
        
        # === PHASE 1: Deterministic context ===
        context = self._generate_deterministic_context(query_text)
        
        # === NOVELTY CHECK ===
        if not self._passes_novelty_check(context, existing_contexts):
            return None
        
        self._emitted_contexts.append(context)
        return context
    
    def _generate_deterministic_context(self, query_text: str) -> str:
        """
        Generate context without LLM. Uses cluster summary.
        Phase 1 only - swap to SLM in Phase 2.
        """
        # Find which summary elements might match query
        query_lower = query_text.lower()
        query_terms = set(query_lower.split())
        
        # Check for technique mentions
        matching_techniques = [
            t for t in self.summary.top_techniques
            if t.lower() in query_lower
        ]
        
        # Check for entity mentions
        matching_entities = [
            e for e in self.summary.top_entities
            if e.lower() in query_lower
        ]
        
        # Check for term overlap
        matching_terms = query_terms.intersection(set(self.summary.top_terms))
        
        # Build context based on matches
        parts = []
        
        if matching_techniques:
            parts.append(f"Contains techniques: {', '.join(matching_techniques[:2])}")
        
        if matching_entities:
            parts.append(f"References: {', '.join(matching_entities[:2])}")
        
        if matching_terms and not (matching_techniques or matching_entities):
            parts.append(f"Related terms: {', '.join(list(matching_terms)[:3])}")
        
        # Add cluster composition
        main_concept = max(self.summary.concept_distribution.items(), key=lambda x: x[1])[0]
        parts.append(f"({self.summary.total_nodes} {main_concept} nodes)")
        
        if not parts:
            # Fallback to generic summary
            return self.summary.summary_text[:100]
        
        return ". ".join(parts)
    
    def _passes_novelty_check(
        self,
        new_context: str,
        existing_contexts: List[str],
    ) -> bool:
        """
        Check if new context is sufficiently different from existing ones.
        Uses simple token overlap for Phase 1.
        """
        if not existing_contexts:
            return True
        
        new_tokens = set(new_context.lower().split())
        
        for existing in existing_contexts:
            existing_tokens = set(existing.lower().split())
            
            # Jaccard similarity
            intersection = len(new_tokens & existing_tokens)
            union = len(new_tokens | existing_tokens)
            
            if union == 0:
                continue
            
            similarity = intersection / union
            
            # If too similar to any existing context, reject
            if similarity > (1.0 - self.config.min_novelty_threshold):
                return False
        
        return True
    
    def get_routing_features(self) -> Dict[str, any]:
        """
        Return features for the routing model to learn from.
        """
        return {
            "agent_id": self.agent_id,
            "cluster_id": self.cluster_id,
            "total_nodes": self.summary.total_nodes,
            "concept_distribution": self.summary.concept_distribution,
            "top_techniques": self.summary.top_techniques,
            "top_terms": self.summary.top_terms,
        }


class DomainHub:
    """
    A hub agent that routes between domains.
    Does not own nodes directly - routes to cluster agents.
    
    Analogous to thalamus routing to cortical regions.
    """
    
    def __init__(
        self,
        hub_id: str,
        domain: str,
        governed_agents: List[str],  # Cluster agent IDs this hub governs
    ):
        self.hub_id = hub_id
        self.domain = domain
        self.governed_agents = set(governed_agents)
        
        # Hub doesn't have nodes, but can have learned preferences
        self.routing_weights: Dict[str, float] = {
            agent_id: 1.0 for agent_id in governed_agents
        }
    
    def select_governed_agents(
        self,
        query_embedding: np.ndarray,
        agent_centroids: Dict[str, np.ndarray],
        top_k: int = 3,
    ) -> List[Tuple[str, float]]:
        """
        Select which governed agents should receive signal.
        
        Args:
            query_embedding: Query vector.
            agent_centroids: agent_id -> centroid embedding.
            top_k: Max agents to select.
            
        Returns:
            List of (agent_id, score) tuples.
        """
        scores = []
        
        for agent_id in self.governed_agents:
            centroid = agent_centroids.get(agent_id)
            if centroid is None:
                continue
            
            # Cosine similarity
            dot = np.dot(query_embedding, centroid)
            norm_q = np.linalg.norm(query_embedding)
            norm_c = np.linalg.norm(centroid)
            
            if norm_q > 0 and norm_c > 0:
                similarity = dot / (norm_q * norm_c)
                # Apply learned routing weight
                weighted_score = similarity * self.routing_weights.get(agent_id, 1.0)
                scores.append((agent_id, weighted_score))
        
        # Sort by score, return top-k
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]
    
    def update_routing_weight(self, agent_id: str, delta: float):
        """
        Update routing weight based on feedback.
        Called when we learn whether an agent contributed to a good answer.
        """
        if agent_id in self.routing_weights:
            self.routing_weights[agent_id] = max(0.1, min(2.0, 
                self.routing_weights[agent_id] + delta
            ))
