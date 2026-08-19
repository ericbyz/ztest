"""Database configuration and transaction helpers."""

from collections.abc import Generator
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_PATH = Path(
    os.environ.get(
        "AI_TEST_DATABASE_PATH",
        str(Path(__file__).resolve().parents[1] / "ai_test_tool.db"),
    )
)
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"


class Base(DeclarativeBase):
    """Base class for persisted entities."""


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    """Yield a database session and always close it after the request."""

    with SessionLocal() as session:
        yield session
