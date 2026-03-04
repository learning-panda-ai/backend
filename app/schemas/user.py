import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    email: EmailStr
    name: str | None
    # avatar_url in DB, serialised as "image" to match frontend expectations
    image: str | None = Field(None, validation_alias="avatar_url")
    is_onboarded: bool
    role: UserRole = UserRole.user
    courses: list[str] = Field(default_factory=list)

    # Profile fields
    first_name: str | None = None
    last_name: str | None = None
    city: str | None = None
    state: str | None = None
    grade: str | None = None
    parent_name: str | None = None
    parent_mobile: str | None = None
    parent_email: str | None = None
    favorite_subject: str | None = None
    study_feeling: str | None = None
    career_thoughts: str | None = None
    strengths_interest: str | None = None

    created_at: datetime


class OnboardingRequest(BaseModel):
    first_name: str
    last_name: str
    city: str
    state: str
    parent_name: str
    parent_mobile: str
    parent_email: str
    grade: str
    school_board: str
    courses: list[str]
    favorite_subject: str
    study_feeling: str
    career_thoughts: str
    strengths_interest: str


class ProfileUpdateRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    city: str | None = None
    state: str | None = None
    grade: str | None = None
    parent_name: str | None = None
    parent_mobile: str | None = None
    parent_email: str | None = None
