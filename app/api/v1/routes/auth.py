"""
Authentication endpoints.

POST /auth/send-otp         — generate & email OTP + magic-link
POST /auth/verify-otp       — verify 6-digit OTP, issue session tokens
GET  /auth/verify-magic     — verify magic-link token, redirect to frontend
GET  /auth/google           — initiate Google OAuth flow
GET  /auth/google/callback  — handle Google OAuth callback
POST /auth/refresh          — issue new access + refresh tokens
GET  /auth/me               — return current authenticated user
POST /auth/logout           — clear session cookies
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_db_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
)
from app.models.account import Account
from app.models.otp import OtpToken
from app.models.user import User
from app.schemas.auth import SendOtpRequest, VerifyOtpRequest
from app.schemas.token import TokenWithUser
from app.schemas.user import UserOut
from app.services import email as email_svc
from app.services import google as google_svc
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["Auth"])
logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Write both JWT tokens as httpOnly cookies."""
    response.set_cookie(
        key="lp_access_token",
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="lp_refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        # Scoped to the refresh endpoint so browsers don't send it with every request
        path="/api/v1/auth/refresh",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("lp_access_token", path="/")
    response.delete_cookie("lp_refresh_token", path="/api/v1/auth/refresh")


async def _get_or_create_user(db: AsyncSession, *, email: str) -> User:
    """Return existing user or create a new unverified one."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(email=email)
        db.add(user)
        await db.flush()  # populate user.id before returning
    return user


def _build_token_response(user: User) -> TokenWithUser:
    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))
    return TokenWithUser(
        access_token=access,
        refresh_token=refresh,
        user=UserOut.model_validate(user),
    )


# ── Rate limiting (DB-backed) ──────────────────────────────────────────────────


async def _check_otp_rate_limit(db: AsyncSession, email: str) -> None:
    """
    Enforce a rolling-window rate limit on OTP send requests.
    Raises HTTP 429 when the limit is exceeded.
    """
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
                f"Too many sign-in requests. "
                f"Please wait {settings.OTP_RATE_LIMIT_WINDOW_MINUTES} minutes before trying again."
            ),
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/send-otp", status_code=status.HTTP_200_OK)
async def send_otp(
    body: SendOtpRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Generate a 6-digit OTP and a magic-link token, persist their hashes,
    and deliver both via an AWS SES email.

    Rate-limited to {OTP_RATE_LIMIT_COUNT} requests per {OTP_RATE_LIMIT_WINDOW_MINUTES} minutes
    per email address.
    """
    email = body.email.lower()

    await _check_otp_rate_limit(db, email)

    # Generate tokens
    otp_code = f"{secrets.randbelow(1_000_000):06d}"
    magic_token = secrets.token_urlsafe(32)

    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.OTP_EXPIRY_MINUTES
    )

    record = OtpToken(
        email=email,
        otp_hash=_sha256(otp_code),
        magic_hash=_sha256(magic_token),
        expires_at=expires_at,
    )
    db.add(record)
    await db.flush()  # ensure record is saved before sending email

    magic_link = (
        f"{settings.FRONTEND_URL}/auth/verify-magic?token={magic_token}"
    )

    await email_svc.send_otp_email(
        to_email=email,
        otp_code=otp_code,
        magic_link=magic_link,
    )

    logger.info("OTP sent to %s (record id=%s)", email, record.id)
    return {"detail": "OTP sent. Check your inbox."}


@router.post("/verify-otp", response_model=TokenWithUser)
async def verify_otp(
    body: VerifyOtpRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenWithUser:
    """
    Verify a 6-digit OTP code.  On success, issue JWT access + refresh tokens
    and set them as httpOnly cookies.
    """
    email = body.email.lower()
    otp_hash = _sha256(body.otp_code)
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(OtpToken)
        .where(OtpToken.email == email)
        .where(OtpToken.otp_hash == otp_hash)
        .where(OtpToken.expires_at > now)
        .where(OtpToken.used_at.is_(None))
        .order_by(OtpToken.created_at.desc())
        .limit(1)
    )
    token_record: OtpToken | None = result.scalar_one_or_none()

    if token_record is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP code.",
        )

    # Consume the token (prevents replay)
    token_record.used_at = now

    user = await _get_or_create_user(db, email=email)
    user.is_verified = True

    token_response = _build_token_response(user)
    _set_auth_cookies(response, token_response.access_token, token_response.refresh_token)

    logger.info("User %s signed in via OTP", user.id)
    return token_response


