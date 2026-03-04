"""
Neural Routing Experiment API
=============================

Provides endpoints for visualizing neural graph routing activation patterns.
Returns step-by-step propagation data that can be animated in the UI.

Add to your unified_api.py:
    from neural_experiment_api import create_neural_experiment_router
    experiment_router = create_neural_experiment_router(neural_router)
    app.include_router(experiment_router)
"""

import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel


# =============================================================================
# DATA MODELS FOR VISUALIZATION
# =============================================================================

@dataclass
class ActivationStep:
    """A single step in the propagation animation"""
    step_number: int
    timestamp_ms: float
    phase: str  # "entry_selection" | "activation" | "propagation" | "context_generation"
    agent_id: str
    agent_type: str  # "cluster" | "hub"
    
    # State changes
    signal_strength: float
    previous_signal: float = 0.0
    activated: bool = False
    context_generated: Optional[str] = None
    
    # Source of activation
    triggered_by: Optional[str] = None  # Which agent sent the signal
    edge_type: Optional[str] = None  # What relationship type
    hop_count: int = 0
    
    # Agent metadata for display
    cluster_id: Optional[str] = None
    node_count: int = 0
    keywords: List[str] = field(default_factory=list)
    
    # Position in graph (for highlighting)
    node_ids: List[str] = field(default_factory=list)


@dataclass
class PropagationPath:
    """An edge in the propagation graph"""
    source_agent: str
    target_agent: str
    edge_type: str
    signal_strength: float
    hop_count: int
    timestamp_ms: float


@dataclass
class ExperimentResult:
    """Complete result of a neural routing experiment"""
    experiment_id: str
    query: str
    timestamp: str
    
    # Timing
    total_time_ms: float
    entry_selection_time_ms: float
    propagation_time_ms: float
    context_generation_time_ms: float
    
    # Results
    total_agents: int
    activated_count: int
    contributed_count: int
    activation_sparsity: float
    
    # Step-by-step data for animation
    steps: List[ActivationStep]
    propagation_paths: List[PropagationPath]
    
    # Final contexts
    contexts: Dict[str, str]
    
    # For validation
    entry_agents: List[str]
    activated_agents: List[str]
    contributing_agents: List[str]
    dormant_agents: List[str]
    
    # Agent metadata (for UI display)
    agent_metadata: Dict[str, Dict[str, Any]]
    
    # Node-to-agent mapping (for graph highlighting)
    node_to_agent: Dict[str, str]


class ExperimentRequest(BaseModel):
    """Request body for running an experiment"""
    query: str
    top_k: int = 5
    include_node_mapping: bool = True
    step_delay_ms: int = 0  # For debugging timing


# =============================================================================
# EXPERIMENT RUNNER
# =============================================================================

