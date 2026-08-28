#!/usr/bin/env python3
"""
ATLAS Unified API - GraphDB native backend for 318th RANS knowledge graph.
"""

import os
import json
import re
import csv
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
from io import StringIO

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

GRAPHDB_ENDPOINT = os.getenv("GRAPHDB_ENDPOINT", "http://localhost:7200")
GRAPHDB_REPO     = os.getenv("GRAPHDB_REPO", "atlas")
PAYLOAD_DIR      = os.getenv("PAYLOAD_STORAGE_DIR", "./data/payloads")
JSON_PATH        = "llm_edge_suggestions.json"

app = FastAPI(title="ProtoGraph Unified API", version="5.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
upload_sessions: Dict[str, Dict[str, Any]] = {}

# ── GraphDB ──────────────────────────────────────────────────────────────────
gdb = None
try:
    from graph_db import GraphDBAdapter
    gdb = GraphDBAdapter(endpoint=GRAPHDB_ENDPOINT, repo=GRAPHDB_REPO)
    _h = gdb.health()
    if _h["status"] == "connected":
        print(f"GraphDB connected: {GRAPHDB_ENDPOINT}/repositories/{GRAPHDB_REPO}")
        print(f"  {_h.get('total_triples','?')} triples, types: {_h.get('artifact_counts',{})}")
        try:
            from ingestion_core import init_ingestion_core, router as ingest_core_router
            init_ingestion_core(gdb)
            app.include_router(ingest_core_router)
            print("Ingestion core loaded at /api/ingest/*")
        except Exception as _e:
            print(f"Ingestion core init failed: {_e}")
    else:
        print(f"GraphDB unhealthy: {_h.get('error','unknown')}")
        gdb = None
except Exception as _e:
    print(f"GraphDB init failed: {_e}")
    gdb = None

# ── LLM backend (via llm_client) ─────────────────────────────────────────────
try:
    from llm_client import (
        chat_completion_sync as llm_chat_sync,
        health_check as llm_health_check,
        backend_info as llm_backend_info,
        active_backend as llm_active_backend,
    )
    _llm_info = llm_backend_info()
    print(f"LLM backend: {_llm_info.get('backend')} @ {_llm_info.get('base_url')}")
    print(f"LLM chat model: {_llm_info.get('chat_model')}")
except Exception as _e:
    llm_chat_sync = None
    llm_health_check = None
    llm_backend_info = None
    llm_active_backend = None
    print(f"LLM client init failed: {_e}")

# ── Models ───────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = None

class CreateNodeRequest(BaseModel):
    label: str
    type: str
    cluster: str
    description: Optional[str] = None
    tags: Optional[List[str]] = []
    custom_fields: Optional[Dict[str, Any]] = {}

class UpdateNodeRequest(BaseModel):
    node_id: str
    label: Optional[str] = None
    type: Optional[str] = None
    cluster: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[Dict[str, Any]] = None

class CreateEdgeRequest(BaseModel):
    from_node: str
    to_node: str
    relationship_type: str
    weight: float = 1.0
    bidirectional: bool = False
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}

# ExecutionEnvironment was removed with the /api/library-modules routes. It
# modelled a Cobalt Strike range (C2 server, listeners, beacons, SSH sessions)
# \u2014 atlas domain vocabulary, and used by nothing else.

class JSONUserReview(BaseModel):
    connectionId: str
    decision: str
    correctedRelationship: Optional[str] = None
    feedback: Optional[str] = None
    reviewedAt: str
    reviewedBy: str

# ── JSON utils ────────────────────────────────────────────────────────────────
def load_json():
    if not os.path.exists(JSON_PATH):
        return {"part1_responses": []}
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return {"part1_responses": []}
        data = json.loads(content)
        if isinstance(data, list):
            return {"part1_responses": data}
        if isinstance(data, dict) and "part1_responses" in data:
            return data
        return {"part1_responses": []}
    except Exception as e:
        print(f"JSON load error: {e}")
        return {"part1_responses": []}

