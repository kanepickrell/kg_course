#!/usr/bin/env python3
"""
Graph Health & LLM Edge Discovery Engine 
"""

import json
import random
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from enum import Enum
from functools import lru_cache

import networkx as nx
from arango.database import StandardDatabase
import os


# ============================================================================
# DATA MODELS
# ============================================================================

class HealthStatus(Enum):
    HEALTHY = "healthy"
    NEEDS_DISCOVERY = "needs_discovery"
    CRITICAL = "critical"


class MatchType(Enum):
    """How a connection was discovered"""
    ATTRIBUTE_MATCH = "attribute_match"      # Shared technique_id, tactic, etc.
    CROSS_FIELD_MATCH = "cross_field_match"  # assigned_to ↔ name
    TEXT_REFERENCE = "text_reference"        # Name appears in description
    KEYWORD_MATCH = "keyword_match"          # Shared significant keyword
    LLM_SEMANTIC = "llm_semantic"            # LLM found semantic relationship


@dataclass
class GraphHealthReport:
    """Current graph health statistics"""
    timestamp: str
    
    # Basic counts
    num_nodes: int
    num_edges: int
    
    # Connectivity metrics
    edge_density: float
    avg_connections_per_node: float
    max_degree: int
    min_degree: int
    median_degree: float
    
    # Clustering
    clustering_coefficient: float
    
    # Component analysis
    num_weakly_connected_components: int
    largest_wcc_size: int
    num_orphan_nodes: int
    
    # Per-collection breakdown
    nodes_by_collection: Dict[str, int]
    edges_by_type: Dict[str, int]
    
    # Health assessment
    status: str
    issues: List[str]
    
    def to_dict(self):
        return asdict(self)


@dataclass
class DiscoveryTriggerResult:
    """Result of checking if discovery should run"""
    should_trigger: bool
    reason: str
    priority: str  # "low", "medium", "high"
    candidates: List[Dict[str, Any]]
    artifact_id: str
    health_snapshot: Dict[str, Any]


@dataclass 
class EdgeSuggestion:
    """A suggested edge from LLM discovery"""
    source_id: str
    target_id: str
    relationship_type: str
    relationship_uri: str  # URI from ontology
    confidence: float
    explanation: str  # CONCISE single sentence
    source_label: str
    target_label: str
    discovered_at: str
    model_used: str
    match_type: str  # "attribute_match", "text_reference", "llm_semantic"
    match_details: Dict[str, Any]  # What specifically matched


# ============================================================================
# ONTOLOGY-DRIVEN RELATIONSHIP RESOLVER
# ============================================================================

class OntologyRelationshipResolver:
    """
    Resolves valid relationship types from the ontology based on source/target concepts.
    
    This class queries:
    - ontology_concepts: To map collections to concept URIs
    - relationship_types: To find valid relationships for concept pairs
    
    It handles inheritance - if LibraryModule is a child of Artifact, and there's
    a relationship defined for Artifact → Agent, it applies to LibraryModule too.
    """
    
    def __init__(self, db: StandardDatabase):
        self.db = db
        self._concept_cache: Dict[str, Dict] = {}
        self._hierarchy_cache: Dict[str, List[str]] = {}
        self._collection_to_concept: Dict[str, str] = {}
        self._valid_targets_cache: Dict[str, Set[str]] = {}
    
    def _load_collection_mappings(self):
        """Load all collection → concept URI mappings"""
        if self._collection_to_concept:
            return
        
        try:
            query = """
                FOR c IN ontology_concepts
                    FILTER c.collection != null
                    RETURN { collection: c.collection, uri: c.uri }
            """
            for row in self.db.aql.execute(query):
                self._collection_to_concept[row['collection']] = row['uri']
        except Exception as e:
            print(f"Error loading collection mappings: {e}")
    
    def _get_concept_for_collection(self, collection_name: str) -> Optional[Dict]:
        """Get the ontology concept for a collection name"""
        if collection_name in self._concept_cache:
            return self._concept_cache[collection_name]
        
        try:
            query = """
                FOR c IN ontology_concepts
                    FILTER c.collection == @coll
                    RETURN c
            """
            result = list(self.db.aql.execute(query, bind_vars={"coll": collection_name}))
            concept = result[0] if result else None
            self._concept_cache[collection_name] = concept
            return concept
        except Exception as e:
            print(f"Error getting concept for collection {collection_name}: {e}")
            return None
    
    def _get_concept_hierarchy(self, concept_uri: str) -> List[str]:
        """
        Get all ancestor concept URIs for a concept (including itself).
        
        For LibraryModule, returns: [proto:concept/LibraryModule, proto:concept/Artifact, proto:concept/Thing]
        """
        if concept_uri in self._hierarchy_cache:
            return self._hierarchy_cache[concept_uri]
        
        hierarchy = [concept_uri]
        
        try:
            # Walk up the parent chain
            current_uri = concept_uri
            max_depth = 10  # Prevent infinite loops
            
            for _ in range(max_depth):
                query = """
                    FOR c IN ontology_concepts
                        FILTER c.uri == @uri
                        RETURN c.parent_uri
                """
                result = list(self.db.aql.execute(query, bind_vars={"uri": current_uri}))
                
                if not result or not result[0]:
                    break
                    
                parent_uri = result[0]
                hierarchy.append(parent_uri)
                current_uri = parent_uri
            
            self._hierarchy_cache[concept_uri] = hierarchy
            return hierarchy
            
        except Exception as e:
            print(f"Error getting hierarchy for {concept_uri}: {e}")
            return hierarchy
    
    def get_valid_target_collections(self, source_collection: str) -> Set[str]:
        if source_collection in self._valid_targets_cache:
            return self._valid_targets_cache[source_collection]
        
        self._load_collection_mappings()
        
        source_concept = self._get_concept_for_collection(source_collection)
        if not source_concept:
            return self._get_all_data_collections()
        
        source_hierarchy = self._get_concept_hierarchy(source_concept['uri'])
        valid_targets: Set[str] = set()
        
        try:
            query = """
                FOR rel IN relationship_types
                    LET source_match = LENGTH(
                        FOR s IN @source_hierarchy
                            FILTER s IN rel.domain
                            RETURN 1
                    ) > 0
                    
                    FILTER source_match
                    
                    // Get all concepts that could be targets (in range or children of range)
                    FOR range_concept IN rel.range
                        // Direct match
                        FOR c IN ontology_concepts
                            FILTER c.uri == range_concept OR c.parent_uri == range_concept
                            FILTER c.collection != null
                            RETURN DISTINCT c.collection
            """
            
            result = list(self.db.aql.execute(query, bind_vars={
                "source_hierarchy": source_hierarchy
            }))
            
            valid_targets = set(result)
            
            # Also check for concepts that inherit from range concepts (deeper)
            query2 = """
                FOR rel IN relationship_types
                    LET source_match = LENGTH(
                        FOR s IN @source_hierarchy
                            FILTER s IN rel.domain
                            RETURN 1
                    ) > 0
                    
                    FILTER source_match
                    
                    FOR range_concept IN rel.range
                        FOR c IN ontology_concepts
                            FILTER c.collection != null
                            LET parents = (
                                FOR p IN 0..5 
                                    LET current = p == 0 ? c.uri : (
                                        FOR pc IN ontology_concepts 
                                            FILTER pc.uri == c.parent_uri 
                                            RETURN pc.uri
                                    )[0]
                                    FILTER current != null
                                    RETURN current
                            )
                            FILTER range_concept IN parents
                            RETURN DISTINCT c.collection
            """
            
            result2 = list(self.db.aql.execute(query2, bind_vars={
                "source_hierarchy": source_hierarchy
            }))
            
            valid_targets.update(result2)
            
        except Exception as e:
            print(f"Error getting valid targets for {source_collection}: {e}")
            return self._get_all_data_collections()
        
        self._valid_targets_cache[source_collection] = valid_targets
        
        print(f"📋 Valid target collections for {source_collection}: {valid_targets}")
        return valid_targets
    
    def _get_all_data_collections(self) -> Set[str]:
        """Get all non-system, non-edge collections"""
        collections = set()
        try:
            for coll in self.db.collections():
                if not coll['name'].startswith('_') and coll.get('type') != 3:
                    if coll['name'] not in {'ontology_concepts', 'concept_properties', 
                                            'relationship_types', 'taxonomy_terms', 'taxonomies',
                                            'taxonomy_schemes', 'ontology_edges'}:
                        collections.add(coll['name'])
        except Exception as e:
            print(f"Error listing collections: {e}")
        return collections
    
    def get_valid_relationships(
        self, 
        source_collection: str, 
        target_collection: str
    ) -> List[Dict]:
        """
        Get valid relationship types for a source/target collection pair.
        
        Returns list of relationship type dicts with: uri, label, definition, inverse
        """
        source_concept = self._get_concept_for_collection(source_collection)
        target_concept = self._get_concept_for_collection(target_collection)
        
        if not source_concept or not target_concept:
            print(f"Warning: Could not find concepts for {source_collection} or {target_collection}")
            return self._get_fallback_relationships()
        
        source_hierarchy = self._get_concept_hierarchy(source_concept['uri'])
        target_hierarchy = self._get_concept_hierarchy(target_concept['uri'])
        
        try:
            query = """
                FOR rel IN relationship_types
                    LET source_match = LENGTH(
                        FOR s IN @source_hierarchy
                            FILTER s IN rel.domain
                            RETURN 1
                    ) > 0
                    
                    LET target_match = LENGTH(
                        FOR t IN @target_hierarchy
                            FILTER t IN rel.range
                            RETURN 1
                    ) > 0
                    
                    FILTER source_match AND target_match
                    
                    RETURN {
                        uri: rel.uri,
                        label: rel.label,
                        definition: rel.definition,
                        inverse: rel.inverse,
                        symmetric: rel.symmetric,
                        transitive: rel.transitive
                    }
            """
            
            result = list(self.db.aql.execute(query, bind_vars={
                "source_hierarchy": source_hierarchy,
                "target_hierarchy": target_hierarchy
            }))
            
            if result:
                return result
            else:
                print(f"No relationships found for {source_collection} → {target_collection}")
                return self._get_fallback_relationships()
                
        except Exception as e:
            print(f"Error querying relationships: {e}")
            return self._get_fallback_relationships()
    
    def _get_fallback_relationships(self) -> List[Dict]:
        """Fallback relationships when ontology query fails."""
        return [{
            "uri": "proto:rel/RELATED_TO",
            "label": "RELATED_TO",
            "definition": "Indicates a generic relationship between any two entities",
            "inverse": None,
            "symmetric": True,
            "transitive": False
        }]
    
    def clear_cache(self):
        """Clear internal caches (call after ontology changes)"""
        self._concept_cache.clear()
        self._hierarchy_cache.clear()
        self._collection_to_concept.clear()
        self._valid_targets_cache.clear()