class NeuralExperimentRunner:
    """
    Runs neural routing experiments with detailed step tracking.
    """
    
    def __init__(self, neural_router):
        self.router = neural_router
        self.experiment_counter = 0
    
    def run_experiment(self, query: str, top_k: int = 5, include_node_mapping: bool = True) -> ExperimentResult:
        """Run a neural routing experiment with full instrumentation."""
        
        self.experiment_counter += 1
        experiment_id = f"exp_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self.experiment_counter}"
        
        start_time = time.time()
        steps: List[ActivationStep] = []
        propagation_paths: List[PropagationPath] = []
        step_counter = 0
        
        # Ensure router is initialized
        if not self.router._initialized:
            self.router.initialize()
        
        if not self.router.agents:
            raise ValueError("No agents available - initialize the router first")
        
        # Get query embedding
        query_embedding = self.router.ollama.get_embedding(query)
        if query_embedding is None:
            # Fall back to keyword matching
            query_embedding = self._get_fallback_embedding(query)
        
        # === PHASE 1: ENTRY SELECTION ===
        entry_start = time.time()
        
        agent_scores: List[Tuple[str, float]] = []
        for agent_id, agent in self.router.agents.items():
            relevant, score = agent.is_relevant(query_embedding, threshold=0.0)
            agent_scores.append((agent_id, score))
        
        agent_scores.sort(key=lambda x: -x[1])
        
        # Select entry agents
        activation_threshold = 0.3
        entry_agents = []
        
        for agent_id, score in agent_scores[:top_k]:
            if score >= activation_threshold or len(entry_agents) == 0:
                entry_agents.append(agent_id)
                
                step_counter += 1
                agent = self.router.agents[agent_id]
                
                steps.append(ActivationStep(
                    step_number=step_counter,
                    timestamp_ms=(time.time() - start_time) * 1000,
                    phase="entry_selection",
                    agent_id=agent_id,
                    agent_type="cluster",
                    signal_strength=score,
                    previous_signal=0.0,
                    activated=True,
                    triggered_by=None,
                    edge_type=None,
                    hop_count=0,
                    cluster_id=agent.cluster_id,
                    node_count=len(agent.node_ids),
                    keywords=agent.summary.keywords[:5] if hasattr(agent, 'summary') else [],
                    node_ids=list(agent.node_ids)[:20],
                ))
        
        entry_selection_time = (time.time() - entry_start) * 1000
        
        # === PHASE 2: PROPAGATION ===
        prop_start = time.time()
        
        activated_agents = set(entry_agents)
        agent_signals: Dict[str, float] = {aid: dict(agent_scores)[aid] for aid in entry_agents}
        
        # BFS propagation
        queue = [(aid, 0, agent_signals[aid]) for aid in entry_agents]
        visited_at_depth: Dict[str, int] = {aid: 0 for aid in entry_agents}
        
        max_hops = 4
        max_active = 15
        max_outgoing = 5
        signal_decay = 0.7
        
        while queue and len(activated_agents) < max_active:
            current_agent, depth, incoming_signal = queue.pop(0)
            
            if depth >= max_hops:
                continue
            
            neighbors = self.router.agent_adjacency.get(current_agent, set())
            propagations = 0
            
            for neighbor in neighbors:
                if propagations >= max_outgoing:
                    break
                
                if neighbor in visited_at_depth and visited_at_depth[neighbor] <= depth:
                    continue
                
                # Calculate propagated signal
                edge_weight = 0.6  # Default
                propagated_signal = min(incoming_signal * edge_weight * signal_decay, 2.0)
                
                # Record propagation path
                propagation_paths.append(PropagationPath(
                    source_agent=current_agent,
                    target_agent=neighbor,
                    edge_type="RELATES_TO",
                    signal_strength=propagated_signal,
                    hop_count=depth + 1,
                    timestamp_ms=(time.time() - start_time) * 1000,
                ))
                
                if propagated_signal >= activation_threshold:
                    was_new = neighbor not in activated_agents
                    
                    if was_new:
                        activated_agents.add(neighbor)
                        visited_at_depth[neighbor] = depth + 1
                        agent_signals[neighbor] = propagated_signal
                        
                        step_counter += 1
                        agent = self.router.agents.get(neighbor)
                        
                        steps.append(ActivationStep(
                            step_number=step_counter,
                            timestamp_ms=(time.time() - start_time) * 1000,
                            phase="propagation",
                            agent_id=neighbor,
                            agent_type="cluster" if agent else "hub",
                            signal_strength=propagated_signal,
                            previous_signal=0.0,
                            activated=True,
                            triggered_by=current_agent,
                            edge_type="RELATES_TO",
                            hop_count=depth + 1,
                            cluster_id=agent.cluster_id if agent else None,
                            node_count=len(agent.node_ids) if agent else 0,
                            keywords=agent.summary.keywords[:5] if agent and hasattr(agent, 'summary') else [],
                            node_ids=list(agent.node_ids)[:20] if agent else [],
                        ))
                        
                        queue.append((neighbor, depth + 1, propagated_signal))
                        propagations += 1
        
        propagation_time = (time.time() - prop_start) * 1000
        
        # === PHASE 3: CONTEXT GENERATION ===
        context_start = time.time()
        
        contexts: Dict[str, str] = {}
        contributing_agents: List[str] = []
        
        for agent_id in activated_agents:
            agent = self.router.agents.get(agent_id)
            if not agent:
                continue
            
            context = self.router.ollama.generate_context(
                agent.summary.summary_text if hasattr(agent, 'summary') else "",
                query
            )
            
            if context and context != "NOT_RELEVANT":
                contexts[agent_id] = context
                contributing_agents.append(agent_id)
                
                # Update step with context
                for step in steps:
                    if step.agent_id == agent_id:
                        step.context_generated = context
                        step.phase = "context_generation"
                        break
        
        context_time = (time.time() - context_start) * 1000
        total_time = (time.time() - start_time) * 1000
        
        # === BUILD RESULT ===
        
        # Dormant agents (never activated)
        all_agent_ids = set(self.router.agents.keys())
        dormant_agents = list(all_agent_ids - activated_agents)
        
        # Agent metadata for UI
        agent_metadata = {}
        for agent_id, agent in self.router.agents.items():
            agent_metadata[agent_id] = {
                "cluster_id": agent.cluster_id,
                "node_count": len(agent.node_ids),
                "keywords": agent.summary.keywords[:10] if hasattr(agent, 'summary') else [],
                "summary": agent.summary.summary_text[:200] if hasattr(agent, 'summary') else "",
                "node_types": dict(agent.summary.node_types) if hasattr(agent, 'summary') else {},
                "activated": agent_id in activated_agents,
                "contributed": agent_id in contributing_agents,
                "signal": agent_signals.get(agent_id, 0.0),
            }
        
        # Node-to-agent mapping
        node_to_agent = {}
        if include_node_mapping:
            for agent_id, agent in self.router.agents.items():
                for node_id in agent.node_ids:
                    node_to_agent[node_id] = agent_id
        
        return ExperimentResult(
            experiment_id=experiment_id,
            query=query,
            timestamp=datetime.now().isoformat(),
            total_time_ms=total_time,
            entry_selection_time_ms=entry_selection_time,
            propagation_time_ms=propagation_time,
            context_generation_time_ms=context_time,
            total_agents=len(self.router.agents),
            activated_count=len(activated_agents),
            contributed_count=len(contributing_agents),
            activation_sparsity=len(activated_agents) / len(self.router.agents) if self.router.agents else 0,
            steps=[asdict(s) for s in steps],
            propagation_paths=[asdict(p) for p in propagation_paths],
            contexts=contexts,
            entry_agents=entry_agents,
            activated_agents=list(activated_agents),
            contributing_agents=contributing_agents,
            dormant_agents=dormant_agents,
            agent_metadata=agent_metadata,
            node_to_agent=node_to_agent,
        )
    
    def _get_fallback_embedding(self, query: str):
        """Generate a fallback embedding based on keyword matching."""
        import numpy as np
        # Simple random embedding as fallback
        return np.random.randn(768)


