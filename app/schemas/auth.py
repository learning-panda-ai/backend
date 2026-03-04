from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class SendOtpRequest(BaseModel):
    email: EmailStr
    # Cloudflare Turnstile challenge response token — required in production.
    turnstile_token: Optional[str] = None


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp_code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
