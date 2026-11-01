"""FastAPI demo exposing a Redis-backed rate-limited endpoint."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response

from app.limiter import RedisTokenBucket

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CAPACITY = int(os.getenv("RATE_LIMIT_CAPACITY", "5"))
REFILL_RATE = int(os.getenv("RATE_LIMIT_REFILL_RATE", "5")) / int(
    os.getenv("RATE_LIMIT_PERIOD_SECONDS", "60")
)
KEY_PREFIX = os.getenv("RATE_LIMIT_KEY_PREFIX", "rate_limit")


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = redis.from_url(REDIS_URL, decode_responses=True)
    app.state.redis = client
    app.state.limiter = RedisTokenBucket(
        client, capacity=CAPACITY, refill_rate=REFILL_RATE, key_prefix=KEY_PREFIX
    )
    yield
    await client.aclose()


app = FastAPI(
    title="API Rate Limiter Demo",
    description="FastAPI + Redis distributed Token Bucket example.",
    version="1.0.0",
    lifespan=lifespan,
)


async def enforce_rate_limit(
    request: Request,
    response: Response,
    x_client_id: str | None = Header(default=None, alias="X-Client-ID"),
) -> None:
    # Demo fallback only. In production, prefer a verified user/API-key identity.
    client_id = x_client_id or (request.client.host if request.client else "unknown")
    result = await request.app.state.limiter.check(client_id)

    response.headers["X-RateLimit-Limit"] = str(CAPACITY)
    response.headers["X-RateLimit-Remaining"] = str(result.remaining)
    response.headers["X-RateLimit-Reset"] = str(result.reset_after)

    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later.",
            headers={
                "Retry-After": str(max(1, result.retry_after)),
                "X-RateLimit-Limit": str(CAPACITY),
                "X-RateLimit-Remaining": "0",
            },
        )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/demo", dependencies=[Depends(enforce_rate_limit)])
async def demo():
    return {"message": "Request allowed", "service": "protected-demo-endpoint"}
