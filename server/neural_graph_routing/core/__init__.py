"""
Neural Graph Routing - Core Module

Components:
- PropagationEngine: Signal propagation with hard limits
- ClusterAgent: Individual cluster agents with gated compute
- EntryPointSelector: Fast top-K selection without polling
- Orchestrator: Synthesis with structure preservation
"""
from core.propagation import (
    PropagationEngine,
    PropagationResult,
    Signal,
    ActivationState,
    AgentActivation,
    compute_activation_sparsity,
    compute_propagation_efficiency,
)
from core.cluster_agent import (
    ClusterAgent,
    ClusterNode,
    ClusterSummary,
    DomainHub,
)
from core.entry_selection import (
    EntryPointSelector,
    EntryPointResult,
    LearnedRouter,
)
from core.orchestrator import (
    Orchestrator,
    SynthesisResult,
    ContextChunk,
    update_propagation_result_with_contributions,
)

__all__ = [
    # Propagation
    "PropagationEngine",
    "PropagationResult", 
    "Signal",
    "ActivationState",
    "AgentActivation",
    "compute_activation_sparsity",
    "compute_propagation_efficiency",
    
    # Agents
    "ClusterAgent",
    "ClusterNode",
    "ClusterSummary",
    "DomainHub",
    
    # Entry Selection
    "EntryPointSelector",
    "EntryPointResult",
    "LearnedRouter",
    
    # Orchestrator
    "Orchestrator",
    "SynthesisResult",
    "ContextChunk",
    "update_propagation_result_with_contributions",
]
