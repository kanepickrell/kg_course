"""
Neural Graph Routing - Activation Logger

Logs everything needed to reproduce and analyze runs:
- Random seed
- Configuration (weights/thresholds)
- Cluster membership ground truth
- Activation traces
- Query-level metrics

CRITICAL: Logs must be complete enough to reproduce any run.
"""
import json
import hashlib
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import numpy as np


@dataclass
class QueryTrace:
    """Complete trace of a single query execution."""
    # Query info
    query_id: str
    query_text: str
    timestamp: str
    
    # Ground truth
    expected_clusters: List[str]
    expected_agents: List[str]
    difficulty: str
    query_type: str
    
    # Entry selection
    entry_method: str  # "centroid", "entity", "learned", "cold_start"
    entry_agents: List[str]
    entry_scores: Dict[str, float]
    matched_entities: List[str]
    
    # Propagation
    activated_agents: List[str]
    contributing_agents: List[str]
    dormant_agents: List[str]
    subthreshold_agents: List[str]
    
    # Propagation paths (for visualization)
    propagation_paths: List[Dict[str, Any]]  # [{source, target, strength, edge_type, hop}]
    
    # Metrics
    total_signals: int
    max_hop_reached: int
    propagation_time_ms: float
    synthesis_time_ms: float
    total_time_ms: float
    
    # Limits hit
    truncated_by_max_agents: bool
    truncated_by_max_hops: bool
    
    # Evaluation (computed against ground truth)
    precision_at_k: Optional[float] = None
    recall: Optional[float] = None
    propagation_rescued: bool = False  # Did propagation find agents entry missed?
    
    # Answer quality (if feedback available)
    user_feedback: Optional[str] = None
    answer_quality_score: Optional[float] = None


@dataclass
class RunMetadata:
    """Metadata for a complete experiment run."""
    run_id: str
    timestamp: str
    random_seed: int
    
    # Configuration snapshot
    propagation_config: Dict[str, Any]
    agent_config: Dict[str, Any]
    experiment_config: Dict[str, Any]
    
    # Dataset info
    num_nodes: int
    num_edges: int
    num_clusters: int
    num_agents: int
    num_queries: int
    
    # Hard case counts
    num_shared_entities: int
    num_weak_bridges: int
    num_misleading_overlaps: int
    
    # Ground truth
    cluster_assignments: Dict[str, str]  # node_id -> cluster_id
    agent_to_cluster: Dict[str, str]     # agent_id -> cluster_id


@dataclass
class RunSummary:
    """Aggregate metrics for a complete run."""
    run_id: str
    
    # Activation metrics
    mean_activation_sparsity: float
    median_activation_sparsity: float
    mean_activated_agents: float
    mean_contributing_agents: float
    
    # Propagation metrics
    mean_propagation_depth: float
    mean_signals_per_query: float
    pct_truncated_by_agents: float
    pct_truncated_by_hops: float
    
    # Timing
    mean_propagation_time_ms: float
    mean_total_time_ms: float
    p95_total_time_ms: float
    
    # Evaluation
    mean_precision_at_k: float
    mean_recall: float
    pct_propagation_rescued: float  # % where propagation found relevant agents entry missed
    
    # By difficulty
    metrics_by_difficulty: Dict[str, Dict[str, float]]
    
    # By query type
    metrics_by_query_type: Dict[str, Dict[str, float]]


