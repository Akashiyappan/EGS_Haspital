import os

# Must be set before the app (and its settings) are imported.
os.environ["ENVIRONMENT"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-0123456789-abcdefghijklmnop"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["CLINIC_TIMEZONE"] = "Asia/Kolkata"
os.environ["GROQ_API_KEY"] = ""
os.environ["CLOUDINARY_CLOUD_NAME"] = ""
os.environ["EMAIL_BACKEND"] = "disabled"

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app import models  # noqa: F401
from app.api.v1.routes.ai import optional_llm_client
from app.core import rate_limit
from app.db.base import Base
from app.db.session import configure_sqlite, get_db, get_session_factory
from app.integrations.storage import get_storage
from app.main import create_app
from app.realtime.manager import manager
from tests.fakes import FakeLLM, FakeStorage

# Run the whole suite against MySQL by setting e.g.
# TEST_DATABASE_URL=mysql+aiomysql://onezae:pass@127.0.0.1:3306/onezae_test?charset=utf8mb4
# (a dedicated, empty database: every test drops and recreates all tables).
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    # A real file (not :memory:) with separate connections, so concurrency
    # tests exercise genuine database locking and constraints.
    url = TEST_DATABASE_URL or f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    options = {"isolation_level": "READ COMMITTED"} if url.startswith("mysql") else {}
    engine = create_async_engine(url, poolclass=NullPool, **options)
    configure_sqlite(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    if TEST_DATABASE_URL:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@pytest.fixture
async def db(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def app(session_factory: async_sessionmaker[AsyncSession], storage: FakeStorage, llm: FakeLLM):  # type: ignore[no-untyped-def]
    application = create_app()

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    application.dependency_overrides[get_db] = override_get_db
    application.dependency_overrides[get_session_factory] = lambda: session_factory
    application.dependency_overrides[get_storage] = lambda: storage
    application.dependency_overrides[optional_llm_client] = lambda: llm
    return application


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_global_state() -> None:
    rate_limit.backend.reset()  # type: ignore[attr-defined]
    manager.reset()
