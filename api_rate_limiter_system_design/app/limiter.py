"""Redis-backed distributed token bucket rate limiter."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import redis.asyncio as redis


# KEYS[1] = bucket key
# ARGV: capacity, refill tokens/second, current time (seconds), TTL seconds
# One atomic script prevents concurrent requests from overspending tokens.
TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])

local values = redis.call('HMGET', key, 'tokens', 'updated_at')
local tokens = tonumber(values[1])
local updated_at = tonumber(values[2])

if tokens == nil then
    tokens = capacity
    updated_at = now
end

local elapsed = math.max(0, now - updated_at)
tokens = math.min(capacity, tokens + elapsed * refill_rate)

local allowed = 0
local retry_after = 0
if tokens >= 1 then
    allowed = 1
    tokens = tokens - 1
else
    retry_after = math.ceil((1 - tokens) / refill_rate)
end

redis.call('HSET', key, 'tokens', tokens, 'updated_at', now)
redis.call('EXPIRE', key, ttl)

local remaining = math.floor(tokens)
local reset_after = math.ceil((capacity - tokens) / refill_rate)
return {allowed, remaining, retry_after, reset_after}
"""


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: int
    reset_after: int


def token_bucket_decision(
    tokens: float,
    updated_at: float,
    now: float,
    capacity: float,
    refill_rate: float,
) -> tuple[float, float, bool, int]:
    """Pure helper used in tests; returns tokens, timestamp, allowed, retry."""
    if refill_rate <= 0:
        raise ValueError("refill_rate must be positive")
    elapsed = max(0.0, now - updated_at)
    current = min(capacity, tokens + elapsed * refill_rate)
    allowed = current >= 1.0
    retry_after = 0 if allowed else math.ceil((1.0 - current) / refill_rate)
    if allowed:
        current -= 1.0
    return current, now, allowed, retry_after


class RedisTokenBucket:
    def __init__(
        self,
        client: redis.Redis,
        capacity: int = 5,
        refill_rate: float = 5 / 60,
        key_prefix: str = "rate_limit",
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        if refill_rate <= 0:
            raise ValueError("refill_rate must be positive")
        self.client = client
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.key_prefix = key_prefix

    async def check(self, client_id: str) -> RateLimitResult:
        now = time.time()
        ttl = max(1, math.ceil(self.capacity / self.refill_rate) * 2)
        key = f"{self.key_prefix}:{client_id}"
        result = await self.client.eval(
            TOKEN_BUCKET_LUA,
            1,
            key,
            self.capacity,
            self.refill_rate,
            now,
            ttl,
        )
        return RateLimitResult(
            allowed=bool(int(result[0])),
            remaining=int(result[1]),
            retry_after=int(result[2]),
            reset_after=int(result[3]),
        )
