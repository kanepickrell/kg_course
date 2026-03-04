#!/usr/bin/env python3
"""
Unified ProtoGraph API Service
Combines:
 - ArangoDB Graph endpoints
 - AI Assistant (Ollama) endpoints
"""

import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from collections import defaultdict
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from arango import ArangoClient
from dotenv import load_dotenv
import ollama
from fastapi import Request

# =========================================
# ENVIRONMENT SETUP
# =========================================
load_dotenv()

ARANGO_HOST = os.getenv("ARANGO_HOST", "http://localhost:8529")
ARANGO_USER = os.getenv("ARANGO_USER", "root")
ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD", "")
ARANGO_DB = os.getenv("ARANGO_DB", "protograph")
ARANGO_GRAPH = os.getenv("ARANGO_GRAPH", "protoGraph")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://10.10.80.99:4001")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:120b")

# =========================================
# FASTAPI APP CONFIGURATION
# =========================================
app = FastAPI(
    title="ProtoGraph Unified API",
    description="ArangoDB Graph + AI Assistant Backend",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://localhost:5173",
        "http://localhost:3000",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================
# DATABASE CONNECTION
# =========================================
try:
    client = ArangoClient(hosts=ARANGO_HOST)
    db = client.db(ARANGO_DB, username=ARANGO_USER, password=ARANGO_PASSWORD)
    print(f"✓ Connected to ArangoDB: {ARANGO_DB}")
except Exception as e:
    print(f"✗ Failed to connect to ArangoDB: {e}")
    db = None

# =========================================
# OLLAMA CONFIGURATION
# =========================================
try:
    ollama_client = ollama.Client(host=OLLAMA_HOST)
except Exception as e:
    ollama_client = None
    print(f"⚠️ Ollama not available: {e}")

# =========================================
# DATA MODELS
# =========================================
class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = None

class UpdateNotification(BaseModel):
    change_type: str
    affected_nodes: List[str] = []
    timestamp: Optional[str] = None

# =========================================
# ARANGODB GRAPH ENDPOINTS
# =========================================
@app.get("/")
def root():
    return {
        "service": "ProtoGraph Unified API",
        "status": "running",
        "database": ARANGO_DB,
        "ollama_model": OLLAMA_MODEL,
        "connected": db is not None,
    }


@app.get("/graph")
def get_graph():
    """Return all nodes and edges from ArangoDB"""
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")

    try:
        nodes_cursor = db.aql.execute("FOR node IN nodes RETURN node")
        edges_cursor = db.aql.execute("FOR edge IN edges RETURN edge")

        nodes = [
            {
                "id": n["_id"],
                "label": n.get("label", n["_key"]),
                "cluster": n.get("cluster"),
                "type": n.get("type"),
                "importance": n.get("importance", 0.5),
                "size": n.get("size", 40),
            }
            for n in nodes_cursor
        ]

        edges = [
            {
                "id": e["_id"],
                "source": e["_from"],
                "target": e["_to"],
                "type": e.get("type", "relation"),
                "weight": e.get("weight", 1.0),
            }
            for e in edges_cursor
        ]

        return {"nodes": nodes, "edges": edges}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch graph: {str(e)}")


@app.get("/neighbors/{node_key}")
def get_neighbors(node_key: str, depth: int = Query(1, ge=1, le=5)):
    """Fetch connected nodes within N hops."""
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")

    try:
        clean_key = node_key.replace("nodes/", "")
        query = """
            FOR v, e, p IN 1..@depth ANY CONCAT('nodes/', @key) GRAPH @graph
                RETURN DISTINCT { node: v, edge: e, distance: LENGTH(p.edges) }
        """
        results = list(db.aql.execute(query, bind_vars={
            "key": clean_key,
            "depth": depth,
            "graph": ARANGO_GRAPH}))

        nodes, edges, seen_nodes, seen_edges = [], [], set(), set()

        # Add center node
        center = list(db.aql.execute("RETURN DOCUMENT(CONCAT('nodes/', @key))", bind_vars={"key": clean_key}))
        if center and center[0]:
            c = center[0]
            nodes.append({
                "id": c["_id"],
                "label": c.get("label", c["_key"]),
                "cluster": c.get("cluster"),
                "type": c.get("type"),
                "importance": c.get("importance", 0.5),
                "size": c.get("size", 40)
            })
            seen_nodes.add(c["_id"])

        # Add neighbors
        for item in results:
            v, e = item["node"], item["edge"]
            if v["_id"] not in seen_nodes:
                nodes.append({
                    "id": v["_id"],
                    "label": v.get("label", v["_key"]),
                    "cluster": v.get("cluster"),
                    "type": v.get("type"),
                    "importance": v.get("importance", 0.5),
                    "size": v.get("size", 40),
                    "distance": item["distance"],
                })
                seen_nodes.add(v["_id"])
            if e and e["_id"] not in seen_edges:
                edges.append({
                    "id": e["_id"],
                    "source": e["_from"],
                    "target": e["_to"],
                    "type": e.get("type", "relation"),
                    "weight": e.get("weight", 1.0),
                })
                seen_edges.add(e["_id"])

        return {"center": clean_key, "depth": depth, "nodes": nodes, "edges": edges, "count": len(nodes)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch neighbors: {str(e)}")


@app.get("/stats")
def get_stats():
    """Graph statistics"""
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")

    try:
        node_count = list(db.aql.execute("RETURN LENGTH(nodes)"))[0]
        edge_count = list(db.aql.execute("RETURN LENGTH(edges)"))[0]
        cluster_query = """
            FOR node IN nodes
                COLLECT cluster = node.cluster WITH COUNT INTO count
                RETURN {cluster: cluster, count: count}
        """
        clusters = list(db.aql.execute(cluster_query))
        return {"total_nodes": node_count, "total_edges": edge_count, "clusters": clusters}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {str(e)}")


@app.get("/search")
def search_nodes(q: str):
    """Search nodes by label"""
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    try:
        results = list(db.aql.execute("""
            FOR node IN nodes
                FILTER CONTAINS(LOWER(node.label), LOWER(@q))
                RETURN node
        """, bind_vars={'q': q}))
        return {"results": [
            {"id": n["_id"], "label": n.get("label", n["_key"]),
             "cluster": n.get("cluster"), "type": n.get("type")}
            for n in results
        ]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

# =========================================
# AI / ANALYTICS ENDPOINTS
# =========================================
chat_history: dict[str, list[dict]] = {}

@app.post("/chat")
async def chat(request: ChatRequest, req: Request):
    """
    Conversational AI assistant for ProtoGraph with short-term memory.
    Remembers tone and previous exchanges for more natural continuity.
    """

    # ----------------------------
    # 1. Identify session
    # ----------------------------
    session_id = req.client.host  # You can replace with user auth/session ID
    history = chat_history.get(session_id, [])

    # ----------------------------
    # 2. Pull graph context from ArangoDB
    # ----------------------------
    context_text = ""
    if db and request.context:
        node_ids = [c.strip() for c in request.context.split(",") if c.strip()]
        node_data, neighbor_data = [], []

        for node_id in node_ids:
            node_result = list(db.aql.execute(
                "RETURN DOCUMENT(@id)", bind_vars={"id": node_id}
            ))
            if node_result and node_result[0]:
                node_data.append(node_result[0])

        if node_data:
            neighbor_result = list(db.aql.execute(
                "FOR v, e IN 1..1 ANY @id edges RETURN DISTINCT {node: v, edge: e}",
                bind_vars={"id": node_ids[0]}
            ))
            neighbor_data.extend(neighbor_result)

            node_summaries = [
                f"{n.get('label','unknown')} ({n.get('type','node type unknown')}) "
                f"in cluster {n.get('cluster','?')} "
                f"with importance {n.get('importance',0.5):.2f}"
                for n in node_data
            ]
            neighbor_summaries = []
            for n in neighbor_data:
                v = n.get("node", {})
                e = n.get("edge", {})
                neighbor_summaries.append(
                    f"{v.get('label','unknown')} via '{e.get('type','relation')}' "
                    f"(weight {e.get('weight',1.0):.2f})"
                )

            context_text = (
                f"You selected {len(node_data)} node(s): "
                + ", ".join(node_summaries)
                + (f". They connect to nearby nodes such as {', '.join(neighbor_summaries[:5])}."
                   if neighbor_summaries else ".")
            )
    else:
        context_text = "No graph context was provided."

    # ----------------------------
    # 3. Build prompt with reinforced tone guidance
    # ----------------------------
    system_msg = (
        "You are Ranger, specifically you are an AI analyst who assists with demystifying complex networks of data relationships. "
        "More generally, the data is all representing workflow process data generated across teams and the relationships between them are graphed"
        "The goal of the conversation is to better help them understand their system better"
        "Speak naturally and conversationally — no markdown, bullet lists, or tables. "
        "Keep responses short and insightful, explaining what relationships mean and why they matter. "
        "Stay consistent with prior tone and style throughout the session."
    )

    user_prompt = (
        f"Context summary: {context_text}\n\n"
        f"User question: {request.message}\n\n"
        "Respond in plain language, anywhere between 1-5 sentences or 1-5 short paragraphs depending on the query"
        "Do not use markdown formatting like **bold**, lists, or code blocks. "
        "Focus on meaningful insights and next-step reasoning."
    )

    # ----------------------------
    # 4. Assemble conversation with history
    # ----------------------------
    messages = [
        {"role": "system", "content": system_msg},
        *history,
        {"role": "user", "content": user_prompt},
    ]

    # ----------------------------
    # 5. Generate response
    # ----------------------------
    try:
        response = ollama_client.chat(model=OLLAMA_MODEL, messages=messages)
        reply = response["message"]["content"]

        # Update short-term history (keep last 10 exchanges)
        chat_history[session_id] = (history + [
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": reply},
        ])[-10:]

    except Exception as e:
        reply = f"There was a problem communicating with the AI model: {str(e)}"

    # ----------------------------
    # 6. Return plain response
    # ----------------------------
    return {"reply": reply}


    # ----------------------------
    # 2. Build conversational prompt
    # ----------------------------
    system_msg = (
        "You are an AI analyst embedded in ProtoGraph. "
        "Speak naturally and conversationally — no markdown or tables. "
        "Focus on explaining what the graph relationships mean, how they might influence each other "
        "and what the user could consider next. "
        "Be concise and insightful, like you're discussing it with a teammate."
    )

    user_prompt = (
        f"Context summary: {context_text}\n\n"
        f"User question: {request.message}\n\n"
        "Respond in plain language (1–2 short paragraphs). "
        "If the user seems to ask 'tell me about', describe key patterns and significance. "
        "If the question implies action, suggest next steps briefly."
    )

    # ----------------------------
    # 3. Call Ollama model
    # ----------------------------
    try:
        response = ollama_client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_prompt},
            ],
        )
        reply = response["message"]["content"]
    except Exception as e:
        reply = f"⚠️ Error communicating with Ollama: {str(e)}"

    # ----------------------------
    # 4. Return plain response
    # ----------------------------
    return {"reply": reply}


@app.get("/health/ollama")
async def check_ollama():
    """Check Ollama connection"""
    try:
        models = ollama_client.list().get("models", [])
        model_names = [m["name"] for m in models]
        return {
            "status": "online",
            "available_models": model_names,
            "current_model": OLLAMA_MODEL,
            "model_exists": OLLAMA_MODEL in model_names,
        }
    except Exception as e:
        return {"status": "offline", "error": str(e)}

@app.post("/analytics/notify-update")
def notify_update(payload: Dict[str, Any]):
    """Notify analytics updates (frontend -> backend)"""
    print(f"📩 Received analytics update: {payload}")
    return {"status": "ok", "received": payload, "timestamp": datetime.now().isoformat()}

# =========================================
# MAIN
# =========================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
