# kg_course

This repo is the ProtoGraph backend. `server/` holds the FastAPI app, the NL→SPARQL
engine, the GraphDB adapter, and the ontology manager. `src/` is the Vite frontend.

# Services

| Service | Address | Notes |
|---|---|---|
| ProtoGraph API | `http://localhost:8000` | FastAPI, from `kg_course/server`. Run without `--reload`. |
| GraphDB | `http://localhost:7200` | Triplestore. Workbench UI at the same address. |
| Ollama (range box) | `http://10.10.80.99:4001` | Not the default 11434. |

If a `protograph` tool returns `connection_failed`, uvicorn is not running. Say so
and stop. Do not grep the filesystem and present the result as a graph answer.

GraphDB config lives in the repo-root `.env` as `GRAPHDB_ENDPOINT` and `GRAPHDB_REPO`.
The server binds one repository at startup; changing it requires a restart.
