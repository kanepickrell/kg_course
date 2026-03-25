"""
llm_client.py
─────────────────────────────────────────────────────────────────────────────
Unified LLM client for ProtoGraph.

Priority:
  1. If OPENAI_API_KEY is set → use OpenAI (or any OpenAI-compatible API)
  2. Otherwise              → use Ollama at OLLAMA_HOST

Chat completions and embeddings are both handled here so every callsite in
main.py, nl_query_engine.py, and discovery_engine.py can import from one
place and stay unaware of which backend is active.

Environment variables
─────────────────────
  OPENAI_API_KEY          Set this to switch to OpenAI. Unset = use Ollama.
  OPENAI_BASE_URL         Default: https://api.openai.com/v1
                          Override to use any OpenAI-compatible endpoint
                          (Azure, Together, Groq, local vLLM, etc.)
  OPENAI_MODEL            Chat model to use.  Default: gpt-4o-mini
  OPENAI_EMBED_MODEL      Embed model to use. Default: text-embedding-3-small

  OLLAMA_HOST             Default: http://10.10.80.99:4001
  OLLAMA_MODEL            Default: gpt-oss:120b
  OLLAMA_EMBED_MODEL      Default: nomic-embed-text:latest

Usage
─────
  from llm_client import chat_completion, get_embedding, active_backend, active_model

  # async chat
  reply = await chat_completion("Explain TTPs in one sentence.")

  # sync embedding
  vec = get_embedding("Initial Access technique using spearphishing")

  # health / config
  print(active_backend())   # "openai" | "ollama"
  print(active_model())     # e.g. "gpt-4o-mini" or "llama3.3:70b"
"""

from __future__ import annotations

import os
from dotenv import load_dotenv
load_dotenv()
from dotenv import load_dotenv
load_dotenv()
from typing import List, Optional

import httpx

# ── Config ─────────────────────────────────────────────────────────────────

OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL   = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL      = os.getenv("OPENAI_MODEL",       "gpt-4o-mini")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

OLLAMA_HOST       = os.getenv("OLLAMA_HOST",        "http://10.10.80.99:4001")
OLLAMA_MODEL      = os.getenv("OLLAMA_MODEL",        "gpt-oss:120b")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest")

# ── Backend selection ───────────────────────────────────────────────────────

def active_backend() -> str:
    """Returns 'openai' if OPENAI_API_KEY is set, otherwise 'ollama'."""
    return "openai" if OPENAI_API_KEY else "ollama"

def active_model() -> str:
    return OPENAI_MODEL if active_backend() == "openai" else OLLAMA_MODEL

def active_embed_model() -> str:
    return OPENAI_EMBED_MODEL if active_backend() == "openai" else OLLAMA_EMBED_MODEL

def backend_info() -> dict:
    backend = active_backend()
    return {
        "backend":     backend,
        "chat_model":  active_model(),
        "embed_model": active_embed_model(),
        "base_url":    OPENAI_BASE_URL if backend == "openai" else OLLAMA_HOST,
    }

# ── Chat completions ────────────────────────────────────────────────────────

