"""
Onboarding Endpoints
====================
POST /api/onboard/analyze-code
  - Accepts a Python file's filename + source content
  - Sends to LLM for analysis
  - Returns CodeAnalysis shape matching AppOnboarding.tsx interface

POST /api/onboard/save-code
  - Saves the uploaded file to plugins/{plugin_id}/
  - Called by register_plugin after scaffolding

Mount in main.py:
    from onboard_endpoints import router as onboard_router
    app.include_router(onboard_router)
"""

import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(prefix="/api/onboard", tags=["Onboarding"])


# ── Request / Response models ─────────────────────────────────────────────────

class AnalyzeCodeRequest(BaseModel):
    filename: str
    content:  str


class EntryPoint(BaseModel):
    fn:        str
    args:      List[str]
    returns:   str
    docstring: Optional[str] = None


class CodeAnalysis(BaseModel):
    language:     str
    entry_points: List[EntryPoint]
    dependencies: List[str]
    requires_env: List[str]
    filename:     str


class SaveCodeRequest(BaseModel):
    plugin_id: str
    filename:  str
    content:   str


# ── LLM analysis prompt ───────────────────────────────────────────────────────

ANALYSIS_SYSTEM = """
You are a code analysis assistant. Analyze the provided Python source code and return ONLY a JSON object — no prose, no markdown fences.

Return this exact schema:
{
  "language": "python",
  "entry_points": [
    {
      "fn": "method_name",
      "args": ["arg1", "arg2"],
      "returns": "ReturnType",
      "docstring": "What this method does in one sentence."
    }
  ],
  "dependencies": ["list", "of", "import", "names"],
  "requires_env": ["ENV_VAR_NAME"],
  "filename": "<filename as provided>"
}

Rules:
- Only include public methods (no leading underscore) that are meaningful entry points for an AI agent to call
- Skip __init__, __str__, __repr__ and other dunder methods
- For args, list parameter names only (no types) — exclude 'self'
- For returns, use the return type annotation if present, otherwise infer from docstring or code (e.g. "dict", "list", "str", "None")
- For dependencies, include only top-level import names (e.g. "requests", "json", "os")
- For requires_env, list any os.getenv() or os.environ keys found in the code
- Keep docstrings to one sentence max
- If a class is present, extract its public methods as the entry points
- Limit to the 8 most useful entry points
"""


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/analyze-code", response_model=CodeAnalysis)
async def analyze_code(req: AnalyzeCodeRequest):
    """
    LLM-powered code analysis.
    Extracts entry points, dependencies, and env requirements from uploaded Python source.
    Called by AppOnboarding CodeDropZone after file upload.
    """
    from llm_client import chat_completion

    prompt = (
        f"Filename: {req.filename}\n\n"
        f"Source code:\n```python\n{req.content[:8000]}\n```\n\n"
        "Analyze this code and return the JSON object."
    )

    try:
        raw = await chat_completion(
            prompt,
            system=ANALYSIS_SYSTEM,
            temperature=0.0,
        )
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = json.loads(clean)

        # Ensure filename is set correctly
        data["filename"] = req.filename

        # Validate and return
        return CodeAnalysis(**data)

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"LLM returned invalid JSON: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Save uploaded code file to plugin directory ───────────────────────────────

@router.post("/save-code")
async def save_code(req: SaveCodeRequest):
    """
    Save an uploaded Python file to plugins/{plugin_id}/{filename}.
    Called by the frontend after registration completes.
    The file becomes importable by tools.py wrappers.
    """
    import os
    from pathlib import Path

    # Sanitize filename
    safe_name = Path(req.filename).name
    if not safe_name.endswith(".py"):
        raise HTTPException(status_code=400, detail="Only .py files are accepted")

    plugin_dir = Path(__file__).parent / "plugins" / req.plugin_id
    if not plugin_dir.exists():
        raise HTTPException(status_code=404, detail=f"Plugin '{req.plugin_id}' not scaffolded yet")

    dest = plugin_dir / safe_name
    dest.write_text(req.content, encoding="utf-8")

    return {
        "success":  True,
        "plugin_id": req.plugin_id,
        "saved_to": str(dest),
        "filename": safe_name,
    }