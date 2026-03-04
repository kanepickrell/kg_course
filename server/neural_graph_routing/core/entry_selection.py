"""
Neural Graph Routing - Entry Point Selection

Fast retrieval to select top-K entry agents without polling all agents.

Methods:
1. Centroid similarity (embedding-based)
2. Lexical/entity matching (ontology-aware)
3. Hub fallback (cold start)

ENFORCEMENT: 
- Returns exactly top_k agents (or fewer if not enough exist)
- Never iterates over all agents for relevance check
"""
from dataclasses import dataclass
from typing import List, Dict, Set, Tuple, Optional
import numpy as np
import re

from config import PROPAGATION_CONFIG, DOMAIN_HUBS, HUB_GOVERNANCE


@dataclass
class EntryPointResult:
    """Result of entry point selection."""
    selected_agents: List[str]
    scores: Dict[str, float]
    selection_method: str  # "centroid", "entity", "hybrid", "cold_start"
    matched_entities: List[str]
    hub_agents_included: List[str]


class EntryPointSelector:
    """
    Selects entry agents for a query without polling.
    
    Uses pre-computed indices for O(k) selection, not O(n) polling.
    """
    
    def __init__(
        self,
        agent_centroids: Dict[str, np.ndarray],     # agent_id -> embedding
        agent_entities: Dict[str, Set[str]],         # agent_id -> entity names
        agent_techniques: Dict[str, Set[str]],       # agent_id -> technique IDs
        agent_terms: Dict[str, Set[str]],            # agent_id -> top terms
        hub_agents: Dict[str, str],                  # hub_id -> domain
    ):
        """
        Args:
            agent_centroids: Pre-computed cluster centroids.
            agent_entities: Pre-computed entity sets per agent.
            agent_techniques: Pre-computed technique IDs per agent.
            agent_terms: Pre-computed top terms per agent.
            hub_agents: Hub agent mapping.
        """
        self.agent_centroids = agent_centroids
        self.agent_entities = agent_entities
        self.agent_techniques = agent_techniques
        self.agent_terms = agent_terms
        self.hub_agents = hub_agents
        
        # Build inverted indices for fast lookup
        self._entity_to_agents: Dict[str, Set[str]] = {}
        self._technique_to_agents: Dict[str, Set[str]] = {}
        self._term_to_agents: Dict[str, Set[str]] = {}
        
        self._build_inverted_indices()
    
    def _build_inverted_indices(self):
        """Build inverted indices for O(1) entity/technique lookup."""
        for agent_id, entities in self.agent_entities.items():
            for entity in entities:
                entity_lower = entity.lower()
                if entity_lower not in self._entity_to_agents:
                    self._entity_to_agents[entity_lower] = set()
                self._entity_to_agents[entity_lower].add(agent_id)
        
        for agent_id, techniques in self.agent_techniques.items():
            for tech in techniques:
                tech_upper = tech.upper()
                if tech_upper not in self._technique_to_agents:
                    self._technique_to_agents[tech_upper] = set()
                self._technique_to_agents[tech_upper].add(agent_id)
        
        for agent_id, terms in self.agent_terms.items():
            for term in terms:
                term_lower = term.lower()
                if term_lower not in self._term_to_agents:
                    self._term_to_agents[term_lower] = set()
                self._term_to_agents[term_lower].add(agent_id)
    
    def select(
        self,
        query_text: str,
        query_embedding: np.ndarray,
        top_k: int = PROPAGATION_CONFIG.top_k_entry_agents,
        include_hubs: bool = PROPAGATION_CONFIG.include_hub_on_cold_start,
        learned_router: Optional['LearnedRouter'] = None,
    ) -> EntryPointResult:
        """
        Select top-K entry agents for a query.
        
        Strategy:
        1. Extract entities/techniques from query
        2. If explicit matches, use those agents
        3. Otherwise, use centroid similarity
        4. Optionally include hub agents
        
        Args:
            query_text: Raw query string.
            query_embedding: Query embedding vector.
            top_k: Max number of entry agents (excluding hubs).
            include_hubs: Whether to add hub agents.
            learned_router: Optional learned routing model.
            
        Returns:
            EntryPointResult with selected agents and metadata.
        """
        scores: Dict[str, float] = {}
        matched_entities: List[str] = []
        selection_method = "cold_start"
        
        # === PHASE 1: Entity/technique extraction ===
        extracted = self._extract_entities_and_techniques(query_text)
        
        # Lookup agents by entity match
        entity_matches: Set[str] = set()
        for entity in extracted["entities"]:
            if entity.lower() in self._entity_to_agents:
                entity_matches.update(self._entity_to_agents[entity.lower()])
                matched_entities.append(entity)
        
        # Lookup agents by technique match
        technique_matches: Set[str] = set()
        for tech in extracted["techniques"]:
            if tech.upper() in self._technique_to_agents:
                technique_matches.update(self._technique_to_agents[tech.upper()])
                matched_entities.append(tech)
        
        # Lookup agents by term match
        term_matches: Set[str] = set()
        for term in extracted["terms"]:
            if term.lower() in self._term_to_agents:
                term_matches.update(self._term_to_agents[term.lower()])
        
        # === PHASE 2: Scoring ===
        if learned_router is not None:
            # Use learned routing if available
            learned_scores = learned_router.predict(query_embedding)
            scores.update(learned_scores)
            selection_method = "learned"
        
        elif entity_matches or technique_matches:
            # Explicit matches get high scores
            for agent_id in entity_matches:
                scores[agent_id] = scores.get(agent_id, 0) + 0.9
            for agent_id in technique_matches:
                scores[agent_id] = scores.get(agent_id, 0) + 0.95
            for agent_id in term_matches:
                scores[agent_id] = scores.get(agent_id, 0) + 0.3
            selection_method = "entity"
        
        else:
            # Fall back to centroid similarity
            for agent_id, centroid in self.agent_centroids.items():
                if agent_id in self.hub_agents:
                    continue  # Don't include hubs in centroid search
                
                similarity = self._cosine_similarity(query_embedding, centroid)
                scores[agent_id] = similarity
            
            selection_method = "centroid"
        
        # === PHASE 3: Select top-K ===
        # Sort by score
        ranked = sorted(
            [(aid, score) for aid, score in scores.items() if aid not in self.hub_agents],
            key=lambda x: x[1],
            reverse=True,
        )
        
        selected = [aid for aid, _ in ranked[:top_k]]
        final_scores = {aid: scores[aid] for aid in selected}
        
        # === PHASE 4: Add hubs if requested ===
        hub_agents_included = []
        if include_hubs and selection_method != "learned":
            # Determine which domain hubs to include based on query
            relevant_hubs = self._select_relevant_hubs(query_text, extracted)
            for hub_id in relevant_hubs:
                if hub_id not in selected:
                    selected.append(hub_id)
                    final_scores[hub_id] = 0.5  # Default hub score
                    hub_agents_included.append(hub_id)
        
        return EntryPointResult(
            selected_agents=selected,
            scores=final_scores,
            selection_method=selection_method,
            matched_entities=matched_entities,
            hub_agents_included=hub_agents_included,
        )
    
    def _extract_entities_and_techniques(self, query_text: str) -> Dict[str, List[str]]:
        """
        Extract recognizable entities and technique IDs from query.
        Simple regex-based extraction for Phase 1.
        """
        result = {
            "entities": [],
            "techniques": [],
            "terms": [],
        }
        
        # MITRE technique IDs (T1234, T1234.001)
        technique_pattern = r'T\d{4}(?:\.\d{3})?'
        techniques = re.findall(technique_pattern, query_text, re.IGNORECASE)
        result["techniques"] = [t.upper() for t in techniques]
        
        # MITRE tactic IDs (TA0001)
        tactic_pattern = r'TA\d{4}'
        tactics = re.findall(tactic_pattern, query_text, re.IGNORECASE)
        result["techniques"].extend([t.upper() for t in tactics])
        
        # Known entity patterns (could be expanded)
        # For now, extract capitalized multi-word phrases
        entity_pattern = r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+'
        entities = re.findall(entity_pattern, query_text)
        result["entities"] = entities
        
        # Extract significant terms (nouns, longer words)
        words = query_text.lower().split()
        stopwords = {"the", "a", "an", "is", "are", "for", "to", "of", "and", "in", "on", 
                     "with", "how", "what", "when", "where", "who", "why", "can", "do", "does"}
        terms = [w for w in words if w not in stopwords and len(w) > 3]
        result["terms"] = terms
        
        return result
    
    def _select_relevant_hubs(
        self,
        query_text: str,
        extracted: Dict[str, List[str]],
    ) -> List[str]:
        """
        Determine which domain hubs are relevant to the query.
        """
        relevant = []
        query_lower = query_text.lower()
        
        # Technique-related queries -> techniques hub
        if extracted["techniques"] or any(term in query_lower for term in 
            ["technique", "attack", "mitre", "tactic", "exploit", "vulnerability"]):
            relevant.append(DOMAIN_HUBS.get("techniques"))
        
        # Artifact-related queries -> artifacts hub
        if any(term in query_lower for term in 
            ["module", "library", "code", "script", "log", "test", "robot"]):
            relevant.append(DOMAIN_HUBS.get("artifacts"))
        
        # Operations-related queries -> operations hub
        if any(term in query_lower for term in 
            ["team", "training", "event", "exercise", "red team", "blue team", "opfor"]):
            relevant.append(DOMAIN_HUBS.get("operations"))
        
        # Filter None values
        return [h for h in relevant if h is not None]
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        if a is None or b is None:
            return 0.0
        
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot / (norm_a * norm_b)


class LearnedRouter:
    """
    Placeholder for learned routing model.
    Will be trained on activation logs in Phase 2.
    """
    
    def __init__(self):
        self.agent_models = {}  # agent_id -> classifier
        self.is_trained = False
    
    def predict(self, query_embedding: np.ndarray) -> Dict[str, float]:
        """
        Predict which agents are likely to be useful.
        Returns empty dict if not trained.
        """
        if not self.is_trained:
            return {}
        
        scores = {}
        for agent_id, model in self.agent_models.items():
            # model.predict_proba returns probability of positive class
            prob = model.predict_proba([query_embedding])[0][1]
            scores[agent_id] = prob
        
        return scores
    
    def train(self, activation_logs: List[dict]):
        """
        Train routing model on activation history.
        Implemented in learning/routing_model.py
        """
        pass
