"""
Neural Graph Routing - Configuration

All thresholds and weights are EXPLICIT. No defaults for edge types.
Unknown edge types will raise errors, not silently spread.
"""
from dataclasses import dataclass, field
from typing import Dict, Set
from enum import Enum


class EdgeDirection(Enum):
    """
    Edge directionality is FIXED per type.
    Format: (source_concept, target_concept)
    Propagation flows in direction of semantic dependency.
    """
    IMPLEMENTS = ("LibraryModule", "Technique")  # Module implements technique
    TESTED_BY = ("LibraryModule", "RobotLog")    # Module tested by log
    SUBTECHNIQUE_OF = ("Technique", "Technique") # Child -> Parent
    MITIGATES = ("LibraryModule", "Technique")   # Module mitigates technique
    AUTHORED = ("Team", "LibraryModule")         # Team authored module
    OWNED_BY = ("Team", "LibraryModule")         # Team owns module (weaker)
    USES = ("RobotLog", "LibraryModule")         # Log uses module
    DEPENDS_ON = ("LibraryModule", "LibraryModule")  # Module depends on module
    ASSIGNED_TO = ("Team", "TrainingEvent")      # Team assigned to event
    COVERS = ("TrainingEvent", "Technique")      # Event covers technique
    RELATED_TO = ("*", "*")                      # Generic - use sparingly


@dataclass(frozen=True)
class PropagationConfig:
    """Immutable propagation settings."""
    
    # === HARD LIMITS (assertions will enforce) ===
    max_hops: int = 4
    max_active_agents: int = 15
    max_outgoing_per_agent: int = 5
    activation_threshold: float = 0.3
    accumulation_ceiling: float = 1.5  # Max signal after multi-path accumulation
    
    # === ENTRY POINT SELECTION ===
    top_k_entry_agents: int = 3
    include_hub_on_cold_start: bool = True
    
    # === SIGNAL DECAY ===
    hop_decay_factor: float = 0.7  # Signal *= this per hop
    
    # === EDGE WEIGHTS (EXPLICIT - unknown types will error) ===
    edge_weights: Dict[str, float] = field(default_factory=lambda: {
        # Semantic edges - strong propagation
        "IMPLEMENTS": 0.9,
        "SUBTECHNIQUE_OF": 0.95,
        "MITIGATES": 0.85,
        "TESTED_BY": 0.8,
        
        # Operational edges - medium propagation
        "USES": 0.7,
        "DEPENDS_ON": 0.7,
        "COVERS": 0.75,
        
        # Organizational edges - weak propagation
        "AUTHORED": 0.4,
        "OWNED_BY": 0.3,
        "ASSIGNED_TO": 0.3,
        
        # Generic - intentionally low
        "RELATED_TO": 0.5,
    })
    
    def get_edge_weight(self, edge_type: str) -> float:
        """Get edge weight. Raises KeyError for unknown types - no silent defaults."""
        if edge_type not in self.edge_weights:
            raise KeyError(
                f"Unknown edge type '{edge_type}'. "
                f"Add it to edge_weights explicitly. Known types: {list(self.edge_weights.keys())}"
            )
        return self.edge_weights[edge_type]


@dataclass(frozen=True)
class AgentConfig:
    """Agent behavior settings."""
    
    # === CONTEXT EMISSION ===
    max_context_tokens: int = 50  # Force concise statements
    min_novelty_threshold: float = 0.3  # Cosine distance from existing contexts
    
    # === SLM SETTINGS (Phase 2+) ===
    slm_timeout_ms: int = 500
    slm_model: str = "gemma2:2b"  # Small, fast
    use_slm: bool = False  # Phase 1: deterministic summaries only
    
    # === EMBEDDING ===
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768


@dataclass(frozen=True)
class ExperimentConfig:
    """Experiment tracking settings."""
    
    # === REPRODUCIBILITY ===
    random_seed: int = 42
    
    # === LOGGING ===
    log_activation_traces: bool = True
    log_propagation_paths: bool = True
    log_context_emissions: bool = True
    
    # === SYNTHETIC DATA ===
    num_nodes: int = 300
    num_queries: int = 100
    
    # Hard case ratios (must sum to < 1.0, remainder is clean clusters)
    shared_entities_ratio: float = 0.15  # Entities in multiple clusters
    weak_bridges_ratio: float = 0.10     # Org-only connections
    misleading_lexical_ratio: float = 0.05  # Same words, different meaning


# === DOMAIN HUB CONFIGURATION ===
# Maps hub agent IDs to their domain names
DOMAIN_HUBS = {
    "hub_techniques": "techniques",
    "hub_artifacts": "artifacts", 
    "hub_operations": "operations",
}

# Which concept types each hub governs
HUB_GOVERNANCE = {
    "hub_techniques": {"Technique"},
    "hub_artifacts": {"LibraryModule", "RobotLog", "DevelopmentStory"},
    "hub_operations": {"Team", "TrainingEvent"},
}


# === SINGLETON INSTANCES ===
PROPAGATION_CONFIG = PropagationConfig()
AGENT_CONFIG = AgentConfig()
EXPERIMENT_CONFIG = ExperimentConfig()
