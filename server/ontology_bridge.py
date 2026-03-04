#!/usr/bin/env python3
"""
Ontology Bridge - Unified Access to ArangoDB-based Ontology

This module provides the same interface as the file-based ontology_manager.py
but reads from ArangoDB collections managed by ontology_api.py.

This allows the ingestion pipeline to use the UI-editable ontology stored in:
- ontology_concepts: Concept definitions with properties and taxonomy constraints
- taxonomy_schemes: Controlled vocabulary definitions
- taxonomy_terms: Terms within taxonomies with labels and aliases

Changes made via the Ontology Manager UI take effect immediately.
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class Property:
    """A property definition from an ontology concept"""
    name: str
    type: str
    required: bool = False
    taxonomy: Optional[str] = None
    description: str = ""
    range: Optional[str] = None  # For URI references


@dataclass
class Concept:
    """An ontology concept loaded from ArangoDB"""
    uri: str
    label: str
    definition: str
    parent_uri: Optional[str]
    abstract: bool
    collection: Optional[str]
    properties: List[Property]
    all_properties: List[Property] = field(default_factory=list)  # Including inherited


@dataclass
class TaxonomyTerm:
    """A term in a controlled vocabulary"""
    uri: str
    label: str
    definition: str = ""
    aliases: List[str] = field(default_factory=list)
    broader: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def matches(self, query: str) -> bool:
        """Check if query matches this term (label or any alias)"""
        query_lower = query.lower().strip()
        if self.label.lower() == query_lower:
            return True
        return any(alias.lower() == query_lower for alias in self.aliases)


# ============================================================================
# ONTOLOGY MANAGER
# ============================================================================

class OntologyManager:
    """
    Provides access to ontology concepts stored in ArangoDB.
    
    Usage:
        manager = OntologyManager(db)
        
        # Get all concrete types for classification
        types = manager.get_concrete_concepts()
        
        # Validate an artifact
        result = manager.validate_artifact(data, "Library Module")
    """
    
    def __init__(self, db):
        self.db = db
        self._concepts_cache: Dict[str, Concept] = {}
        self._label_index: Dict[str, str] = {}  # lowercase label -> uri
        self._load_concepts()
    
    def _load_concepts(self):
        """Load all concepts from ArangoDB"""
        if self.db is None:
            print("⚠️ OntologyManager: No database connection")
            return
        
        if not self.db.has_collection('ontology_concepts'):
            print("⚠️ OntologyManager: ontology_concepts collection not found")
            return
        
        try:
            cursor = self.db.aql.execute("FOR c IN ontology_concepts RETURN c")
            
            for doc in cursor:
                # Parse properties
                properties = []
                for prop_data in doc.get('properties', []):
                    properties.append(Property(
                        name=prop_data.get('name', ''),
                        type=prop_data.get('type', 'string'),
                        required=prop_data.get('required', False),
                        taxonomy=prop_data.get('taxonomy'),
                        description=prop_data.get('description', ''),
                        range=prop_data.get('range')
                    ))
                
                concept = Concept(
                    uri=doc.get('uri', ''),
                    label=doc.get('label', ''),
                    definition=doc.get('definition', ''),
                    parent_uri=doc.get('parent_uri'),
                    abstract=doc.get('abstract', False),
                    collection=doc.get('collection'),
                    properties=properties
                )
                
                self._concepts_cache[concept.uri] = concept
                self._label_index[concept.label.lower()] = concept.uri
            
            # Build inherited properties
            self._build_inherited_properties()
            
            print(f"✓ OntologyManager: Loaded {len(self._concepts_cache)} concepts")
            
        except Exception as e:
            print(f"❌ OntologyManager: Failed to load concepts: {e}")
    
    def _build_inherited_properties(self):
        """Build the all_properties list including inherited properties"""
        for concept in self._concepts_cache.values():
            all_props = []
            seen_names = set()
            
            # Walk up the hierarchy
            current = concept
            while current:
                for prop in current.properties:
                    if prop.name not in seen_names:
                        all_props.append(prop)
                        seen_names.add(prop.name)
                
                # Get parent
                if current.parent_uri and current.parent_uri in self._concepts_cache:
                    current = self._concepts_cache[current.parent_uri]
                else:
                    current = None
            
            concept.all_properties = all_props
    
    def refresh(self):
        """Reload concepts from database"""
        self._concepts_cache.clear()
        self._label_index.clear()
        self._load_concepts()
    
    def get_all_concepts(self) -> List[Dict[str, Any]]:
        """Get all concepts as dictionaries"""
        return [
            {
                'uri': c.uri,
                'label': c.label,
                'definition': c.definition,
                'parent_uri': c.parent_uri,
                'abstract': c.abstract,
                'collection': c.collection,
                'properties': [
                    {
                        'name': p.name,
                        'type': p.type,
                        'required': p.required,
                        'taxonomy': p.taxonomy,
                        'description': p.description
                    }
                    for p in c.properties
                ]
            }
            for c in self._concepts_cache.values()
        ]
    
    def get_concrete_concepts(self) -> List[Dict[str, Any]]:
        """Get non-abstract concepts (valid for instantiation)"""
        return [c for c in self.get_all_concepts() if not c.get('abstract', False)]
    
    def get_concept_by_label(self, label: str) -> Optional[Dict[str, Any]]:
        """Look up a concept by its label (case-insensitive)"""
        label_lower = label.lower().strip()
        
        # Debug logging
        print(f"🔍 Looking for concept: '{label}' (normalized: '{label_lower}')")
        print(f"   Available labels: {list(self._label_index.keys())}")
        
        uri = self._label_index.get(label_lower)
        
        if uri and uri in self._concepts_cache:
            concept = self._concepts_cache[uri]
            print(f"   ✓ Found: {concept.label} -> {concept.collection}")
            return {
                'uri': concept.uri,
                'label': concept.label,
                'definition': concept.definition,
                'parent_uri': concept.parent_uri,
                'abstract': concept.abstract,
                'collection': concept.collection,
                'properties': [
                    {
                        'name': p.name,
                        'type': p.type,
                        'required': p.required,
                        'taxonomy': p.taxonomy,
                        'description': p.description
                    }
                    for p in concept.properties
                ]
            }
        
        # Try direct match against cached concepts (backup)
        for cached_uri, cached_concept in self._concepts_cache.items():
            if cached_concept.label.lower() == label_lower:
                print(f"   ✓ Found via direct search: {cached_concept.label}")
                return {
                    'uri': cached_concept.uri,
                    'label': cached_concept.label,
                    'definition': cached_concept.definition,
                    'parent_uri': cached_concept.parent_uri,
                    'abstract': cached_concept.abstract,
                    'collection': cached_concept.collection,
                    'properties': [
                        {
                            'name': p.name,
                            'type': p.type,
                            'required': p.required,
                            'taxonomy': p.taxonomy,
                            'description': p.description
                        }
                        for p in cached_concept.properties
                    ]
                }
        
        print(f"   ✗ Not found")
        return None
    
    def get_concept_by_uri(self, uri: str) -> Optional[Concept]:
        """Look up a concept by URI"""
        return self._concepts_cache.get(uri)
    
    def get_all_properties(self, label: str) -> List[Dict[str, Any]]:
        """Get all properties for a concept, including inherited ones"""
        label_lower = label.lower().strip()
        uri = self._label_index.get(label_lower)
        
        if uri and uri in self._concepts_cache:
            concept = self._concepts_cache[uri]
            return [
                {
                    'name': p.name,
                    'type': p.type,
                    'required': p.required,
                    'taxonomy': p.taxonomy,
                    'description': p.description
                }
                for p in concept.all_properties
            ]
        return []
    
    def validate_artifact(self, data: Dict[str, Any], type_label: str) -> Dict[str, Any]:
        """
        Validate artifact data against concept schema.
        
        Note: This only checks required fields from the concept schema.
        Taxonomy validation is handled by TaxonomyRegistry.
        
        Returns:
            {
                "valid": bool,
                "errors": [...],
                "warnings": [...],
                "normalized": {}
            }
        """
        errors = []
        warnings = []
        
        concept_dict = self.get_concept_by_label(type_label)
        if not concept_dict:
            return {
                "valid": False,
                "errors": [{"field": "_type", "message": f"Unknown type: {type_label}"}],
                "warnings": [],
                "normalized": {}
            }
        
        # Get all properties (including inherited)
        all_props = self.get_all_properties(type_label)
        
        # Check required fields
        for prop in all_props:
            if prop.get('required', False):
                prop_name = prop.get('name')
                if prop_name not in data or data[prop_name] is None:
                    errors.append({
                        "field": prop_name,
                        "message": f"Required field '{prop_name}' is missing"
                    })
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "normalized": {}
        }


# ============================================================================
# TAXONOMY REGISTRY
# ============================================================================

class TaxonomyRegistry:
    """
    Provides access to taxonomies stored in ArangoDB.
    
    Usage:
        registry = TaxonomyRegistry(db)
        
        # Validate and normalize a value
        is_valid, canonical, uri = registry.validate("teams", "Auto")
        # Returns: (True, "Automation", "proto:team/Automation")
        
        # Get all valid values for LLM prompt
        values = registry.get_valid_values("mitre_tactics")
    """
    
    def __init__(self, db):
        self.db = db
        self._taxonomies: Dict[str, Dict[str, TaxonomyTerm]] = {}  # scheme_id -> {uri -> term}
        self._label_indexes: Dict[str, Dict[str, str]] = {}  # scheme_id -> {lowercase label -> uri}
        self._alias_indexes: Dict[str, Dict[str, str]] = {}  # scheme_id -> {lowercase alias -> uri}
        self._load_taxonomies()
    
    def _load_taxonomies(self):
        """Load all taxonomies from ArangoDB"""
        if self.db is None:
            print("⚠️ TaxonomyRegistry: No database connection")
            return
        
        # Try ArangoDB collections first
        if self.db.has_collection('taxonomy_terms'):
            self._load_from_arangodb()
        else:
            # Fallback to file-based
            self._load_from_files()
    
    def _load_from_arangodb(self):
        """Load taxonomies from ArangoDB collections"""
        try:
            # Load schemes
            schemes = {}
            if self.db.has_collection('taxonomy_schemes'):
                cursor = self.db.aql.execute("FOR s IN taxonomy_schemes RETURN s")
                for doc in cursor:
                    scheme_id = doc.get('_key', doc.get('scheme_id', ''))
                    schemes[scheme_id] = doc
            
            # Load terms
            cursor = self.db.aql.execute("FOR t IN taxonomy_terms RETURN t")
            
            for doc in cursor:
                # FIX: Support both 'taxonomy_id' (used by ontology_api.py) and 'scheme_id' (legacy)
                scheme_id = doc.get('taxonomy_id', doc.get('scheme_id', ''))
                
                if not scheme_id:
                    print(f"⚠️ TaxonomyRegistry: Term missing taxonomy_id/scheme_id: {doc.get('label', doc.get('uri', 'unknown'))}")
                    continue
                
                if scheme_id not in self._taxonomies:
                    self._taxonomies[scheme_id] = {}
                    self._label_indexes[scheme_id] = {}
                    self._alias_indexes[scheme_id] = {}
                
                term = TaxonomyTerm(
                    uri=doc.get('uri', ''),
                    label=doc.get('label', ''),
                    definition=doc.get('definition', ''),
                    aliases=doc.get('aliases', []),
                    broader=doc.get('broader'),
                    metadata={k: v for k, v in doc.items() 
                             if k not in {'_key', '_id', '_rev', 'uri', 'label', 
                                         'definition', 'aliases', 'broader', 'scheme_id', 'taxonomy_id'}}
                )
                
                self._taxonomies[scheme_id][term.uri] = term
                self._label_indexes[scheme_id][term.label.lower()] = term.uri
                
                # Index all aliases
                for alias in term.aliases:
                    if alias:  # Skip empty aliases
                        self._alias_indexes[scheme_id][alias.lower()] = term.uri
            
            # Log what was loaded with alias counts
            total_terms = sum(len(t) for t in self._taxonomies.values())
            total_aliases = sum(len(a) for a in self._alias_indexes.values())
            print(f"✓ TaxonomyRegistry: Loaded {len(self._taxonomies)} taxonomies, {total_terms} terms, {total_aliases} aliases")
            
            # Debug: show counts per taxonomy
            for tax_id in sorted(self._taxonomies.keys()):
                term_count = len(self._taxonomies[tax_id])
                alias_count = len(self._alias_indexes.get(tax_id, {}))
                print(f"   {tax_id}: {term_count} terms, {alias_count} aliases")
            
        except Exception as e:
            print(f"❌ TaxonomyRegistry: Failed to load from ArangoDB: {e}")
            import traceback
            traceback.print_exc()
    
    def _load_from_files(self):
        """Fallback: Load taxonomies from JSON files"""
        import os
        import json
        from pathlib import Path
        
        taxonomy_dir = Path(__file__).parent / "taxonomies"
        if not taxonomy_dir.exists():
            print(f"⚠️ TaxonomyRegistry: Taxonomy directory not found: {taxonomy_dir}")
            return
        
        for json_file in taxonomy_dir.glob("*.json"):
            if json_file.name == "ontology_concepts.json":
                continue  # Skip ontology file
            
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                scheme_id = json_file.stem
                self._taxonomies[scheme_id] = {}
                self._label_indexes[scheme_id] = {}
                self._alias_indexes[scheme_id] = {}
                
                for term_data in data.get('terms', []):
                    term = TaxonomyTerm(
                        uri=term_data.get('uri', ''),
                        label=term_data.get('label', ''),
                        definition=term_data.get('definition', ''),
                        aliases=term_data.get('aliases', []),
                        broader=term_data.get('broader')
                    )
                    
                    self._taxonomies[scheme_id][term.uri] = term
                    self._label_indexes[scheme_id][term.label.lower()] = term.uri
                    
                    for alias in term.aliases:
                        if alias:  # Skip empty aliases
                            self._alias_indexes[scheme_id][alias.lower()] = term.uri
                
                print(f"✓ Loaded taxonomy: {scheme_id} ({len(self._taxonomies[scheme_id])} terms)")
                
            except Exception as e:
                print(f"❌ Failed to load {json_file}: {e}")
    
    def refresh(self):
        """Reload taxonomies from database"""
        self._taxonomies.clear()
        self._label_indexes.clear()
        self._alias_indexes.clear()
        self._load_taxonomies()
    
    def validate(self, taxonomy_name: str, value: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate a value against a taxonomy.
        
        Args:
            taxonomy_name: Name of the taxonomy (e.g., "teams", "mitre_tactics")
            value: Value to validate
            
        Returns:
            (is_valid, canonical_label, uri) if valid
            (False, None, None) if invalid
        """
        if taxonomy_name not in self._taxonomies:
            return (False, None, None)
        
        value_lower = value.lower().strip()
        
        # Try exact label match
        label_index = self._label_indexes.get(taxonomy_name, {})
        if value_lower in label_index:
            uri = label_index[value_lower]
            term = self._taxonomies[taxonomy_name][uri]
            return (True, term.label, term.uri)
        
        # Try alias match
        alias_index = self._alias_indexes.get(taxonomy_name, {})
        if value_lower in alias_index:
            uri = alias_index[value_lower]
            term = self._taxonomies[taxonomy_name][uri]
            return (True, term.label, term.uri)
        
        return (False, None, None)
    
    def get_valid_values(self, taxonomy_name: str, include_aliases: bool = False) -> List[str]:
        """Get list of valid values for a taxonomy"""
        if taxonomy_name not in self._taxonomies:
            return []
        
        terms = self._taxonomies[taxonomy_name].values()
        
        if include_aliases:
            result = []
            for term in terms:
                result.append(term.label)
                result.extend(term.aliases)
            return result
        
        return [term.label for term in terms]
    
    def get_term_details(self, taxonomy_name: str, value: str) -> Optional[Dict[str, Any]]:
        """Get full term details including metadata"""
        is_valid, canonical, uri = self.validate(taxonomy_name, value)
        
        if not is_valid or taxonomy_name not in self._taxonomies:
            return None
        
        term = self._taxonomies[taxonomy_name].get(uri)
        if not term:
            return None
        
        return {
            "uri": term.uri,
            "label": term.label,
            "definition": term.definition,
            "aliases": term.aliases,
            "broader": term.broader,
            **term.metadata
        }
    
    def resolve_to_canonical(self, taxonomy_name: str, value: str) -> str:
        """
        Resolve a value (possibly an alias) to its canonical label.
        Returns original value if not found.
        """
        is_valid, canonical, _ = self.validate(taxonomy_name, value)
        return canonical if is_valid else value
    
    def generate_llm_constraint_prompt(self, taxonomy_name: str, field_name: str) -> str:
        """Generate prompt text constraining LLM to valid taxonomy values"""
        if taxonomy_name not in self._taxonomies:
            return f"For the '{field_name}' field, use your best judgment."
        
        terms = sorted(self._taxonomies[taxonomy_name].values(), key=lambda t: t.label)
        
        lines = [f"For the '{field_name}' field, use ONLY one of these values:"]
        for term in terms[:15]:  # Limit to 15 for prompt length
            short_def = term.definition[:60] + "..." if len(term.definition) > 60 else term.definition
            lines.append(f'- "{term.label}"{f" - {short_def}" if short_def else ""}')
        
        if len(terms) > 15:
            lines.append(f"... and {len(terms) - 15} more options")
        
        return "\n".join(lines)
    
    def debug_taxonomy(self, taxonomy_name: str) -> Dict[str, Any]:
        """Debug helper to see what's loaded for a taxonomy"""
        if taxonomy_name not in self._taxonomies:
            return {"error": f"Taxonomy '{taxonomy_name}' not loaded"}
        
        return {
            "taxonomy_name": taxonomy_name,
            "term_count": len(self._taxonomies[taxonomy_name]),
            "labels": list(self._label_indexes.get(taxonomy_name, {}).keys()),
            "aliases": list(self._alias_indexes.get(taxonomy_name, {}).keys()),
            "terms": [
                {
                    "label": t.label,
                    "uri": t.uri,
                    "aliases": t.aliases
                }
                for t in self._taxonomies[taxonomy_name].values()
            ]
        }


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

_ontology_manager: Optional[OntologyManager] = None
_taxonomy_registry: Optional[TaxonomyRegistry] = None


def init_bridge(db):
    """Initialize the bridge with a database connection"""
    global _ontology_manager, _taxonomy_registry
    _ontology_manager = OntologyManager(db)
    _taxonomy_registry = TaxonomyRegistry(db)
    return _ontology_manager, _taxonomy_registry


def get_ontology_manager() -> Optional[OntologyManager]:
    """Get the global ontology manager instance"""
    return _ontology_manager


def get_taxonomy_registry() -> Optional[TaxonomyRegistry]:
    """Get the global taxonomy registry instance"""
    return _taxonomy_registry


def refresh_all():
    """Refresh both ontology and taxonomy caches"""
    if _ontology_manager:
        _ontology_manager.refresh()
    if _taxonomy_registry:
        _taxonomy_registry.refresh()