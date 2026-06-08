from __future__ import annotations

import time
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session() -> Generator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db_with_retries(
    *,
    retries: int = settings.init_db_retries,
    retry_seconds: float = settings.init_db_retry_seconds,
) -> None:
    # Import models here so metadata is registered before create_all.
    import app.models  # noqa: F401

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except Exception as exc:  # pragma: no cover - exercised in container startup
            last_error = exc
            if attempt == retries - 1:
                break
            time.sleep(retry_seconds)

    if last_error is not None:
        raise last_error
