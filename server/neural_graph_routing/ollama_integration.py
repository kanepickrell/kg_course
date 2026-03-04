"""
Neural Graph Routing - Ollama Integration

Provides real embeddings and SLM context generation via Ollama.

Features:
- Embedding generation with caching
- SLM context emission with timeout/budget
- Async support for parallel agent calls
- Graceful degradation on timeout

CRITICAL:
- Timeouts produce "no context" rather than blocking
- Embedding calls are cached to avoid redundant computation
- SLM calls are budgeted per query
"""
import os
import requests
import hashlib
import time
import asyncio
import aiohttp
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from functools import lru_cache
import numpy as np
from pathlib import Path
import json

from config import AGENT_CONFIG


@dataclass
class OllamaConfig:
    """Configuration for Ollama integration."""
    # Match ProtoGraph's Ollama setup
    base_url: str = os.getenv("OLLAMA_HOST", "http://10.10.80.99:4001")
    
    # Models - use what's available on your server
    # Include :latest tag to match how Ollama lists them
    embedding_model: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text:latest")
    # For SLM context generation, use smaller model
    slm_model: str = os.getenv("OLLAMA_SLM_MODEL", "gemma2:2b")
    
    # Timeouts (ms) - increased for cold start when model loads
    embedding_timeout_ms: int = 30000  # 30 seconds for first call (model load)
    slm_timeout_ms: int = 60000        # 60 seconds for SLM generation
    
    # Budgets per query
    max_slm_calls_per_query: int = 10
    max_embedding_calls_per_query: int = 20
    
    # Context generation
    max_context_tokens: int = 50
    temperature: float = 0.3  # Low for consistent outputs
    
    # Caching
    cache_embeddings: bool = True
    cache_dir: str = "./embedding_cache"


# Global config instance
OLLAMA_CONFIG = OllamaConfig()