def save_json(data):
    with open(JSON_PATH, "w") as f:
        json.dump(data, f, indent=2)

# ── Root / Health ─────────────────────────────────────────────────────────────
@app.get("/")
def root():
    llm_ok = False
    llm_backend = "unavailable"
    if llm_health_check:
        try:
            h = llm_health_check()
            llm_ok = bool(h.get("reachable"))
            llm_backend = h.get("backend", "unknown")
        except Exception:
            pass
    return {"service": "ATLAS Unified API", "version": "5.0.0",
            "graphdb_connected": gdb is not None,
            "llm_connected": llm_ok,
            "llm_backend": llm_backend}

@app.get("/health")
def health_check():
    llm_ok = False
    llm_backend = "unavailable"
    llm_info = {}
    if llm_health_check:
        try:
            llm_info = llm_health_check()
            llm_ok = bool(llm_info.get("reachable"))
            llm_backend = llm_info.get("backend", "unknown")
        except Exception:
            llm_info = {"status": "error"}
    info = {"status": "ok", "time": datetime.utcnow().isoformat(),
            "graphdb_connected": gdb is not None,
            "llm_connected": llm_ok,
            "llm_backend": llm_backend}
    if gdb:
        try:
            info["graphdb"] = gdb.health()
        except Exception:
            info["graphdb"] = {"status": "error"}
    if llm_info:
        info["llm"] = llm_info
    return info

@app.get("/api/health")
def api_health_check():
    return health_check()

@app.get("/api/graph/stats")
def graph_stats():
    if not gdb:
        return {"nodes": 0, "edges": 0}
    graph = gdb.get_full_graph()
    return {"nodes": graph.get("count", 0), "edges": len(graph.get("edges", []))}

@app.get("/api/graph/recent")
def graph_recent(limit: int = Query(5, ge=1, le=50)):
    if not gdb:
        return {"items": []}
    graph = gdb.get_full_graph()
    nodes = graph.get("nodes", [])[:limit]
    items = [{"id": n.get("id"), "label": n.get("label"), "type": n.get("type")} for n in nodes]
    return {"items": items}

@app.get("/api/ontology/stats")
def ontology_stats():
    if not gdb:
        return {"taxonomies": 0, "concepts": 0}
    concept_rows = gdb.sparql_query("""
        SELECT (COUNT(DISTINCT ?cls) AS ?count) WHERE {
            ?cls a owl:Class .
            FILTER(STRSTARTS(STR(?cls), "https://proto.atlas/ontology/"))
        }
    """)
    tax_rows = gdb.sparql_query("""
        SELECT (COUNT(DISTINCT ?s) AS ?count) WHERE { ?s a skos:ConceptScheme . }
    """)
    return {
        "taxonomies": int(tax_rows[0]["count"]) if tax_rows else 0,
        "concepts": int(concept_rows[0]["count"]) if concept_rows else 0,
    }

@app.get("/api/pipelines/stats")
def pipeline_stats():
    return {"pipelines": 0, "active": 0}

@app.get("/api/upload/stats")
def upload_stats():
    pdir = Path(PAYLOAD_DIR)
    ingested = len(list(pdir.glob("*.json"))) if pdir.exists() else 0
    return {"ingested": ingested, "pending": 0}

@app.get("/api/onboarding/schemas-latest")
def latest_schema():
    if not gdb:
        return {"fields": {}, "relationships": [], "domain_name": "default"}
    types = gdb.get_ontology_types()
    preferred = next((t for t in types if t.get("label") == "Service"), types[0] if types else None)
    if not preferred:
        return {"fields": {}, "relationships": [], "domain_name": "default"}
    fields = {}
    for p in preferred.get("properties", []):
        fields[p["name"]] = {
            "data_type": p.get("type", "string"),
            "description": p.get("description", ""),
            "required": bool(p.get("required", False)),
            "example_values": [],
            "extraction_hint": "",
        }
    return {
        "fields": fields,
        "default_fields": {},
        "relationships": [],
        "session_id": f"schema_{int(datetime.utcnow().timestamp())}",
        "domain_name": preferred.get("label", "default"),
    }

