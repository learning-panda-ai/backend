from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from jose import ExpiredSignatureError, JWTError, jwt

from app.core.config import settings

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired access token.",
    headers={"WWW-Authenticate": "Bearer"},
)


# ── Token creation ────────────────────────────────────────────────────────────


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    """Create a short-lived JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload: dict[str, Any] = {"sub": subject, "exp": expire, "type": "access"}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str) -> str:
    """Create a long-lived JWT refresh token."""
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload: dict[str, Any] = {"sub": subject, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# ── Token verification ────────────────────────────────────────────────────────


def verify_access_token(token: str) -> dict:
    """
    Decode and validate a JWT Bearer token.

    Raises HTTP 401 when the token is missing required claims,
    has an invalid signature, or has expired.
    """
    try:
        payload: dict = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise _CREDENTIALS_EXCEPTION

    # `sub` (subject / user identity) is a required claim
    if not payload.get("sub"):
        raise _CREDENTIALS_EXCEPTION

    # Reject refresh / admin tokens presented as access tokens
    if payload.get("type") != "access":
        raise _CREDENTIALS_EXCEPTION

    return payload


def verify_refresh_token(token: str) -> str:
    """
    Decode a refresh token and return the user ID (sub).
    Raises HTTP 401 on any validation failure.
    """
    try:
        payload: dict = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired.",
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
        )

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token: missing subject.",
        )
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type.",
        )
    return sub


# ── Admin token helpers ───────────────────────────────────────────────────────


def create_admin_access_token(subject: str) -> str:
    """Create a short-lived JWT access token exclusively for admin users.

    Uses token type ``"admin_access"`` so it cannot be accepted by endpoints
    that expect a regular user token (and vice-versa).
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "type": "admin_access",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_admin_access_token(token: str) -> dict:
    """Decode and validate a JWT admin Bearer token.

    Raises HTTP 401 when the token is invalid/expired and HTTP 403 when the
    token type is not ``"admin_access"``.
    """
    try:
        payload: dict = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin access token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise _CREDENTIALS_EXCEPTION

    if not payload.get("sub"):
        raise _CREDENTIALS_EXCEPTION

    if payload.get("type") != "admin_access":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator token required.",
        )

    return payload
