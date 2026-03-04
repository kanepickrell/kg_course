"""
Neural Graph Routing - Propagation Engine

HARD RULES ENFORCED:
1. No global agent polling - only entry points + propagated signals
2. Agents cannot compute unless incoming_signal >= activation_threshold
3. hop_limit, max_active_agents, max_outgoing enforced via assertions
4. Signal decay + accumulation ceiling prevent runaway
"""
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional, Callable
from collections import defaultdict
import time
from enum import Enum

from config import PROPAGATION_CONFIG, PropagationConfig


class ActivationState(Enum):
    """Agent activation states for tracking."""
    DORMANT = "dormant"           # Never received signal
    RECEIVED = "received"         # Got signal but below threshold
    ACTIVATED = "activated"       # Fired, emitted context
    CONTRIBUTED = "contributed"   # Context used by orchestrator


@dataclass
class Signal:
    """A signal propagating through the agent network."""
    source_agent: str
    target_agent: str
    strength: float
    edge_type: str
    hop_count: int
    path: List[str]  # Full path from entry point
    
    def __post_init__(self):
        assert 0 <= self.strength <= PROPAGATION_CONFIG.accumulation_ceiling, \
            f"Signal strength {self.strength} out of bounds"
        assert self.hop_count >= 0, f"Negative hop count: {self.hop_count}"


@dataclass
class AgentActivation:
    """Record of an agent's activation during a query."""
    agent_id: str
    incoming_signal: float
    state: ActivationState
    context_emitted: Optional[str] = None
    activation_time_ms: Optional[float] = None
    incoming_paths: List[List[str]] = field(default_factory=list)


@dataclass
class PropagationResult:
    """Complete result of propagating a query through the network."""
    query_id: str
    entry_agents: List[str]
    
    # Activation tracking (separate concepts per your rules)
    activated_agents: List[str]      # Fired (met threshold)
    dormant_agents: List[str]        # Never received signal
    subthreshold_agents: List[str]   # Received but didn't fire
    
    # Will be filled by orchestrator
    contributing_agents: List[str] = field(default_factory=list)
    
    # Detailed traces
    activation_records: Dict[str, AgentActivation] = field(default_factory=dict)
    propagation_paths: List[Signal] = field(default_factory=list)
    
    # Metrics
    total_signals_sent: int = 0
    max_hop_reached: int = 0
    total_time_ms: float = 0
    
    # Warnings/errors
    truncated_by_max_agents: bool = False
    truncated_by_max_hops: bool = False


