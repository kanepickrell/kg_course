"""
Relationship Rules Engine
=========================
Deterministic, SPARQL-based relationship inference.

Runs after every artifact ingest to create structural edges that
are provably correct from the ontology and data.

Three rule categories:
  1. MITRE Reference Rules — Link modules to TTPs by technique ID
  2. Shared Attribute Rules — Link artifacts with matching taxonomy values
  3. Structural Rules — Enforce ontology-level constraints

Every edge created by rules gets:
  - source: "ontology_rule"
  - confidence: 1.0 (deterministic) or 0.9 (high-confidence heuristic)

No LLM. No review queue. No human in the loop.
"""

import re
from typing import Dict, Any, List, Optional


class RelationshipRulesEngine:
    """
    Post-ingest rules engine that creates structural edges.

    Usage:
        engine = RelationshipRulesEngine(gdb)
        edges_created = engine.run_rules_for("kerberoast", "LibraryModule", attributes)
    """

    def __init__(self, gdb):
        self.gdb = gdb

    def run_rules_for(
        self,
        key: str,
        artifact_type: str,
        attributes: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Run all applicable rules for a newly ingested artifact.
        Returns list of edges created.
        """
        created = []

        if artifact_type == "LibraryModule":
            created.extend(self._rule_mitre_reference(key, attributes))
            created.extend(self._rule_same_tactic_modules(key, attributes))

        if artifact_type == "TTP":
            created.extend(self._rule_ttp_back_references(key, attributes))

        # Generic rules for all types
        created.extend(self._rule_execution_plan_contains(key, artifact_type, attributes))

        if created:
            print(f"  🔗 Rules engine: {len(created)} edges created for {artifact_type}/{key}")
        else:
            print(f"  🔗 Rules engine: No new edges for {artifact_type}/{key}")

        return created

    # ================================================================
    # RULE 1: MITRE Reference
    # ================================================================
    # If a LibraryModule's description or tactic contains a MITRE
    # technique ID (T1234 or T1234.001), create a REFERENCES edge
    # to that TTP. If the TTP doesn't exist, create it.
    # ================================================================

    def _rule_mitre_reference(self, key: str, attrs: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract MITRE technique IDs from description/tactic and create REFERENCES edges."""
        created = []

        # Scan description and tactic for technique IDs
        text_fields = " ".join(
            str(attrs.get(f, "")) for f in ["description", "tactic", "name", "subcategory"]
        )
        technique_ids = self._extract_mitre_ids(text_fields)

        for tid in technique_ids:
            ttp_key = tid.replace(".", "_")

            # Check if TTP exists, create if not
            if not self.gdb.has_artifact(ttp_key):
                self.gdb.create_node(ttp_key, "TTP", {
                    "name": tid,
                    "mitreId": tid,
                })
                print(f"    📌 Auto-created TTP: {tid}")

            # Check if edge already exists
            if not self._edge_exists(key, ttp_key, "REFERENCES"):
                result = self.gdb.create_edge(
                    "LibraryModule", key,
                    "TTP", ttp_key,
                    "REFERENCES",
                    source="ontology_rule",
                    confidence=1.0,
                )
                created.append(result)

        return created

    # ================================================================
    # RULE 2: Same-Tactic Module Linking
    # ================================================================
    # If a LibraryModule shares a tactic with existing modules owned
    # by the same team, create RELATED_TO edges.
    # Only fires for exact tactic + owner matches.
    # ================================================================

    def _rule_same_tactic_modules(self, key: str, attrs: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Link modules that share the same tactic AND owner."""
        created = []
        tactic = attrs.get("tactic", "")
        owner = attrs.get("owner", "")

        if not tactic or not owner:
            return created

        # Find other modules with same tactic and owner
        safe_tactic = tactic.replace('"', '\\"')
        safe_owner = owner.replace('"', '\\"')
        my_uri = self.gdb.key_to_uri(key)

        rows = self.gdb.sparql_query(f"""
            SELECT ?entity WHERE {{
                ?entity a proto:LibraryModule ;
                        proto:tactic "{safe_tactic}" .
                ?entity proto:owner ?ownerConcept .
                ?ownerConcept skos:prefLabel "{safe_owner}" .
                FILTER(?entity != <{my_uri}>)
            }}
        """)

        for row in rows:
            other_uri = row["entity"]
            other_key = self.gdb.uri_to_key(other_uri)

            if other_key == key:
                continue

            if not self._edge_exists(key, other_key, "RELATED_TO") and \
               not self._edge_exists(other_key, key, "RELATED_TO"):
                result = self.gdb.create_edge(
                    "LibraryModule", key,
                    "LibraryModule", other_key,
                    "RELATED_TO",
                    source="ontology_rule",
                    confidence=0.9,
                )
                created.append(result)

        return created

    # ================================================================
    # RULE 3: TTP Back-References
    # ================================================================
    # When a new TTP is created, scan existing LibraryModules for
    # descriptions that mention this TTP's MITRE ID.
    # ================================================================

    def _rule_ttp_back_references(self, key: str, attrs: Dict[str, Any]) -> List[Dict[str, Any]]:
        """When a TTP is created, find modules that should reference it."""
        created = []
        mitre_id = attrs.get("mitreId", attrs.get("mitre_id", ""))

        if not mitre_id:
            return created

        safe_id = mitre_id.replace('"', '\\"')

        # Find modules whose description contains this MITRE ID
        rows = self.gdb.sparql_query(f"""
            SELECT ?entity WHERE {{
                ?entity a proto:LibraryModule ;
                        proto:description ?desc .
                FILTER(CONTAINS(UCASE(?desc), "{safe_id.upper()}"))
            }}
        """)

        for row in rows:
            module_uri = row["entity"]
            module_key = self.gdb.uri_to_key(module_uri)

            if not self._edge_exists(module_key, key, "REFERENCES"):
                result = self.gdb.create_edge(
                    "LibraryModule", module_key,
                    "TTP", key,
                    "REFERENCES",
                    source="ontology_rule",
                    confidence=1.0,
                )
                created.append(result)

        return created

    # ================================================================
    # RULE 4: Execution Plan Contains
    # ================================================================
    # If an artifact has a "modules" or "steps" field listing keys,
    # create CONTAINS edges from the parent to each child.
    # ================================================================

    def _rule_execution_plan_contains(
        self, key: str, artifact_type: str, attrs: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """If artifact lists module keys, create CONTAINS edges."""
        created = []

        if artifact_type not in ("ExecutionPlan", "Scenario"):
            return created

        # Check for module key lists
        module_keys = attrs.get("modules", attrs.get("steps", []))
        if not isinstance(module_keys, list):
            return created

        for module_key in module_keys:
            if isinstance(module_key, str) and self.gdb.has_artifact(module_key):
                if not self._edge_exists(key, module_key, "CONTAINS"):
                    result = self.gdb.create_edge(
                        artifact_type, key,
                        "LibraryModule", module_key,
                        "CONTAINS",
                        source="ontology_rule",
                        confidence=1.0,
                    )
                    created.append(result)

        return created

    # ================================================================
    # HELPERS
    # ================================================================

    def _extract_mitre_ids(self, text: str) -> List[str]:
        """Extract all MITRE ATT&CK technique IDs from text."""
        if not text:
            return []

        # Match T1234 or T1234.001
        pattern = r'\bT\d{4}(?:\.\d{3})?\b'
        matches = re.findall(pattern, text, re.IGNORECASE)

        # Normalize to uppercase and deduplicate
        seen = set()
        result = []
        for m in matches:
            normalized = m.upper()
            if normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result

    def _edge_exists(self, from_key: str, to_key: str, rel_type: str) -> bool:
        """Check if a specific edge already exists."""
        from_uri = self.gdb.key_to_uri(from_key)
        to_uri = self.gdb.key_to_uri(to_key)
        rel_uri = f"https://proto.atlas/relationship/{rel_type}"

        return self.gdb.sparql_ask(f"""
            ASK {{ <{from_uri}> <{rel_uri}> <{to_uri}> }}
        """)