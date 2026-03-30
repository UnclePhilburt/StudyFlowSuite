"""
Search Analytics Tracker -- logs every search query to Redis.

Keys:
  search:all:{YYYY-MM-DD}        -- sorted set of {query: count} (all searches)
  search:zero:{YYYY-MM-DD}       -- sorted set of {query: count} (zero-result searches)
  search:volume:{YYYY-MM-DD}     -- integer total search count for the day
  search:all:alltime              -- sorted set of {query: count} (all time)
  search:zero:alltime             -- sorted set of {query: count} (all time zero results)
"""

import os
import redis
from datetime import datetime

_redis = None

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


def track_search(query, result_count, source="browse"):
    """
    Log a search query.

    Args:
        query: the search text
        result_count: number of results returned
        source: 'browse' or 'chat'
    """
    r = _get_redis()
    if not r:
        return

    try:
        query_lower = query.strip().lower()
        if not query_lower:
            return

        day = datetime.utcnow().strftime("%Y-%m-%d")

        pipe = r.pipeline()

        # Track all searches
        pipe.zincrby(f"search:all:{day}", 1, query_lower)
        pipe.zincrby("search:all:alltime", 1, query_lower)

        # Track daily volume
        pipe.incr(f"search:volume:{day}")

        # Track zero-result searches
        if result_count == 0:
            pipe.zincrby(f"search:zero:{day}", 1, query_lower)
            pipe.zincrby("search:zero:alltime", 1, query_lower)

        # Track by source
        pipe.zincrby(f"search:source:{day}", 1, source)

        # Expire daily keys after 90 days
        pipe.expire(f"search:all:{day}", 7776000)
        pipe.expire(f"search:zero:{day}", 7776000)
        pipe.expire(f"search:volume:{day}", 7776000)
        pipe.expire(f"search:source:{day}", 7776000)

        pipe.execute()

    except:
        pass  # Never block the search


def get_search_analytics(days=30):
    """Get search analytics for the admin dashboard."""
    r = _get_redis()
    if not r:
        return None

    try:
        from datetime import timedelta
        now = datetime.utcnow()

        # Daily volume for chart
        dates = []
        daily_volume = []
        for i in range(days, -1, -1):
            d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            dates.append(d)
            vol = r.get(f"search:volume:{d}")
            daily_volume.append(int(vol) if vol else 0)

        # Top searches (all time)
        top_searches = r.zrevrangebyscore("search:all:alltime", "+inf", "-inf", withscores=True, start=0, num=25)

        # Top zero-result searches (all time) -- these are the content gaps
        zero_results = r.zrevrangebyscore("search:zero:alltime", "+inf", "-inf", withscores=True, start=0, num=25)

        # Today's top searches
        today = now.strftime("%Y-%m-%d")
        today_top = r.zrevrangebyscore(f"search:all:{today}", "+inf", "-inf", withscores=True, start=0, num=15)
        today_zero = r.zrevrangebyscore(f"search:zero:{today}", "+inf", "-inf", withscores=True, start=0, num=15)

        # Totals
        total_searches = sum(daily_volume)
        total_today = daily_volume[-1] if daily_volume else 0
        total_7d = sum(daily_volume[-7:])

        return {
            "dates": dates,
            "daily_volume": daily_volume,
            "top_searches": [{"query": q, "count": int(c)} for q, c in top_searches],
            "zero_results": [{"query": q, "count": int(c)} for q, c in zero_results],
            "today_top": [{"query": q, "count": int(c)} for q, c in today_top],
            "today_zero": [{"query": q, "count": int(c)} for q, c in today_zero],
            "summary": {
                "total_30d": total_searches,
                "total_today": total_today,
                "total_7d": total_7d,
                "avg_daily": round(total_searches / max(days, 1), 1)
            }
        }

    except:
        return None
