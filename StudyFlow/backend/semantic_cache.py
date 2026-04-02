"""
Semantic AI Cache -- caches AI responses by vector similarity.

Instead of exact string matching, compares question embeddings using
cosine similarity. If a new question is >0.95 similar to a cached one,
returns the cached response instantly (~5ms vs ~3000ms from Gemini).

Storage: Redis hash per cached entry, plus a list of all cache keys
per user for iteration.

Keys:
  sem_cache:{user_id}:keys          -- list of cache entry IDs
  sem_cache:{user_id}:{entry_id}    -- hash with: embedding, response, sources, question, timestamp
"""

import os
import json
import math
import time
import hashlib
import redis

_redis = None
SIMILARITY_THRESHOLD = 0.95
MAX_CACHE_ENTRIES = 100  # Per user, keep last 100 Q&A pairs
CACHE_TTL = 86400  # 24 hours

def _get_redis():
    global _redis
    if _redis is None:
        try:
            url = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
            _redis = redis.from_url(url, decode_responses=True)
            _redis.ping()
        except:
            _redis = False
    return _redis if _redis else None


def cosine_similarity(vec1, vec2):
    """Fast cosine similarity between two vectors."""
    dot = sum(a * b for a, b in zip(vec1, vec2))
    mag1 = math.sqrt(sum(a * a for a in vec1))
    mag2 = math.sqrt(sum(b * b for b in vec2))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


def check_semantic_cache(user_id, query_embedding):
    """
    Check if a similar question has been asked before.
    Returns cached response dict or None.

    DISABLED: Always returns None to force fresh AI answers.
    This prevents reusing old/wrong cached answers for similar questions.
    """
    # Semantic caching disabled - always get fresh answers
    return None

    # Original implementation below (disabled):
    # r = _get_redis()
    # if not r:
    #     return None
    #
    # try:
    #     # Get all cache entry keys for this user
    #     keys_key = f"sem_cache:{user_id}:keys"
    #     entry_ids = r.lrange(keys_key, 0, MAX_CACHE_ENTRIES - 1)
    #
    #     if not entry_ids:
    #         return None
    #
    #     best_match = None
    #     best_similarity = 0
    #
    #     for entry_id in entry_ids:
    #         entry_key = f"sem_cache:{user_id}:{entry_id}"
    #         cached_embedding_str = r.hget(entry_key, "embedding")
    #
    #         if not cached_embedding_str:
    #             continue
    #
    #         cached_embedding = json.loads(cached_embedding_str)
    #         similarity = cosine_similarity(query_embedding, cached_embedding)
    #
    #         if similarity > best_similarity:
    #             best_similarity = similarity
    #             best_match = entry_key
    #
    #     if best_similarity >= SIMILARITY_THRESHOLD and best_match:
    #         # Cache hit!
    #         cached = r.hgetall(best_match)
    #         if cached and cached.get("response"):
    #             return {
    #                 "response": cached["response"],
    #                 "sources": json.loads(cached.get("sources", "[]")),
    #                 "cached_question": cached.get("question", ""),
    #                 "similarity": round(best_similarity, 4),
    #                 "cache_hit": True
    #             }
    #
    #     return None
    #
    # except Exception as e:
    #     print(f"Semantic cache check error: {e}")
    #     return None


def store_semantic_cache(user_id, question, query_embedding, response, sources):
    """
    Store a Q&A pair in the semantic cache.

    DISABLED: Does nothing since check_semantic_cache() is disabled.
    No point storing answers that will never be retrieved.
    """
    # Semantic caching disabled - don't store anything
    return

    # Original implementation below (disabled):
    # r = _get_redis()
    # if not r:
    #     return
    #
    # try:
    #     entry_id = hashlib.md5(f"{question}:{time.time()}".encode()).hexdigest()[:12]
    #     entry_key = f"sem_cache:{user_id}:{entry_id}"
    #     keys_key = f"sem_cache:{user_id}:keys"
    #
    #     # Store the entry
    #     r.hset(entry_key, mapping={
    #         "question": question,
    #         "embedding": json.dumps(query_embedding),
    #         "response": response,
    #         "sources": json.dumps(sources or []),
    #         "timestamp": str(time.time())
    #     })
    #     r.expire(entry_key, CACHE_TTL)
    #
    #     # Add to the keys list (most recent first)
    #     r.lpush(keys_key, entry_id)
    #     r.ltrim(keys_key, 0, MAX_CACHE_ENTRIES - 1)  # Keep only last N
    #     r.expire(keys_key, CACHE_TTL)
    #
    # except Exception as e:
    #     print(f"Semantic cache store error: {e}")
