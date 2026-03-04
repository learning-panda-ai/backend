import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class AdminSendOtpRequest(BaseModel):
    """Payload for sending an OTP to an admin email address."""

    email: EmailStr


class AdminVerifyOtpRequest(BaseModel):
    """Payload for verifying the OTP code sent to an admin email address."""

    email: EmailStr
    otp_code: str


class AdminUserOut(BaseModel):
    """Public representation of an admin user."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: EmailStr
    is_active: bool
    created_at: datetime


class AdminTokenResponse(BaseModel):
    """Returned after a successful admin login."""

    access_token: str
    token_type: str = "bearer"
    admin: AdminUserOut


class AdminCreateRequest(BaseModel):
    """Payload for creating a new admin account (requires existing admin JWT)."""

    name: str
    email: EmailStr