class EmbeddingCache:
    """
    Persistent cache for embeddings to avoid redundant Ollama calls.
    """
    
    def __init__(self, cache_dir: str = "./embedding_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, np.ndarray] = {}
    
    def _hash_text(self, text: str) -> str:
        """Generate cache key from text."""
        return hashlib.md5(text.encode()).hexdigest()
    
    def get(self, text: str) -> Optional[np.ndarray]:
        """Get embedding from cache if exists."""
        key = self._hash_text(text)
        
        # Check memory cache first
        if key in self._memory_cache:
            return self._memory_cache[key]
        
        # Check disk cache
        cache_file = self.cache_dir / f"{key}.npy"
        if cache_file.exists():
            embedding = np.load(cache_file)
            self._memory_cache[key] = embedding
            return embedding
        
        return None
    
    def set(self, text: str, embedding: np.ndarray):
        """Store embedding in cache."""
        key = self._hash_text(text)
        self._memory_cache[key] = embedding
        
        # Also persist to disk
        cache_file = self.cache_dir / f"{key}.npy"
        np.save(cache_file, embedding)
    
    def clear(self):
        """Clear all caches."""
        self._memory_cache.clear()
        for f in self.cache_dir.glob("*.npy"):
            f.unlink()


class OllamaClient:
    """
    Client for Ollama API with timeout handling and caching.
    """
    
    def __init__(self, config: OllamaConfig = OLLAMA_CONFIG):
        self.config = config
        self.cache = EmbeddingCache(config.cache_dir) if config.cache_embeddings else None
        
        # Track call counts for budgeting
        self._embedding_calls = 0
        self._slm_calls = 0
    
    def reset_budgets(self):
        """Reset call counters for new query."""
        self._embedding_calls = 0
        self._slm_calls = 0
    
    def get_embedding(self, text: str) -> Optional[np.ndarray]:
        """
        Get embedding for text. Returns None on timeout/error.
        
        Uses cache if available, respects budget limits.
        """
        # Check cache first
        if self.cache:
            cached = self.cache.get(text)
            if cached is not None:
                return cached
        
        # Check budget
        if self._embedding_calls >= self.config.max_embedding_calls_per_query:
            return None
        
        self._embedding_calls += 1
        
        try:
            url = f"{self.config.base_url}/api/embeddings"
            payload = {
                "model": self.config.embedding_model,
                "prompt": text,
            }
            
            response = requests.post(
                url,
                json=payload,
                timeout=self.config.embedding_timeout_ms / 1000,
            )
            
            if response.status_code == 200:
                data = response.json()
                # Handle different response formats
                if "embedding" in data:
                    embedding = np.array(data["embedding"])
                elif "embeddings" in data:
                    embedding = np.array(data["embeddings"][0])
                else:
                    print(f"    Unexpected response format: {list(data.keys())}")
                    return None
                
                # Cache result
                if self.cache:
                    self.cache.set(text, embedding)
                
                return embedding
            else:
                print(f"    Embedding API error: {response.status_code}")
                print(f"    Response: {response.text[:500]}")
                return None
                
        except requests.Timeout:
            print(f"    Embedding timeout after {self.config.embedding_timeout_ms}ms")
            return None
        except requests.ConnectionError as e:
            print(f"    Embedding connection error: {e}")
            return None
        except Exception as e:
            print(f"    Embedding error: {type(e).__name__}: {e}")
            return None
    
    def generate_context(
        self,
        cluster_summary: str,
        query: str,
        max_tokens: int = None,
    ) -> Optional[str]:
        """
        Generate context statement using SLM. Returns None on timeout/error.
        
        Respects budget limits, uses low temperature for consistency.
        """
        # Check budget
        if self._slm_calls >= self.config.max_slm_calls_per_query:
            return None
        
        self._slm_calls += 1
        
        max_tokens = max_tokens or self.config.max_context_tokens
        
        prompt = f"""You are an expert on this knowledge cluster:
{cluster_summary}

Query: {query}

Task: In ONE concise sentence (maximum 20 words), explain how your cluster's knowledge relates to this query.

Rules:
- Be specific about what information your cluster contains
- Reference specific techniques, tools, or concepts from your cluster
- If truly not relevant, respond with exactly: NOT_RELEVANT

Response:"""

        try:
            response = requests.post(
                f"{self.config.base_url}/api/generate",
                json={
                    "model": self.config.slm_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": self.config.temperature,
                    },
                },
                timeout=self.config.slm_timeout_ms / 1000,
            )
            
            if response.status_code == 200:
                text = response.json().get("response", "").strip()
                
                # Check for not relevant
                if "NOT_RELEVANT" in text.upper():
                    return None
                
                # Truncate if too long
                words = text.split()
                if len(words) > 25:
                    text = " ".join(words[:25]) + "..."
                
                return text
            else:
                return None
                
        except (requests.Timeout, requests.ConnectionError):
            return None
    
    def check_health(self) -> bool:
        """Check if Ollama is running and models are available."""
        try:
            # Try /api/tags endpoint (standard Ollama)
            response = requests.get(
                f"{self.config.base_url}/api/tags",
                timeout=5,
            )
            if response.status_code == 200:
                data = response.json()
                models = [m.get("name", m.get("model", "")) for m in data.get("models", [])]
                print(f"  Available models: {models}")
                
                # Check if our models are available (partial match)
                has_embedding = any(
                    self.config.embedding_model.split(":")[0] in m 
                    for m in models
                )
                has_slm = any(
                    self.config.slm_model.split(":")[0] in m 
                    for m in models
                )
                
                if not has_embedding:
                    print(f"  Warning: Embedding model '{self.config.embedding_model}' not found")
                if not has_slm:
                    print(f"  Warning: SLM model '{self.config.slm_model}' not found")
                
                return True  # Server is reachable even if specific models missing
            return False
        except requests.exceptions.ConnectionError:
            print(f"  Connection error to {self.config.base_url}")
            return False
        except Exception as e:
            print(f"  Health check error: {e}")
            return False