async def chat_completion(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.1,
    timeout: float = 120.0,
) -> str:
    """
    Send a chat completion request. Returns the assistant's reply as a string.
    Raises on HTTP errors — callers should catch and handle gracefully.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    if active_backend() == "openai":
        return await _openai_chat(messages, model=model or OPENAI_MODEL,
                                   temperature=temperature, timeout=timeout)
    else:
        return await _ollama_chat(messages, model=model or OLLAMA_MODEL,
                                   temperature=temperature, timeout=timeout)


async def _openai_chat(
    messages: list,
    model: str,
    temperature: float,
    timeout: float,
) -> str:
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers=headers,
            json={"model": model, "messages": messages, "temperature": temperature},
        )
    if res.status_code != 200:
        raise Exception(f"OpenAI chat returned {res.status_code}: {res.text[:300]}")
    return res.json()["choices"][0]["message"]["content"].strip()


async def _ollama_chat(
    messages: list,
    model: str,
    temperature: float,
    timeout: float,
) -> str:
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.post(
            f"{OLLAMA_HOST}/v1/chat/completions",
            json={"model": model, "messages": messages, "temperature": temperature},
        )
    if res.status_code != 200:
        raise Exception(f"Ollama chat returned {res.status_code}: {res.text[:300]}")
    return res.json()["choices"][0]["message"]["content"].strip()


# ── Sync chat (for main.py /chat endpoint which is sync) ───────────────────

def chat_completion_sync(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.1,
    timeout: float = 60.0,
) -> str:
    """Synchronous wrapper around chat_completion for non-async callsites."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    if active_backend() == "openai":
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        res = httpx.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers=headers,
            json={"model": model or OPENAI_MODEL, "messages": messages, "temperature": temperature},
            timeout=timeout,
        )
        if res.status_code != 200:
            raise Exception(f"OpenAI chat returned {res.status_code}: {res.text[:300]}")
        return res.json()["choices"][0]["message"]["content"].strip()
    else:
        # Fall back to ollama SDK if available, else httpx
        try:
            import ollama as _ollama
            client = _ollama.Client(host=OLLAMA_HOST)
            response = client.chat(
                model=model or OLLAMA_MODEL,
                messages=messages,
            )
            return response["message"]["content"]
        except Exception:
            res = httpx.post(
                f"{OLLAMA_HOST}/v1/chat/completions",
                json={"model": model or OLLAMA_MODEL, "messages": messages, "temperature": temperature},
                timeout=timeout,
            )
            if res.status_code != 200:
                raise Exception(f"Ollama chat returned {res.status_code}: {res.text[:300]}")
            return res.json()["choices"][0]["message"]["content"].strip()


# ── Embeddings ──────────────────────────────────────────────────────────────

def get_embedding(text: str, *, model: Optional[str] = None, timeout: float = 30.0) -> Optional[List[float]]:
    """
    Get an embedding vector for text. Returns None on failure (callers
    gracefully degrade to non-embedding fallbacks when None is returned).
    """
    try:
        if active_backend() == "openai":
            return _openai_embed(text, model=model or OPENAI_EMBED_MODEL, timeout=timeout)
        else:
            return _ollama_embed(text, model=model or OLLAMA_EMBED_MODEL, timeout=timeout)
    except Exception as e:
        print(f"⚠️  Embedding error ({active_backend()}): {e}")
        return None


def _openai_embed(text: str, model: str, timeout: float) -> Optional[List[float]]:
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    res = httpx.post(
        f"{OPENAI_BASE_URL}/embeddings",
        headers=headers,
        json={"model": model, "input": text[:8191]},  # OpenAI token limit
        timeout=timeout,
    )
    if res.status_code != 200:
        raise Exception(f"OpenAI embeddings returned {res.status_code}: {res.text[:200]}")
    return res.json()["data"][0]["embedding"]


def _ollama_embed(text: str, model: str, timeout: float) -> Optional[List[float]]:
    res = httpx.post(
        f"{OLLAMA_HOST}/api/embeddings",
        json={"model": model, "prompt": text[:512]},
        timeout=timeout,
    )
    if res.status_code != 200:
        raise Exception(f"Ollama embeddings returned {res.status_code}: {res.text[:200]}")
    data = res.json()
    return data.get("embedding") or data.get("embeddings", [None])[0]


# ── Health check ────────────────────────────────────────────────────────────

def health_check() -> dict:
    """
    Quick reachability test. Returns status dict suitable for /health endpoint.
    Does NOT raise — always returns a dict.
    """
    info = backend_info()
    try:
        if active_backend() == "openai":
            # Minimal models list call — fast and doesn't consume tokens
            res = httpx.get(
                f"{OPENAI_BASE_URL}/models",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                timeout=8.0,
            )
            info["reachable"] = res.status_code == 200
            info["status"]    = "ok" if res.status_code == 200 else f"http_{res.status_code}"
        else:
            res = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=5.0)
            info["reachable"] = res.status_code == 200
            info["status"]    = "ok" if res.status_code == 200 else f"http_{res.status_code}"
            if res.status_code == 200:
                models = [m["name"] for m in res.json().get("models", [])]
                info["available_models"] = models
    except Exception as e:
        info["reachable"] = False
        info["status"]    = f"unreachable: {e}"
    return info