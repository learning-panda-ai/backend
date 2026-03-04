"""
Admin authentication endpoints.

POST /admin/auth/send-otp   — send a 6-digit OTP to a registered admin email
POST /admin/auth/verify-otp — verify OTP, receive admin JWT
GET  /admin/auth/me         — return the currently authenticated admin user
POST /admin/auth/create     — create a new admin account (requires existing admin JWT)
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_admin_user
from app.core.security import create_admin_access_token
from app.models.admin_user import AdminUser
from app.models.otp import OtpToken
from app.schemas.admin import (
    AdminCreateRequest,
    AdminSendOtpRequest,
    AdminTokenResponse,
    AdminUserOut,
    AdminVerifyOtpRequest,
)
from app.services import email as email_svc

router = APIRouter(prefix="/admin/auth", tags=["Admin Auth"])
logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def _check_admin_otp_rate_limit(db: AsyncSession, email: str) -> None:
    """Enforce a rolling-window rate limit on admin OTP send requests."""
    window_start = datetime.now(timezone.utc) - timedelta(
        minutes=settings.OTP_RATE_LIMIT_WINDOW_MINUTES
    )
    result = await db.execute(
        select(OtpToken)
        .where(OtpToken.email == email)
        .where(OtpToken.created_at >= window_start)
    )
    recent = result.scalars().all()
    if len(recent) >= settings.OTP_RATE_LIMIT_COUNT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too many requests. "
                f"Please wait {settings.OTP_RATE_LIMIT_WINDOW_MINUTES} minutes before trying again."
            ),
        )


# ── OTP-based auth ────────────────────────────────────────────────────────────


@router.post(
    "/send-otp",
    status_code=status.HTTP_200_OK,
    summary="Send OTP to admin email",
    description=(
        "Validates that the email belongs to an active admin account, then "
        "sends a 6-digit one-time passcode to that address."
    ),
    responses={
        200: {"description": "OTP sent successfully."},
        401: {"description": "Email is not registered as an active admin."},
        429: {"description": "Rate limit exceeded."},
    },
)
async def admin_send_otp(
    body: AdminSendOtpRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    email = body.email.lower()

    # Rate limit FIRST — before any DB lookup that could leak account existence
    await _check_admin_otp_rate_limit(db, email)

    result = await db.execute(
        select(AdminUser).where(AdminUser.email == email)
    )
    admin: AdminUser | None = result.scalar_one_or_none()

    # Always return the same response regardless of whether the email exists.
    # This prevents user enumeration via differential error messages.
    if admin is None or not admin.is_active:
        logger.info("Admin OTP requested for unknown/inactive email (suppressed): %s", email)
        return {"detail": "If this email is registered, an OTP has been sent."}

    otp_code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.OTP_EXPIRY_MINUTES
    )
    record = OtpToken(
        email=email,
        otp_hash=_sha256(otp_code),
        expires_at=expires_at,
    )
    db.add(record)
    await db.flush()

    await email_svc.send_otp_email(
        to_email=email,
        otp_code=otp_code,
        magic_link="",  # Admin portal does not use magic links
    )
    logger.info("Admin OTP sent to %s", email)

    return {"detail": "OTP sent. Check your inbox."}


@router.post(
    "/verify-otp",
    response_model=AdminTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify admin OTP and receive access token",
    description=(
        "Verifies the 6-digit OTP sent to the admin's email address. "
        "On success, returns a short-lived admin JWT."
    ),
    responses={
        200: {"description": "OTP verified — admin token returned."},
        400: {"description": "Invalid or expired OTP."},
        401: {"description": "Admin account not found or inactive."},
    },
)
async def admin_verify_otp(
    body: AdminVerifyOtpRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AdminTokenResponse:
    email = body.email.lower()
    otp_hash = _sha256(body.otp_code)
    now = datetime.now(timezone.utc)

    # Atomically consume the OTP — prevents replay and concurrent-use race condition
    consume_result = await db.execute(
        update(OtpToken)
        .where(OtpToken.email == email)
        .where(OtpToken.otp_hash == otp_hash)
        .where(OtpToken.expires_at > now)
        .where(OtpToken.used_at.is_(None))
        .values(used_at=now)
        .returning(OtpToken.id)
    )
    if consume_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP code.",
        )

    admin_result = await db.execute(
        select(AdminUser).where(AdminUser.email == email)
    )
    admin: AdminUser | None = admin_result.scalar_one_or_none()

    if admin is None or not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin account not found or deactivated.",
        )

    token = create_admin_access_token(str(admin.id))
    logger.info("Admin %s signed in via OTP", admin.email)

    # Set the admin token as an httpOnly cookie to protect against XSS theft.
    # The token is also returned in the response body for backward compatibility
    # with admin clients that read it programmatically.
    response.set_cookie(
        key="lp_admin_token",
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",   # admin panel — stricter than lax
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/api/v1/admin",
    )

    return AdminTokenResponse(
        access_token=token,
        admin=AdminUserOut.model_validate(admin),
    )


@router.get(
    "/me",
    response_model=AdminUserOut,
    summary="Current admin profile",
    description="Return the profile of the currently authenticated admin user.",
    responses={
        200: {"description": "Admin profile returned."},
        401: {"description": "Missing or invalid admin token."},
        403: {"description": "Token is not an admin token."},
    },
)
async def admin_me(
    current_admin: AdminUser = Depends(get_current_admin_user),
) -> AdminUserOut:
    return AdminUserOut.model_validate(current_admin)


@router.post(
    "/create",
    response_model=AdminUserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new admin account",
    description=(
        "Register a new admin user. "
        "Requires an existing valid admin JWT — only admins can create other admins."
    ),
    responses={
        201: {"description": "Admin account created."},
        400: {"description": "Email already registered."},
        401: {"description": "Missing or invalid admin token."},
        403: {"description": "Token is not an admin token."},
    },
)
async def admin_create(
    body: AdminCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),  # authentication gate
) -> AdminUserOut:
    # Check for duplicate email
    result = await db.execute(
        select(AdminUser).where(AdminUser.email == body.email)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An admin with that email already exists.",
        )

    admin = AdminUser(
        name=body.name,
        email=body.email,
    )
    db.add(admin)
    await db.flush()  # populate admin.id

    logger.info("New admin account created: %s", admin.email)
    return AdminUserOut.model_validate(admin)
