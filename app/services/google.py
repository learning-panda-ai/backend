"""
Google OAuth 2.0 service.

Flow:
  1. build_authorization_url() → send user to Google consent screen
  2. exchange_code(code, state) → receive tokens + fetch profile
  3. Caller upserts User/Account in DB and issues JWT session tokens
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import TypedDict
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

_SCOPES = "openid email profile"


class GoogleProfile(TypedDict):
    provider_account_id: str  # Google's `sub` claim
    email: str
    name: str | None
    avatar_url: str | None
    access_token: str
    refresh_token: str | None
    expires_at: int | None  # Unix timestamp


# ── State token (stateless CSRF protection) ───────────────────────────────────


def _create_state_token() -> str:
    """
    Create a short-lived, signed JWT used as the OAuth `state` parameter.
    Signing with JWT_SECRET_KEY prevents CSRF — an attacker cannot forge a
    valid state without the secret.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=10)
    payload = {
        "nonce": secrets.token_hex(16),
        "exp": expire,
        "type": "oauth_state",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _verify_state_token(state: str) -> None:
    """Raise HTTP 400 if the OAuth state token is invalid or expired."""
    try:
        payload = jwt.decode(
            state, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        if payload.get("type") != "oauth_state":
            raise ValueError("wrong token type")
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state. Please try signing in again.",
        )


# ── Public API ────────────────────────────────────────────────────────────────


def build_authorization_url() -> str:
    """
    Return the Google OAuth consent URL. The state parameter embeds a
    signed JWT to protect against CSRF on the callback.

    Raises HTTP 503 when Google OAuth credentials are not configured.
    """
    _require_google_config()

    state = _create_state_token()
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": _SCOPES,
        "state": state,
        "access_type": "offline",   # request refresh_token
        "prompt": "select_account",  # always show account picker
    }
    return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code(*, code: str, state: str) -> GoogleProfile:
    """
    Exchange an authorization code for tokens and return the user's profile.

    Raises HTTP 400 on bad state, HTTP 502 on upstream Google errors.
    """
    _require_google_config()
    _verify_state_token(state)

    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Exchange code for tokens
        token_resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            logger.error(
                "Google token exchange failed: %s %s",
                token_resp.status_code,
                token_resp.text,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to exchange authorization code with Google.",
            )

        token_data: dict = token_resp.json()
        access_token: str = token_data["access_token"]
        refresh_token: str | None = token_data.get("refresh_token")
        expires_in: int | None = token_data.get("expires_in")
        expires_at = (
            int((datetime.now(timezone.utc) + timedelta(seconds=expires_in)).timestamp())
            if expires_in
            else None
        )

        # 2. Fetch user profile
        userinfo_resp = await client.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            logger.error(
                "Google userinfo fetch failed: %s %s",
                userinfo_resp.status_code,
                userinfo_resp.text,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to fetch user profile from Google.",
            )

        userinfo: dict = userinfo_resp.json()

    email: str | None = userinfo.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account does not have a verified email address.",
        )

    return GoogleProfile(
        provider_account_id=userinfo["sub"],
        email=email,
        name=userinfo.get("name"),
        avatar_url=userinfo.get("picture"),
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────


def _require_google_config() -> None:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured.",
        )
