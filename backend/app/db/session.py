from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def _engine_options(url: str) -> dict[str, Any]:
    options: dict[str, Any] = {"echo": settings.DB_ECHO, "pool_pre_ping": True}
    if url.startswith("mysql"):
        options |= {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            # Recycle before MySQL's wait_timeout closes idle connections.
            "pool_recycle": settings.DB_POOL_RECYCLE_SECONDS,
            # READ COMMITTED avoids InnoDB gap locks (fewer deadlocks) and lets
            # each statement see rows committed by concurrent requests.
            "isolation_level": "READ COMMITTED",
        }
    return options


def configure_sqlite(async_engine: AsyncEngine) -> None:
    """SQLite ignores foreign keys unless enabled per connection; also wait on
    locks instead of failing immediately under concurrent writes."""
    if async_engine.dialect.name != "sqlite":
        return

    @event.listens_for(async_engine.sync_engine, "connect")
    def _on_connect(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


engine = create_async_engine(settings.DATABASE_URL, **_engine_options(settings.DATABASE_URL))
configure_sqlite(engine)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield a session per request. Services commit explicitly; anything
    uncommitted is rolled back when the session closes."""
    async with SessionLocal() as session:
        yield session


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """For long-lived connections (WebSockets) that open short sessions per
    operation instead of holding one for the connection's lifetime."""
    return SessionLocal
