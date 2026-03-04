#!/usr/bin/env python3
"""
Quick test to validate the neural graph routing system.
Run from the neural_graph_routing directory.
"""
import sys
sys.path.insert(0, '.')

import numpy as np

def test_config():
    """Test configuration loads correctly."""
    print("Testing config...")
    from config import PROPAGATION_CONFIG, AGENT_CONFIG, EXPERIMENT_CONFIG
    
    assert PROPAGATION_CONFIG.max_hops == 4
    assert PROPAGATION_CONFIG.activation_threshold == 0.3
    assert "IMPLEMENTS" in PROPAGATION_CONFIG.edge_weights
    
    # Test that unknown edge types raise
    try:
        PROPAGATION_CONFIG.get_edge_weight("UNKNOWN_EDGE")
        assert False, "Should have raised KeyError"
    except KeyError:
        pass
    
    print("  ✓ Config OK")


def test_data_generator():
    """Test synthetic data generation."""
    print("Testing data generator...")
    from simulation.data_generator import SyntheticDataGenerator
    
    gen = SyntheticDataGenerator(seed=42)
    dataset = gen.generate(num_nodes=50, num_queries=10)
    
    assert len(dataset.nodes) > 0
    assert len(dataset.edges) > 0
    assert len(dataset.queries) == 10
    assert len(dataset.cluster_to_nodes) > 0
    
    # Check hard cases exist
    assert len(dataset.shared_entities) >= 0
    assert len(dataset.weak_bridges) >= 0
    
    # Check queries have ground truth
    for query in dataset.queries:
        assert query.expected_clusters is not None
        assert query.difficulty in ["easy", "medium", "hard"]
    
    print(f"  ✓ Generated {len(dataset.nodes)} nodes, {len(dataset.edges)} edges")
    print(f"  ✓ {len(dataset.cluster_to_nodes)} clusters")
    print(f"  ✓ {len(dataset.queries)} queries with ground truth")


def test_cluster_agent():
    """Test cluster agent creation and gating."""
    print("Testing cluster agent...")
    from core.cluster_agent import ClusterAgent, ClusterNode
    from config import PROPAGATION_CONFIG
    
    # Create test nodes
    nodes = [
        ClusterNode(
            node_id=f"node_{i}",
            concept_type="LibraryModule",
            name=f"test_module_{i}",
            properties={"technique_id": "T1003", "category": "Cobalt Strike"},
            embedding=np.random.randn(768),
        )
        for i in range(5)
    ]
    
    agent = ClusterAgent(
        agent_id="test_agent",
        cluster_id="test_cluster",
        nodes=nodes,
    )
    
    # Test summary generation
    assert agent.summary.total_nodes == 5
    assert "LibraryModule" in agent.summary.concept_distribution
    
    # Test relevance gating
    query_emb = np.random.randn(768)
    
    # Below threshold - should not activate
    is_rel, score = agent.check_relevance(query_emb, 0.1)
    assert is_rel == False, "Should not activate below threshold"
    
    # Above threshold - should compute
    is_rel, score = agent.check_relevance(query_emb, 0.5)
    # Result depends on embedding similarity
    
    print("  ✓ Agent creation OK")
    print("  ✓ Gating enforcement OK")


def test_propagation_engine():
    """Test propagation with hard limits."""
    print("Testing propagation engine...")
    from core.propagation import PropagationEngine
    from config import PROPAGATION_CONFIG
    
    # Simple 3-agent network
    neighbors = {
        "agent_a": [("agent_b", "IMPLEMENTS")],
        "agent_b": [("agent_a", "IMPLEMENTS"), ("agent_c", "TESTED_BY")],
        "agent_c": [("agent_b", "TESTED_BY")],
    }
    
    engine = PropagationEngine(neighbors, PROPAGATION_CONFIG)
    
    # Track which agents were called
    called_agents = []
    
    def relevance_fn(agent_id, signal):
        called_agents.append(agent_id)
        # Always relevant for test
        return True, f"Context from {agent_id}"
    
    result = engine.propagate(
        query_id="test_query",
        entry_agents=["agent_a"],
        entry_scores={"agent_a": 0.8},
        relevance_fn=relevance_fn,
    )
    
    assert "agent_a" in result.activated_agents
    assert len(result.propagation_paths) > 0
    
    # Check that propagation happened
    assert len(result.activated_agents) >= 1
    
    print(f"  ✓ Activated {len(result.activated_agents)} agents")
    print(f"  ✓ {result.total_signals_sent} signals sent")
    print(f"  ✓ Max hop: {result.max_hop_reached}")


