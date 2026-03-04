#!/usr/bin/env python3
"""
Ontology Manager
Manages the ProtoGraph core ontology - concepts, hierarchies, and constraints.

This module:
1. Loads ontology concepts from JSON
2. Provides IS-A hierarchy traversal
3. Validates artifacts against concept schemas
4. Maps ArangoDB collections to ontology concepts
5. Generates LLM prompts with ontology context
"""

import json
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from pathlib import Path

from .loader import TaxonomyRegistry, get_registry, ArtifactValidator


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class PropertyDefinition:
    """Defines a property that a concept can have"""
    name: str
    type: str  # "string", "integer", "datetime", "uri", "object", "string[]", etc.
    required: bool = False
    taxonomy: Optional[str] = None  # If type is constrained by a taxonomy
    range: Optional[str] = None  # If type is uri, what concept(s) can it reference
    default: Optional[Any] = None
    description: Optional[str] = None
    inherited_from: Optional[str] = None  # URI of concept this was inherited from


@dataclass
class OntologyConcept:
    """A concept in the ontology (class/type)"""
    uri: str
    label: str
    definition: str
    parent_uri: Optional[str] = None
    abstract: bool = False
    collection: Optional[str] = None  # ArangoDB collection name
    taxonomy: Optional[str] = None  # If this concept maps to a taxonomy
    properties: List[PropertyDefinition] = field(default_factory=list)
    
    # Computed fields (set after loading)
    children: List[str] = field(default_factory=list)  # Child concept URIs
    all_properties: List[PropertyDefinition] = field(default_factory=list)  # Including inherited
    ancestors: List[str] = field(default_factory=list)  # All parent URIs up to root


@dataclass
class Ontology:
    """The complete ontology"""
    ontology_id: str
    label: str
    description: str
    namespace: str
    version: str
    concepts: Dict[str, OntologyConcept]  # uri -> concept
    
    # Lookup indexes
    _label_index: Dict[str, str] = field(default_factory=dict)  # label -> uri
    _collection_index: Dict[str, str] = field(default_factory=dict)  # collection -> uri


# ============================================================================
# ONTOLOGY MANAGER
# ============================================================================