@app.post("/api/upload/files")
async def upload_files(files: List[UploadFile] = File(...)):
    parsed_files = []
    all_rows: List[Dict[str, Any]] = []
    warnings = []
    for f in files:
        raw = await f.read()
        name = f.filename or "upload"
        ext = Path(name).suffix.lower()
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            text = ""
        if ext in [".csv", ".tsv"]:
            delim = "," if ext == ".csv" else "\t"
            reader = csv.DictReader(StringIO(text))
            rows = []
            for idx, row in enumerate(reader, start=1):
                r = {k: v for k, v in row.items()}
                r["_source_row"] = idx
                rows.append(r)
            parsed_files.append({
                "filename": name,
                "extension": ext,
                "row_count": len(rows),
                "columns": [c for c in (reader.fieldnames or []) if c],
                "is_structured": True,
                "sample_rows": rows[:5],
            })
            for r in rows:
                r["_source_file"] = name
            all_rows.extend(rows)
        elif ext == ".json":
            obj = json.loads(text) if text.strip() else []
            rows = obj if isinstance(obj, list) else [obj]
            for idx, row in enumerate(rows, start=1):
                row["_source_row"] = idx
                row["_source_file"] = name
            columns = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []
            parsed_files.append({
                "filename": name,
                "extension": ext,
                "row_count": len(rows),
                "columns": columns,
                "is_structured": True,
                "sample_rows": rows[:5],
            })
            all_rows.extend(rows)
        else:
            parsed_files.append({
                "filename": name,
                "extension": ext,
                "row_count": 1,
                "columns": ["_full_text"],
                "is_structured": False,
                "sample_rows": [{"_full_text": text[:5000], "_source_row": 1}],
            })
            all_rows.append({"_full_text": text[:5000], "_source_row": 1, "_source_file": name})
            warnings.append(f"{name}: treated as unstructured text")

    session_id = f"upload_{int(datetime.utcnow().timestamp())}"
    upload_sessions[session_id] = {"rows": all_rows, "files": parsed_files, "created_at": datetime.utcnow().isoformat()}
    return {"upload_session_id": session_id, "files": parsed_files, "warnings": warnings}

class UploadExtractRequest(BaseModel):
    upload_session_id: str
    schema_fields: Dict[str, Any] = {}
    relationships: List[Dict[str, Any]] = []
    collection_name: str = "artifacts"

