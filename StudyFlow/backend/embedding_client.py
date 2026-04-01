"""
Gemini Embedding Client for StudyFlow
Generates vector embeddings using Google's text-embedding-004 (768 dimensions).
Redis-cached to avoid duplicate API calls for identical queries.
"""

import os
import json
import hashlib
import time
import requests
from typing import List
from StudyFlow.logging_utils import debug_log

GEMINI_EMBED_URL = "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent"
GEMINI_BATCH_URL = "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:batchEmbedContents"
EMBEDDING_DIMENSIONS = 768

def _get_gemini_key():
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

# Redis cache for embeddings
_embedding_cache = None
EMBEDDING_CACHE_TTL = 86400  # 24 hours


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


def generate_embedding(text: str, model: str = None) -> List[float]:
    """
    Generate a single embedding for text using Gemini. Cached in Redis for 24h.
    Retries with exponential backoff on rate limit.
    """
    try:
        print(f"[EMBEDDING] generate_embedding called with {len(text)} chars", flush=True)
        text = text.replace("\n", " ").strip()
        if not text:
            print("[EMBEDDING] Empty text, returning None", flush=True)
            return None

        # Check Redis cache (use gemini-prefixed key to avoid old OpenAI cache collisions)
        cache_key = "gemb:" + hashlib.md5(text.encode()).hexdigest()
        r = _get_redis()
        if r:
            try:
                cached = r.get(cache_key)
                if cached:
                    debug_log(f"Embedding cache HIT ({len(text)} chars)")
                    return json.loads(cached)
            except:
                pass

        gemini_key = _get_gemini_key()
        if not gemini_key:
            print("[EMBEDDING] No Gemini API key found. GEMINI_API_KEY env var not set.", flush=True)
            return None

        print(f"[EMBEDDING] Calling Gemini API ({len(text)} chars, key={gemini_key[:8]}...)", flush=True)

        # Call Gemini API with retry on rate limit
        embedding = None
        max_retries = 4
        for attempt in range(max_retries):
            try:
                resp = requests.post(
                    f"{GEMINI_EMBED_URL}?key={_get_gemini_key()}",
                    json={
                        "model": "models/text-embedding-004",
                        "content": {"parts": [{"text": text[:2048]}]},
                        "outputDimensionality": EMBEDDING_DIMENSIONS
                    },
                    timeout=10
                )

                if resp.status_code == 429:
                    raise Exception("429 Too Many Requests")

                if resp.status_code != 200:
                    debug_log(f"Gemini embedding error {resp.status_code}: {resp.text[:200]}")
                    return None

                data = resp.json()
                embedding = data.get("embedding", {}).get("values")
                if not embedding:
                    debug_log(f"No embedding in Gemini response: {json.dumps(data)[:200]}")
                    return None
                break

            except Exception as e:
                err_str = str(e)
                if '429' not in err_str and 'rate' not in err_str.lower() and 'Too Many' not in err_str:
                    debug_log(f"Gemini embedding error: {e}")
                    return None
                wait = (2 ** attempt) + 0.5
                debug_log(f"Embedding rate limited, retry {attempt+1}/{max_retries} in {wait}s")
                if attempt < max_retries - 1:
                    time.sleep(wait)
                else:
                    debug_log("Embedding rate limit exhausted all retries")
                    return None

        if not embedding:
            return None

        debug_log(f"Generated Gemini embedding ({len(embedding)} dimensions)")

        # Track cost (Gemini embeddings are free but track for stats)
        try:
            from StudyFlow.backend.cost_tracker import track_ai_call
            track_ai_call("google", "text-embedding-004", "embedding", tokens_estimate=len(text) // 4)
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
        debug_log(f"Error generating embedding: {e}")
        return None


def generate_embeddings_batch(texts: List[str], model: str = None) -> List[List[float]]:
    """
    Generate embeddings for multiple texts using Gemini batch API.
    """
    try:
        cleaned_texts = [text.replace("\n", " ").strip()[:2048] for text in texts if text.strip()]
        if not cleaned_texts:
            debug_log("No valid texts to embed")
            return []

        if not _get_gemini_key():
            debug_log("No Gemini API key configured for embeddings")
            return []

        # Gemini batch supports up to 100 inputs
        batch_size = 100
        all_embeddings = []

        for i in range(0, len(cleaned_texts), batch_size):
            batch = cleaned_texts[i:i + batch_size]

            requests_payload = [
                {
                    "model": "models/text-embedding-004",
                    "content": {"parts": [{"text": t}]},
                    "outputDimensionality": EMBEDDING_DIMENSIONS
                }
                for t in batch
            ]

            resp = requests.post(
                f"{GEMINI_BATCH_URL}?key={_get_gemini_key()}",
                json={"requests": requests_payload},
                timeout=30
            )

            if resp.status_code != 200:
                debug_log(f"Gemini batch embedding error {resp.status_code}: {resp.text[:200]}")
                return []

            data = resp.json()
            batch_embeddings = [
                emb.get("values", [])
                for emb in data.get("embeddings", [])
            ]
            all_embeddings.extend(batch_embeddings)

            # Track cost
            try:
                from StudyFlow.backend.cost_tracker import track_ai_call
                total_chars = sum(len(t) for t in batch)
                track_ai_call("google", "text-embedding-004", "embedding_batch", tokens_estimate=total_chars // 4)
            except:
                pass

            debug_log(f"Generated {len(batch_embeddings)} Gemini embeddings (batch {i//batch_size + 1})")

        return all_embeddings

    except Exception as e:
        debug_log(f"Error generating batch embeddings: {e}")
        return []


def estimate_embedding_cost(text_length: int) -> float:
    """Gemini embeddings are free -- return 0."""
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