# ============================================================================
# GRAPH HEALTH CALCULATOR
# ============================================================================

class GraphHealthCalculator:
    """
    Calculates graph health statistics using NetworkX.
    
    Dynamically discovers edge collections from relationship_types.
    """
    
    # Collections to exclude from node queries (schema/ontology collections)
    SCHEMA_COLLECTIONS = {
        'ontology_concepts', 'concept_properties', 'relationship_types',
        'taxonomy_terms', 'taxonomies', 'ontology_properties',
        'taxonomy_schemes', 'ontology_edges'
    }
    
    def __init__(self, db: StandardDatabase):
        self.db = db
        self._edge_collections = None
    
    @property
    def edge_collections(self) -> List[str]:
        """Dynamically get edge collections from ontology + known collections"""
        if self._edge_collections is None:
            self._edge_collections = self._discover_edge_collections()
        return self._edge_collections
    
    def _discover_edge_collections(self) -> List[str]:
        """Discover edge collections from relationship_types and existing collections"""
        edge_colls = set()
        
        try:
            if self.db.has_collection('relationship_types'):
                query = "FOR r IN relationship_types RETURN DISTINCT r.label"
                labels = list(self.db.aql.execute(query))
                edge_colls.update(labels)
        except Exception as e:
            print(f"Could not query relationship_types: {e}")
        
        try:
            for coll in self.db.collections():
                if coll.get('type') == 3:  # Edge collection type
                    if not coll['name'].startswith('_'):
                        edge_colls.add(coll['name'])
        except Exception as e:
            print(f"Could not list collections: {e}")
        
        return list(edge_colls)
    
    def get_data_collections(self) -> List[str]:
        """Get all collections that contain actual data (not schema/edges)"""
        data_colls = []
        for coll in self.db.collections():
            name = coll['name']
            if (name.startswith('_') or 
                name in self.edge_collections or 
                name in self.SCHEMA_COLLECTIONS or
                coll.get('type') == 3):
                continue
            data_colls.append(name)
        return data_colls
    
    def get_all_nodes(self) -> List[Dict]:
        """Fetch all nodes from data collections"""
        nodes = []
        for coll_name in self.get_data_collections():
            try:
                query = f"FOR doc IN `{coll_name}` RETURN doc"
                nodes.extend(list(self.db.aql.execute(query)))
            except:
                continue
        return nodes
    
    def get_all_edges(self) -> List[Dict]:
        """Fetch all edges from edge collections"""
        edges = []
        for coll_name in self.edge_collections:
            try:
                if self.db.has_collection(coll_name):
                    query = f"FOR doc IN `{coll_name}` RETURN doc"
                    edges.extend(list(self.db.aql.execute(query)))
            except:
                continue
        return edges
    
    def calculate_health(self) -> GraphHealthReport:
        """Calculate comprehensive graph health statistics."""
        nodes = self.get_all_nodes()
        edges = self.get_all_edges()
        
        num_nodes = len(nodes)
        num_edges = len(edges)
        
        G = nx.DiGraph()
        
        for node in nodes:
            G.add_node(node['_id'], **node)
        
        for edge in edges:
            if edge.get('_from') and edge.get('_to'):
                G.add_edge(edge['_from'], edge['_to'], **edge)
        
        degrees = [d for n, d in G.degree()]
        if degrees:
            max_degree = max(degrees)
            min_degree = min(degrees)
            median_degree = sorted(degrees)[len(degrees) // 2]
        else:
            max_degree = min_degree = median_degree = 0
        
        if num_nodes > 1:
            edge_density = num_edges / (num_nodes * (num_nodes - 1))
        else:
            edge_density = 0.0
        
        avg_connections = num_edges / num_nodes if num_nodes > 0 else 0.0
        
        try:
            clustering = nx.average_clustering(G.to_undirected())
        except:
            clustering = 0.0
        
        if num_nodes > 0:
            wccs = list(nx.weakly_connected_components(G))
            num_wccs = len(wccs)
            largest_wcc = max(len(wcc) for wcc in wccs) if wccs else 0
        else:
            num_wccs = 0
            largest_wcc = 0
        
        orphan_count = sum(1 for n, d in G.degree() if d == 0)
        
        nodes_by_collection = {}
        for node in nodes:
            coll = node['_id'].split('/')[0]
            nodes_by_collection[coll] = nodes_by_collection.get(coll, 0) + 1
        
        edges_by_type = {}
        for edge in edges:
            coll = edge['_id'].split('/')[0]
            edges_by_type[coll] = edges_by_type.get(coll, 0) + 1
        
        issues = []
        status = HealthStatus.HEALTHY.value
        
        if orphan_count > 0:
            issues.append(f"{orphan_count} orphan node(s) with no connections")
            status = HealthStatus.NEEDS_DISCOVERY.value
        
        if edge_density < 0.01 and num_nodes > 10:
            issues.append(f"Low edge density ({edge_density:.4f}) - graph may be under-connected")
            status = HealthStatus.NEEDS_DISCOVERY.value
        
        if num_wccs > 1:
            issues.append(f"Graph fragmented into {num_wccs} disconnected components")
            if num_wccs > 5:
                status = HealthStatus.CRITICAL.value
            else:
                status = HealthStatus.NEEDS_DISCOVERY.value
        
        if avg_connections < 1.0 and num_nodes > 5:
            issues.append(f"Low average connections ({avg_connections:.2f}) per node")
        
        return GraphHealthReport(
            timestamp=datetime.utcnow().isoformat(),
            num_nodes=num_nodes,
            num_edges=num_edges,
            edge_density=round(edge_density, 6),
            avg_connections_per_node=round(avg_connections, 2),
            max_degree=max_degree,
            min_degree=min_degree,
            median_degree=median_degree,
            clustering_coefficient=round(clustering, 4),
            num_weakly_connected_components=num_wccs,
            largest_wcc_size=largest_wcc,
            num_orphan_nodes=orphan_count,
            nodes_by_collection=nodes_by_collection,
            edges_by_type=edges_by_type,
            status=status,
            issues=issues
        )


# ============================================================================
# DISCOVERY TRIGGER (ONTOLOGY-DRIVEN CANDIDATE SELECTION)
# ============================================================================

class DiscoveryTrigger:
    """
    Determines when LLM edge discovery should run.
    
    **ONTOLOGY-DRIVEN:**
    - Candidate selection queries ontology to find collections with valid relationships
    - Only selects candidates from collections where relationships are defined
    """
    
    EDGE_DENSITY_THRESHOLD = 0.005
    MAX_ORPHANS_BEFORE_CRITICAL = 5
    
    def __init__(self, db: StandardDatabase, health_calculator: GraphHealthCalculator):
        self.db = db
        self.health_calc = health_calculator
        self.relationship_resolver = OntologyRelationshipResolver(db)
    
    def check_trigger(
        self, 
        new_artifact_id: str,
        previous_health: Optional[GraphHealthReport] = None
    ) -> DiscoveryTriggerResult:
        """Check if discovery should be triggered for a new artifact."""
        current_health = self.health_calc.calculate_health()
        
        should_trigger = False
        reasons = []
        priority = "low"
        
        new_node_degree = self._get_node_degree(new_artifact_id)
        if new_node_degree == 0:
            should_trigger = True
            reasons.append(f"New artifact '{new_artifact_id}' has no connections")
            priority = "high"
        
        if previous_health:
            if current_health.num_weakly_connected_components > previous_health.num_weakly_connected_components:
                should_trigger = True
                reasons.append("Graph fragmentation increased")
                priority = "medium" if priority != "high" else priority
            
            density_delta = current_health.edge_density - previous_health.edge_density
            if density_delta < -0.001:
                should_trigger = True
                reasons.append(f"Edge density dropped by {abs(density_delta):.4f}")
        
        if current_health.status == HealthStatus.CRITICAL.value:
            should_trigger = True
            priority = "high"
            reasons.append("Graph health is critical")
        elif current_health.status == HealthStatus.NEEDS_DISCOVERY.value and not should_trigger:
            should_trigger = True
            priority = "medium"
            reasons.append("Graph health indicates discovery needed")
        
        candidates = []
        if should_trigger:
            candidates = self._select_candidates_ontology_driven(new_artifact_id, limit=20)
        
        return DiscoveryTriggerResult(
            should_trigger=should_trigger,
            reason="; ".join(reasons) if reasons else "No issues detected",
            priority=priority,
            candidates=candidates,
            artifact_id=new_artifact_id,
            health_snapshot={
                "num_nodes": current_health.num_nodes,
                "num_edges": current_health.num_edges,
                "edge_density": current_health.edge_density,
                "num_wccs": current_health.num_weakly_connected_components,
                "orphans": current_health.num_orphan_nodes
            }
        )
    
    def _get_node_degree(self, node_id: str) -> int:
        """Get the degree (number of connections) for a node"""
        edge_collections = self.health_calc.edge_collections
        
        total_degree = 0
        for coll in edge_collections:
            try:
                if not self.db.has_collection(coll):
                    continue
                query = f"""
                    FOR e IN `{coll}`
                        FILTER e._from == @node_id OR e._to == @node_id
                        COLLECT WITH COUNT INTO cnt
                        RETURN cnt
                """
                result = list(self.db.aql.execute(query, bind_vars={"node_id": node_id}))
                if result:
                    total_degree += result[0]
            except:
                continue
        
        return total_degree
    
    def _select_candidates_ontology_driven(self, new_artifact_id: str, limit: int = 20) -> List[Dict]:
        """
        ONTOLOGY-DRIVEN candidate selection.
        
        Only selects from collections that have valid relationship types defined.
        """
        candidates = []
        seen_ids = {new_artifact_id}
        
        source_collection = new_artifact_id.split('/')[0]
        
        valid_target_collections = self.relationship_resolver.get_valid_target_collections(source_collection)
        
        print(f"\n🎯 Ontology-driven candidate selection for {new_artifact_id}")
        print(f"   Valid target collections: {valid_target_collections}")
        
        if not valid_target_collections:
            print(f"   ⚠️ No valid target collections found - using all data collections")
            valid_target_collections = set(self.health_calc.get_data_collections())
        
        per_collection_limit = max(3, limit // len(valid_target_collections)) if valid_target_collections else limit
        
        for target_coll in valid_target_collections:
            if not self.db.has_collection(target_coll):
                continue
            
            try:
                query = f"""
                    FOR doc IN `{target_coll}`
                        FILTER doc._id != @new_id
                        SORT RAND()
                        LIMIT @limit
                        RETURN {{
                            _id: doc._id,
                            label: doc.name || doc.label || doc.title || doc._key,
                            type: '{target_coll}',
                            description: SUBSTRING(doc.description || '', 0, 200),
                            technique_id: doc.technique_id,
                            category: doc.category,
                            tactic: doc.tactic,
                            team: doc.team,
                            owner: doc.owner,
                            sprint: doc.sprint,
                            name: doc.name,
                            title: doc.title
                        }}
                """
                
                results = list(self.db.aql.execute(query, bind_vars={
                    "new_id": new_artifact_id,
                    "limit": per_collection_limit
                }))
                
                for c in results:
                    if c['_id'] not in seen_ids:
                        candidates.append(c)
                        seen_ids.add(c['_id'])
                        
                print(f"   ✓ {target_coll}: {len(results)} candidates")
                
            except Exception as e:
                print(f"   ❌ Error getting candidates from {target_coll}: {e}")
        
        random.shuffle(candidates)
        
        print(f"   📊 Total candidates: {len(candidates)}")
        
        return candidates[:limit]


# ============================================================================
# HYBRID MATCHING ENGINE (Attribute + Text + LLM)
# ============================================================================

class HybridMatcher:
    """
    Fast matching before LLM calls.
    
    Stage 0: Attribute matching (technique_id, tactic, team, etc.)
    Stage 0.5: Cross-field matching (assigned_to ↔ name, owner ↔ name)
    Stage 0.75: Text reference detection (name appears in description)
    
    These return definitive matches without LLM calls.
    """
    
    # Attributes that indicate a strong connection when matched exactly
    KEY_ATTRIBUTES = {
        'technique_id',  # MITRE technique - strongest signal
        'tactic',        # MITRE tactic
        'category',      # C2 framework, etc.
        'team',          # Same team
        'owner',         # Same owner
        'sprint',        # Same sprint
        'epic',          # Same epic
        'robot_suite',   # Same test suite
        'assigned_to',   # Same assignee
        'created_by',    # Same creator
    }
    
    # Cross-field mappings: source_field → target_fields to check
    CROSS_FIELD_MAPPINGS = {
        'assigned_to': ['name', 'label', 'title', 'email'],  # Story assigned_to → Person name
        'owner': ['name', 'label', 'title', 'team'],         # Artifact owner → Person/Team name
        'created_by': ['name', 'label', 'title'],            # Story created_by → Person name
        'team': ['name', 'label'],                           # Reference to team → Team name
        'name': ['assigned_to', 'owner', 'created_by', 'team'],  # Person name → references
    }
    
    def __init__(self):
        pass
    
    def find_attribute_match(self, source: Dict, target: Dict) -> Optional[Tuple[str, str]]:
        """
        Check for shared key attributes (same field, same value).
        
        Returns: (attribute_name, shared_value) or None
        """
        for attr in self.KEY_ATTRIBUTES:
            source_val = source.get(attr)
            target_val = target.get(attr)
            
            if source_val and target_val:
                # Normalize for comparison
                if str(source_val).strip().lower() == str(target_val).strip().lower():
                    return (attr, str(source_val))
        
        return None
    
    def find_cross_field_match(self, source: Dict, target: Dict) -> Optional[Tuple[str, str, str, str]]:
        """
        Check for cross-field matches (e.g., assigned_to ↔ name).
        
        Returns: (source_field, source_value, target_field, target_value) or None
        """
        # Check source fields against target's mapped fields
        for source_field, target_fields in self.CROSS_FIELD_MAPPINGS.items():
            source_val = source.get(source_field)
            if not source_val:
                continue
                
            source_val_norm = str(source_val).strip().lower()
            
            for target_field in target_fields:
                target_val = target.get(target_field)
                if not target_val:
                    continue
                    
                target_val_norm = str(target_val).strip().lower()
                
                # Exact match
                if source_val_norm == target_val_norm:
                    return (source_field, str(source_val), target_field, str(target_val))
                
                # Partial match for names (e.g., "Kane Pickrel" contains "Kane")
                if len(source_val_norm) >= 3 and len(target_val_norm) >= 3:
                    if source_val_norm in target_val_norm or target_val_norm in source_val_norm:
                        return (source_field, str(source_val), target_field, str(target_val))
        
        # Also check reverse direction
        for target_field, source_fields in self.CROSS_FIELD_MAPPINGS.items():
            target_val = target.get(target_field)
            if not target_val:
                continue
                
            target_val_norm = str(target_val).strip().lower()
            
            for source_field in source_fields:
                source_val = source.get(source_field)
                if not source_val:
                    continue
                    
                source_val_norm = str(source_val).strip().lower()
                
                if source_val_norm == target_val_norm:
                    return (source_field, str(source_val), target_field, str(target_val))
                    
                if len(source_val_norm) >= 3 and len(target_val_norm) >= 3:
                    if source_val_norm in target_val_norm or target_val_norm in source_val_norm:
                        return (source_field, str(source_val), target_field, str(target_val))
        
        return None
    
    def find_text_reference(self, source: Dict, target: Dict) -> Optional[Tuple[str, str]]:
        """
        Check if source's name/id appears in target's description, or vice versa.
        
        Returns: (field_matched, reference_found) or None
        """
        # Get source identifiers
        source_names = self._get_searchable_names(source)
        target_names = self._get_searchable_names(target)
        
        # Get descriptions and other text fields
        source_text = self._get_searchable_text(source)
        target_text = self._get_searchable_text(target)
        
        # Check if source name appears in target text
        for name in source_names:
            if len(name) >= 3 and name.lower() in target_text:
                return ('source_in_target_desc', name)
        
        # Check if target name appears in source text
        for name in target_names:
            if len(name) >= 3 and name.lower() in source_text:
                return ('target_in_source_desc', name)
        
        return None
    
    def find_shared_keyword(self, source: Dict, target: Dict) -> Optional[Tuple[str, str, str]]:
        """
        Check if both nodes share a significant keyword in their text content.
        
        Returns: (keyword, source_field, target_field) or None
        """
        # Significant keywords that indicate a strong connection
        SIGNIFICANT_KEYWORDS = {
            # Tools/Frameworks
            'cobalt strike', 'mythic', 'sliver', 'metasploit', 'mimikatz', 'bloodhound',
            # MITRE techniques (partial matches)
            't1003', 't1558', 't1059', 't1021', 't1071',
            # Tactics
            'credential access', 'lateral movement', 'persistence', 'defense evasion',
            'initial access', 'execution', 'privilege escalation', 'discovery',
            # Domains
            'kerberos', 'lsass', 'active directory', 'ldap', 'ntlm', 'sam',
            # Actions
            'dump', 'inject', 'beacon', 'payload', 'exfil',
        }
        
        source_text = self._get_all_text(source)
        target_text = self._get_all_text(target)
        
        for keyword in SIGNIFICANT_KEYWORDS:
            if keyword in source_text and keyword in target_text:
                # Find which fields contain the keyword
                source_field = self._find_field_with_keyword(source, keyword)
                target_field = self._find_field_with_keyword(target, keyword)
                return (keyword, source_field, target_field)
        
        return None
    
    def _get_all_text(self, node: Dict) -> str:
        """Get all text from a node for keyword matching"""
        text_parts = []
        for key, val in node.items():
            if key.startswith('_'):
                continue
            if isinstance(val, str):
                text_parts.append(val.lower())
            elif isinstance(val, list):
                text_parts.extend([str(v).lower() for v in val])
        return ' '.join(text_parts)
    
    def _find_field_with_keyword(self, node: Dict, keyword: str) -> str:
        """Find which field contains a keyword"""
        for key, val in node.items():
            if key.startswith('_'):
                continue
            if isinstance(val, str) and keyword in val.lower():
                return key
            elif isinstance(val, list):
                for v in val:
                    if keyword in str(v).lower():
                        return key
        return 'content'
    
    def _get_keyword_context(self, node: Dict, keyword: str, field: str, max_len: int = 50) -> str:
        """
        Get a snippet of text around the keyword for context.
        Returns something like "...Cobalt Strike module for..." or "category: Cobalt Strike"
        """
        val = node.get(field)
        
        if not val:
            # Try to find keyword anywhere
            for key, v in node.items():
                if key.startswith('_'):
                    continue
                if isinstance(v, str) and keyword.lower() in v.lower():
                    val = v
                    field = key
                    break
        
        if not val:
            return keyword
        
        if isinstance(val, str):
            val_lower = val.lower()
            keyword_lower = keyword.lower()
            
            # If it's a short field value, just return field: value
            if len(val) <= max_len:
                if field in ['category', 'tactic', 'team', 'owner', 'technique_id']:
                    return f"{field}={val}"
                return val
            
            # Find keyword position and extract context
            pos = val_lower.find(keyword_lower)
            if pos >= 0:
                # Get surrounding context
                start = max(0, pos - 15)
                end = min(len(val), pos + len(keyword) + 15)
                snippet = val[start:end].strip()
                
                # Add ellipsis if truncated
                if start > 0:
                    snippet = "..." + snippet
                if end < len(val):
                    snippet = snippet + "..."
                
                return snippet
        
        elif isinstance(val, list):
            for item in val:
                if keyword.lower() in str(item).lower():
                    return str(item)
        
        return keyword
    
    def _get_searchable_names(self, node: Dict) -> List[str]:
        """Get all searchable identifiers from a node"""
        names = []
        
        for field in ['name', 'title', 'label', '_key', 'technique_id']:
            val = node.get(field)
            if val and isinstance(val, str):
                names.append(val)
                # Also add underscore-split versions
                if '_' in val:
                    names.extend(val.split('_'))
        
        # Filter out very short names
        return [n for n in names if len(n) >= 3]
    
    def _get_searchable_text(self, node: Dict) -> str:
        """Get all searchable text from a node"""
        text_parts = []
        for field in ['description', 'title', 'labels', 'tags']:
            val = node.get(field)
            if val:
                if isinstance(val, str):
                    text_parts.append(val.lower())
                elif isinstance(val, list):
                    text_parts.extend([str(v).lower() for v in val])
        return ' '.join(text_parts)


# ============================================================================
# LLM DISCOVERY ENGINE (ONTOLOGY-DRIVEN + HYBRID)
# ============================================================================

class LLMDiscoveryEngine:
    """
    Runs hybrid matching + LLM ensemble for edge discovery.
    
    Pipeline:
    1. Stage 0: Attribute matching (instant, no LLM)
    2. Stage 0.5: Cross-field matching (instant, no LLM)
    3. Stage 0.75: Text reference detection (instant, no LLM)
    4. Stage 0.9: Shared keyword detection (instant, no LLM)
    5. Stage 1: LLM binary classification (do they share a concept?)
    6. Stage 2: Relationship type selection
       - If 1 valid relationship: use it (deterministic)
       - If multiple: LLM classification (ontology-constrained)
    
    **NO HARDCODED RELATIONSHIP LABELS** - All types come from ontology API
    
    Produces CONCISE explanations for reviewer UI.
    """

    def __init__(self, ollama_client, db: StandardDatabase, model_fast: str = None, model_reason: str = None):
        self.ollama = ollama_client
        self.db = db
        self.relationship_resolver = OntologyRelationshipResolver(db)
        self.hybrid_matcher = HybridMatcher()
        
        self.model_fast = model_fast or os.getenv("OLLAMA_MODEL_FAST", "gemma3:27b-it-qat")
        self.model_reason = model_reason or os.getenv("OLLAMA_MODEL_REASON", "llama3.3:70b")
    
    def discover_edges(
        self, 
        source_node: Dict, 
        candidate_nodes: List[Dict],
        confidence_threshold: float = 0.6
    ) -> List[EdgeSuggestion]:
        """
        Run discovery between source node and candidates.
        
        Uses hybrid matching first, then LLM for non-obvious connections.
        """
        print(f"\n{'='*60}")
        print(f"🚀 Starting HYBRID discovery for: {source_node.get('_id', 'unknown')}")
        print(f"📊 Candidates: {len(candidate_nodes)}")
        print(f"🎯 Confidence threshold: {confidence_threshold}")
        print(f"⚡ Fast matching: Attribute + Cross-field + Text reference + Keyword")
        print(f"🤖 LLM fallback: {self.model_fast} / {self.model_reason}")
        print(f"📋 Relationship selection: Deterministic (1 option) or LLM (multiple)")
        print(f"{'='*60}\n")
        
        suggestions = []
        source_collection = source_node['_id'].split('/')[0]
        
        for candidate in candidate_nodes:
            try:
                target_collection = candidate['_id'].split('/')[0]
                
                # Get valid relationships from ontology
                valid_rels = self.relationship_resolver.get_valid_relationships(
                    source_collection, target_collection
                )
                
                if not valid_rels:
                    print(f"   ⚠️ No valid relationships for {source_collection} → {target_collection} - skipping")
                    continue
                
                print(f"\n🔍 Checking: {source_node.get('name', source_node['_id'])} → {candidate.get('label', candidate['_id'])}")
                print(f"   📋 Valid relationships ({len(valid_rels)}): {[r['label'] for r in valid_rels]}")
                
                # ============================================
                # STAGE 0: ATTRIBUTE MATCHING (INSTANT)
                # ============================================
                attr_match = self.hybrid_matcher.find_attribute_match(source_node, candidate)
                
                if attr_match:
                    attr_name, attr_value = attr_match
                    print(f"   ⚡ FAST MATCH: Shared {attr_name} = {attr_value}")
                    
                    # Select relationship type - deterministic if 1 option
                    edge_type, edge_uri, model_used = self._select_relationship(
                        valid_rels, source_node, candidate, 'attribute_match'
                    )
                    
                    # EXPLICIT explanation showing both data points
                    source_label = source_node.get('name', source_node.get('label', source_node['_id'].split('/')[1]))
                    target_label = candidate.get('label', candidate.get('name', candidate['_id'].split('/')[1]))
                    explanation = f"{source_label}.{attr_name}='{attr_value}' ↔ {target_label}.{attr_name}='{attr_value}'"
                    
                    suggestions.append(EdgeSuggestion(
                        source_id=source_node['_id'],
                        target_id=candidate['_id'],
                        relationship_type=edge_type,
                        relationship_uri=edge_uri,
                        confidence=0.95,  # High confidence for exact attribute match
                        explanation=explanation,
                        source_label=source_node.get('name', source_node.get('label', source_node['_id'])),
                        target_label=candidate.get('label', candidate.get('name', candidate['_id'])),
                        discovered_at=datetime.utcnow().isoformat(),
                        model_used=model_used,
                        match_type=MatchType.ATTRIBUTE_MATCH.value,
                        match_details={"attribute": attr_name, "value": attr_value}
                    ))
                    print(f"   ✅ ACCEPTED via attribute match: {edge_type} (95%)")
                    continue
                
                # ============================================
                # STAGE 0.5: CROSS-FIELD MATCHING (INSTANT)
                # ============================================
                cross_match = self.hybrid_matcher.find_cross_field_match(source_node, candidate)
                
                if cross_match:
                    src_field, src_val, tgt_field, tgt_val = cross_match
                    print(f"   ⚡ FAST MATCH: Cross-field {src_field}='{src_val}' ↔ {tgt_field}='{tgt_val}'")
                    
                    # Select relationship type - deterministic if 1 option
                    edge_type, edge_uri, model_used = self._select_relationship(
                        valid_rels, source_node, candidate, 'cross_field_match'
                    )
                    
                    source_label = source_node.get('name', source_node.get('label', source_node['_id'].split('/')[1]))
                    target_label = candidate.get('label', candidate.get('name', candidate['_id'].split('/')[1]))
                    explanation = f"{source_label}.{src_field}='{src_val}' → {target_label}.{tgt_field}='{tgt_val}'"
                    
                    suggestions.append(EdgeSuggestion(
                        source_id=source_node['_id'],
                        target_id=candidate['_id'],
                        relationship_type=edge_type,
                        relationship_uri=edge_uri,
                        confidence=0.92,  # High confidence for cross-field match
                        explanation=explanation,
                        source_label=source_node.get('name', source_node.get('label', source_node['_id'])),
                        target_label=candidate.get('label', candidate.get('name', candidate['_id'])),
                        discovered_at=datetime.utcnow().isoformat(),
                        model_used=model_used,
                        match_type=MatchType.CROSS_FIELD_MATCH.value,
                        match_details={
                            "source_field": src_field, 
                            "source_value": src_val,
                            "target_field": tgt_field,
                            "target_value": tgt_val
                        }
                    ))
                    print(f"   ✅ ACCEPTED via cross-field match: {edge_type} (92%)")
                    continue
                
                # ============================================
                # STAGE 0.75: TEXT REFERENCE (INSTANT)
                # ============================================
                text_match = self.hybrid_matcher.find_text_reference(source_node, candidate)
                
                if text_match:
                    match_type_str, reference = text_match
                    print(f"   ⚡ FAST MATCH: Text reference '{reference}' in description")
                    
                    # Select relationship type - deterministic if 1 option
                    edge_type, edge_uri, model_used = self._select_relationship(
                        valid_rels, source_node, candidate, 'text_reference'
                    )
                    
                    # EXPLICIT explanation showing where the reference was found
                    source_label = source_node.get('name', source_node.get('label', source_node['_id'].split('/')[1]))
                    target_label = candidate.get('label', candidate.get('name', candidate['_id'].split('/')[1]))
                    
                    if match_type_str == 'source_in_target_desc':
                        explanation = f"'{reference}' (from {source_label}) found in {target_label}'s description"
                    else:
                        explanation = f"'{reference}' (from {target_label}) found in {source_label}'s description"
                    
                    suggestions.append(EdgeSuggestion(
                        source_id=source_node['_id'],
                        target_id=candidate['_id'],
                        relationship_type=edge_type,
                        relationship_uri=edge_uri,
                        confidence=0.90,  # High confidence for explicit reference
                        explanation=explanation,
                        source_label=source_node.get('name', source_node.get('label', source_node['_id'])),
                        target_label=candidate.get('label', candidate.get('name', candidate['_id'])),
                        discovered_at=datetime.utcnow().isoformat(),
                        model_used=model_used,
                        match_type=MatchType.TEXT_REFERENCE.value,
                        match_details={"match_type": match_type_str, "reference": reference}
                    ))
                    print(f"   ✅ ACCEPTED via text reference: {edge_type} (90%)")
                    continue
                
                # ============================================
                # STAGE 0.9: SHARED KEYWORD (INSTANT)
                # ============================================
                keyword_match = self.hybrid_matcher.find_shared_keyword(source_node, candidate)
                
                if keyword_match:
                    keyword, src_field, tgt_field = keyword_match
                    print(f"   ⚡ FAST MATCH: Shared keyword '{keyword}' in both nodes")
                    
                    # Select relationship type - deterministic if 1 option
                    edge_type, edge_uri, model_used = self._select_relationship(
                        valid_rels, source_node, candidate, 'keyword_match'
                    )
                    
                    source_label = source_node.get('name', source_node.get('title', source_node.get('label', source_node['_id'].split('/')[1])))
                    target_label = candidate.get('name', candidate.get('label', candidate.get('title', candidate['_id'].split('/')[1])))
                    
                    # Get the actual text snippets containing the keyword for context
                    src_context = self.hybrid_matcher._get_keyword_context(source_node, keyword, src_field)
                    tgt_context = self.hybrid_matcher._get_keyword_context(candidate, keyword, tgt_field)
                    
                    explanation = f"Both involve {keyword.title()}: '{src_context}' and '{tgt_context}'"
                    
                    suggestions.append(EdgeSuggestion(
                        source_id=source_node['_id'],
                        target_id=candidate['_id'],
                        relationship_type=edge_type,
                        relationship_uri=edge_uri,
                        confidence=0.85,  # Good confidence for shared significant keyword
                        explanation=explanation,
                        source_label=source_node.get('name', source_node.get('label', source_node['_id'])),
                        target_label=candidate.get('label', candidate.get('name', candidate['_id'])),
                        discovered_at=datetime.utcnow().isoformat(),
                        model_used=model_used,
                        match_type=MatchType.KEYWORD_MATCH.value,
                        match_details={"keyword": keyword, "source_field": src_field, "target_field": tgt_field}
                    ))
                    print(f"   ✅ ACCEPTED via shared keyword: {edge_type} (85%)")
                    continue
                
                # ============================================
                # STAGE 1-2: LLM ENSEMBLE (SEMANTIC)
                # ============================================
                print(f"   🤖 No fast match - using LLM ensemble...")
                
                # Stage 1: What do they share?
                should_connect, shared_concept = self._stage1_binary(source_node, candidate)
                
                if not should_connect or not shared_concept:
                    print(f"   ❌ Stage 1: No shared concept found")
                    continue
                
                # VERIFY the shared concept actually exists in both nodes
                source_text = json.dumps(source_node, default=str).lower()
                target_text = json.dumps(candidate, default=str).lower()
                shared_lower = shared_concept.lower()
                
                in_source = shared_lower in source_text
                in_target = shared_lower in target_text
                
                if not in_source or not in_target:
                    print(f"   ❌ Verification failed: '{shared_concept}' not found in both nodes")
                    print(f"      In source: {in_source}, In target: {in_target}")
                    continue
                
                print(f"   ✓ Verified: '{shared_concept}' exists in both nodes")
                
                # Find where exactly the concept appears
                src_field = self._find_field_containing(source_node, shared_concept)
                tgt_field = self._find_field_containing(candidate, shared_concept)
                
                # ============================================
                # STAGE 2: RELATIONSHIP TYPE SELECTION
                # Smart: deterministic if 1 option, LLM if multiple
                # ============================================
                edge_type, edge_uri, model_used = self._select_relationship(
                    valid_rels, source_node, candidate, 'llm_semantic'
                )
                
                # Build explanation showing the actual shared concept
                source_label = source_node.get('name', source_node.get('title', source_node['_id'].split('/')[1]))
                target_label = candidate.get('name', candidate.get('label', candidate['_id'].split('/')[1]))
                
                explanation = f"Both mention '{shared_concept}': found in {source_label}.{src_field} and {target_label}.{tgt_field}"
                
                # Confidence based on how specific the match is
                confidence = 0.75
                if len(shared_concept) > 10:  # Longer/more specific = higher confidence
                    confidence = 0.85
                if shared_concept.upper().startswith('T1'):  # MITRE technique
                    confidence = 0.90
                
                print(f"   ✓ Confidence: {confidence:.2f}")
                
                if confidence >= confidence_threshold:
                    suggestions.append(EdgeSuggestion(
                        source_id=source_node['_id'],
                        target_id=candidate['_id'],
                        relationship_type=edge_type,
                        relationship_uri=edge_uri,
                        confidence=confidence,
                        explanation=explanation,
                        source_label=source_node.get('name', source_node.get('label', source_node['_id'])),
                        target_label=candidate.get('label', candidate.get('name', candidate['_id'])),
                        discovered_at=datetime.utcnow().isoformat(),
                        model_used=model_used,
                        match_type=MatchType.LLM_SEMANTIC.value,
                        match_details={
                            "shared_concept": shared_concept,
                            "source_field": src_field,
                            "target_field": tgt_field
                        }
                    ))
                    print(f"   ✅ ACCEPTED via LLM: {edge_type} ({confidence:.0%}) - shared '{shared_concept}'")
                else:
                    print(f"   ⚠️ Below threshold ({confidence:.2f} < {confidence_threshold})")
                    
            except Exception as e:
                print(f"   ❌ Discovery error for {candidate.get('_id')}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"\n{'='*60}")
        print(f"✨ Discovery complete: {len(suggestions)} suggestions")
        print(f"   - Attribute matches: {sum(1 for s in suggestions if s.match_type == 'attribute_match')}")
        print(f"   - Cross-field matches: {sum(1 for s in suggestions if s.match_type == 'cross_field_match')}")
        print(f"   - Text references: {sum(1 for s in suggestions if s.match_type == 'text_reference')}")
        print(f"   - Keyword matches: {sum(1 for s in suggestions if s.match_type == 'keyword_match')}")
        print(f"   - LLM semantic: {sum(1 for s in suggestions if s.match_type == 'llm_semantic')}")
        print(f"{'='*60}\n")
        
        return suggestions
    
    def _select_relationship(
        self,
        valid_rels: List[Dict],
        source_node: Dict,
        candidate: Dict,
        match_type: str
    ) -> Tuple[str, str, str]:
        """
        Smart relationship selection - NO HARDCODED LABELS
        
        - If only 1 valid relationship: use it (deterministic)
        - If multiple: use LLM to choose from ontology options
        
        Returns: (edge_type, edge_uri, model_used)
        """
        # DETERMINISTIC: Only one valid relationship
        if len(valid_rels) == 1:
            rel = valid_rels[0]
            print(f"   📌 Deterministic: only 1 valid relationship → {rel['label']}")
            return rel['label'], rel['uri'], "deterministic_single_rel"
        
        # MULTIPLE OPTIONS: Use LLM to decide
        print(f"   🤖 Multiple options ({len(valid_rels)}): {[r['label'] for r in valid_rels]}")
        print(f"   🤖 Using LLM to select relationship type...")
        
        edge_type, edge_uri, explanation = self._stage2_classify_ontology(
            source_node, candidate, valid_rels
        )
        
        print(f"   ✓ LLM selected: {edge_type}")
        return edge_type, edge_uri, f"llm_selected:{self.model_reason}"
    
    def _stage1_binary(self, source: Dict, target: Dict) -> Tuple[bool, Optional[str]]:
        """
        Stage 1: Do these nodes share a concept/word/idea?
        
        Returns: (should_connect, shared_concept)
        """
        source_summary = self._summarize_node(source)
        target_summary = self._summarize_node(target)
        
        # Print what the LLM is seeing
        print(f"   📄 Source data: {json.dumps(source_summary, default=str, indent=None)[:200]}")
        print(f"   📄 Target data: {json.dumps(target_summary, default=str, indent=None)[:200]}")
        
        prompt = f"""Look at these two data records:

Record A: {json.dumps(source_summary, default=str)}

Record B: {json.dumps(target_summary, default=str)}

Do they share any specific concept, term, technique, tool, or keyword that appears in BOTH records?

If YES: respond with ONLY the shared term/concept (e.g., "Cobalt Strike" or "T1003.001" or "credential access")
If NO: respond with NONE

Answer with just the shared term or NONE:"""

        try:
            response = self.ollama.generate(
                model=self.model_fast,
                prompt=prompt,
                options={'temperature': 0.1}
            )
            answer = response['response'].strip()
            print(f"   🤖 Stage 1 LLM response: '{answer}'")
            
            # Check if LLM found something
            if answer.upper() == 'NONE' or answer.upper() == 'NO' or len(answer) < 2:
                return False, None
            
            # LLM claims they share something - we'll verify this
            shared_concept = answer.strip('"\'').strip()
            return True, shared_concept
            
        except Exception as e:
            print(f"   ❌ Stage 1 error: {e}")
            return False, None
    
    def _stage2_classify_ontology(
        self, 
        source: Dict, 
        target: Dict, 
        valid_relationships: List[Dict]
    ) -> Tuple[str, str, str]:
        """
        Stage 2: What type of relationship? (ONTOLOGY-DRIVEN)
        
        LLM chooses from the valid relationships provided by ontology.
        NO HARDCODED LABELS - only ontology-provided options.
        """
        
        # Build options text from ontology relationships
        options_text = "\n".join([
            f"- {rel['label']}: {rel.get('definition', 'No definition')}"
            for rel in valid_relationships
        ])
        
        valid_labels = {rel['label'].upper(): rel for rel in valid_relationships}
        
        source_summary = self._summarize_node(source)
        target_summary = self._summarize_node(target)
        
        # Print relationship options
        print(f"   📋 LLM choosing from: {[r['label'] for r in valid_relationships]}")
        
        prompt = f"""These two nodes should be connected. Choose the BEST relationship type from the options below.

Source ({source['_id'].split('/')[0]}): {json.dumps(source_summary, default=str)}
Target ({target['_id'].split('/')[0]}): {json.dumps(target_summary, default=str)}

Valid relationship types (choose ONE):
{options_text}

Respond with ONLY: TYPE|one sentence explanation
Example: REFERENCES|Source cites target for implementation details"""

        try:
            response = self.ollama.generate(
                model=self.model_reason,
                prompt=prompt,
                options={'temperature': 0.2}
            )
            
            raw_response = response['response'].strip()
            print(f"   🤖 Stage 2 LLM response: '{raw_response[:100]}...'")
            
            parts = raw_response.split('|', 1)
            if len(parts) >= 2:
                edge_type = parts[0].strip().upper()
                explanation = parts[1].strip()
            else:
                # Try to extract just the first word as the type
                edge_type = raw_response.split()[0].strip().upper() if raw_response.split() else ""
                explanation = raw_response
            
            # Validate against ontology options
            if edge_type in valid_labels:
                rel = valid_labels[edge_type]
                return edge_type, rel['uri'], explanation
            else:
                # Find closest match in valid labels
                for valid_label, rel in valid_labels.items():
                    if edge_type in valid_label or valid_label in edge_type:
                        print(f"   ⚠️ Fuzzy match: '{edge_type}' → '{valid_label}'")
                        return valid_label, rel['uri'], explanation
                
                # Fallback to first valid relationship
                if valid_relationships:
                    fallback = valid_relationships[0]
                    print(f"   ⚠️ LLM returned invalid type '{edge_type}', using fallback: {fallback['label']}")
                    return fallback['label'], fallback['uri'], f"(fallback) {explanation}"
                
                return "RELATED_TO", "proto:rel/RELATED_TO", explanation
                
        except Exception as e:
            print(f"   ❌ Stage 2 error: {e}")
            # Fallback to first valid relationship
            if valid_relationships:
                fallback = valid_relationships[0]
                return fallback['label'], fallback['uri'], "LLM error - using first valid relationship"
            return "RELATED_TO", "proto:rel/RELATED_TO", "Error fallback"
    
    def _summarize_node(self, node: Dict, max_fields: int = 8) -> Dict:
        """Create a summary of a node for LLM prompts"""
        summary = {}
        priority_fields = ['_id', 'name', 'label', 'title', 'description', 
                          'technique_id', 'tactic', 'category', 'team', 'owner']
        
        for field in priority_fields:
            if field in node:
                value = node[field]
                if isinstance(value, str) and len(value) > 150:
                    value = value[:150] + "..."
                summary[field] = value
        
        return summary
    
    def _find_field_containing(self, node: Dict, concept: str) -> str:
        """Find which field in a node contains a given concept/term"""
        concept_lower = concept.lower()
        
        # Check priority fields first
        priority = ['name', 'title', 'label', 'technique_id', 'tactic', 'category', 
                   'description', 'team', 'owner', 'assigned_to', 'created_by']
        
        for field in priority:
            val = node.get(field)
            if val and concept_lower in str(val).lower():
                return field
        
        # Check all other fields
        for field, val in node.items():
            if field.startswith('_'):
                continue
            if val and concept_lower in str(val).lower():
                return field
        
        return 'content'


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

class DiscoveryOrchestrator:
    """
    Main orchestrator that ties everything together.
    
    Usage:
        orchestrator = DiscoveryOrchestrator(db, ollama_client)
        result = orchestrator.process_new_artifact(artifact_id)
    """
    
    def __init__(self, db: StandardDatabase, ollama_client=None):
        self.db = db
        self.health_calc = GraphHealthCalculator(db)
        self.trigger = DiscoveryTrigger(db, self.health_calc)
        
        self.discovery = LLMDiscoveryEngine(ollama_client, db) if ollama_client else None
        
        self._last_health: Optional[GraphHealthReport] = None
    
    def get_health(self) -> GraphHealthReport:
        """Get current graph health"""
        health = self.health_calc.calculate_health()
        self._last_health = health
        return health
    
    def check_discovery_needed(self, artifact_id: str) -> DiscoveryTriggerResult:
        """Check if discovery should run for new artifact"""
        return self.trigger.check_trigger(artifact_id, self._last_health)
    
    def run_discovery(self, artifact_id: str, candidates: List[Dict]) -> List[EdgeSuggestion]:
        """Run LLM discovery on candidates"""
        if not self.discovery:
            raise RuntimeError("Ollama client not configured")
        
        collection, key = artifact_id.split('/')
        
        print(f"🔍 Looking for node: collection={collection}, key={key}")
        
        if not self.db.has_collection(collection):
            raise RuntimeError(f"Collection '{collection}' does not exist")
        
        source_node = self.db.collection(collection).get(key)
        
        if source_node is None:
            raise RuntimeError(f"Node '{artifact_id}' not found in database")
        
        print(f"✅ Found source node: {source_node.get('name', source_node.get('_key'))}")
        
        return self.discovery.discover_edges(source_node, candidates)
    
    def process_new_artifact(self, artifact_id: str) -> Dict[str, Any]:
        """
        Full pipeline: check trigger → run discovery → return suggestions
        """
        trigger_result = self.check_discovery_needed(artifact_id)
        
        result = {
            "artifact_id": artifact_id,
            "discovery_triggered": trigger_result.should_trigger,
            "trigger_reason": trigger_result.reason,
            "priority": trigger_result.priority,
            "health_snapshot": trigger_result.health_snapshot,
            "suggestions": []
        }
        
        if trigger_result.should_trigger and self.discovery and trigger_result.candidates:
            suggestions = self.run_discovery(artifact_id, trigger_result.candidates)
            result["suggestions"] = [asdict(s) for s in suggestions]
        
        self._last_health = self.health_calc.calculate_health()
        
        return result
    
    def clear_ontology_cache(self):
        """Clear ontology caches (call after ontology changes)"""
        if self.discovery:
            self.discovery.relationship_resolver.clear_cache()
        self.trigger.relationship_resolver.clear_cache()
        self.health_calc._edge_collections = None


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def create_orchestrator(
    arango_host: str = "http://localhost:8529",
    arango_db: str = "AUTO_DB",
    arango_user: str = "root",
    arango_password: str = "",
    ollama_host: str = "http://localhost:11434"
) -> DiscoveryOrchestrator:
    """
    Factory function to create a fully configured orchestrator.
    """
    from arango import ArangoClient
    
    client = ArangoClient(hosts=arango_host)
    db = client.db(arango_db, username=arango_user, password=arango_password)
    
    ollama_client = None
    try:
        import ollama
        ollama_client = ollama.Client(host=ollama_host)
        ollama_client.list()
        print(f"✅ Connected to Ollama at {ollama_host}")
    except Exception as e:
        print(f"⚠️ Ollama not available: {e}")
        print("   Discovery will be disabled, health metrics still available")
    
    return DiscoveryOrchestrator(db, ollama_client)