class OntologyManager:
    """
    Central manager for the ProtoGraph ontology.
    
    Usage:
        manager = OntologyManager("./taxonomies")
        
        # Get concept by URI or label
        concept = manager.get_concept("proto:concept/LibraryModule")
        concept = manager.get_concept_by_label("Library Module")
        
        # Check IS-A relationships
        manager.is_a("proto:concept/LibraryModule", "proto:concept/Artifact")  # True
        
        # Get all properties (including inherited)
        props = manager.get_all_properties("proto:concept/LibraryModule")
        
        # Validate artifact data
        result = manager.validate_artifact(data, "LibraryModule")
    """
    
    def __init__(self, base_dir: str = "./taxonomies"):
        self.base_dir = Path(base_dir)
        self.ontology: Optional[Ontology] = None
        self.taxonomy_registry: TaxonomyRegistry = get_registry(str(base_dir))
        self.artifact_validator = ArtifactValidator(self.taxonomy_registry)
        
        self._load_ontology()
        self._compute_inheritance()
        
        if self.ontology:
            print(f"✓ Loaded ontology: {len(self.ontology.concepts)} concepts")
    
    def _load_ontology(self):
        """Load ontology from JSON file"""
        ontology_file = self.base_dir / "ontology_concepts.json"
        
        if not ontology_file.exists():
            print(f"⚠️ Ontology file not found: {ontology_file}")
            self.ontology = Ontology(
                ontology_id="proto:ProtoGraphOntology",
                label="ProtoGraph Ontology",
                description="Auto-generated empty ontology",
                namespace="https://protograph.ai/ontology/",
                version="0.0.0",
                concepts={},
                _label_index={},
                _collection_index={}
            )
            return
        
        with open(ontology_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Parse concepts
        concepts = {}
        label_index = {}
        collection_index = {}
        
        for concept_data in data.get("concepts", []):
            uri = concept_data.get("uri", "")
            label = concept_data.get("label", "")
            
            if not uri:
                continue
            
            # Parse properties
            properties = []
            for prop_data in concept_data.get("properties", []):
                prop = PropertyDefinition(
                    name=prop_data.get("name", ""),
                    type=prop_data.get("type", "string"),
                    required=prop_data.get("required", False),
                    taxonomy=prop_data.get("taxonomy"),
                    range=prop_data.get("range"),
                    default=prop_data.get("default"),
                    description=prop_data.get("description")
                )
                properties.append(prop)
            
            concept = OntologyConcept(
                uri=uri,
                label=label,
                definition=concept_data.get("definition", ""),
                parent_uri=concept_data.get("parent_uri"),
                abstract=concept_data.get("abstract", False),
                collection=concept_data.get("collection"),
                taxonomy=concept_data.get("taxonomy"),
                properties=properties
            )
            
            concepts[uri] = concept
            label_index[label.lower()] = uri
            
            if concept.collection:
                collection_index[concept.collection] = uri
        
        self.ontology = Ontology(
            ontology_id=data.get("ontology_id", ""),
            label=data.get("ontology_label", ""),
            description=data.get("description", ""),
            namespace=data.get("namespace", ""),
            version=data.get("version", "1.0.0"),
            concepts=concepts,
            _label_index=label_index,
            _collection_index=collection_index
        )
    
    def _compute_inheritance(self):
        """Compute inherited properties and children for all concepts"""
        if not self.ontology:
            return
        
        # First pass: compute children
        for uri, concept in self.ontology.concepts.items():
            if concept.parent_uri and concept.parent_uri in self.ontology.concepts:
                parent = self.ontology.concepts[concept.parent_uri]
                parent.children.append(uri)
        
        # Second pass: compute ancestors and inherited properties
        for uri, concept in self.ontology.concepts.items():
            concept.ancestors = self._get_ancestors(uri)
            concept.all_properties = self._get_all_properties(uri)
    
    def _get_ancestors(self, concept_uri: str) -> List[str]:
        """Get all ancestor URIs for a concept"""
        ancestors = []
        current = self.ontology.concepts.get(concept_uri)
        
        while current and current.parent_uri:
            ancestors.append(current.parent_uri)
            current = self.ontology.concepts.get(current.parent_uri)
        
        return ancestors
    
    def _get_all_properties(self, concept_uri: str) -> List[PropertyDefinition]:
        """Get all properties including inherited from ancestors"""
        concept = self.ontology.concepts.get(concept_uri)
        if not concept:
            return []
        
        # Start with own properties
        all_props = list(concept.properties)
        seen_names = {p.name for p in all_props}
        
        # Walk up the hierarchy and add inherited properties
        for ancestor_uri in concept.ancestors:
            ancestor = self.ontology.concepts.get(ancestor_uri)
            if ancestor:
                for prop in ancestor.properties:
                    if prop.name not in seen_names:
                        # Create copy with inheritance marker
                        inherited_prop = PropertyDefinition(
                            name=prop.name,
                            type=prop.type,
                            required=prop.required,
                            taxonomy=prop.taxonomy,
                            range=prop.range,
                            default=prop.default,
                            description=prop.description,
                            inherited_from=ancestor_uri
                        )
                        all_props.append(inherited_prop)
                        seen_names.add(prop.name)
        
        return all_props
    
    # ========================================================================
    # PUBLIC API
    # ========================================================================
    
    def get_concept(self, uri: str) -> Optional[OntologyConcept]:
        """Get a concept by URI"""
        return self.ontology.concepts.get(uri) if self.ontology else None
    
    def get_concept_by_label(self, label: str) -> Optional[OntologyConcept]:
        """Get a concept by label (case-insensitive)"""
        if not self.ontology:
            return None
        uri = self.ontology._label_index.get(label.lower())
        return self.ontology.concepts.get(uri) if uri else None
    
    def get_concept_by_collection(self, collection_name: str) -> Optional[OntologyConcept]:
        """Get a concept by its ArangoDB collection name"""
        if not self.ontology:
            return None
        uri = self.ontology._collection_index.get(collection_name)
        return self.ontology.concepts.get(uri) if uri else None
    
    def is_a(self, concept_uri: str, parent_uri: str) -> bool:
        """Check if concept IS-A (subclass of) parent"""
        concept = self.ontology.concepts.get(concept_uri)
        if not concept:
            return False
        if concept_uri == parent_uri:
            return True
        return parent_uri in concept.ancestors
    
    def get_children(self, concept_uri: str, recursive: bool = False) -> List[str]:
        """Get direct children (or all descendants if recursive)"""
        concept = self.ontology.concepts.get(concept_uri)
        if not concept:
            return []
        
        if not recursive:
            return concept.children
        
        # BFS for all descendants
        descendants = []
        queue = list(concept.children)
        while queue:
            child_uri = queue.pop(0)
            descendants.append(child_uri)
            child = self.ontology.concepts.get(child_uri)
            if child:
                queue.extend(child.children)
        
        return descendants
    
    def get_concrete_concepts(self, parent_uri: str = None) -> List[OntologyConcept]:
        """Get all non-abstract concepts (optionally under a parent)"""
        if not self.ontology:
            return []
        
        concepts = []
        for concept in self.ontology.concepts.values():
            if concept.abstract:
                continue
            if parent_uri and not self.is_a(concept.uri, parent_uri):
                continue
            concepts.append(concept)
        
        return concepts
    
    def get_all_properties(self, concept_uri: str) -> List[PropertyDefinition]:
        """Get all properties including inherited"""
        concept = self.ontology.concepts.get(concept_uri)
        return concept.all_properties if concept else []
    
    def get_required_properties(self, concept_uri: str) -> List[PropertyDefinition]:
        """Get only required properties"""
        return [p for p in self.get_all_properties(concept_uri) if p.required]
    
    # ========================================================================
    # VALIDATION
    # ========================================================================
    
    def validate_artifact(self, data: Dict[str, Any], collection_or_type: str) -> Dict[str, Any]:
        """
        Validate artifact data against ontology concept schema.
        
        Args:
            data: Artifact data to validate
            collection_or_type: Either collection name or concept label
            
        Returns:
            {
                "valid": bool,
                "concept": str (concept URI),
                "errors": [...],
                "warnings": [...],
                "normalized": {...}
            }
        """
        # Find the concept
        concept = self.get_concept_by_collection(collection_or_type)
        if not concept:
            concept = self.get_concept_by_label(collection_or_type)
        if not concept:
            # Try as URI
            concept = self.get_concept(collection_or_type)
        
        if not concept:
            return {
                "valid": False,
                "concept": None,
                "errors": [{"field": "_type", "message": f"Unknown type: {collection_or_type}"}],
                "warnings": [],
                "normalized": {}
            }
        
        errors = []
        warnings = []
        normalized = {}
        
        # Check required properties
        for prop in concept.all_properties:
            if prop.required and prop.name not in data:
                errors.append({
                    "field": prop.name,
                    "message": f"Required property '{prop.name}' is missing"
                })
        
        # Validate property values against taxonomies
        for prop in concept.all_properties:
            if prop.name not in data:
                continue
            
            value = data[prop.name]
            
            # Taxonomy validation
            if prop.taxonomy:
                if isinstance(value, list):
                    normalized_list = []
                    for v in value:
                        is_valid, canonical, uri = self.taxonomy_registry.validate(prop.taxonomy, str(v))
                        if is_valid:
                            normalized_list.append(canonical)
                        else:
                            valid_values = self.taxonomy_registry.get_valid_values(prop.taxonomy)[:5]
                            errors.append({
                                "field": prop.name,
                                "value": v,
                                "message": f"Invalid value. Valid options: {valid_values}..."
                            })
                    if normalized_list:
                        normalized[prop.name] = normalized_list
                else:
                    is_valid, canonical, uri = self.taxonomy_registry.validate(prop.taxonomy, str(value))
                    if is_valid:
                        if canonical != value:
                            warnings.append({
                                "field": prop.name,
                                "message": f"Normalized '{value}' to '{canonical}'"
                            })
                        normalized[prop.name] = canonical
                    else:
                        valid_values = self.taxonomy_registry.get_valid_values(prop.taxonomy)
                        errors.append({
                            "field": prop.name,
                            "value": value,
                            "message": f"Invalid value. Valid options: {valid_values}"
                        })
        
        return {
            "valid": len(errors) == 0,
            "concept": concept.uri,
            "concept_label": concept.label,
            "errors": errors,
            "warnings": warnings,
            "normalized": normalized
        }
    
    # ========================================================================
    # LLM INTEGRATION
    # ========================================================================
    
    def generate_classification_prompt(self) -> str:
        """Generate prompt text listing all concrete concept types for LLM classification"""
        lines = ["Classify this artifact as ONE of these types:"]
        
        for concept in sorted(self.get_concrete_concepts(), key=lambda c: c.label):
            lines.append(f'- "{concept.label}" - {concept.definition}')
        
        return "\n".join(lines)
    
    def generate_schema_prompt(self, concept_uri_or_label: str) -> str:
        """Generate prompt text describing the schema for a concept"""
        concept = self.get_concept(concept_uri_or_label)
        if not concept:
            concept = self.get_concept_by_label(concept_uri_or_label)
        
        if not concept:
            return f"Unknown concept: {concept_uri_or_label}"
        
        lines = [
            f"Schema for '{concept.label}':",
            f"Description: {concept.definition}",
            "",
            "Required fields:"
        ]
        
        required = self.get_required_properties(concept.uri)
        optional = [p for p in concept.all_properties if not p.required]
        
        if not required:
            lines.append("  (none)")
        else:
            for prop in required:
                constraint = ""
                if prop.taxonomy:
                    valid_values = self.taxonomy_registry.get_valid_values(prop.taxonomy)[:5]
                    constraint = f" (use: {valid_values})"
                lines.append(f"  - {prop.name}: {prop.type}{constraint}")
        
        lines.append("")
        lines.append("Optional fields:")
        
        if not optional:
            lines.append("  (none)")
        else:
            for prop in optional[:10]:  # Limit to 10 to avoid huge prompts
                constraint = ""
                if prop.taxonomy:
                    valid_values = self.taxonomy_registry.get_valid_values(prop.taxonomy)[:3]
                    constraint = f" (use: {valid_values}...)"
                inherited = " [inherited]" if prop.inherited_from else ""
                lines.append(f"  - {prop.name}: {prop.type}{constraint}{inherited}")
        
        return "\n".join(lines)
    
    def get_taxonomy_constraints_for_concept(self, concept_uri: str) -> Dict[str, List[str]]:
        """Get all taxonomy constraints for a concept's properties"""
        constraints = {}
        
        for prop in self.get_all_properties(concept_uri):
            if prop.taxonomy:
                constraints[prop.name] = self.taxonomy_registry.get_valid_values(prop.taxonomy)
        
        return constraints
    
    # ========================================================================
    # HIERARCHY VISUALIZATION
    # ========================================================================
    
    def print_hierarchy(self, root_uri: str = None, indent: int = 0):
        """Print concept hierarchy as tree"""
        if root_uri is None:
            # Find root concepts (no parent)
            roots = [c for c in self.ontology.concepts.values() if c.parent_uri is None]
            for root in sorted(roots, key=lambda c: c.label):
                self.print_hierarchy(root.uri, indent)
            return
        
        concept = self.ontology.concepts.get(root_uri)
        if not concept:
            return
        
        prefix = "  " * indent
        abstract_marker = " (abstract)" if concept.abstract else ""
        collection_marker = f" [{concept.collection}]" if concept.collection else ""
        
        print(f"{prefix}├─ {concept.label}{abstract_marker}{collection_marker}")
        
        for child_uri in sorted(concept.children):
            self.print_hierarchy(child_uri, indent + 1)
    
    def to_dict(self) -> Dict[str, Any]:
        """Export ontology as dictionary (for API responses)"""
        if not self.ontology:
            return {}
        
        concepts_list = []
        for concept in self.ontology.concepts.values():
            concepts_list.append({
                "uri": concept.uri,
                "label": concept.label,
                "definition": concept.definition,
                "parent_uri": concept.parent_uri,
                "abstract": concept.abstract,
                "collection": concept.collection,
                "children": concept.children,
                "ancestors": concept.ancestors,
                "properties": [
                    {
                        "name": p.name,
                        "type": p.type,
                        "required": p.required,
                        "taxonomy": p.taxonomy,
                        "inherited_from": p.inherited_from
                    }
                    for p in concept.all_properties
                ]
            })
        
        return {
            "id": self.ontology.ontology_id,
            "label": self.ontology.label,
            "description": self.ontology.description,
            "namespace": self.ontology.namespace,
            "version": self.ontology.version,
            "concepts": concepts_list
        }


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_manager: Optional[OntologyManager] = None

def get_ontology_manager(base_dir: str = None) -> OntologyManager:
    """Get or create the global ontology manager"""
    global _manager
    
    if _manager is None:
        if base_dir is None:
            base_dir = Path(__file__).parent
        _manager = OntologyManager(str(base_dir))
    
    return _manager


# ============================================================================
# CLI FOR TESTING
# ============================================================================

if __name__ == "__main__":
    manager = get_ontology_manager()
    
    print("\n📊 Ontology Concept Hierarchy:")
    print("=" * 50)
    manager.print_hierarchy()
    
    print("\n🔍 Testing IS-A Relationships:")
    test_cases = [
        ("proto:concept/LibraryModule", "proto:concept/Artifact"),
        ("proto:concept/LibraryModule", "proto:concept/Thing"),
        ("proto:concept/RobotLog", "proto:concept/Artifact"),
        ("proto:concept/DevelopmentStory", "proto:concept/Artifact"),
    ]
    
    for child, parent in test_cases:
        child_concept = manager.get_concept(child)
        parent_concept = manager.get_concept(parent)
        child_label = child_concept.label if child_concept else child
        parent_label = parent_concept.label if parent_concept else parent
        result = "✓" if manager.is_a(child, parent) else "✗"
        print(f"  {result} {child_label} IS-A {parent_label}")
    
    print("\n📋 LLM Classification Prompt:")
    print("-" * 40)
    print(manager.generate_classification_prompt()[:500] + "...")