#!/usr/bin/env python3
"""
protograph_mcp.py — MCP server exposing ProtoGraph's graph as agent tools.

Wraps the FastAPI server at PROTOGRAPH_URL (default http://localhost:8000).
Read + write: search, inspect, create nodes, create edges.

Run standalone to smoke-test the REST layer without an MCP client:
    python protograph_mcp.py --selftest

Install:
    pip install mcp httpx
"""

import os
import sys
import json
from typing import Optional, List, Dict, Any

import httpx
from mcp.server import MCPServer

BASE = os.getenv("PROTOGRAPH_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = float(os.getenv("PROTOGRAPH_TIMEOUT", "30"))

# Mirrors _TYPE_MAP in main.py:627. Kept here so the agent gets a hard
# rejection instead of main.py's silent fallback to "LibraryModule".
VALID_NODE_TYPES = [
    "library_module", "ttp", "person", "team", "execution_plan",
    "scenario", "development_story", "range_environment", "robot_log",
]

mcp = MCPServer("protograph")


def _get(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    try:
        r = httpx.get(f"{BASE}{path}", params=params, timeout=TIMEOUT)
    except httpx.RequestError as e:
        return {"error": "connection_failed",
                "detail": f"{BASE} unreachable — is uvicorn running? ({e})"}
    if r.status_code >= 400:
        return {"error": f"HTTP {r.status_code}", "detail": r.text[:400]}
    try:
        return r.json()
    except ValueError:
        return {"error": "bad_json", "detail": r.text[:400]}


def _post(path: str, payload: Dict[str, Any]) -> Any:
    try:
        r = httpx.post(f"{BASE}{path}", json=payload, timeout=TIMEOUT)
    except httpx.RequestError as e:
        return {"error": "connection_failed",
                "detail": f"{BASE} unreachable — is uvicorn running? ({e})"}
    if r.status_code >= 400:
        return {"error": f"HTTP {r.status_code}", "detail": r.text[:400]}
    try:
        return r.json()
    except ValueError:
        return {"error": "bad_json", "detail": r.text[:400]}

# ── Read tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def search_graph(query: str, limit: int = 20) -> str:
    """Search the knowledge graph for artifacts matching a text query.

    Returns matching nodes with their id, label, type, and description.
    Use this first to find node ids before calling get_neighbors or create_edge.
    """
    return json.dumps(_get("/api/search/smart", {"q": query, "limit": limit}), indent=2)


@mcp.tool()
def get_neighbors(node_id: str, depth: int = 1) -> str:
    """Get nodes connected to a given node, out to the given depth (1-5).

    node_id must be in 'Collection/key' form, e.g. 'TTP/spearphishing'.
    Get valid ids from search_graph.
    """
    return json.dumps(_get("/neighbors", {"node_id": node_id, "depth": depth}), indent=2)


@mcp.tool()
def get_artifact(doc_id: str) -> str:
    """Fetch the full record for a single artifact by its id ('Collection/key')."""
    return json.dumps(_get(f"/api/artifact/{doc_id}"), indent=2)


@mcp.tool()
def graph_overview() -> str:
    """Get counts of nodes and edges by type — a summary of what's in the graph.

    Cheap orientation call. Use before a broad exploration.
    """
    return json.dumps({
        "graph_stats": _get("/api/graph/stats"),
        "ontology_stats": _get("/api/ontology/stats"),
        "recent": _get("/api/graph/recent", {"limit": 5}),
    }, indent=2)


@mcp.tool()
def list_library_modules() -> str:
    """List all LibraryModule artifacts (the reusable operator capability library)."""
    return json.dumps(_get("/api/library-modules"), indent=2)


@mcp.tool()
def validate_nodes(node_ids: str) -> str:
    """Check whether nodes exist. node_ids is a comma-separated list of 'Collection/key'.

    Call this before create_edge — edges to nonexistent nodes are accepted
    silently by the server and produce dangling references.
    """
    return json.dumps(_get("/prospector/validate-nodes", {"node_ids": node_ids}), indent=2)


# ── Write tools ───────────────────────────────────────────────────────────────

@mcp.tool()
def create_node(
    label: str,
    type: str,
    cluster: str = "default",
    description: str = "",
    tags: Optional[List[str]] = None,
) -> str:
    """Create a new node in the knowledge graph.

    label: human-readable name. The storage key is derived by lowercasing it and
           replacing non-alphanumerics with underscores, so two labels that
           slugify identically will collide and overwrite.
    type:  must be one of: library_module, ttp, person, team, execution_plan,
           scenario, development_story, range_environment, robot_log.

    Search first — do not create a node that already exists.
    """
    if type.lower() not in VALID_NODE_TYPES:
        return json.dumps({
            "error": f"Invalid type '{type}'.",
            "valid_types": VALID_NODE_TYPES,
            "note": "The server would silently store this as LibraryModule. Pick a real type.",
        }, indent=2)
    return json.dumps(_post("/prospector/node", {
        "label": label,
        "type": type.lower(),
        "cluster": cluster,
        "description": description,
        "tags": tags or [],
        "custom_fields": {},
    }), indent=2)


@mcp.tool()
def create_edge(
    from_node: str,
    to_node: str,
    relationship_type: str,
    weight: float = 1.0,
    description: str = "",
) -> str:
    """Create a directed relationship between two existing nodes.

    from_node / to_node must be 'Collection/key' ids — a bare key is stored
    against an 'Unknown' collection and the edge will not resolve.
    relationship_type is uppercased, e.g. USES, IMPLEMENTS, OWNED_BY.
    weight is stored as the edge's confidence (0.0-1.0).

    Call validate_nodes on both ids first.
    """
    for label, nid in (("from_node", from_node), ("to_node", to_node)):
        if "/" not in nid:
            return json.dumps({
                "error": f"{label} '{nid}' is not in 'Collection/key' form.",
                "hint": "Use search_graph to get a full id.",
            }, indent=2)
    return json.dumps(_post("/prospector/edge", {
        "from_node": from_node,
        "to_node": to_node,
        "relationship_type": relationship_type.upper(),
        "weight": weight,
        "bidirectional": False,
        "description": description,
        "metadata": {},
    }), indent=2)


# ── Self-test ─────────────────────────────────────────────────────────────────

def _selftest() -> int:
    print(f"ProtoGraph at {BASE}\n")
    health = _get("/api/health")
    print("health:", json.dumps(health)[:200])
    if isinstance(health, dict) and health.get("error"):
        print("\nServer unreachable. Start uvicorn first.")
        return 1
    print("\nstats:", json.dumps(_get("/api/graph/stats"))[:300])
    print("\nsearch 'team':", json.dumps(_get("/api/search/smart", {"q": "team", "limit": 5}))[:500])
    print("\nOK — REST layer reachable. Tools should work.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    mcp.run()