@app.post("/api/upload/extract")
async def upload_extract(req: UploadExtractRequest):
    sess = upload_sessions.get(req.upload_session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Upload session not found")
    field_names = list(req.schema_fields.keys())
    records = []
    for i, row in enumerate(sess["rows"], start=1):
        rec = {
            "_id": f"rec_{i}",
            "_source_file": row.get("_source_file", "upload"),
            "_source_row": row.get("_source_row", i),
            "_confidence": 0.9,
            "_status": "pending",
        }
        if field_names:
            for f in field_names:
                rec[f] = row.get(f)
        else:
            for k, v in row.items():
                if not k.startswith("_"):
                    rec[k] = v
        records.append(rec)
    sess["records"] = records
    return {"records": records, "extraction_method": "schema_projection", "warnings": []}

class UploadCommitRequest(BaseModel):
    upload_session_id: str
    records: List[Dict[str, Any]]
    collection_name: str = "artifacts"
    domain_name: Optional[str] = None
    create_edges: bool = True

@app.post("/api/upload/commit")
async def upload_commit(req: UploadCommitRequest):
    if not gdb:
        raise HTTPException(status_code=503, detail="GraphDB not connected")
    created = 0
    errors = []
    valid_types = {t.get("collection") for t in gdb.get_ontology_types()}
    for idx, r in enumerate(req.records, start=1):
        if r.get("_status") not in ("approved", "edited"):
            continue
        artifact_type = str(r.get("type") or req.domain_name or req.collection_name or "Service")
        artifact_type = artifact_type.replace(" ", "")
        if artifact_type not in valid_types:
            artifact_type = "Service" if "Service" in valid_types else next(iter(valid_types), None)
        if not artifact_type:
            errors.append(f"Record {idx}: no valid ontology type available")
            continue
        key = str(r.get("key") or r.get("name") or f"upload-{idx}").strip().lower()
        key = re.sub(r"[^a-zA-Z0-9_-]", "-", key).strip("-") or f"upload-{idx}"
        props = {k: v for k, v in r.items() if not k.startswith("_") and k not in ("key",)}
        try:
            gdb.create_node(key, artifact_type, props)
            created += 1
        except Exception as e:
            errors.append(f"Record {idx}: {e}")
    return {"nodes_created": created, "edges_created": 0, "collection": req.collection_name, "errors": errors}

# ── Graph ─────────────────────────────────────────────────────────────────────
@app.get("/graph")
def get_graph(include_schema: bool = False):
    if not gdb:
        raise HTTPException(status_code=503, detail="GraphDB not connected")
    try:
        result = gdb.get_full_graph(include_schema=include_schema)
        print(f"/graph: {result['count']} nodes, {len(result['edges'])} edges")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/neighbors")
def get_neighbors(node_id: str = Query(...), depth: int = Query(1, ge=1, le=5)):
    if not gdb:
        raise HTTPException(status_code=503, detail="GraphDB not connected")
    try:
        result = gdb.get_neighbors(node_id, depth=depth)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Search ────────────────────────────────────────────────────────────────────
@app.get("/api/search/smart")
async def smart_search(q: str = Query(..., min_length=1), limit: int = Query(20, le=100)):
    if not gdb:
        raise HTTPException(status_code=503, detail="GraphDB not connected")
    try:
        results = gdb.search(q, limit=limit)
        return {"query": q, "count": len(results),
                "results": [{"id": r["_id"], "label": r.get("name", r["_key"]),
                              "type": r.get("_artifact_type", "Unknown"),
                              "description": r.get("description", "")} for r in results]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Artifact fetch ────────────────────────────────────────────────────────────
@app.get("/api/artifact/{doc_id}")
def get_artifact(doc_id: str):
    if not gdb:
        raise HTTPException(status_code=503, detail="GraphDB not connected")
    if "/" not in doc_id:
        raise HTTPException(status_code=400, detail="Invalid doc_id - expected collection/key")
    collection, key = doc_id.split("/", 1)
    try:
        doc = gdb.get_artifact(collection, key)
        if doc is None:
            raise HTTPException(status_code=404, detail=f"Not found: {doc_id}")
        return {"success": True, "data": doc}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/artifact/{collection}/{key:path}")
def get_artifact_by_parts(collection: str, key: str):
    if not gdb:
        raise HTTPException(status_code=503, detail="GraphDB not connected")
    try:
        doc = gdb.get_artifact(collection, key)
        if doc is None:
            raise HTTPException(status_code=404, detail=f"Not found: {collection}/{key}")
        return {"success": True, "data": doc}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Chat ──────────────────────────────────────────────────────────────────────
@app.post("/chat")
def chat(req: ChatRequest):
    if not llm_chat_sync:
        raise HTTPException(status_code=503, detail="LLM client unavailable")
    try:
        system = ("You are ATLAS, AI assistant for the 318th RANS knowledge graph. "
                  "Help analysts understand cyber ops artifacts, TTPs, and range configs. "
                  "No markdown. Match response length to question. Speak naturally.")
        prompt = f"Graph context: {req.context or 'None'}\n\nQuestion: {req.message}"
        response = llm_chat_sync(prompt=prompt, system=system, temperature=0.2)
        return {"reply": response}
    except Exception as e:
        backend = llm_active_backend() if llm_active_backend else "unknown"
        raise HTTPException(status_code=500, detail=f"LLM chat failed ({backend}): {str(e)}")

# ── TTL ingest proxy ──────────────────────────────────────────────────────────
@app.post("/api/ingest/ttl")
async def ingest_ttl(request: Request):
    ttl_body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                f"{GRAPHDB_ENDPOINT}/repositories/{GRAPHDB_REPO}/statements",
                content=ttl_body, headers={"Content-Type": "text/turtle"})
        if res.status_code not in (200, 204):
            raise HTTPException(status_code=res.status_code,
                                detail=f"GraphDB rejected TTL: {res.text[:500]}")
        return {"ok": True, "status": res.status_code}
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=f"Cannot reach GraphDB at {GRAPHDB_ENDPOINT}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTL ingest failed: {str(e)}")

