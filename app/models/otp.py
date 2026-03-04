import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OtpToken(Base):
    """
    Stores pending OTP / magic-link authentication requests.

    Both the OTP code and the magic-link token are stored as SHA-256 hashes
    (hex digest) rather than plaintext. Only the hashed value is persisted;
    the raw values are emailed to the user and never logged or stored.
    """

    __tablename__ = "otp_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )

    # SHA-256(otp_code) — the 6-digit numeric code shown in the email
    otp_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # SHA-256(magic_token) — the one-click sign-in token embedded in the link
    magic_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Set when the token is consumed; prevents replay
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
