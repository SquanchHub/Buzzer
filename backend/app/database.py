from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.is_development,
    pool_pre_ping=True,
    pool_recycle=3600,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Inject the session with this, never with a bare Depends(get_db). scope="function"
# runs get_db's commit as soon as the handler returns, *before* the response is sent;
# FastAPI's default ("request") commits only after the response has gone out, so a
# client that reads right after a write could miss it. Every use must share the same
# scope: FastAPI caches dependencies per scope, so mixing the two would give one
# request two separate sessions (e.g. get_current_user's and the handler's).
# tests/unit/test_db_scope.py fails on any get_db dependency that isn't function-scoped.
DbSession = Annotated[AsyncSession, Depends(get_db, scope="function")]
