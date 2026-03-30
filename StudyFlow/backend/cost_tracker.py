"""
AI Cost Tracker -- logs every API call to Redis with estimated cost.
Uses Redis sorted sets keyed by date for easy aggregation.

Keys:
  ai_cost:daily:{YYYY-MM-DD}  -- sorted set of {provider:endpoint: total_cost}
  ai_cost:calls:{YYYY-MM-DD}  -- sorted set of {provider:endpoint: call_count}
  ai_cost:monthly:{YYYY-MM}   -- total cost for the month
"""

import os
import redis
from datetime import datetime

# Estimated costs per unit (USD)
COST_TABLE = {
    # OpenAI
    "openai:embedding": 0.00002,       # $0.02 per 1M tokens, ~1000 tokens per call
    "openai:gpt-4o": 0.005,            # ~$5/1M input + $15/1M output, ~500 tokens avg
    "openai:gpt-4o-mini": 0.0003,      # ~$0.15/1M input + $0.60/1M output
    "openai:gpt-3.5-turbo": 0.0005,    # ~$0.50/1M input + $1.50/1M output

    # Gemini
    "gemini:flash": 0.0001,            # Very cheap, ~$0.075/1M input
    "gemini:flash-lite": 0.00005,      # Even cheaper
    "gemini:pro": 0.001,               # $1.25/1M input

    # Anthropic
    "anthropic:claude-sonnet": 0.006,   # $3/1M input + $15/1M output
    "anthropic:claude-haiku": 0.0005,   # $0.25/1M input + $1.25/1M output

    # Cohere
    "cohere:command-r": 0.0005,         # $0.50/1M tokens
    "cohere:command-r-plus": 0.003,     # $3/1M input
}

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


def track_ai_call(provider, model, endpoint="default", tokens_estimate=None):
    """
    Log an AI API call with estimated cost.

    Args:
        provider: 'openai', 'gemini', 'anthropic', 'cohere'
        model: model name for cost lookup
        endpoint: which feature triggered this (e.g. 'embedding', 'chat', 'verification')
        tokens_estimate: optional token count for more accurate cost
    """
    r = _get_redis()
    if not r:
        return

    try:
        # Determine cost
        cost_key = f"{provider}:{model}"
        base_cost = COST_TABLE.get(cost_key, 0.001)  # Default $0.001 if unknown

        if tokens_estimate:
            # Adjust cost based on actual tokens
            cost = (tokens_estimate / 1000) * base_cost
        else:
            cost = base_cost

        now = datetime.utcnow()
        day_key = now.strftime("%Y-%m-%d")
        month_key = now.strftime("%Y-%m")
        member = f"{provider}:{endpoint}"

        pipe = r.pipeline()

        # Daily cost by provider:endpoint
        pipe.zincrby(f"ai_cost:daily:{day_key}", cost, member)
        # Daily call count
        pipe.zincrby(f"ai_cost:calls:{day_key}", 1, member)
        # Monthly total
        pipe.incrbyfloat(f"ai_cost:monthly:{month_key}", cost)
        # Daily total (for chart)
        pipe.incrbyfloat(f"ai_cost:daytotal:{day_key}", cost)

        # Expire keys after 90 days
        pipe.expire(f"ai_cost:daily:{day_key}", 7776000)
        pipe.expire(f"ai_cost:calls:{day_key}", 7776000)
        pipe.expire(f"ai_cost:monthly:{month_key}", 7776000)
        pipe.expire(f"ai_cost:daytotal:{day_key}", 7776000)

        pipe.execute()

    except Exception as e:
        pass  # Never block the actual API call


def get_cost_summary(days=30):
    """Get cost data for the admin dashboard."""
    r = _get_redis()
    if not r:
        return None

    try:
        from datetime import timedelta
        now = datetime.utcnow()

        # Daily totals for chart
        dates = []
        daily_totals = []
        for i in range(days, -1, -1):
            d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            dates.append(d)
            val = r.get(f"ai_cost:daytotal:{d}")
            daily_totals.append(round(float(val), 4) if val else 0)

        # Today's breakdown by provider:endpoint
        today = now.strftime("%Y-%m-%d")
        today_breakdown = r.zrevrangebyscore(f"ai_cost:daily:{today}", "+inf", "-inf", withscores=True)
        today_calls = r.zrevrangebyscore(f"ai_cost:calls:{today}", "+inf", "-inf", withscores=True)

        # This month total
        month_key = now.strftime("%Y-%m")
        month_total = r.get(f"ai_cost:monthly:{month_key}")

        # Last month total
        last_month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        last_month_total = r.get(f"ai_cost:monthly:{last_month}")

        # 7-day total
        seven_day_total = sum(daily_totals[-7:])

        # Aggregate by provider across last 30 days
        provider_totals = {}
        for i in range(days, -1, -1):
            d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            entries = r.zrangebyscore(f"ai_cost:daily:{d}", "-inf", "+inf", withscores=True)
            for member, score in entries:
                provider = member.split(":")[0]
                provider_totals[provider] = provider_totals.get(provider, 0) + score

        return {
            "dates": dates,
            "daily_totals": daily_totals,
            "month_total": round(float(month_total), 4) if month_total else 0,
            "last_month_total": round(float(last_month_total), 4) if last_month_total else 0,
            "seven_day_total": round(seven_day_total, 4),
            "today_breakdown": [{"name": b[0], "cost": round(b[1], 4)} for b in today_breakdown],
            "today_calls": [{"name": c[0], "count": int(c[1])} for c in today_calls],
            "provider_totals": [{"provider": k, "cost": round(v, 4)} for k, v in sorted(provider_totals.items(), key=lambda x: -x[1])]
        }

    except Exception as e:
        return None