# =============================================================================
# FASTAPI ROUTER
# =============================================================================

def create_neural_experiment_router(neural_router) -> APIRouter:
    """
    Create FastAPI router for neural routing experiments.
    
    Usage:
        from neural_experiment_api import create_neural_experiment_router
        experiment_router = create_neural_experiment_router(neural_router)
        app.include_router(experiment_router)
    """
    
    router = APIRouter(prefix="/api/neural/experiment", tags=["Neural Experiment"])
    runner = NeuralExperimentRunner(neural_router)
    
    @router.post("/run")
    async def run_experiment(request: ExperimentRequest):
        """
        Run a neural routing experiment with full instrumentation.
        
        Returns step-by-step activation data for visualization.
        """
        try:
            result = runner.run_experiment(
                query=request.query,
                top_k=request.top_k,
                include_node_mapping=request.include_node_mapping,
            )
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/run")
    async def run_experiment_get(
        q: str = Query(..., description="Query to test"),
        top_k: int = Query(5, description="Number of entry agents"),
    ):
        """GET version for easy browser testing."""
        try:
            result = runner.run_experiment(query=q, top_k=top_k)
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/agents")
    async def get_agents_for_visualization():
        """
        Get all agents with their node mappings for graph overlay.
        """
        if not neural_router._initialized:
            neural_router.initialize()
        
        agents = []
        for agent_id, agent in neural_router.agents.items():
            agents.append({
                "agent_id": agent_id,
                "cluster_id": agent.cluster_id,
                "node_ids": list(agent.node_ids),
                "node_count": len(agent.node_ids),
                "keywords": agent.summary.keywords[:10] if hasattr(agent, 'summary') else [],
                "summary": agent.summary.summary_text[:200] if hasattr(agent, 'summary') else "",
                "neighbors": list(neural_router.agent_adjacency.get(agent_id, set())),
            })
        
        # Also return node-to-agent mapping
        node_to_agent = {}
        for agent_id, agent in neural_router.agents.items():
            for node_id in agent.node_ids:
                node_to_agent[node_id] = agent_id
        
        return {
            "agents": agents,
            "total": len(agents),
            "node_to_agent": node_to_agent,
        }
    
    @router.get("/test-queries")
    async def get_test_queries():
        """
        Get sample test queries for experimentation.
        """
        return {
            "queries": [
                {
                    "query": "How do we test credential dumping?",
                    "expected_topics": ["T1003", "mimikatz", "test logs"],
                    "difficulty": "medium",
                },
                {
                    "query": "What Cobalt Strike modules do we have?",
                    "expected_topics": ["Cobalt Strike", "beacon", "library modules"],
                    "difficulty": "easy",
                },
                {
                    "query": "Show me OPFOR automation scripts",
                    "expected_topics": ["OPFOR", "automation", "scripts"],
                    "difficulty": "easy",
                },
                {
                    "query": "What techniques relate to lateral movement?",
                    "expected_topics": ["T1021", "T1550", "lateral movement"],
                    "difficulty": "medium",
                },
                {
                    "query": "Find test failures for persistence techniques",
                    "expected_topics": ["test logs", "FAIL", "persistence", "T1547"],
                    "difficulty": "hard",
                },
            ]
        }
    
    print("✓ Neural experiment router registered at /api/neural/experiment/*")
    return router
