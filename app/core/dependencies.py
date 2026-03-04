import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_access_token, verify_admin_access_token

_bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """
    FastAPI dependency — extracts the Bearer token from the Authorization
    header and returns the decoded JWT payload on success.

    Backward-compatible: existing routes that use current_user["sub"] continue
    to work unchanged.
    """
    return verify_access_token(credentials.credentials)


async def get_current_db_user(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    FastAPI dependency — looks up the authenticated user in the database and
    returns the ORM User instance.

    Use this in auth/user routes that need the full user record.
    """
    from app.models.user import User  # local import avoids circular deps at module load

    user_id_str: str = payload["sub"]
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject.",
        )

    user: User | None = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )
    return user


async def get_current_active_db_user(
    user: "User" = Depends(get_current_db_user),
):
    """
    FastAPI dependency — same as get_current_db_user but additionally enforces
    that the account is active (is_active=True).  Use this on all paid / gated
    endpoints (chat, agent, profile, activity, courses).

    Inactive users receive HTTP 403 so the frontend can redirect to /suspended
    rather than /login.
    """
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not yet activated. Please contact support.",
        )
    return user


async def get_current_admin_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """
    FastAPI dependency — validates an admin Bearer token and returns the
    corresponding AdminUser record from the ``admin_users`` table.

    The token must have been issued by the ``/admin/auth/login`` endpoint
    (token type ``"admin_access"``). Regular user tokens are rejected with
    HTTP 403.  Inactive admin accounts are rejected with HTTP 401.
    """
    from app.models.admin_user import AdminUser  # local import avoids circular deps

    payload = verify_admin_access_token(credentials.credentials)

    admin_id_str: str = payload["sub"]
    try:
        admin_id = uuid.UUID(admin_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject.",
        )

    admin: AdminUser | None = await db.get(AdminUser, admin_id)
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin user not found.",
        )

    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin account is deactivated.",
        )

    return admin