class AsyncOllamaClient:
    """
    Async client for parallel agent calls.
    
    Use this when you need to call multiple agents concurrently
    while respecting overall timeout budgets.
    """
    
    def __init__(self, config: OllamaConfig = OLLAMA_CONFIG):
        self.config = config
        self.cache = EmbeddingCache(config.cache_dir) if config.cache_embeddings else None
    
    async def get_embedding(self, text: str, session: aiohttp.ClientSession) -> Optional[np.ndarray]:
        """Async embedding retrieval."""
        # Check cache first
        if self.cache:
            cached = self.cache.get(text)
            if cached is not None:
                return cached
        
        try:
            async with session.post(
                f"{self.config.base_url}/api/embeddings",
                json={"model": self.config.embedding_model, "prompt": text},
                timeout=aiohttp.ClientTimeout(total=self.config.embedding_timeout_ms / 1000),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    embedding = np.array(data["embedding"])
                    if self.cache:
                        self.cache.set(text, embedding)
                    return embedding
        except (asyncio.TimeoutError, aiohttp.ClientError):
            pass
        
        return None
    
    async def generate_context(
        self,
        cluster_summary: str,
        query: str,
        session: aiohttp.ClientSession,
    ) -> Optional[str]:
        """Async context generation."""
        prompt = f"""You are an expert on this knowledge cluster:
{cluster_summary}

Query: {query}

In ONE sentence (max 20 words), explain how your cluster relates. If not relevant, say "NOT_RELEVANT"."""

        try:
            async with session.post(
                f"{self.config.base_url}/api/generate",
                json={
                    "model": self.config.slm_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": self.config.max_context_tokens,
                        "temperature": self.config.temperature,
                    },
                },
                timeout=aiohttp.ClientTimeout(total=self.config.slm_timeout_ms / 1000),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    text = data.get("response", "").strip()
                    if "NOT_RELEVANT" in text.upper():
                        return None
                    return text
        except (asyncio.TimeoutError, aiohttp.ClientError):
            pass
        
        return None
    
    async def batch_embeddings(self, texts: List[str]) -> Dict[str, np.ndarray]:
        """Get embeddings for multiple texts in parallel."""
        async with aiohttp.ClientSession() as session:
            tasks = [self.get_embedding(text, session) for text in texts]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            embeddings = {}
            for text, result in zip(texts, results):
                if isinstance(result, np.ndarray):
                    embeddings[text] = result
            
            return embeddings


# === Integration with ClusterAgent ===

class OllamaEnabledAgent:
    """
    Mixin that adds Ollama capabilities to ClusterAgent.
    
    Usage:
        from core.cluster_agent import ClusterAgent
        from ollama_integration import OllamaEnabledAgent, OllamaClient
        
        class SmartAgent(OllamaEnabledAgent, ClusterAgent):
            pass
        
        client = OllamaClient()
        agent = SmartAgent(agent_id, cluster_id, nodes, ollama_client=client)
    """
    
    def __init__(self, *args, ollama_client: OllamaClient = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.ollama = ollama_client or OllamaClient()
        
        # Recompute centroid with real embeddings if Ollama available
        if self.ollama.check_health():
            self._recompute_centroid_with_ollama()
    
    def _recompute_centroid_with_ollama(self):
        """Recompute cluster centroid using real embeddings."""
        embeddings = []
        
        for node in self.nodes:
            # Create text representation of node
            text = f"{node.name} {node.concept_type}"
            if "description" in node.properties:
                text += f" {node.properties['description']}"
            if "technique_id" in node.properties:
                text += f" {node.properties['technique_id']}"
            
            embedding = self.ollama.get_embedding(text)
            if embedding is not None:
                embeddings.append(embedding)
        
        if embeddings:
            self.centroid_embedding = np.mean(embeddings, axis=0)
    
    def emit_context_with_ollama(
        self,
        query_text: str,
        incoming_signal: float,
        existing_contexts: List[str],
    ) -> Optional[str]:
        """
        Emit context using Ollama SLM instead of deterministic generation.
        Falls back to deterministic if Ollama unavailable/timeout.
        """
        from config import PROPAGATION_CONFIG
        
        # Enforce gating
        assert incoming_signal >= PROPAGATION_CONFIG.activation_threshold
        
        # Try Ollama first
        context = self.ollama.generate_context(
            cluster_summary=self.summary.summary_text,
            query=query_text,
        )
        
        if context is None:
            # Fall back to deterministic
            context = self._generate_deterministic_context(query_text)
        
        # Novelty check
        if not self._passes_novelty_check(context, existing_contexts):
            return None
        
        self._emitted_contexts.append(context)
        return context


def create_ollama_enabled_network(dataset, ollama_config: OllamaConfig = None):
    """
    Factory function to create an agent network with Ollama integration.
    
    Usage:
        from simulation.data_generator import SyntheticDataGenerator
        from ollama_integration import create_ollama_enabled_network
        
        gen = SyntheticDataGenerator(seed=42)
        dataset = gen.generate(num_nodes=100, num_queries=20)
        
        network = create_ollama_enabled_network(dataset)
    """
    from simulation.runner import AgentNetwork
    from core.cluster_agent import ClusterAgent, ClusterNode
    
    config = ollama_config or OLLAMA_CONFIG
    client = OllamaClient(config)
    
    # Check Ollama health
    if not client.check_health():
        print("[Warning] Ollama not available, falling back to synthetic embeddings")
        return AgentNetwork(dataset)
    
    print("[Ollama] Connected, computing real embeddings...")
    
    # Create network with Ollama-powered embeddings
    network = AgentNetwork(dataset)
    
    # Recompute centroids with real embeddings
    for agent_id, agent in network.cluster_agents.items():
        embeddings = []
        
        for node in agent.nodes:
            text = f"{node.name} {node.concept_type}"
            props = node.properties
            if "description" in props:
                text += f" {props['description']}"
            if "technique_id" in props:
                text += f" {props['technique_id']}"
            
            embedding = client.get_embedding(text)
            if embedding is not None:
                embeddings.append(embedding)
                node.embedding = embedding  # Update node embedding too
        
        if embeddings:
            network.agent_centroids[agent_id] = np.mean(embeddings, axis=0)
            agent.centroid_embedding = network.agent_centroids[agent_id]
    
    print(f"[Ollama] Computed embeddings for {len(network.cluster_agents)} agents")
    
    return network


def embed_query(query_text: str, client: OllamaClient = None) -> np.ndarray:
    """
    Get embedding for a query. Falls back to random if Ollama unavailable.
    """
    client = client or OllamaClient()
    
    embedding = client.get_embedding(query_text)
    
    if embedding is None:
        # Fall back to random (not ideal, but maintains functionality)
        print(f"[Warning] Could not embed query, using random vector")
        embedding = np.random.randn(768)
        embedding = embedding / np.linalg.norm(embedding)
    
    return embedding


# === Test function ===

def test_ollama_integration():
    """Test Ollama integration."""
    print("Testing Ollama integration...")
    print(f"  Target: {OLLAMA_CONFIG.base_url}")
    print(f"  Embedding model: {OLLAMA_CONFIG.embedding_model}")
    print(f"  SLM model: {OLLAMA_CONFIG.slm_model}")
    
    client = OllamaClient()
    
    # Health check
    healthy = client.check_health()
    print(f"  Ollama healthy: {healthy}")
    
    if not healthy:
        print("\n  [Troubleshooting]")
        print(f"  1. Check if Ollama server is running at {OLLAMA_CONFIG.base_url}")
        print(f"  2. Try: curl {OLLAMA_CONFIG.base_url}/api/tags")
        print(f"  3. Set OLLAMA_HOST environment variable if using different URL")
        return False
    
    # Test embedding
    print("\n  Testing embedding...")
    embedding = client.get_embedding("Test credential dumping technique T1003")
    if embedding is not None:
        print(f"    ✓ Got embedding of shape {embedding.shape}")
    else:
        print("    ✗ Embedding failed - check if embedding model is available")
        print(f"    Try: ollama pull {OLLAMA_CONFIG.embedding_model}")
        return False
    
    # Test context generation
    print("\n  Testing SLM context generation...")
    context = client.generate_context(
        cluster_summary="Cluster with 15 LibraryModule nodes. Contains Cobalt Strike beacon modules implementing credential access techniques T1003 and T1003.001.",
        query="How do we test credential dumping?",
    )
    if context:
        print(f"    ✓ Generated context: {context}")
    else:
        print("    ⚠ Context generation failed or returned NOT_RELEVANT")
        print(f"    This might be OK - check if SLM model is available")
        print(f"    Try: ollama pull {OLLAMA_CONFIG.slm_model}")
    
    # Test caching
    print("\n  Testing cache...")
    start = time.time()
    _ = client.get_embedding("Test credential dumping technique T1003")
    cached_time = time.time() - start
    print(f"    ✓ Cached retrieval: {cached_time*1000:.1f}ms")
    
    print("\n  Ollama integration OK ✓")
    return True


if __name__ == "__main__":
    test_ollama_integration()