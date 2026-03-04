import uuid

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Account(Base):
    """
    Stores OAuth provider links for a user.
    One user can have multiple provider accounts (e.g. Google + future GitHub).
    """

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_account_id", name="uq_provider_account"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Provider identifier, e.g. "google"
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    # The ID the provider uses for this user (Google's `sub` claim)
    provider_account_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # OAuth tokens — stored for potential future use (refresh, revocation)
    access_token: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    # Unix timestamp when the provider access token expires
    expires_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="accounts")  # noqa: F821
