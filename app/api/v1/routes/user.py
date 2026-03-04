"""
User profile endpoints.

PATCH /user/profile     — update basic profile fields
POST  /user/onboarding  — complete onboarding (all fields required)
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_db_user
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
    if body.parent_name is not None:
        current_user.parent_name = body.parent_name
    if body.parent_mobile is not None:
        current_user.parent_mobile = body.parent_mobile
    if body.parent_email is not None:
        current_user.parent_email = body.parent_email

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