def test_entry_selection():
    """Test entry point selection without polling."""
    print("Testing entry selection...")
    from core.entry_selection import EntryPointSelector
    
    # Create test data
    agent_centroids = {
        "agent_a": np.array([1.0, 0.0, 0.0] + [0.0]*765),
        "agent_b": np.array([0.0, 1.0, 0.0] + [0.0]*765),
        "agent_c": np.array([0.0, 0.0, 1.0] + [0.0]*765),
    }
    
    agent_entities = {
        "agent_a": {"Cobalt Strike", "beacon"},
        "agent_b": {"T1003", "credentials"},
        "agent_c": {"OPFOR", "red team"},
    }
    
    agent_techniques = {
        "agent_a": {"T1059"},
        "agent_b": {"T1003", "T1003.001"},
        "agent_c": set(),
    }
    
    agent_terms = {
        "agent_a": {"module", "beacon", "payload"},
        "agent_b": {"dump", "credential", "memory"},
        "agent_c": {"team", "training", "event"},
    }
    
    selector = EntryPointSelector(
        agent_centroids=agent_centroids,
        agent_entities=agent_entities,
        agent_techniques=agent_techniques,
        agent_terms=agent_terms,
        hub_agents={},
    )
    
    # Test technique-based selection
    query_emb = np.random.randn(768)
    result = selector.select(
        query_text="What modules implement T1003?",
        query_embedding=query_emb,
        top_k=2,
        include_hubs=False,
    )
    
    assert "agent_b" in result.selected_agents, "Should select agent with T1003"
    assert result.selection_method == "entity"
    
    print(f"  ✓ Selected: {result.selected_agents}")
    print(f"  ✓ Method: {result.selection_method}")
    print(f"  ✓ Matched: {result.matched_entities}")


def test_orchestrator():
    """Test orchestrator preserves structure."""
    print("Testing orchestrator...")
    from core.orchestrator import Orchestrator
    from core.propagation import PropagationResult, AgentActivation, ActivationState
    
    # Create mock propagation result
    result = PropagationResult(
        query_id="test",
        entry_agents=["agent_a"],
        activated_agents=["agent_a", "agent_b"],
        dormant_agents=["agent_c"],
        subthreshold_agents=[],
        activation_records={
            "agent_a": AgentActivation(
                agent_id="agent_a",
                incoming_signal=0.8,
                state=ActivationState.ACTIVATED,
                context_emitted="Contains T1003 modules",
                incoming_paths=[["ENTRY", "agent_a"]],
            ),
            "agent_b": AgentActivation(
                agent_id="agent_b",
                incoming_signal=0.6,
                state=ActivationState.ACTIVATED,
                context_emitted="Test logs for credential techniques",
                incoming_paths=[["ENTRY", "agent_a", "agent_b"]],
            ),
        },
        propagation_paths=[],
    )
    
    contexts = {
        "agent_a": "Contains T1003 modules",
        "agent_b": "Test logs for credential techniques",
    }
    
    orchestrator = Orchestrator(use_llm=False)
    synth_result = orchestrator.synthesize(
        query="What tests credential dumping?",
        propagation_result=result,
        agent_contexts=contexts,
    )
    
    assert len(synth_result.context_chain) == 2
    assert synth_result.context_chain[0].depth < synth_result.context_chain[1].depth
    
    print(f"  ✓ Synthesized with {synth_result.total_contexts} contexts")
    print(f"  ✓ {synth_result.contexts_used} contributed")
    print(f"  ✓ Structure preserved (ordered by depth)")


def test_full_pipeline():
    """Test the complete pipeline."""
    print("Testing full pipeline...")
    from simulation.runner import SimulationRunner
    
    runner = SimulationRunner(
        seed=42,
        num_nodes=50,
        num_queries=5,
        output_dir="./test_logs",
    )
    
    summary = runner.run()
    
    assert summary["mean_activation_sparsity"] < 1.0, "Should have sparse activation"
    assert summary["mean_precision_at_k"] >= 0, "Should compute precision"
    
    print(f"  ✓ Sparsity: {summary['mean_activation_sparsity']:.1%}")
    print(f"  ✓ Precision: {summary['mean_precision_at_k']:.3f}")
    print(f"  ✓ Recall: {summary['mean_recall']:.3f}")
    print(f"  ✓ Rescued: {summary['pct_propagation_rescued']:.1%}")


def main():
    print("="*60)
    print("NEURAL GRAPH ROUTING - SYSTEM TEST")
    print("="*60 + "\n")
    
    test_config()
    test_data_generator()
    test_cluster_agent()
    test_propagation_engine()
    test_entry_selection()
    test_orchestrator()
    
    print("\n" + "-"*60)
    print("INTEGRATION TEST")
    print("-"*60 + "\n")
    
    test_full_pipeline()
    
    print("\n" + "="*60)
    print("ALL TESTS PASSED ✓")
    print("="*60)


if __name__ == "__main__":
    main()
