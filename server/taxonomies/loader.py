#!/usr/bin/env python3
"""
Taxonomy Loader and Validator
Provides controlled vocabulary validation for ProtoGraph ingestion

This module:
1. Loads JSON taxonomy files at startup
2. Provides validation functions for LLM outputs
3. Supports alias resolution (e.g., "CS" -> "Cobalt Strike")
4. Enables hierarchical lookups (e.g., get all tactics in "attack" phase)
"""

import json
import os
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class TaxonomyTerm:
    """A single term in a controlled vocabulary"""
    uri: str
    label: str
    definition: str
    aliases: List[str] = field(default_factory=list)
    broader: Optional[str] = None  # Parent term URI
    narrower: List[str] = field(default_factory=list)  # Child term URIs
    related: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)  # Extra fields
    
    def matches(self, query: str) -> bool:
        """Check if query matches this term (label or any alias)"""
        query_lower = query.lower().strip()
        if self.label.lower() == query_lower:
            return True
        return any(alias.lower() == query_lower for alias in self.aliases)


@dataclass
class Taxonomy:
    """A complete controlled vocabulary"""
    taxonomy_id: str
    label: str
    description: str
    version: str
    terms: Dict[str, TaxonomyTerm]  # uri -> TaxonomyTerm
    
    # Lookup indexes built at load time
    _label_index: Dict[str, str] = field(default_factory=dict)  # lowercase label -> uri
    _alias_index: Dict[str, str] = field(default_factory=dict)  # lowercase alias -> uri
    
    def get_term_by_label(self, label: str) -> Optional[TaxonomyTerm]:
        """Look up term by label or alias"""
        label_lower = label.lower().strip()
        
        # Try exact label match first
        if label_lower in self._label_index:
            return self.terms[self._label_index[label_lower]]
        
        # Try alias match
        if label_lower in self._alias_index:
            return self.terms[self._alias_index[label_lower]]
        
        return None
    
    def get_term_by_uri(self, uri: str) -> Optional[TaxonomyTerm]:
        """Look up term by URI"""
        return self.terms.get(uri)
    
    def validate_value(self, value: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate a value against this taxonomy.
        
        Returns:
            (is_valid, canonical_label, uri) if valid
            (False, None, None) if invalid
        """
        term = self.get_term_by_label(value)
        if term:
            return (True, term.label, term.uri)
        return (False, None, None)
    
    def get_all_labels(self) -> List[str]:
        """Get all valid labels (not aliases)"""
        return [term.label for term in self.terms.values()]
    
    def get_all_with_aliases(self) -> List[str]:
        """Get all labels and aliases"""
        result = []
        for term in self.terms.values():
            result.append(term.label)
            result.extend(term.aliases)
        return result
    
    def get_children(self, parent_uri: str) -> List[TaxonomyTerm]:
        """Get all terms that have this URI as their broader term"""
        return [
            term for term in self.terms.values()
            if term.broader == parent_uri
        ]
    
    def get_terms_by_metadata(self, key: str, value: Any) -> List[TaxonomyTerm]:
        """Filter terms by a metadata field value"""
        return [
            term for term in self.terms.values()
            if term.metadata.get(key) == value
        ]


# ============================================================================
# TAXONOMY REGISTRY
# ============================================================================

class TaxonomyRegistry:
    """
    Central registry for all loaded taxonomies.
    
    Usage:
        registry = TaxonomyRegistry("./taxonomies")
        
        # Validate a value
        is_valid, canonical, uri = registry.validate("teams", "Auto")
        # Returns: (True, "Automation", "proto:team/Automation")
        
        # Get all valid values for LLM prompt
        valid_tactics = registry.get_valid_values("mitre_tactics")
    """
    
    def __init__(self, taxonomy_dir: str = "./taxonomies"):
        self.taxonomy_dir = Path(taxonomy_dir)
        self.taxonomies: Dict[str, Taxonomy] = {}
        self._load_all_taxonomies()
    
    def _load_all_taxonomies(self):
        """Load all JSON taxonomy files from directory"""
        if not self.taxonomy_dir.exists():
            print(f"⚠️ Taxonomy directory not found: {self.taxonomy_dir}")
            return
        
        for json_file in self.taxonomy_dir.glob("*.json"):
            try:
                taxonomy = self._load_taxonomy_file(json_file)
                if taxonomy:
                    # Use filename (without .json) as key
                    key = json_file.stem
                    self.taxonomies[key] = taxonomy
                    print(f"✓ Loaded taxonomy: {key} ({len(taxonomy.terms)} terms)")
            except Exception as e:
                print(f"❌ Failed to load {json_file}: {e}")
    
    def _load_taxonomy_file(self, filepath: Path) -> Optional[Taxonomy]:
        """Load a single taxonomy JSON file"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Parse terms
        terms = {}
        label_index = {}
        alias_index = {}
        
        for term_data in data.get("terms", []):
            uri = term_data.get("uri", "")
            label = term_data.get("label", "")
            
            if not uri or not label:
                continue
            
            # Extract known fields, put rest in metadata
            known_fields = {"uri", "label", "definition", "aliases", "broader", "narrower", "related"}
            metadata = {k: v for k, v in term_data.items() if k not in known_fields}
            
            term = TaxonomyTerm(
                uri=uri,
                label=label,
                definition=term_data.get("definition", ""),
                aliases=term_data.get("aliases", []),
                broader=term_data.get("broader"),
                narrower=term_data.get("narrower", []),
                related=term_data.get("related", []),
                metadata=metadata
            )
            
            terms[uri] = term
            
            # Build indexes
            label_index[label.lower()] = uri
            for alias in term.aliases:
                alias_index[alias.lower()] = uri
        
        taxonomy = Taxonomy(
            taxonomy_id=data.get("taxonomy_id", ""),
            label=data.get("taxonomy_label", filepath.stem),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            terms=terms,
            _label_index=label_index,
            _alias_index=alias_index
        )
        
        return taxonomy
    
    def get_taxonomy(self, name: str) -> Optional[Taxonomy]:
        """Get a taxonomy by name"""
        return self.taxonomies.get(name)
    
    def validate(self, taxonomy_name: str, value: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate a value against a specific taxonomy.
        
        Args:
            taxonomy_name: Name of taxonomy (e.g., "teams", "mitre_tactics")
            value: Value to validate
            
        Returns:
            (is_valid, canonical_label, uri)
        """
        taxonomy = self.taxonomies.get(taxonomy_name)
        if not taxonomy:
            return (False, None, None)
        return taxonomy.validate_value(value)
    
    def get_valid_values(self, taxonomy_name: str, include_aliases: bool = False) -> List[str]:
        """Get list of valid values for a taxonomy (for LLM prompts)"""
        taxonomy = self.taxonomies.get(taxonomy_name)
        if not taxonomy:
            return []
        
        if include_aliases:
            return taxonomy.get_all_with_aliases()
        return taxonomy.get_all_labels()
    
    def get_term_details(self, taxonomy_name: str, value: str) -> Optional[Dict[str, Any]]:
        """Get full term details including metadata"""
        taxonomy = self.taxonomies.get(taxonomy_name)
        if not taxonomy:
            return None
        
        term = taxonomy.get_term_by_label(value)
        if not term:
            return None
        
        return {
            "uri": term.uri,
            "label": term.label,
            "definition": term.definition,
            "aliases": term.aliases,
            "broader": term.broader,
            "related": term.related,
            **term.metadata
        }
    
    def resolve_to_canonical(self, taxonomy_name: str, value: str) -> str:
        """
        Resolve a value (possibly an alias) to its canonical label.
        Returns original value if not found.
        """
        is_valid, canonical, _ = self.validate(taxonomy_name, value)
        return canonical if is_valid else value
    
    def get_hierarchy(self, taxonomy_name: str, root_uri: Optional[str] = None) -> List[Dict]:
        """
        Get hierarchical structure of taxonomy.
        
        Returns:
            List of term dicts with nested 'children' arrays
        """
        taxonomy = self.taxonomies.get(taxonomy_name)
        if not taxonomy:
            return []
        
        def build_tree(parent_uri: Optional[str]) -> List[Dict]:
            children = []
            for term in taxonomy.terms.values():
                if term.broader == parent_uri:
                    children.append({
                        "uri": term.uri,
                        "label": term.label,
                        "children": build_tree(term.uri)
                    })
            return children
        
        return build_tree(root_uri)
    
    def generate_llm_constraint_prompt(self, taxonomy_name: str, field_name: str) -> str:
        """
        Generate prompt text constraining LLM to use only valid taxonomy values.
        
        Example output:
        For the 'tactic' field, use ONLY one of these values:
        - "Reconnaissance" - The adversary is trying to gather information...
        - "Initial Access" - The adversary is trying to get into your network...
        """
        taxonomy = self.taxonomies.get(taxonomy_name)
        if not taxonomy:
            return f"For the '{field_name}' field, use your best judgment."
        
        lines = [f"For the '{field_name}' field, use ONLY one of these values:"]
        
        for term in sorted(taxonomy.terms.values(), key=lambda t: t.label):
            short_def = term.definition[:80] + "..." if len(term.definition) > 80 else term.definition
            lines.append(f'- "{term.label}" - {short_def}')
        
        return "\n".join(lines)


# ============================================================================
# VALIDATION HELPERS
# ============================================================================

class ArtifactValidator:
    """
    Validates artifact data against taxonomy constraints.
    
    Usage:
        validator = ArtifactValidator(registry)
        result = validator.validate_artifact(artifact_data, "LibraryModule")
    """
    
    # Field -> Taxonomy mapping
    FIELD_TAXONOMY_MAP = {
        # Library Module fields
        "tactic": "mitre_tactics",
        "category": "c2_frameworks",
        "riskLevel": "risk_levels",
        "risk_level": "risk_levels",
        "owner": "teams",
        
        # Robot Log fields
        "technique_id": "mitre_techniques",
        "result_status": "test_statuses",
        
        # Development Story fields
        "status": "work_statuses",
        "priority": "priority_levels",
        "story_type": "work_types",
        "assigned_to": "team_members",
        
        # Common fields
        "team": "teams",
        "collaboration_with": "teams",
    }
    
    def __init__(self, registry: TaxonomyRegistry):
        self.registry = registry
    
    def validate_artifact(self, data: Dict[str, Any], artifact_type: str = None) -> Dict[str, Any]:
        """
        Validate artifact data against taxonomies.
        
        Returns:
            {
                "valid": bool,
                "errors": [{"field": str, "value": str, "message": str}],
                "warnings": [{"field": str, "value": str, "message": str}],
                "normalized": {field: canonical_value} - corrected values
            }
        """
        errors = []
        warnings = []
        normalized = {}
        
        for field, value in data.items():
            if field not in self.FIELD_TAXONOMY_MAP:
                continue
            
            taxonomy_name = self.FIELD_TAXONOMY_MAP[field]
            
            # Handle list fields (e.g., collaboration_with)
            if isinstance(value, list):
                normalized_list = []
                for v in value:
                    is_valid, canonical, uri = self.registry.validate(taxonomy_name, str(v))
                    if is_valid:
                        normalized_list.append(canonical)
                    else:
                        valid_values = self.registry.get_valid_values(taxonomy_name)
                        errors.append({
                            "field": field,
                            "value": v,
                            "message": f"Invalid value '{v}'. Valid options: {valid_values[:5]}..."
                        })
                normalized[field] = normalized_list
            else:
                # Single value field
                is_valid, canonical, uri = self.registry.validate(taxonomy_name, str(value))
                if is_valid:
                    if canonical != value:
                        warnings.append({
                            "field": field,
                            "value": value,
                            "message": f"Normalized '{value}' to '{canonical}'"
                        })
                    normalized[field] = canonical
                else:
                    valid_values = self.registry.get_valid_values(taxonomy_name)
                    errors.append({
                        "field": field,
                        "value": value,
                        "message": f"Invalid value '{value}'. Valid options: {valid_values}"
                    })
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "normalized": normalized
        }
    
    def normalize_artifact(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return artifact data with all taxonomy fields normalized to canonical values.
        Invalid values are left unchanged.
        """
        result = data.copy()
        validation = self.validate_artifact(data)
        
        for field, canonical_value in validation["normalized"].items():
            result[field] = canonical_value
        
        return result


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

# Global registry instance - loaded once at import
_registry: Optional[TaxonomyRegistry] = None

def get_registry(taxonomy_dir: str = None) -> TaxonomyRegistry:
    """Get or create the global taxonomy registry"""
    global _registry
    
    if _registry is None:
        # Default to ./taxonomies relative to this file
        if taxonomy_dir is None:
            taxonomy_dir = Path(__file__).parent
        _registry = TaxonomyRegistry(taxonomy_dir)
    
    return _registry


def validate(taxonomy_name: str, value: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Convenience function for quick validation"""
    return get_registry().validate(taxonomy_name, value)


def get_valid_values(taxonomy_name: str) -> List[str]:
    """Convenience function to get valid values"""
    return get_registry().get_valid_values(taxonomy_name)


# ============================================================================
# CLI FOR TESTING
# ============================================================================

if __name__ == "__main__":
    import sys
    
    # Load taxonomies
    registry = get_registry()
    
    print("\n📚 Loaded Taxonomies:")
    for name, taxonomy in registry.taxonomies.items():
        print(f"  - {name}: {len(taxonomy.terms)} terms")
    
    # Test validation
    print("\n🔍 Validation Tests:")
    
    test_cases = [
        ("teams", "Auto"),           # Should resolve to "Automation"
        ("teams", "Automation"),     # Exact match
        ("teams", "Red Team"),       # Alias for OPFOR
        ("teams", "Invalid Team"),   # Should fail
        ("mitre_tactics", "TA0006"), # Should pass (ID as label)
        ("mitre_tactics", "Credential Access"),  # Alias
        ("risk_levels", "critical"), # Case insensitive
        ("c2_frameworks", "CS"),     # Alias for Cobalt Strike
    ]
    
    for taxonomy_name, value in test_cases:
        is_valid, canonical, uri = registry.validate(taxonomy_name, value)
        status = "✓" if is_valid else "✗"
        result = f"{canonical} ({uri})" if is_valid else "INVALID"
        print(f"  {status} {taxonomy_name}/{value} -> {result}")
    
    # Show LLM constraint prompt example
    print("\n📝 Example LLM Constraint Prompt:")
    print(registry.generate_llm_constraint_prompt("risk_levels", "riskLevel"))