"""
Admin — website user management endpoints.

GET   /admin/users                      — list all website users (paginated + search)
PATCH /admin/users/{user_id}/status     — activate or deactivate a user account
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_admin_user
from app.models.admin_user import AdminUser
from app.models.user import User
from app.schemas.user import UserAdminOut, UserStatusUpdateRequest

router = APIRouter(prefix="/admin/users", tags=["Admin — User Management"])
logger = logging.getLogger(__name__)


@router.get(
    "",
    summary="List website users",
    description=(
        "Return a paginated list of all website users. "
        "Optionally filter by email or name with the `search` parameter."
    ),
)
async def list_users(
    search: str | None = Query(default=None, description="Filter by name or email"),
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> dict:
    offset = (page - 1) * limit

    base_query = select(User)
    count_query = select(func.count()).select_from(User)

    if search:
        pattern = f"%{search.lower()}%"
        filter_clause = or_(
            func.lower(User.email).like(pattern),
            func.lower(User.name).like(pattern),
        )
        base_query = base_query.where(filter_clause)
        count_query = count_query.where(filter_clause)

    total_result = await db.execute(count_query)
    total: int = total_result.scalar_one()

    users_result = await db.execute(
        base_query
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    users = users_result.scalars().all()

    return {
        "users": [UserAdminOut.model_validate(u) for u in users],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": max(1, -(-total // limit)),  # ceiling division
    }


@router.patch(
    "/{user_id}/status",
    response_model=UserAdminOut,
    summary="Activate or deactivate a user account",
    description=(
        "Set `is_active` to `true` or `false` for the given user. "
        "Inactive users will receive a 403 on any authenticated endpoint."
    ),
    responses={
        200: {"description": "User status updated."},
        404: {"description": "User not found."},
        401: {"description": "Missing or invalid admin token."},
        403: {"description": "Token is not an admin token."},
    },
)
async def update_user_status(
    user_id: uuid.UUID,
    body: UserStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin_user),
) -> UserAdminOut:
    user: User | None = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    user.is_active = body.is_active
    await db.flush()

    action = "activated" if body.is_active else "deactivated"
    logger.info("Admin %s %s user %s", admin.email, action, user.email)

    return UserAdminOut.model_validate(user)
