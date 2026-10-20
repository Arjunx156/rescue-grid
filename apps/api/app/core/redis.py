from __future__ import annotations

from functools import lru_cache

from redis.asyncio import Redis

from app.core.settings import get_settings

STREAM_RAW = "stream:intake:raw"
STREAM_EXTRACTED = "stream:intake:extracted"
STREAM_CASES = "stream:cases:updated"
STREAM_DISPATCH = "stream:dispatch:trigger"
STREAM_MAXLEN = 100_000


def disaster_channel(disaster_id: object) -> str:
    return f"ws:disaster:{disaster_id}"


def team_channel(team_id: object) -> str:
    return f"ws:team:{team_id}"


@lru_cache
def redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True, health_check_interval=30)


async def rate_limited(key: str, limit: int, window_s: int) -> bool:
    """Fixed-window limiter; True means the caller is over the limit."""
    r = redis()
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, window_s)
    return count > limit
