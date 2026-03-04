"""
Async Redis client — thin singleton wrapper around redis.asyncio.

Also provides one-time exchange-code helpers used by the OAuth / magic-link
flows to avoid placing raw JWTs in redirect URLs.

Usage:
    from app.core.redis import get_redis

    async def my_endpoint(redis = Depends(get_redis)):
        await redis.set("key", "value", ex=60)
"""
from __future__ import annotations

import json
import secrets

import redis.asyncio as aioredis
from fastapi import HTTPException, status

from app.core.config import settings

# One-time exchange codes expire after 60 seconds.
_EXCHANGE_CODE_TTL = 60

_pool: aioredis.ConnectionPool | None = None


def _get_pool() -> aioredis.ConnectionPool:
    global _pool
    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=20,
        )
    return _pool


def get_redis_client() -> aioredis.Redis:
    """Return a Redis client backed by the shared connection pool."""
    return aioredis.Redis(connection_pool=_get_pool())


async def get_redis() -> aioredis.Redis:
    """FastAPI dependency — yields a Redis client."""
    client = get_redis_client()
    try:
        yield client
    finally:
        await client.aclose()


# ── One-time exchange codes ────────────────────────────────────────────────────


async def create_exchange_code(
    redis: aioredis.Redis,
    access_token: str,
    refresh_token: str,
) -> str:
    """
    Store an access+refresh token pair under a random one-time code.

    Returns the opaque code (URL-safe, 32 bytes of entropy).
    The code expires in 60 seconds and is deleted on first use, so even
    if the redirect URL is captured in logs or browser history the tokens
    cannot be extracted after the legitimate client exchanges the code.
    """
    code = secrets.token_urlsafe(32)
    payload = json.dumps({"at": access_token, "rt": refresh_token})
    await redis.set(f"otc:{code}", payload, ex=_EXCHANGE_CODE_TTL)
    return code


async def consume_exchange_code(
    redis: aioredis.Redis,
    code: str,
) -> tuple[str, str]:
    """
    Atomically fetch-and-delete the token pair stored under *code*.

    Returns (access_token, refresh_token).
    Raises HTTP 400 if the code is missing, expired, or already used.
    """
    key = f"otc:{code}"
    # Use GET + DELETE in a pipeline for atomicity (GETDEL requires Redis >= 6.2)
    pipe = redis.pipeline(transaction=True)
    await pipe.get(key)
    await pipe.delete(key)
    results = await pipe.execute()
    raw = results[0]
    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired sign-in link. Please sign in again.",
        )
    data = json.loads(raw)
    return data["at"], data["rt"]
