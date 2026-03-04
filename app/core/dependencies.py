import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_access_token

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


async def get_current_admin_user(
    current_user: "User" = Depends(get_current_db_user),
) -> "User":
    """
    FastAPI dependency — ensures the authenticated user has the 'admin' role.

    Raises HTTP 403 when the user exists but is not an admin.
    Chain after get_current_db_user so admin routes also get a full DB user object.
    """
    from app.models.user import UserRole  # local import avoids circular deps

    if current_user.role != UserRole.admin.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )
    return current_user
