"""
Gemini Embedding Client for StudyFlow
Uses Google's gemini-embedding-2-preview (768 dimensions, multimodal).
Redis-cached to avoid duplicate API calls.
"""

import os
import json
import hashlib
import time
from typing import List
from StudyFlow.logging_utils import debug_log

EMBEDDING_DIMENSIONS = 768
EMBEDDING_MODEL = "gemini-embedding-2-preview"

# Redis cache for embeddings
_embedding_cache = None
EMBEDDING_CACHE_TTL = 86400  # 24 hours

# Lazy-init genai client
_genai_client = None


def _get_client():
    global _genai_client
    if _genai_client is None:
        try:
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not api_key:
                print("[EMBEDDING] No GEMINI_API_KEY env var found", flush=True)
                return None
            _genai_client = genai.Client(api_key=api_key)
            print(f"[EMBEDDING] genai client initialized (key={api_key[:8]}...)", flush=True)
        except ImportError:
            print("[EMBEDDING] google-genai package not installed, falling back to REST", flush=True)
            return None
        except Exception as e:
            print(f"[EMBEDDING] Failed to init genai client: {e}", flush=True)
            return None
    return _genai_client


def _get_redis():
    global _embedding_cache
    if _embedding_cache is None:
        try:
            import redis
            url = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
            _embedding_cache = redis.from_url(url, decode_responses=True)
            _embedding_cache.ping()
        except:
            _embedding_cache = False
    return _embedding_cache if _embedding_cache else None


def _embed_via_sdk(text):
    """Use the google-genai SDK."""
    client = _get_client()
    if not client:
        return None

    try:
        from google.genai import types
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text[:8000],
            config=types.EmbedContentConfig(
                output_dimensionality=EMBEDDING_DIMENSIONS,
                task_type='RETRIEVAL_DOCUMENT'
            )
        )
        values = result.embeddings[0].values
        print(f"[EMBEDDING] SDK success: {len(values)} dims", flush=True)
        return list(values)
    except Exception as e:
        print(f"[EMBEDDING] SDK error: {e}", flush=True)
        return None


def _embed_via_rest(text):
    """Fallback: use REST API directly."""
    import requests as req

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None

    # Try multiple model IDs
    models = [EMBEDDING_MODEL, "text-embedding-005", "embedding-001"]

    for model_name in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1/models/{model_name}:embedContent?key={api_key}"
            resp = req.post(url, json={
                "model": f"models/{model_name}",
                "content": {"parts": [{"text": text[:8000]}]},
                "outputDimensionality": EMBEDDING_DIMENSIONS
            }, timeout=15)

            print(f"[EMBEDDING] REST {model_name}: {resp.status_code}", flush=True)

            if resp.status_code == 404:
                continue  # Try next model

            if resp.status_code != 200:
                print(f"[EMBEDDING] REST error: {resp.text[:200]}", flush=True)
                continue

            data = resp.json()
            values = data.get("embedding", {}).get("values")
            if values:
                print(f"[EMBEDDING] REST success with {model_name}: {len(values)} dims", flush=True)
                return values
        except Exception as e:
            print(f"[EMBEDDING] REST {model_name} exception: {e}", flush=True)
            continue

    return None


def generate_embedding(text: str, model: str = None) -> List[float]:
    """
    Generate a single embedding. Tries SDK first, then REST fallback.
    Cached in Redis for 24h.
    """
    try:
        print(f"[EMBEDDING] generate_embedding called ({len(text)} chars)", flush=True)
        text = text.replace("\n", " ").strip()
        if not text:
            return None

        # Check Redis cache
        cache_key = "gemb:" + hashlib.md5(text.encode()).hexdigest()
        r = _get_redis()
        if r:
            try:
                cached = r.get(cache_key)
                if cached:
                    print(f"[EMBEDDING] Cache HIT", flush=True)
                    return json.loads(cached)
            except:
                pass

        # Try SDK first, then REST
        embedding = _embed_via_sdk(text)
        if not embedding:
            print("[EMBEDDING] SDK failed, trying REST fallback", flush=True)
            embedding = _embed_via_rest(text)

        if not embedding:
            print("[EMBEDDING] All methods failed", flush=True)
            return None

        # Track cost (free but track for stats)
        try:
            from StudyFlow.backend.cost_tracker import track_ai_call
            track_ai_call("google", EMBEDDING_MODEL, "embedding", tokens_estimate=len(text) // 4)
        except:
            pass

        # Cache in Redis
        if r:
            try:
                r.setex(cache_key, EMBEDDING_CACHE_TTL, json.dumps(embedding))
            except:
                pass

        return embedding

    except Exception as e:
        print(f"[EMBEDDING] Fatal error: {e}", flush=True)
        return None


def generate_embeddings_batch(texts: List[str], model: str = None) -> List[List[float]]:
    """Generate embeddings for multiple texts. Falls back to one-by-one if batch fails."""
    try:
        cleaned = [t.replace("\n", " ").strip()[:8000] for t in texts if t.strip()]
        if not cleaned:
            return []

        # Try SDK batch
        client = _get_client()
        if client:
            try:
                from google.genai import types
                all_embeddings = []
                batch_size = 100
                for i in range(0, len(cleaned), batch_size):
                    batch = cleaned[i:i + batch_size]
                    results = client.models.embed_content(
                        model=EMBEDDING_MODEL,
                        contents=batch,
                        config=types.EmbedContentConfig(
                            output_dimensionality=EMBEDDING_DIMENSIONS,
                            task_type='RETRIEVAL_DOCUMENT'
                        )
                    )
                    for emb in results.embeddings:
                        all_embeddings.append(list(emb.values))
                    print(f"[EMBEDDING BATCH] SDK: {len(batch)} done", flush=True)
                return all_embeddings
            except Exception as e:
                print(f"[EMBEDDING BATCH] SDK error: {e}, falling back to one-by-one", flush=True)

        # Fallback: one by one
        embeddings = []
        for t in cleaned:
            emb = generate_embedding(t)
            if emb:
                embeddings.append(emb)
            else:
                embeddings.append([0.0] * EMBEDDING_DIMENSIONS)
            time.sleep(0.05)  # Rate limit respect
        return embeddings

    except Exception as e:
        print(f"[EMBEDDING BATCH] Fatal error: {e}", flush=True)
        return []


def estimate_embedding_cost(text_length: int) -> float:
    """Gemini embeddings are free."""
    return 0.0


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    import math
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)