class PropagationEngine:
    """
    Manages signal propagation through the agent network.
    
    ENFORCES:
    - No polling: only entry agents + propagated signals
    - Activation gating: no compute below threshold
    - Hard limits: hops, active agents, outgoing signals
    """
    
    def __init__(
        self,
        agent_neighbors: Dict[str, List[Tuple[str, str]]],  # agent_id -> [(neighbor_id, edge_type), ...]
        config: PropagationConfig = PROPAGATION_CONFIG,
    ):
        """
        Args:
            agent_neighbors: Adjacency list with edge types. 
                             Edge types MUST be in config.edge_weights.
            config: Propagation configuration.
        """
        self.agent_neighbors = agent_neighbors
        self.config = config
        self.all_agents = set(agent_neighbors.keys())
        
        # Validate all edge types are known
        for agent_id, neighbors in agent_neighbors.items():
            for neighbor_id, edge_type in neighbors:
                _ = config.get_edge_weight(edge_type)  # Raises if unknown
    
    def propagate(
        self,
        query_id: str,
        entry_agents: List[str],
        entry_scores: Dict[str, float],
        relevance_fn: Callable[[str, float], Tuple[bool, Optional[str]]],
    ) -> PropagationResult:
        """
        Propagate signals from entry agents through the network.
        
        Args:
            query_id: Unique identifier for this query.
            entry_agents: Top-K agents selected by entry point selection (NOT all agents).
            entry_scores: Initial relevance scores for entry agents.
            relevance_fn: Function(agent_id, signal_strength) -> (is_relevant, context_or_none).
                         ONLY called when signal >= activation_threshold.
        
        Returns:
            PropagationResult with all activation data.
        """
        assert len(entry_agents) <= self.config.top_k_entry_agents + len(self._get_hub_agents()), \
            f"Too many entry agents: {len(entry_agents)}. Max allowed: {self.config.top_k_entry_agents} + hubs"
        
        start_time = time.time()
        
        # Initialize tracking
        accumulated_signals: Dict[str, float] = defaultdict(float)
        activation_records: Dict[str, AgentActivation] = {}
        propagation_paths: List[Signal] = []
        activated_agents: List[str] = []
        signal_queue: List[Signal] = []
        agents_at_capacity: Set[str] = set()  # Agents that hit max_outgoing
        
        # Track signals sent per agent (for max_outgoing enforcement)
        outgoing_count: Dict[str, int] = defaultdict(int)
        
        # === PHASE 1: Initialize entry agents ===
        for agent_id in entry_agents:
            assert agent_id in self.all_agents, f"Unknown entry agent: {agent_id}"
            initial_score = entry_scores.get(agent_id, 0.5)
            accumulated_signals[agent_id] = min(initial_score, self.config.accumulation_ceiling)
            
            # Entry agents are at hop 0
            signal_queue.append(Signal(
                source_agent="ENTRY",
                target_agent=agent_id,
                strength=initial_score,
                edge_type="ENTRY",
                hop_count=0,
                path=["ENTRY", agent_id],
            ))
        
        # === PHASE 2: Process signals (BFS with constraints) ===
        total_signals = 0
        max_hop_seen = 0
        truncated_by_agents = False
        truncated_by_hops = False
        
        while signal_queue:
            signal = signal_queue.pop(0)
            total_signals += 1
            max_hop_seen = max(max_hop_seen, signal.hop_count)
            propagation_paths.append(signal)
            
            agent_id = signal.target_agent
            
            # Check if already processed this agent
            if agent_id in activation_records:
                # Update incoming paths
                activation_records[agent_id].incoming_paths.append(signal.path)
                continue
            
            # Get accumulated signal for this agent
            current_signal = accumulated_signals[agent_id]
            
            # === ENFORCEMENT: Activation threshold gating ===
            if current_signal < self.config.activation_threshold:
                # Record as subthreshold - NO COMPUTE ALLOWED
                activation_records[agent_id] = AgentActivation(
                    agent_id=agent_id,
                    incoming_signal=current_signal,
                    state=ActivationState.RECEIVED,
                    incoming_paths=[signal.path],
                )
                continue
            
            # === ENFORCEMENT: Max active agents ===
            if len(activated_agents) >= self.config.max_active_agents:
                truncated_by_agents = True
                activation_records[agent_id] = AgentActivation(
                    agent_id=agent_id,
                    incoming_signal=current_signal,
                    state=ActivationState.RECEIVED,  # Would have activated, but capped
                    incoming_paths=[signal.path],
                )
                continue
            
            # === ACTIVATION: Agent fires ===
            activation_start = time.time()
            is_relevant, context = relevance_fn(agent_id, current_signal)
            activation_time = (time.time() - activation_start) * 1000
            
            if is_relevant:
                activated_agents.append(agent_id)
                activation_records[agent_id] = AgentActivation(
                    agent_id=agent_id,
                    incoming_signal=current_signal,
                    state=ActivationState.ACTIVATED,
                    context_emitted=context,
                    activation_time_ms=activation_time,
                    incoming_paths=[signal.path],
                )
                
                # === PROPAGATION: Send signals to neighbors ===
                if signal.hop_count < self.config.max_hops:
                    neighbors = self.agent_neighbors.get(agent_id, [])
                    signals_sent = 0
                    
                    for neighbor_id, edge_type in neighbors:
                        # === ENFORCEMENT: Max outgoing per agent ===
                        if outgoing_count[agent_id] >= self.config.max_outgoing_per_agent:
                            agents_at_capacity.add(agent_id)
                            break
                        
                        # Skip if neighbor already fully processed
                        if neighbor_id in activation_records and \
                           activation_records[neighbor_id].state == ActivationState.ACTIVATED:
                            continue
                        
                        # Calculate propagated signal strength
                        edge_weight = self.config.get_edge_weight(edge_type)
                        decay = self.config.hop_decay_factor ** (signal.hop_count + 1)
                        propagated_strength = current_signal * edge_weight * decay
                        
                        # Skip if signal too weak to matter
                        if propagated_strength < self.config.activation_threshold * 0.5:
                            continue
                        
                        # Accumulate signal at neighbor (with ceiling)
                        accumulated_signals[neighbor_id] = min(
                            accumulated_signals[neighbor_id] + propagated_strength,
                            self.config.accumulation_ceiling,
                        )
                        
                        # Queue the signal
                        signal_queue.append(Signal(
                            source_agent=agent_id,
                            target_agent=neighbor_id,
                            strength=propagated_strength,
                            edge_type=edge_type,
                            hop_count=signal.hop_count + 1,
                            path=signal.path + [neighbor_id],
                        ))
                        
                        outgoing_count[agent_id] += 1
                        signals_sent += 1
                else:
                    truncated_by_hops = True
            else:
                # Relevance check failed
                activation_records[agent_id] = AgentActivation(
                    agent_id=agent_id,
                    incoming_signal=current_signal,
                    state=ActivationState.RECEIVED,
                    activation_time_ms=activation_time,
                    incoming_paths=[signal.path],
                )
        
        # === PHASE 3: Identify dormant agents ===
        dormant = [a for a in self.all_agents if a not in activation_records]
        subthreshold = [
            a for a, rec in activation_records.items()
            if rec.state == ActivationState.RECEIVED
        ]
        
        total_time = (time.time() - start_time) * 1000
        
        return PropagationResult(
            query_id=query_id,
            entry_agents=entry_agents,
            activated_agents=activated_agents,
            dormant_agents=dormant,
            subthreshold_agents=subthreshold,
            activation_records=activation_records,
            propagation_paths=propagation_paths,
            total_signals_sent=total_signals,
            max_hop_reached=max_hop_seen,
            total_time_ms=total_time,
            truncated_by_max_agents=truncated_by_agents,
            truncated_by_max_hops=truncated_by_hops,
        )
    
    def _get_hub_agents(self) -> Set[str]:
        """Return hub agent IDs (for limit calculations)."""
        from config import DOMAIN_HUBS
        return set(DOMAIN_HUBS.values())


def compute_activation_sparsity(result: PropagationResult, total_agents: int) -> float:
    """Calculate what fraction of agents activated."""
    return len(result.activated_agents) / total_agents if total_agents > 0 else 0.0


def compute_propagation_efficiency(result: PropagationResult) -> float:
    """Ratio of activated agents to total signals sent."""
    if result.total_signals_sent == 0:
        return 0.0
    return len(result.activated_agents) / result.total_signals_sent
