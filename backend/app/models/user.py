from datetime import datetime

from sqlalchemy import Enum, String, false, text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UTCDateTime
from app.models.enums import Role


class User(TimestampMixin, Base):
    """Identity and credentials for every role. Role-specific data lives in
    `doctors` / `patients`, keyed by user_id."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, length=16, create_constraint=True, name="user_role"),
        index=True,
    )
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(32))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    avatar_public_id: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    # Set for admin-issued temporary passwords; the API blocks everything except
    # changing the password until it is cleared.
    must_change_password: Mapped[bool] = mapped_column(default=False, server_default=false())
    # Bumped on logout / password change to invalidate every issued token.
    token_version: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part)

    def __repr__(self) -> str:
        return f"<User id={self.id} role={self.role}>"
