"""
User profile endpoints.

PATCH /user/profile            — update basic profile fields
POST  /user/onboarding         — complete onboarding (all fields required)
POST  /user/activity           — record daily activity and update streak
GET   /user/available-subjects — subjects ingested by admin for the user's class
"""
import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_db_user
from app.models.uploaded_file import UploadedFile
from app.models.user import User
from app.schemas.user import OnboardingRequest, ProfileUpdateRequest, UserOut

router = APIRouter(prefix="/user", tags=["User"])
logger = logging.getLogger(__name__)


@router.patch("/profile", response_model=UserOut)
async def update_profile(
    body: ProfileUpdateRequest,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Partially update the authenticated user's profile."""
    if body.first_name is not None:
        current_user.first_name = body.first_name
    if body.last_name is not None:
        current_user.last_name = body.last_name
    if body.city is not None:
        current_user.city = body.city
    if body.state is not None:
        current_user.state = body.state
    if body.grade is not None:
        current_user.grade = body.grade
    if body.school_board is not None:
        current_user.school_board = body.school_board
    if body.parent_name is not None:
        current_user.parent_name = body.parent_name
    if body.parent_mobile is not None:
        current_user.parent_mobile = body.parent_mobile
    if body.parent_email is not None:
        current_user.parent_email = body.parent_email
    if body.courses is not None:
        current_user.courses = body.courses

    # Keep display name in sync
    fn = body.first_name or current_user.first_name
    ln = body.last_name or current_user.last_name
    if fn and ln:
        current_user.name = f"{fn} {ln}"
    elif fn:
        current_user.name = fn

    logger.info("User %s updated profile", current_user.id)
    return UserOut.model_validate(current_user)


@router.post("/onboarding", response_model=UserOut)
async def complete_onboarding(
    body: OnboardingRequest,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Complete the onboarding flow and mark user as onboarded."""
    current_user.first_name = body.first_name
    current_user.last_name = body.last_name
    current_user.city = body.city
    current_user.state = body.state
    current_user.parent_name = body.parent_name
    current_user.parent_mobile = body.parent_mobile
    current_user.parent_email = body.parent_email
    current_user.grade = body.grade
    current_user.school_board = body.school_board
    current_user.courses = body.courses
    current_user.favorite_subject = body.favorite_subject
    current_user.study_feeling = body.study_feeling
    current_user.career_thoughts = body.career_thoughts
    current_user.strengths_interest = body.strengths_interest
    current_user.name = f"{body.first_name} {body.last_name}"
    current_user.is_onboarded = True

    logger.info("User %s completed onboarding", current_user.id)
    return UserOut.model_validate(current_user)


@router.post("/activity", response_model=UserOut)
async def record_activity(
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Record today's activity and update the user's streak.

    - If last_activity_date is today → no change (idempotent).
    - If last_activity_date is yesterday → increment current_streak.
    - Otherwise (gap > 1 day or first activity) → reset current_streak to 1.
    - Updates longest_streak if current_streak exceeds it.
    """
    today = date.today()
    last = current_user.last_activity_date

    if last == today:
        # Already recorded today — return as-is
        return UserOut.model_validate(current_user)

    if last is not None and last == today - timedelta(days=1):
        current_user.current_streak += 1
    else:
        current_user.current_streak = 1

    if current_user.current_streak > current_user.longest_streak:
        current_user.longest_streak = current_user.current_streak

    current_user.last_activity_date = today

    await db.flush()
    logger.info(
        "User %s activity recorded — streak=%d", current_user.id, current_user.current_streak
    )
    return UserOut.model_validate(current_user)


@router.get("/available-subjects", response_model=list[str])
async def get_available_subjects(
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db),
) -> list[str]:
    """Return distinct subjects that have been ingested by admin for the user's class.

    Filters uploaded_files by board and standard matching the user's profile,
    restricted to successfully ingested files.

    Grade format normalisation: onboarding stores grade as "class-10" while the
    admin upload form stores standard as "Class 10".  We convert before querying.
    """
    if not current_user.grade or not current_user.school_board:
        return []

    # "class-10" → "Class 10"  (matches the admin STANDARDS constant)
    standard = current_user.grade.replace("-", " ").title()

    stmt = (
        select(UploadedFile.subject)
        .where(
            UploadedFile.standard == standard,
            UploadedFile.board == current_user.school_board,
            UploadedFile.ingest_status == "completed",
        )
        .distinct()
        .order_by(UploadedFile.subject)
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())
