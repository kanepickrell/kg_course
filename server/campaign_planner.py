"""
campaign_planner.py
===================
Campaign planning tools for the 318th RANS cyber range.

Upload this file via the App Onboarding Code step to generate
agent-callable tools for the Campaign Planner agent.

Usage (agent will call these via tools.py wrappers):
    planner = CampaignPlanner(gdb)
    planner.build_campaign(tactic="Initial Access", max_modules=5)
    planner.get_coverage_gaps(tactic="Credential Access")
    planner.suggest_sequence(objective="Kerberoast domain accounts")
"""

from typing import List, Dict, Optional, Any


class CampaignPlanner:
    """
    Builds and analyzes adversary emulation campaigns using the ATLAS knowledge graph.
    Queries LibraryModules, ExecutionSequences, and TTPs to support campaign planning.
    """

    def __init__(self, gdb):
        """
        Initialize with a GraphDB adapter instance.
        The agent infrastructure injects this automatically.
        """
        self.gdb = gdb

    def build_campaign(self, tactic: str, max_modules: int = 5) -> Dict[str, Any]:
        """
        Build a campaign by selecting Library Modules that cover a given MITRE tactic.
        Returns a ranked list of modules with execution order and risk summary.
        """
        try:
            sparql = f"""
            PREFIX proto: <http://protograph.ai/ontology#>
            PREFIX data: <http://protograph.ai/data/>

            SELECT ?module ?name ?tactic ?riskLevel WHERE {{
                ?module a proto:LibraryModule ;
                        proto:name ?name ;
                        proto:tactic ?tactic .
                OPTIONAL {{ ?module proto:riskLevel ?riskLevel }}
                FILTER(CONTAINS(STR(?tactic), "{tactic}"))
            }}
            LIMIT {max_modules}
            """
            results = self.gdb.sparql_query(sparql)
            modules = []
            for i, row in enumerate(results):
                modules.append({
                    "order": i + 1,
                    "name": row.get("name", "Unknown"),
                    "tactic": row.get("tactic", ""),
                    "risk_level": row.get("riskLevel", "medium"),
                    "uri": row.get("module", ""),
                })
            return {
                "success": True,
                "tactic": tactic,
                "module_count": len(modules),
                "modules": modules,
                "summary": f"Found {len(modules)} modules covering {tactic}",
            }
        except Exception as e:
            return {"success": False, "error": str(e), "tactic": tactic}

    def get_coverage_gaps(self, tactic: str) -> Dict[str, Any]:
        """
        Identify TTPs within a tactic that have no corresponding Library Module.
        Returns a list of uncovered techniques — the coverage gaps.
        """
        try:
            sparql = f"""
            PREFIX proto: <http://protograph.ai/ontology#>

            SELECT ?ttp ?name WHERE {{
                ?ttp a proto:TTP ;
                     proto:name ?name ;
                     proto:tactic ?tactic .
                FILTER(CONTAINS(STR(?tactic), "{tactic}"))
                FILTER NOT EXISTS {{
                    ?module a proto:LibraryModule ;
                            proto:mapsToTechnique ?ttp .
                }}
            }}
            """
            results = self.gdb.sparql_query(sparql)
            gaps = [{"ttp": row.get("name", ""), "uri": row.get("ttp", "")} for row in results]
            return {
                "success": True,
                "tactic": tactic,
                "gap_count": len(gaps),
                "gaps": gaps,
                "summary": f"{len(gaps)} techniques in {tactic} have no coverage",
            }
        except Exception as e:
            return {"success": False, "error": str(e), "tactic": tactic}

    def suggest_sequence(self, objective: str) -> Dict[str, Any]:
        """
        Suggest an Execution Sequence that matches a given campaign objective.
        Searches sequence names and descriptions for relevance.
        """
        try:
            sparql = f"""
            PREFIX proto: <http://protograph.ai/ontology#>

            SELECT ?seq ?name ?description WHERE {{
                ?seq a proto:ExecutionSequence ;
                     proto:name ?name .
                OPTIONAL {{ ?seq proto:description ?description }}
                FILTER(
                    CONTAINS(LCASE(?name), LCASE("{objective}")) ||
                    CONTAINS(LCASE(COALESCE(?description, "")), LCASE("{objective}"))
                )
            }}
            LIMIT 5
            """
            results = self.gdb.sparql_query(sparql)
            sequences = [
                {
                    "name": row.get("name", ""),
                    "description": row.get("description", ""),
                    "uri": row.get("seq", ""),
                }
                for row in results
            ]
            return {
                "success": True,
                "objective": objective,
                "sequence_count": len(sequences),
                "sequences": sequences,
                "summary": f"Found {len(sequences)} sequences matching '{objective}'",
            }
        except Exception as e:
            return {"success": False, "error": str(e), "objective": objective}

    def list_tactics_with_coverage(self) -> Dict[str, Any]:
        """
        List all MITRE tactics present in the graph with their module counts.
        Useful for a coverage overview dashboard.
        """
        try:
            sparql = """
            PREFIX proto: <http://protograph.ai/ontology#>

            SELECT ?tactic (COUNT(?module) AS ?count) WHERE {
                ?module a proto:LibraryModule ;
                        proto:tactic ?tactic .
            }
            GROUP BY ?tactic
            ORDER BY DESC(?count)
            """
            results = self.gdb.sparql_query(sparql)
            tactics = [
                {
                    "tactic": row.get("tactic", ""),
                    "module_count": int(row.get("count", 0)),
                }
                for row in results
            ]
            return {
                "success": True,
                "tactic_count": len(tactics),
                "tactics": tactics,
                "summary": f"{len(tactics)} tactics with module coverage",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_module_details(self, module_name: str) -> Dict[str, Any]:
        """
        Retrieve full details for a specific Library Module by name.
        Returns tactic, risk level, execution type, and linked TTPs.
        """
        try:
            sparql = f"""
            PREFIX proto: <http://protograph.ai/ontology#>

            SELECT ?module ?tactic ?riskLevel ?executionType ?ttp WHERE {{
                ?module a proto:LibraryModule ;
                        proto:name "{module_name}" ;
                        proto:tactic ?tactic .
                OPTIONAL {{ ?module proto:riskLevel ?riskLevel }}
                OPTIONAL {{ ?module proto:executionType ?executionType }}
                OPTIONAL {{ ?module proto:mapsToTechnique ?ttp }}
            }}
            LIMIT 1
            """
            results = self.gdb.sparql_query(sparql)
            if not results:
                return {"success": False, "error": f"Module '{module_name}' not found"}
            row = results[0]
            return {
                "success": True,
                "name": module_name,
                "tactic": row.get("tactic", ""),
                "risk_level": row.get("riskLevel", "medium"),
                "execution_type": row.get("executionType", ""),
                "linked_ttp": row.get("ttp", ""),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}