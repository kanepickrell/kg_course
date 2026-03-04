"""
Neural Graph Routing - Synthetic Data Generator

Generates ProtoGraph-like data with controlled difficulty:
- Clean clusters (easy)
- Shared entities across clusters (medium)
- Weak organizational bridges (medium)
- Misleading lexical overlaps (hard)

CRITICAL: Each generated query has expected_relevant_clusters for evaluation.
"""
import random
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple, Optional
import numpy as np

from config import EXPERIMENT_CONFIG, PROPAGATION_CONFIG


@dataclass
class SyntheticNode:
    """A generated graph node."""
    node_id: str
    concept_type: str
    name: str
    properties: Dict[str, any]
    cluster_id: Optional[str] = None  # Ground truth cluster assignment
    
    # For hard cases
    is_shared_entity: bool = False  # Belongs to multiple clusters
    is_bridge: bool = False  # Weak organizational connection
    has_misleading_terms: bool = False  # Lexical overlap with unrelated cluster


@dataclass
class SyntheticEdge:
    """A generated graph edge."""
    source_id: str
    target_id: str
    edge_type: str
    weight: float = 1.0
    is_weak_bridge: bool = False  # Organizational-only connection


@dataclass
class SyntheticQuery:
    """A generated test query with ground truth."""
    query_id: str
    query_text: str
    expected_clusters: List[str]  # Clusters that SHOULD be relevant
    expected_agents: List[str]  # Agents that SHOULD activate
    difficulty: str  # "easy", "medium", "hard"
    query_type: str  # "technique", "entity", "term", "cross_domain"
    
    # For computing metrics
    relevant_nodes: List[str]  # Nodes that contain answer


@dataclass
class SyntheticDataset:
    """Complete generated dataset."""
    nodes: List[SyntheticNode]
    edges: List[SyntheticEdge]
    queries: List[SyntheticQuery]
    
    # Ground truth
    cluster_assignments: Dict[str, str]  # node_id -> cluster_id
    cluster_to_nodes: Dict[str, List[str]]  # cluster_id -> [node_ids]
    
    # Metadata
    random_seed: int
    config: Dict[str, any]
    
    # Hard case tracking
    shared_entities: List[str]
    weak_bridges: List[Tuple[str, str]]  # (source, target) pairs
    misleading_overlaps: List[str]