@app.post("/api/ingest/payloads/{key}.json")
async def save_payload_file(key: str, request: Request):
    payload = await request.json()
    path = Path(PAYLOAD_DIR) / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return {"saved": str(path), "key": key}
# The /api/library-modules/* endpoints were removed (6 routes), along with
# _enrich_module() and the ExecutionEnvironment model that only they used:
#
#   GET  /api/library-modules
#   GET  /api/library-modules/categories
#   GET  /api/library-modules/tactics
#   GET  /api/library-modules/stats
#   GET  /api/library-modules/{module_key}
#   POST /api/library-modules/validate-requirements
#
# Every one hardcoded proto:LibraryModule plus atlas properties (tactic,
# riskLevel, executionType, c2Server, listeners, beacons). They served the
# Operator/Lumen UI, which is retired. They also called five adapter methods
# that no longer exist, so each returned 500.
#
# Generic replacements live on the adapter and work for any declared class:
#   gdb.get_artifacts_by_type(collection, filters=..., limit=...)
#   gdb.get_property_value_counts(collection, property_name)
#   gdb.get_type_stats(collection)
#   gdb.get_artifact(collection, key)

# ── Prospector ────────────────────────────────────────────────────────────────
# _TYPE_MAP was removed. It mapped ten atlas type strings to class names and
# fell back to "LibraryModule" for anything unrecognised \u2014 so a typo, or any
# class declared after this file was written, was silently stored as a
# LibraryModule instead of being rejected.
#
# Type resolution now goes through the adapter, which validates against the
# classes the ontology actually declares in the connected repository.