@router.get("/verify-magic")
async def verify_magic(
    token: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    Verify a magic-link token (delivered via email).

    On success, issues tokens and redirects the browser to:
      {FRONTEND_URL}/auth/callback?at=<access>&rt=<refresh>

    The frontend stores these tokens and finalises the session.
    """
    magic_hash = _sha256(token)
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(OtpToken)
        .where(OtpToken.magic_hash == magic_hash)
        .where(OtpToken.expires_at > now)
        .where(OtpToken.used_at.is_(None))
        .order_by(OtpToken.created_at.desc())
        .limit(1)
    )
    token_record: OtpToken | None = result.scalar_one_or_none()

    if token_record is None:
        # Redirect to an error page rather than returning JSON — this is a browser request
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/auth/error?reason=invalid_magic_link",
            status_code=status.HTTP_302_FOUND,
        )

    token_record.used_at = now
    user = await _get_or_create_user(db, email=token_record.email)
    user.is_verified = True

    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))

    logger.info("User %s signed in via magic link", user.id)

    # Redirect to frontend callback handler — consistent with Google OAuth pattern
    redirect_url = f"{settings.FRONTEND_URL}/auth/callback?at={access}&rt={refresh}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


@router.get("/google")
async def google_login() -> RedirectResponse:
    """
    Redirect the user to Google's OAuth 2.0 consent screen.
    Requires GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to be configured.
    """
    url = google_svc.build_authorization_url()
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get("/google/callback")
async def google_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    Handle the Google OAuth callback.

    Exchanges the authorization code for tokens, upserts the user and their
    linked Google account in the database, then redirects to the frontend
    callback handler with session tokens in the query string.
    """
    profile = await google_svc.exchange_code(code=code, state=state)

    # ── Find or create user ────────────────────────────────────────────────
    result = await db.execute(
        select(User).where(User.email == profile["email"].lower())
    )
    user: User | None = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=profile["email"].lower(),
            name=profile["name"],
            avatar_url=profile["avatar_url"],
            is_verified=True,
        )
        db.add(user)
        await db.flush()

    # Fill in missing profile info on first Google sign-in
    if user.name is None and profile["name"]:
        user.name = profile["name"]
    if user.avatar_url is None and profile["avatar_url"]:
        user.avatar_url = profile["avatar_url"]
    user.is_verified = True

    # ── Upsert Google account link ─────────────────────────────────────────
    acct_result = await db.execute(
        select(Account)
        .where(Account.provider == "google")
        .where(Account.provider_account_id == profile["provider_account_id"])
    )
    account: Account | None = acct_result.scalar_one_or_none()

    if account is None:
        account = Account(
            user_id=user.id,
            provider="google",
            provider_account_id=profile["provider_account_id"],
        )
        db.add(account)

    account.access_token = profile["access_token"]
    account.refresh_token = profile.get("refresh_token") or account.refresh_token
    account.expires_at = profile["expires_at"]

    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))

    logger.info("User %s signed in via Google", user.id)

    redirect_url = f"{settings.FRONTEND_URL}/auth/callback?at={access}&rt={refresh}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


@router.post("/refresh", response_model=TokenWithUser)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    # Cookie-based refresh token (web clients)
    lp_refresh_token: str | None = Cookie(default=None),
) -> TokenWithUser:
    """
    Issue a new access + refresh token pair.

    Accepts the refresh token from either:
      - The `lp_refresh_token` httpOnly cookie (web browser clients)
      - A JSON body `{"refresh_token": "..."}` (API / mobile clients)
    """
    token: str | None = lp_refresh_token

    if not token:
        try:
            body = await request.json()
            token = body.get("refresh_token")
        except Exception:
            pass

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not provided.",
        )

    user_id_str = verify_refresh_token(token)

    import uuid
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token subject.",
        )

    user: User | None = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    token_response = _build_token_response(user)
    _set_auth_cookies(response, token_response.access_token, token_response.refresh_token)
    return token_response


@router.get("/me", response_model=UserOut)
async def get_me(
    current_user: User = Depends(get_current_db_user),
) -> UserOut:
    """Return the profile of the currently authenticated user."""
    return UserOut.model_validate(current_user)


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(response: Response) -> dict:
    """
    Clear session cookies. The access token will expire naturally within
    ACCESS_TOKEN_EXPIRE_MINUTES; the refresh token cookie is removed immediately.
    """
    _clear_auth_cookies(response)
    return {"detail": "Logged out successfully."}
