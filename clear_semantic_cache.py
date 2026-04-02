"""
Clear all semantic cache entries from Redis.

This removes all sem_cache:* keys to ensure no old/wrong answers
are reused for similar questions.
"""

import os
import redis

def clear_semantic_cache():
    """Delete all sem_cache:* keys from Redis."""
    try:
        # Connect to Redis
        redis_url = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        r = redis.from_url(redis_url, decode_responses=True)

        # Test connection
        r.ping()
        print("Connected to Redis successfully")

        # Find all semantic cache keys
        print("\nSearching for semantic cache keys...")
        cache_keys = []

        # Get all sem_cache keys using scan (more efficient than keys())
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match="sem_cache:*", count=100)
            cache_keys.extend(keys)
            if cursor == 0:
                break

        if not cache_keys:
            print("No semantic cache keys found - already clean!")
            return

        print(f"Found {len(cache_keys)} semantic cache keys")

        # Delete all keys
        print("\nDeleting cache keys...")
        deleted_count = 0
        for key in cache_keys:
            r.delete(key)
            deleted_count += 1
            if deleted_count % 100 == 0:
                print(f"  Deleted {deleted_count}/{len(cache_keys)} keys...")

        print(f"\nSuccessfully deleted {deleted_count} semantic cache keys!")
        print("All old cached questions have been removed.")

    except redis.ConnectionError:
        print("ERROR: Could not connect to Redis")
        print("Make sure Redis is running and REDIS_URL/CELERY_BROKER_URL is set correctly")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("SEMANTIC CACHE CLEARING SCRIPT")
    print("=" * 60)
    clear_semantic_cache()
    print("=" * 60)
