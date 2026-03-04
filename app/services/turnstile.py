"""
Cloudflare Turnstile server-side verification.

Validates that a Turnstile challenge response token is genuine by calling
Cloudflare's siteverify API. Raises HTTP 403 on failure.

If TURNSTILE_SECRET_KEY is not configured (local dev), verification is skipped
with a warning — set the key in production to enforce the check.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException, Request, status

from app.core.config import settings

logger = logging.getLogger(__name__)

_SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def verify_turnstile(token: str | None, request: Request) -> None:
    """
    Verify a Cloudflare Turnstile *token* server-side.

    Raises HTTP 400 when the token is missing.
    Raises HTTP 403 when Turnstile rejects the token.
    Skips verification if TURNSTILE_SECRET_KEY is not set (local dev only).
    """
    if not settings.TURNSTILE_SECRET_KEY:
        logger.warning(
            "TURNSTILE_SECRET_KEY not set — skipping Turnstile verification. "
            "Set this in production to prevent bot abuse."
        )
        return

    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bot verification token is required.",
        )

    form: dict[str, str] = {
        "secret": settings.TURNSTILE_SECRET_KEY,
        "response": token,
    }
    ip = _client_ip(request)
    if ip:
        form["remoteip"] = ip

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(_SITEVERIFY_URL, data=form)
            data: dict = resp.json()
    except Exception as exc:
        logger.error("Turnstile verification request failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bot verification service unavailable. Please try again.",
        )

    if not data.get("success"):
        error_codes = data.get("error-codes", [])
        logger.warning("Turnstile rejected token. error-codes=%s", error_codes)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bot verification failed. Please refresh the page and try again.",
        )