@app.post("/prospector/node")
async def prospector_create_node(request: CreateNodeRequest):
    if not gdb:
        raise HTTPException(status_code=503, detail="GraphDB not connected")
    try:
        # Resolve against the live ontology. collection_to_class_uri() is
        # case- and underscore-insensitive, so "source_file", "sourcefile" and
        # "SourceFile" all match a declared SourceFile class.
        if not gdb.collection_to_class_uri(request.type):
            declared = gdb.live_collections()
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unknown artifact type: {request.type!r}. "
                    f"Declared classes: {', '.join(declared) if declared else '(none)'}. "
                    f"Declare it in the ontology manager first."
                ),
            )
        artifact_type = gdb.collection_to_class_uri(request.type).rsplit("/", 1)[-1]
        key = re.sub(r"[^a-zA-Z0-9_-]", "_", request.label.lower()).strip("_")
        props = {"name": request.label, "description": request.description or ""}
        if request.custom_fields:
            props.update(request.custom_fields)
        result = gdb.create_node(key, artifact_type, props)
        return {"success": True, "node": {"_id": result["_id"], "_key": key,
                "name": request.label, "type": request.type, "cluster": request.cluster,
                "description": request.description or "", "tags": request.tags or [],
                "created_at": datetime.utcnow().isoformat()}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/prospector/node")
async def prospector_update_node(request: UpdateNodeRequest):
    if not gdb:
        raise HTTPException(status_code=503, detail="GraphDB not connected")
    if "/" not in request.node_id:
        raise HTTPException(status_code=400, detail="Invalid node_id - expected collection/key")
    coll, key = request.node_id.split("/", 1)
    updates = {}
    if request.label is not None: updates["name"] = request.label
    if request.description is not None: updates["description"] = request.description
    if request.custom_fields: updates.update(request.custom_fields)
    try:
        result = gdb.update_node(coll, key, updates)
        return {"success": True, "node_id": result["_id"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/prospector/node/{node_id:path}")
async def prospector_delete_node(node_id: str):
    if not gdb:
        raise HTTPException(status_code=503, detail="GraphDB not connected")
    if "/" not in node_id:
        raise HTTPException(status_code=400, detail="Invalid node_id - expected collection/key")
    coll, key = node_id.split("/", 1)
    try:
        gdb.delete_node(coll, key)
        return {"success": True, "deleted_node_id": node_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/prospector/edge")
async def prospector_create_edge(request: CreateEdgeRequest):
    if not gdb:
        raise HTTPException(status_code=503, detail="GraphDB not connected")
    try:
        fp = request.from_node.split("/",1) if "/" in request.from_node else ("Unknown", request.from_node)
        tp = request.to_node.split("/",1)   if "/" in request.to_node   else ("Unknown", request.to_node)
        result = gdb.create_edge(fp[0], fp[1], tp[0], tp[1],
                                  request.relationship_type.upper(),
                                  source="operator_authored", confidence=request.weight)
        return {"success": True, "edge": result,
                "message": "Edge created" + (" (bidirectional)" if request.bidirectional else "")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/prospector/edge/{edge_id:path}")
async def prospector_delete_edge(edge_id: str):
    if not gdb:
        raise HTTPException(status_code=503, detail="GraphDB not connected")
    if "/" not in edge_id:
        raise HTTPException(status_code=400, detail="Invalid edge_id - expected rel_type/key")
    rel_type, key_pair = edge_id.split("/", 1)
    try:
        if "-" in key_pair:
            fk, tk = key_pair.split("-", 1)
            gdb.delete_edge(fk, tk, rel_type)
        else:
            ns = "https://proto.atlas/relationship/"
            dn = "https://proto.atlas/data/"
            gdb.sparql_update(
                "DELETE WHERE { ?s <" + ns + rel_type + "> ?o . "
                "FILTER(STRENDS(STR(?s), \"" + key_pair + "\") || "
                "STRENDS(STR(?o), \"" + key_pair + "\")) }"
            )
        return {"success": True, "deleted_edge_id": edge_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/prospector/validate-nodes")
async def prospector_validate_nodes(node_ids: str):
    if not gdb:
        raise HTTPException(status_code=503, detail="GraphDB not connected")
    id_list = [n.strip() for n in node_ids.split(",")]
    results = {}
    for node_id in id_list:
        if "/" not in node_id:
            results[node_id] = False
            continue
        _, key = node_id.split("/", 1)
        results[node_id] = gdb.has_artifact(key)
    return {"success": True, "all_nodes_exist": all(results.values()), "nodes": results}

# ── Connection review ─────────────────────────────────────────────────────────
@app.get("/connections/pending")
def get_pending_connections():
    data = load_json()
    formatted = []
    for idx, item in enumerate(data.get("part1_responses", [])):
        if "user_decision" in item:
            continue
        src = item.get("src_node", {})
        tgt = item.get("pair_node", {})
        src_type = src.get("_id","").split("/")[0] if "/" in src.get("_id","") else "Unknown"
        tgt_type = tgt.get("_id","").split("/")[0] if "/" in tgt.get("_id","") else "Unknown"
        def _cluster(node, _nt):
            # Read what the node actually carries. This used to substring-match
            # the owner against "automation"/"range"/"opfor" \u2014 318th RANS team
            # names hardcoded here \u2014 which invented a cluster for atlas data and
            # returned "Unknown" for everything else.
            return node.get("cluster") or node.get("team") or "Unknown"
        excl = {"_id","_key","_rev","name","description","label"}
        formatted.append({
            "id": f"json_{idx}",
            "sourceNode": {"id": src.get("_id"),
                           "label": src.get("name", src.get("label", src.get("_key","Unknown"))),
                           "type": src_type, "cluster": _cluster(src, src_type),
                           "description": src.get("description",""),
                           "metadata": {k:v for k,v in src.items() if k not in excl}},
            "targetNode": {"id": tgt.get("_id"),
                           "label": tgt.get("name", tgt.get("label", tgt.get("_key","Unknown"))),
                           "type": tgt_type, "cluster": _cluster(tgt, tgt_type),
                           "description": tgt.get("description",""),
                           "metadata": {k:v for k,v in tgt.items() if k not in excl}},
            # No default relationship type: RELATED_TO is not declared in every
            # repository, and defaulting to it would surface a proposal that
            # cannot legally be written.
            "proposedRelationship": item.get("type") or None,
            "confidence": item.get("conn_strength",5) / 10.0,
            "reasoning": item.get("explanation","No explanation provided"),
            "llmModel": item.get("model","unknown"),
            "createdAt": item.get("created_at", datetime.utcnow().isoformat()),
        })
    return {"connections": formatted, "count": len(formatted)}

@app.post("/connections/review")
async def review_connection(review: JSONUserReview):
    data = load_json()
    try:
        index = int(review.connectionId.split("_")[1])
        entry = data["part1_responses"][index]
    except (IndexError, ValueError, KeyError):
        raise HTTPException(status_code=404, detail=f"Invalid connectionId: {review.connectionId}")
    entry["user_decision"] = review.decision
    entry["corrected_relationship"] = review.correctedRelationship
    entry["feedback"] = review.feedback
    entry["reviewed_at"] = review.reviewedAt
    entry["reviewed_by"] = review.reviewedBy
    save_json(data)
    if review.decision in ("approve","modify") and gdb:
        try:
            rel = (review.correctedRelationship
                   if review.decision == "modify" and review.correctedRelationship
                   else entry.get("type"))
            if not rel:
                return {"success": True, "review_saved": True, "edge_created": False,
                        "error": "No relationship type on this proposal, and none "
                                 "supplied. Re-review with correctedRelationship set."}
            rel = rel.upper()

            # Refuse to write an edge whose predicate the ontology does not
            # declare. Without this the approval step could mint an undeclared
            # predicate that nothing downstream will traverse or explain.
            declared = {u.rsplit("/", 1)[-1] for u in gdb.live_relationship_uris()}
            if rel not in declared:
                return {"success": True, "review_saved": True, "edge_created": False,
                        "error": (f"Relationship type {rel!r} is not declared in this "
                                  f"repository. Declared: "
                                  f"{', '.join(sorted(declared)) if declared else '(none)'}. "
                                  f"Declare it in the ontology manager first.")}
            si = entry["src_node"]["_id"]
            ti = entry["pair_node"]["_id"]
            sp = si.split("/",1) if "/" in si else ("Unknown", si)
            tp = ti.split("/",1) if "/" in ti else ("Unknown", ti)
            conf = entry.get("conn_strength",5) / 10.0
            result = gdb.create_edge(sp[0],sp[1],tp[0],tp[1],rel,
                                      source="llm_suggested", confidence=conf)
            return {"success":True,"review_saved":True,"edge_created":True,"edge":result}
        except Exception as e:
            print(f"Edge creation from review failed: {e}")
            return {"success":True,"review_saved":True,"edge_created":False,"error":str(e)}
    return {"success":True,"review_saved":True,"edge_created":False}

@app.get("/connections/stats")
def get_connection_stats():
    data = load_json()
    items = data.get("part1_responses",[])
    reviewed = [i for i in items if "user_decision" in i]
    approved = [i for i in reviewed if i.get("user_decision")=="approve"]
    modified = [i for i in reviewed if i.get("user_decision")=="modify"]
    rejected = [i for i in reviewed if i.get("user_decision")=="reject"]
    td = len(approved)+len(rejected)
    avg_conf = (sum(i.get("conn_strength",5) for i in approved+modified)
                /len(approved+modified)/10.0 if approved or modified else 0.0)
    return {"total_pending":len(items)-len(reviewed),"total_reviewed":len(reviewed),
            "approved_count":len(approved),"rejected_count":len(rejected),
            "modified_count":len(modified),
            "precision":len(approved)/td if td>0 else 0.0,
            "avg_approved_confidence":avg_conf}

@app.post("/connections/batch-approve")
async def batch_approve_connections(confidence_threshold: float=0.8,
                                    max_count: int=10, reviewed_by: str="batch_automation"):
    data = load_json()
    candidates = [(idx,item) for idx,item in enumerate(data.get("part1_responses",[]))
                  if "user_decision" not in item
                  and item.get("conn_strength",0)/10.0 >= confidence_threshold][:max_count]
    results = []
    for idx, item in candidates:
        fake = JSONUserReview(
            connectionId=f"json_{idx}", decision="approve", correctedRelationship=None,
            feedback=f"Auto-approved (conf {item.get('conn_strength',0)/10.0:.2f})",
            reviewedAt=datetime.utcnow().isoformat(), reviewedBy=reviewed_by)
        r = await review_connection(fake)
        results.append({"connectionId":f"json_{idx}","confidence":item.get("conn_strength",0)/10.0,**r})
    return {"success":True,"approved_count":len(results),"results":results}

# ── Router mounts ─────────────────────────────────────────────────────────────
import plugins.operator_plugin  # noqa: F401 - registers OperatorPlugin in PluginRegistry

# ── Load persisted plugin manifests ───────────────────────────────────────────
def _load_persisted_plugins():
    """
    Reload any plugins registered via POST /api/plugins/register.
    Manifests are saved to data/plugin_manifests/{id}.json at registration time.
    This runs once at startup so registered apps survive server restarts.
    """
    manifests_dir = Path(PAYLOAD_DIR).parent / "plugin_manifests"
    if not manifests_dir.exists():
        return
    from plugins.endpoints import register_plugin, RegisterManifest
    loaded = 0
    for manifest_file in manifests_dir.glob("*.json"):
        try:
            data = json.loads(manifest_file.read_text())
            manifest = RegisterManifest(**data)
            register_plugin(manifest)
            loaded += 1
        except Exception as e:
            print(f"⚠️  Failed to reload plugin manifest {manifest_file.name}: {e}")
    if loaded:
        print(f"✓ Reloaded {loaded} persisted plugin(s) from {manifests_dir}")

_load_persisted_plugins()
from plugins.endpoints import router as plugin_router
from plugins.plugin_router import create_plugin_data_router
from plugins.config_endpoints import router as config_router
from onboard_endpoints import router as onboard_router

app.include_router(plugin_router)
plugin_data_router = create_plugin_data_router(None, PAYLOAD_DIR, gdb)
app.include_router(plugin_data_router)

app.include_router(config_router)
app.include_router(onboard_router)

from plugins.proposal_endpoints import router as proposal_router
app.include_router(proposal_router)

if gdb:
    try:
        from ontology_graphdb import init_ontology_graphdb, router as ontology_gdb_router
        init_ontology_graphdb(gdb)
        app.include_router(ontology_gdb_router)
        print("Ontology API mounted at /api/ontology/*")
    except Exception as _e:
        print(f"Ontology GraphDB API failed: {_e}")

if gdb:
    try:
        from nl_query_engine import init_query_engine, router as nl_query_router
        init_query_engine(gdb)
        app.include_router(nl_query_router)
        print("NL query engine mounted at /api/query/*")
    except Exception as _e:
        print(f"NL query engine failed: {_e}")

# ── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)