class SyntheticDataGenerator:
    """
    Generates synthetic ProtoGraph data for testing.
    
    Cluster structure mimics real ProtoGraph:
    - Technique clusters (MITRE-aligned)
    - Library module clusters (by C2 framework or function)
    - Robot log clusters (by test campaign)
    - Team clusters (organizational)
    - Training event clusters (by exercise)
    """
    
    # Concept types and their properties
    CONCEPT_SCHEMAS = {
        "Technique": {
            "required": ["technique_id", "name", "tactic"],
            "optional": ["description", "platforms"],
        },
        "LibraryModule": {
            "required": ["name", "category"],
            "optional": ["technique_id", "tactic", "risk_level", "author"],
        },
        "RobotLog": {
            "required": ["name", "timestamp", "result_status"],
            "optional": ["technique_id", "module_id", "command"],
        },
        "Team": {
            "required": ["name", "team_type"],
            "optional": ["members", "focus_area"],
        },
        "TrainingEvent": {
            "required": ["name", "event_type"],
            "optional": ["techniques_covered", "teams_involved", "date"],
        },
    }
    
    # Realistic MITRE-like data
    TACTICS = ["TA0001", "TA0002", "TA0003", "TA0004", "TA0005", "TA0006", "TA0007"]
    TECHNIQUES = [
        "T1003", "T1059", "T1078", "T1087", "T1110",
        "T1021", "T1053", "T1055", "T1071", "T1105",
        "T1003.001", "T1003.002", "T1059.001", "T1059.003",
    ]
    C2_FRAMEWORKS = ["Cobalt Strike", "Sliver", "Metasploit", "Havoc", "Mythic"]
    TEAM_NAMES = ["OPFOR", "Automation", "Content Development", "Range", "Red Team"]
    EVENT_TYPES = ["Exercise", "Training", "Assessment", "Drill"]
    
    # Terms for generating realistic names
    TECHNIQUE_VERBS = ["dump", "inject", "execute", "spawn", "harvest", "exfiltrate", "persist"]
    TECHNIQUE_NOUNS = ["credentials", "process", "memory", "registry", "token", "service"]
    MODULE_PREFIXES = ["beacon", "payload", "loader", "stager", "implant", "dropper"]
    
    def __init__(self, seed: int = EXPERIMENT_CONFIG.random_seed):
        self.seed = seed
        random.seed(seed)
        np.random.seed(seed)
        
        # Track generated items for consistency
        self._nodes: List[SyntheticNode] = []
        self._edges: List[SyntheticEdge] = []
        self._clusters: Dict[str, List[str]] = {}  # cluster_id -> node_ids
        
        # Hard case tracking
        self._shared_entities: List[str] = []
        self._weak_bridges: List[Tuple[str, str]] = []
        self._misleading_overlaps: List[str] = []
    
    def generate(
        self,
        num_nodes: int = EXPERIMENT_CONFIG.num_nodes,
        num_queries: int = EXPERIMENT_CONFIG.num_queries,
    ) -> SyntheticDataset:
        """
        Generate complete synthetic dataset.
        """
        self._nodes = []
        self._edges = []
        self._clusters = {}
        
        # === STEP 1: Generate base clusters ===
        self._generate_technique_clusters(num_nodes // 5)
        self._generate_library_clusters(num_nodes // 4)
        self._generate_log_clusters(num_nodes // 4)
        self._generate_team_cluster(num_nodes // 10)
        self._generate_event_clusters(num_nodes // 10)
        
        # === STEP 2: Add semantic edges (strong) ===
        self._generate_semantic_edges()
        
        # === STEP 3: Add hard cases ===
        num_shared = int(len(self._nodes) * EXPERIMENT_CONFIG.shared_entities_ratio)
        num_bridges = int(len(self._edges) * EXPERIMENT_CONFIG.weak_bridges_ratio)
        num_misleading = int(len(self._nodes) * EXPERIMENT_CONFIG.misleading_lexical_ratio)
        
        self._add_shared_entities(num_shared)
        self._add_weak_bridges(num_bridges)
        self._add_misleading_overlaps(num_misleading)
        
        # === STEP 4: Generate queries with ground truth ===
        queries = self._generate_queries(num_queries)
        
        # === STEP 5: Generate embeddings ===
        self._generate_embeddings()
        
        # Build cluster assignments
        cluster_assignments = {n.node_id: n.cluster_id for n in self._nodes if n.cluster_id}
        cluster_to_nodes = {}
        for cluster_id, node_ids in self._clusters.items():
            cluster_to_nodes[cluster_id] = node_ids
        
        return SyntheticDataset(
            nodes=self._nodes,
            edges=self._edges,
            queries=queries,
            cluster_assignments=cluster_assignments,
            cluster_to_nodes=cluster_to_nodes,
            random_seed=self.seed,
            config={
                "num_nodes": num_nodes,
                "num_queries": num_queries,
                "shared_entities_ratio": EXPERIMENT_CONFIG.shared_entities_ratio,
                "weak_bridges_ratio": EXPERIMENT_CONFIG.weak_bridges_ratio,
                "misleading_lexical_ratio": EXPERIMENT_CONFIG.misleading_lexical_ratio,
            },
            shared_entities=self._shared_entities,
            weak_bridges=self._weak_bridges,
            misleading_overlaps=self._misleading_overlaps,
        )
    
    def _generate_technique_clusters(self, count: int):
        """Generate technique nodes clustered by tactic."""
        for tactic in self.TACTICS[:4]:  # Use first 4 tactics
            cluster_id = f"cluster_technique_{tactic}"
            self._clusters[cluster_id] = []
            
            # Generate techniques for this tactic
            techniques_for_tactic = [t for t in self.TECHNIQUES if t.startswith("T")]
            num_in_cluster = min(count // 4, len(techniques_for_tactic))
            
            for i in range(num_in_cluster):
                tech_id = techniques_for_tactic[i % len(techniques_for_tactic)]
                verb = random.choice(self.TECHNIQUE_VERBS)
                noun = random.choice(self.TECHNIQUE_NOUNS)
                
                node = SyntheticNode(
                    node_id=f"tech_{tactic}_{i}",
                    concept_type="Technique",
                    name=f"{verb.title()} {noun.title()}",
                    properties={
                        "technique_id": tech_id,
                        "tactic": tactic,
                        "description": f"Technique for {verb}ing {noun}",
                    },
                    cluster_id=cluster_id,
                )
                self._nodes.append(node)
                self._clusters[cluster_id].append(node.node_id)
    
    def _generate_library_clusters(self, count: int):
        """Generate library module nodes clustered by C2 framework."""
        for framework in self.C2_FRAMEWORKS[:3]:  # Use first 3 frameworks
            cluster_id = f"cluster_library_{framework.lower().replace(' ', '_')}"
            self._clusters[cluster_id] = []
            
            num_in_cluster = count // 3
            for i in range(num_in_cluster):
                prefix = random.choice(self.MODULE_PREFIXES)
                tech = random.choice(self.TECHNIQUES)
                
                node = SyntheticNode(
                    node_id=f"lib_{framework[:2].lower()}_{i}",
                    concept_type="LibraryModule",
                    name=f"{prefix}_{framework[:2].lower()}_{i}",
                    properties={
                        "category": framework,
                        "technique_id": tech,
                        "tactic": random.choice(self.TACTICS),
                        "risk_level": random.choice(["High", "Medium", "Low"]),
                    },
                    cluster_id=cluster_id,
                )
                self._nodes.append(node)
                self._clusters[cluster_id].append(node.node_id)
    
    def _generate_log_clusters(self, count: int):
        """Generate robot log nodes clustered by campaign."""
        campaigns = ["campaign_alpha", "campaign_beta", "campaign_gamma"]
        
        for campaign in campaigns:
            cluster_id = f"cluster_logs_{campaign}"
            self._clusters[cluster_id] = []
            
            num_in_cluster = count // 3
            for i in range(num_in_cluster):
                tech = random.choice(self.TECHNIQUES)
                status = random.choice(["PASS", "FAIL"])
                
                node = SyntheticNode(
                    node_id=f"log_{campaign}_{i}",
                    concept_type="RobotLog",
                    name=f"Test_{campaign}_{i}",
                    properties={
                        "timestamp": f"2025-01-{10+i:02d}T10:00:00Z",
                        "result_status": status,
                        "technique_id": tech,
                        "command": f"Run-Test -Technique {tech}",
                    },
                    cluster_id=cluster_id,
                )
                self._nodes.append(node)
                self._clusters[cluster_id].append(node.node_id)
    
    def _generate_team_cluster(self, count: int):
        """Generate team nodes (single cluster typically)."""
        cluster_id = "cluster_teams"
        self._clusters[cluster_id] = []
        
        for i, team_name in enumerate(self.TEAM_NAMES):
            node = SyntheticNode(
                node_id=f"team_{i}",
                concept_type="Team",
                name=team_name,
                properties={
                    "team_type": "Red" if "OPFOR" in team_name or "Red" in team_name else "Support",
                    "focus_area": random.choice(["Offensive", "Defensive", "Infrastructure"]),
                },
                cluster_id=cluster_id,
            )
            self._nodes.append(node)
            self._clusters[cluster_id].append(node.node_id)
    
    def _generate_event_clusters(self, count: int):
        """Generate training event nodes."""
        cluster_id = "cluster_events"
        self._clusters[cluster_id] = []
        
        for i in range(count):
            event_type = random.choice(self.EVENT_TYPES)
            techniques_covered = random.sample(self.TECHNIQUES, min(3, len(self.TECHNIQUES)))
            
            node = SyntheticNode(
                node_id=f"event_{i}",
                concept_type="TrainingEvent",
                name=f"{event_type} {i+1}",
                properties={
                    "event_type": event_type,
                    "techniques_covered": techniques_covered,
                    "teams_involved": random.sample(self.TEAM_NAMES, 2),
                },
                cluster_id=cluster_id,
            )
            self._nodes.append(node)
            self._clusters[cluster_id].append(node.node_id)
    
    def _generate_semantic_edges(self):
        """Generate strong semantic edges between related nodes."""
        node_map = {n.node_id: n for n in self._nodes}
        
        # Technique -> LibraryModule (IMPLEMENTED_BY)
        tech_nodes = [n for n in self._nodes if n.concept_type == "Technique"]
        lib_nodes = [n for n in self._nodes if n.concept_type == "LibraryModule"]
        
        for lib_node in lib_nodes:
            tech_id = lib_node.properties.get("technique_id")
            if tech_id:
                # Find matching technique node
                for tech_node in tech_nodes:
                    if tech_node.properties.get("technique_id") == tech_id:
                        self._edges.append(SyntheticEdge(
                            source_id=lib_node.node_id,
                            target_id=tech_node.node_id,
                            edge_type="IMPLEMENTS",
                        ))
                        break
        
        # LibraryModule -> RobotLog (TESTED_BY)
        log_nodes = [n for n in self._nodes if n.concept_type == "RobotLog"]
        
        for log_node in log_nodes:
            tech_id = log_node.properties.get("technique_id")
            # Find library modules with same technique
            matching_libs = [
                l for l in lib_nodes 
                if l.properties.get("technique_id") == tech_id
            ]
            if matching_libs:
                lib_node = random.choice(matching_libs)
                self._edges.append(SyntheticEdge(
                    source_id=lib_node.node_id,
                    target_id=log_node.node_id,
                    edge_type="TESTED_BY",
                ))
        
        # Team -> LibraryModule (AUTHORED)
        team_nodes = [n for n in self._nodes if n.concept_type == "Team"]
        for lib_node in lib_nodes:
            team = random.choice(team_nodes)
            self._edges.append(SyntheticEdge(
                source_id=team.node_id,
                target_id=lib_node.node_id,
                edge_type="AUTHORED",
            ))
        
        # TrainingEvent -> Technique (COVERS)
        event_nodes = [n for n in self._nodes if n.concept_type == "TrainingEvent"]
        for event_node in event_nodes:
            techniques_covered = event_node.properties.get("techniques_covered", [])
            for tech_id in techniques_covered:
                for tech_node in tech_nodes:
                    if tech_node.properties.get("technique_id") == tech_id:
                        self._edges.append(SyntheticEdge(
                            source_id=event_node.node_id,
                            target_id=tech_node.node_id,
                            edge_type="COVERS",
                        ))
                        break
    
    def _add_shared_entities(self, count: int):
        """
        Add nodes that belong to multiple clusters (hard case).
        These are modules/techniques that span domains.
        """
        lib_nodes = [n for n in self._nodes if n.concept_type == "LibraryModule"]
        
        for i in range(min(count, len(lib_nodes) // 2)):
            # Pick a random library module
            node = random.choice(lib_nodes)
            
            # Give it properties from another cluster
            other_framework = random.choice([
                f for f in self.C2_FRAMEWORKS if f != node.properties.get("category")
            ])
            
            # Mark as shared
            node.is_shared_entity = True
            node.properties["secondary_category"] = other_framework
            
            self._shared_entities.append(node.node_id)
            
            # Add edge to a node in the other cluster
            other_cluster = f"cluster_library_{other_framework.lower().replace(' ', '_')}"
            if other_cluster in self._clusters and self._clusters[other_cluster]:
                target = random.choice(self._clusters[other_cluster])
                self._edges.append(SyntheticEdge(
                    source_id=node.node_id,
                    target_id=target,
                    edge_type="RELATED_TO",
                ))
    
    def _add_weak_bridges(self, count: int):
        """
        Add weak organizational edges (hard case).
        These connect clusters through org relationships, not semantic ones.
        """
        team_nodes = [n for n in self._nodes if n.concept_type == "Team"]
        lib_nodes = [n for n in self._nodes if n.concept_type == "LibraryModule"]
        
        for i in range(count):
            team = random.choice(team_nodes)
            lib = random.choice(lib_nodes)
            
            edge = SyntheticEdge(
                source_id=team.node_id,
                target_id=lib.node_id,
                edge_type="OWNED_BY",
                is_weak_bridge=True,
            )
            self._edges.append(edge)
            self._weak_bridges.append((team.node_id, lib.node_id))
            
            # Mark nodes
            lib_node = next(n for n in self._nodes if n.node_id == lib.node_id)
            lib_node.is_bridge = True
    
    def _add_misleading_overlaps(self, count: int):
        """
        Add nodes with terms that overlap unrelated clusters (hard case).
        E.g., "credential_scanner" in logs that's unrelated to T1003.
        """
        log_nodes = [n for n in self._nodes if n.concept_type == "RobotLog"]
        
        misleading_terms = [
            ("credential", "T1087"),  # credential in name but T1087 (account discovery) not T1003
            ("process", "T1071"),     # process in name but T1071 (C2) not T1055 (injection)
            ("memory", "T1053"),      # memory in name but T1053 (scheduled task) not T1003.001
        ]
        
        for i in range(min(count, len(log_nodes) // 3)):
            term, actual_tech = random.choice(misleading_terms)
            node = random.choice(log_nodes)
            
            # Update name to include misleading term
            node.name = f"{term}_test_{node.node_id}"
            node.properties["technique_id"] = actual_tech  # Actual technique is different
            node.has_misleading_terms = True
            
            self._misleading_overlaps.append(node.node_id)
    
    def _generate_queries(self, count: int) -> List[SyntheticQuery]:
        """
        Generate test queries with ground truth expected clusters/agents.
        """
        queries = []
        
        # Distribution: 40% easy, 35% medium, 25% hard
        num_easy = int(count * 0.4)
        num_medium = int(count * 0.35)
        num_hard = count - num_easy - num_medium
        
        # Easy queries - explicit technique or entity mentions
        queries.extend(self._generate_easy_queries(num_easy))
        
        # Medium queries - require some propagation
        queries.extend(self._generate_medium_queries(num_medium))
        
        # Hard queries - cross-domain or misleading
        queries.extend(self._generate_hard_queries(num_hard))
        
        return queries
    
    def _generate_easy_queries(self, count: int) -> List[SyntheticQuery]:
        """Generate queries with explicit technique/entity mentions."""
        queries = []
        
        for i in range(count):
            query_type = random.choice(["technique", "entity"])
            
            if query_type == "technique":
                tech = random.choice(self.TECHNIQUES)
                query_text = f"What modules implement {tech}?"
                
                # Expected: technique cluster + library clusters with this technique
                expected_clusters = []
                for cluster_id, node_ids in self._clusters.items():
                    for node_id in node_ids:
                        node = next(n for n in self._nodes if n.node_id == node_id)
                        if node.properties.get("technique_id") == tech:
                            expected_clusters.append(cluster_id)
                            break
                
                expected_clusters = list(set(expected_clusters))
                
            else:  # entity
                framework = random.choice(self.C2_FRAMEWORKS[:3])
                query_text = f"Show me {framework} modules"
                
                # Expected: library cluster for this framework
                cluster_id = f"cluster_library_{framework.lower().replace(' ', '_')}"
                expected_clusters = [cluster_id] if cluster_id in self._clusters else []
            
            queries.append(SyntheticQuery(
                query_id=f"easy_{i}",
                query_text=query_text,
                expected_clusters=expected_clusters,
                expected_agents=[f"agent_{c}" for c in expected_clusters],
                difficulty="easy",
                query_type=query_type,
                relevant_nodes=self._get_relevant_nodes(expected_clusters),
            ))
        
        return queries
    
    def _generate_medium_queries(self, count: int) -> List[SyntheticQuery]:
        """Generate queries that require propagation."""
        queries = []
        
        for i in range(count):
            query_type = random.choice(["propagation", "multi_cluster"])
            
            if query_type == "propagation":
                # Query about test results for a technique (requires Technique -> Library -> Log propagation)
                tech = random.choice(self.TECHNIQUES)
                query_text = f"What are the test results for {tech}?"
                
                # Expected: technique cluster, library cluster, log cluster
                expected_clusters = set()
                for cluster_id, node_ids in self._clusters.items():
                    for node_id in node_ids:
                        node = next(n for n in self._nodes if n.node_id == node_id)
                        if node.properties.get("technique_id") == tech:
                            expected_clusters.add(cluster_id)
                
                expected_clusters = list(expected_clusters)
                
            else:  # multi_cluster
                # Query spanning multiple domains
                framework = random.choice(self.C2_FRAMEWORKS[:3])
                tactic = random.choice(self.TACTICS[:4])
                query_text = f"What {framework} capabilities cover {tactic}?"
                
                # Expected: library cluster + technique cluster
                lib_cluster = f"cluster_library_{framework.lower().replace(' ', '_')}"
                tech_cluster = f"cluster_technique_{tactic}"
                expected_clusters = [c for c in [lib_cluster, tech_cluster] if c in self._clusters]
            
            queries.append(SyntheticQuery(
                query_id=f"medium_{i}",
                query_text=query_text,
                expected_clusters=expected_clusters,
                expected_agents=[f"agent_{c}" for c in expected_clusters],
                difficulty="medium",
                query_type=query_type,
                relevant_nodes=self._get_relevant_nodes(expected_clusters),
            ))
        
        return queries
    
    def _generate_hard_queries(self, count: int) -> List[SyntheticQuery]:
        """Generate queries with misleading terms or cross-domain requirements."""
        queries = []
        
        for i in range(count):
            query_type = random.choice(["misleading", "cross_domain"])
            
            if query_type == "misleading":
                # Query that uses a term present in misleading nodes
                # Correct answer requires understanding context, not just lexical match
                query_text = "Find all credential-related test logs"
                
                # Expected: only logs that actually test credential techniques (T1003.*)
                # NOT logs with "credential" in name but different technique
                expected_clusters = []
                for cluster_id, node_ids in self._clusters.items():
                    if "logs" in cluster_id:
                        for node_id in node_ids:
                            node = next(n for n in self._nodes if n.node_id == node_id)
                            tech = node.properties.get("technique_id", "")
                            if tech.startswith("T1003"):
                                expected_clusters.append(cluster_id)
                                break
                
                expected_clusters = list(set(expected_clusters))
                
            else:  # cross_domain
                # Query requiring synthesis across unrelated clusters
                query_text = "What training events involved OPFOR testing credential techniques?"
                
                # Expected: events cluster + teams cluster + technique cluster + logs cluster
                expected_clusters = ["cluster_events", "cluster_teams"]
                for cluster_id in self._clusters:
                    if "technique_TA0006" in cluster_id:  # Credential access tactic
                        expected_clusters.append(cluster_id)
                    if "logs" in cluster_id:
                        expected_clusters.append(cluster_id)
                
                expected_clusters = list(set([c for c in expected_clusters if c in self._clusters]))
            
            queries.append(SyntheticQuery(
                query_id=f"hard_{i}",
                query_text=query_text,
                expected_clusters=expected_clusters,
                expected_agents=[f"agent_{c}" for c in expected_clusters],
                difficulty="hard",
                query_type=query_type,
                relevant_nodes=self._get_relevant_nodes(expected_clusters),
            ))
        
        return queries
    
    def _get_relevant_nodes(self, cluster_ids: List[str]) -> List[str]:
        """Get all nodes in the given clusters."""
        nodes = []
        for cluster_id in cluster_ids:
            nodes.extend(self._clusters.get(cluster_id, []))
        return nodes
    
    def _generate_embeddings(self):
        """
        Generate synthetic embeddings for nodes.
        Embeddings are structured so similar nodes have high cosine similarity.
        """
        embedding_dim = 768
        
        # Generate cluster centroids
        cluster_centroids = {}
        for cluster_id in self._clusters:
            # Random centroid with some structure based on cluster type
            centroid = np.random.randn(embedding_dim)
            
            # Add bias based on cluster type
            if "technique" in cluster_id:
                centroid[:100] += 1.0  # Technique dimension
            elif "library" in cluster_id:
                centroid[100:200] += 1.0  # Library dimension
            elif "logs" in cluster_id:
                centroid[200:300] += 1.0  # Log dimension
            elif "team" in cluster_id:
                centroid[300:400] += 1.0  # Team dimension
            elif "event" in cluster_id:
                centroid[400:500] += 1.0  # Event dimension
            
            centroid = centroid / np.linalg.norm(centroid)
            cluster_centroids[cluster_id] = centroid
        
        # Generate node embeddings near their cluster centroid
        for node in self._nodes:
            if node.cluster_id and node.cluster_id in cluster_centroids:
                centroid = cluster_centroids[node.cluster_id]
                # Add noise
                noise = np.random.randn(embedding_dim) * 0.2
                embedding = centroid + noise
                embedding = embedding / np.linalg.norm(embedding)
            else:
                embedding = np.random.randn(embedding_dim)
                embedding = embedding / np.linalg.norm(embedding)
            
            node.properties["embedding"] = embedding.tolist()
