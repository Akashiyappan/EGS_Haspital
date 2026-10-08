from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Dialect, MetaData
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator, TypeEngine

# Deterministic constraint names keep Alembic migrations stable (all < 64 chars for MySQL).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Datetime stored as UTC and always returned timezone-aware (UTC).

    MySQL DATETIME has no timezone, so values are converted to UTC and stored
    as naive UTC wall-clock with microsecond precision (DATETIME(6)); SQLite
    likewise returns naive values. Reads re-attach UTC.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "mysql":
            return dialect.type_descriptor(mysql.DATETIME(fsp=6))
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetimes are not allowed; use timezone-aware UTC values")
        as_utc = value.astimezone(UTC)
        return as_utc.replace(tzinfo=None) if dialect.name == "mysql" else as_utc

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if not isinstance(value, datetime):
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    # Python-side defaults: values are known after flush without a refresh (lazy
    # refreshes are not allowed under AsyncSession). No server default, because
    # MySQL requires CURRENT_TIMESTAMP(6) to match DATETIME(6) precision.
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
