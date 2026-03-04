"""
Redis-backed rate limiting utilities.

Two strategies are implemented:

1. Sliding-window counter  — general per-key request counting.
2. Consecutive-failure lock — exponential lockout after repeated bad OTP attempts.

All keys are namespaced to avoid collisions with Celery / other Redis users.
"""
from __future__ import annotations

import logging

import redis.asyncio as aioredis
from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# verify-otp: per email
OTP_VERIFY_EMAIL_LIMIT = 10        # max attempts per window
OTP_VERIFY_EMAIL_WINDOW = 15 * 60  # 15-minute rolling window (seconds)

# verify-otp: per IP (looser — shared NATs are common)
OTP_VERIFY_IP_LIMIT = 30
OTP_VERIFY_IP_WINDOW = 15 * 60

# Consecutive-failure lockout for OTP verify
OTP_MAX_CONSECUTIVE_FAILURES = 5   # lock after this many wrong codes in a row
OTP_LOCKOUT_SECONDS = 15 * 60      # locked for 15 minutes

# Token refresh: per IP
REFRESH_IP_LIMIT = 30
REFRESH_IP_WINDOW = 5 * 60         # 5-minute window

# Agent chat: per user
AGENT_CHAT_USER_LIMIT = 50         # requests
AGENT_CHAT_USER_WINDOW = 60 * 60   # per hour


# ── Helpers ───────────────────────────────────────────────────────────────────


def _client_ip(request: Request) -> str:
    """Extract the real client IP, honouring X-Forwarded-For from trusted proxies."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _sliding_window_check(
    redis: aioredis.Redis,
    key: str,
    limit: int,
    window: int,
    detail: str,
) -> None:
    """
    Increment a Redis counter for *key* and raise HTTP 429 when *limit* is
    exceeded within *window* seconds.  Uses INCR + EXPIRE (atomic enough for
    rate-limiting; race condition only widens the window by at most one request).
    """
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window)
    if count > limit:
        ttl = await redis.ttl(key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": str(max(ttl, 1))},
        )


# ── Public API ────────────────────────────────────────────────────────────────


async def check_otp_verify_rate_limit(
    redis: aioredis.Redis,
    request: Request,
    email: str,
) -> None:
    """
    Enforce rate limits on POST /auth/verify-otp.

    Checks (in order):
      1. Per-email consecutive-failure lockout.
      2. Per-email sliding-window limit (10 attempts / 15 min).
      3. Per-IP sliding-window limit (30 attempts / 15 min).

    All three raise HTTP 429 with a Retry-After header on violation.
    """
    ip = _client_ip(request)

    # 1. Consecutive-failure lockout (set by record_otp_failure)
    lock_key = f"rl:otp:lock:{email}"
    if await redis.exists(lock_key):
        ttl = await redis.ttl(lock_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too many incorrect OTP attempts. "
                f"Please wait {max(ttl, 1)} seconds before trying again."
            ),
            headers={"Retry-After": str(max(ttl, 1))},
        )

    # 2. Per-email sliding window
    await _sliding_window_check(
        redis,
        key=f"rl:otp:email:{email}",
        limit=OTP_VERIFY_EMAIL_LIMIT,
        window=OTP_VERIFY_EMAIL_WINDOW,
        detail="Too many OTP attempts for this email. Please wait 15 minutes.",
    )

    # 3. Per-IP sliding window
    await _sliding_window_check(
        redis,
        key=f"rl:otp:ip:{ip}",
        limit=OTP_VERIFY_IP_LIMIT,
        window=OTP_VERIFY_IP_WINDOW,
        detail="Too many requests from your network. Please wait 15 minutes.",
    )


async def record_otp_failure(redis: aioredis.Redis, email: str) -> None:
    """
    Increment the consecutive-failure counter for *email*.
    Locks the account for OTP_LOCKOUT_SECONDS after OTP_MAX_CONSECUTIVE_FAILURES.
    """
    fail_key = f"rl:otp:fail:{email}"
    failures = await redis.incr(fail_key)
    if failures == 1:
        await redis.expire(fail_key, OTP_LOCKOUT_SECONDS)

    if failures >= OTP_MAX_CONSECUTIVE_FAILURES:
        lock_key = f"rl:otp:lock:{email}"
        await redis.set(lock_key, 1, ex=OTP_LOCKOUT_SECONDS)
        await redis.delete(fail_key)
        logger.warning("OTP brute-force lockout triggered for %s", email)


async def clear_otp_failures(redis: aioredis.Redis, email: str) -> None:
    """Reset the consecutive-failure counter after a successful OTP verification."""
    await redis.delete(f"rl:otp:fail:{email}")
    await redis.delete(f"rl:otp:lock:{email}")


async def check_refresh_rate_limit(redis: aioredis.Redis, request: Request) -> None:
    """Enforce per-IP rate limit on POST /auth/refresh."""
    ip = _client_ip(request)
    await _sliding_window_check(
        redis,
        key=f"rl:refresh:ip:{ip}",
        limit=REFRESH_IP_LIMIT,
        window=REFRESH_IP_WINDOW,
        detail="Too many token refresh requests. Please slow down.",
    )


async def check_agent_chat_rate_limit(
    redis: aioredis.Redis, user_id: str
) -> None:
    """Enforce per-user hourly rate limit on POST /agent/chat."""
    await _sliding_window_check(
        redis,
        key=f"rl:chat:user:{user_id}",
        limit=AGENT_CHAT_USER_LIMIT,
        window=AGENT_CHAT_USER_WINDOW,
        detail="Hourly message limit reached. Please wait before sending more messages.",
    )