class ActivationLogger:
    """
    Logs all activation data for reproducibility and analysis.
    
    Writes:
    - {run_id}_metadata.json: Configuration and ground truth
    - {run_id}_traces.jsonl: Per-query traces (streaming)
    - {run_id}_summary.json: Aggregate metrics
    """
    
    def __init__(self, output_dir: str = "./logs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.run_id: Optional[str] = None
        self.metadata: Optional[RunMetadata] = None
        self.traces: List[QueryTrace] = []
        
        self._trace_file = None
    
    def start_run(
        self,
        random_seed: int,
        propagation_config: Dict[str, Any],
        agent_config: Dict[str, Any],
        experiment_config: Dict[str, Any],
        num_nodes: int,
        num_edges: int,
        num_clusters: int,
        num_agents: int,
        num_queries: int,
        num_shared_entities: int,
        num_weak_bridges: int,
        num_misleading_overlaps: int,
        cluster_assignments: Dict[str, str],
        agent_to_cluster: Dict[str, str],
    ) -> str:
        """
        Initialize a new run. Returns run_id.
        """
        # Generate unique run ID
        timestamp = datetime.now().isoformat()
        hash_input = f"{timestamp}_{random_seed}"
        self.run_id = hashlib.md5(hash_input.encode()).hexdigest()[:12]
        
        self.metadata = RunMetadata(
            run_id=self.run_id,
            timestamp=timestamp,
            random_seed=random_seed,
            propagation_config=propagation_config,
            agent_config=agent_config,
            experiment_config=experiment_config,
            num_nodes=num_nodes,
            num_edges=num_edges,
            num_clusters=num_clusters,
            num_agents=num_agents,
            num_queries=num_queries,
            num_shared_entities=num_shared_entities,
            num_weak_bridges=num_weak_bridges,
            num_misleading_overlaps=num_misleading_overlaps,
            cluster_assignments=cluster_assignments,
            agent_to_cluster=agent_to_cluster,
        )
        
        # Write metadata immediately
        metadata_path = self.output_dir / f"{self.run_id}_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(asdict(self.metadata), f, indent=2, default=str)
        
        # Open trace file for streaming writes
        trace_path = self.output_dir / f"{self.run_id}_traces.jsonl"
        self._trace_file = open(trace_path, "w")
        
        self.traces = []
        
        return self.run_id
    
    def log_query(
        self,
        query_id: str,
        query_text: str,
        expected_clusters: List[str],
        expected_agents: List[str],
        difficulty: str,
        query_type: str,
        entry_method: str,
        entry_agents: List[str],
        entry_scores: Dict[str, float],
        matched_entities: List[str],
        activated_agents: List[str],
        contributing_agents: List[str],
        dormant_agents: List[str],
        subthreshold_agents: List[str],
        propagation_paths: List[Dict[str, Any]],
        total_signals: int,
        max_hop_reached: int,
        propagation_time_ms: float,
        synthesis_time_ms: float,
        total_time_ms: float,
        truncated_by_max_agents: bool,
        truncated_by_max_hops: bool,
    ) -> QueryTrace:
        """
        Log a single query execution.
        """
        # Compute evaluation metrics
        precision_at_k = self._compute_precision(activated_agents, expected_agents)
        recall = self._compute_recall(activated_agents, expected_agents)
        propagation_rescued = self._check_propagation_rescued(
            entry_agents, activated_agents, expected_agents
        )
        
        trace = QueryTrace(
            query_id=query_id,
            query_text=query_text,
            timestamp=datetime.now().isoformat(),
            expected_clusters=expected_clusters,
            expected_agents=expected_agents,
            difficulty=difficulty,
            query_type=query_type,
            entry_method=entry_method,
            entry_agents=entry_agents,
            entry_scores=entry_scores,
            matched_entities=matched_entities,
            activated_agents=activated_agents,
            contributing_agents=contributing_agents,
            dormant_agents=dormant_agents,
            subthreshold_agents=subthreshold_agents,
            propagation_paths=propagation_paths,
            total_signals=total_signals,
            max_hop_reached=max_hop_reached,
            propagation_time_ms=propagation_time_ms,
            synthesis_time_ms=synthesis_time_ms,
            total_time_ms=total_time_ms,
            truncated_by_max_agents=truncated_by_max_agents,
            truncated_by_max_hops=truncated_by_max_hops,
            precision_at_k=precision_at_k,
            recall=recall,
            propagation_rescued=propagation_rescued,
        )
        
        self.traces.append(trace)
        
        # Stream to file
        if self._trace_file:
            self._trace_file.write(json.dumps(asdict(trace), default=str) + "\n")
            self._trace_file.flush()
        
        return trace
    
    def end_run(self) -> RunSummary:
        """
        Finalize run and compute summary metrics.
        """
        if self._trace_file:
            self._trace_file.close()
            self._trace_file = None
        
        summary = self._compute_summary()
        
        # Write summary
        summary_path = self.output_dir / f"{self.run_id}_summary.json"
        with open(summary_path, "w") as f:
            json.dump(asdict(summary), f, indent=2, default=str)
        
        return summary
    
    def _compute_precision(
        self,
        activated: List[str],
        expected: List[str],
    ) -> float:
        """Precision: what fraction of activated agents were relevant."""
        if not activated:
            return 0.0
        relevant_activated = set(activated) & set(expected)
        return len(relevant_activated) / len(activated)
    
    def _compute_recall(
        self,
        activated: List[str],
        expected: List[str],
    ) -> float:
        """Recall: what fraction of relevant agents were activated."""
        if not expected:
            return 1.0  # No expected = perfect recall by default
        relevant_activated = set(activated) & set(expected)
        return len(relevant_activated) / len(expected)
    
    def _check_propagation_rescued(
        self,
        entry_agents: List[str],
        activated_agents: List[str],
        expected_agents: List[str],
    ) -> bool:
        """
        Did propagation find relevant agents that entry selection missed?
        This is the key metric for whether propagation adds value.
        """
        entry_set = set(entry_agents)
        activated_set = set(activated_agents)
        expected_set = set(expected_agents)
        
        # Agents found by propagation (not in entry)
        propagation_found = activated_set - entry_set
        
        # Were any of those relevant?
        relevant_from_propagation = propagation_found & expected_set
        
        return len(relevant_from_propagation) > 0
    
    def _compute_summary(self) -> RunSummary:
        """Compute aggregate metrics from all traces."""
        if not self.traces:
            return RunSummary(
                run_id=self.run_id,
                mean_activation_sparsity=0,
                median_activation_sparsity=0,
                mean_activated_agents=0,
                mean_contributing_agents=0,
                mean_propagation_depth=0,
                mean_signals_per_query=0,
                pct_truncated_by_agents=0,
                pct_truncated_by_hops=0,
                mean_propagation_time_ms=0,
                mean_total_time_ms=0,
                p95_total_time_ms=0,
                mean_precision_at_k=0,
                mean_recall=0,
                pct_propagation_rescued=0,
                metrics_by_difficulty={},
                metrics_by_query_type={},
            )
        
        # Compute total agents (from first trace's dormant + activated + subthreshold)
        total_agents = (
            len(self.traces[0].activated_agents) +
            len(self.traces[0].dormant_agents) +
            len(self.traces[0].subthreshold_agents)
        )
        
        # Activation metrics
        activation_counts = [len(t.activated_agents) for t in self.traces]
        sparsities = [len(t.activated_agents) / total_agents if total_agents > 0 else 0 
                      for t in self.traces]
        contributing_counts = [len(t.contributing_agents) for t in self.traces]
        
        # Propagation metrics
        depths = [t.max_hop_reached for t in self.traces]
        signals = [t.total_signals for t in self.traces]
        truncated_agents = sum(1 for t in self.traces if t.truncated_by_max_agents)
        truncated_hops = sum(1 for t in self.traces if t.truncated_by_max_hops)
        
        # Timing
        prop_times = [t.propagation_time_ms for t in self.traces]
        total_times = [t.total_time_ms for t in self.traces]
        
        # Evaluation
        precisions = [t.precision_at_k for t in self.traces if t.precision_at_k is not None]
        recalls = [t.recall for t in self.traces if t.recall is not None]
        rescued = sum(1 for t in self.traces if t.propagation_rescued)
        
        # By difficulty
        metrics_by_difficulty = {}
        for difficulty in ["easy", "medium", "hard"]:
            diff_traces = [t for t in self.traces if t.difficulty == difficulty]
            if diff_traces:
                metrics_by_difficulty[difficulty] = {
                    "count": len(diff_traces),
                    "mean_precision": np.mean([t.precision_at_k for t in diff_traces if t.precision_at_k]),
                    "mean_recall": np.mean([t.recall for t in diff_traces if t.recall]),
                    "mean_activated": np.mean([len(t.activated_agents) for t in diff_traces]),
                    "pct_propagation_rescued": sum(1 for t in diff_traces if t.propagation_rescued) / len(diff_traces),
                }
        
        # By query type
        metrics_by_query_type = {}
        query_types = set(t.query_type for t in self.traces)
        for qtype in query_types:
            type_traces = [t for t in self.traces if t.query_type == qtype]
            if type_traces:
                metrics_by_query_type[qtype] = {
                    "count": len(type_traces),
                    "mean_precision": np.mean([t.precision_at_k for t in type_traces if t.precision_at_k]),
                    "mean_recall": np.mean([t.recall for t in type_traces if t.recall]),
                    "mean_activated": np.mean([len(t.activated_agents) for t in type_traces]),
                }
        
        return RunSummary(
            run_id=self.run_id,
            mean_activation_sparsity=np.mean(sparsities),
            median_activation_sparsity=np.median(sparsities),
            mean_activated_agents=np.mean(activation_counts),
            mean_contributing_agents=np.mean(contributing_counts),
            mean_propagation_depth=np.mean(depths),
            mean_signals_per_query=np.mean(signals),
            pct_truncated_by_agents=truncated_agents / len(self.traces),
            pct_truncated_by_hops=truncated_hops / len(self.traces),
            mean_propagation_time_ms=np.mean(prop_times),
            mean_total_time_ms=np.mean(total_times),
            p95_total_time_ms=np.percentile(total_times, 95),
            mean_precision_at_k=np.mean(precisions) if precisions else 0,
            mean_recall=np.mean(recalls) if recalls else 0,
            pct_propagation_rescued=rescued / len(self.traces),
            metrics_by_difficulty=metrics_by_difficulty,
            metrics_by_query_type=metrics_by_query_type,
        )
    
    @staticmethod
    def load_run(run_id: str, log_dir: str = "./logs") -> tuple:
        """
        Load a previous run for analysis.
        Returns (metadata, traces, summary).
        """
        log_path = Path(log_dir)
        
        # Load metadata
        with open(log_path / f"{run_id}_metadata.json") as f:
            metadata = json.load(f)
        
        # Load traces
        traces = []
        with open(log_path / f"{run_id}_traces.jsonl") as f:
            for line in f:
                traces.append(json.loads(line))
        
        # Load summary
        with open(log_path / f"{run_id}_summary.json") as f:
            summary = json.load(f)
        
        return metadata, traces, summary
