"""Database configuration and transaction helpers."""

from collections.abc import Generator
import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
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


def ensure_sqlite_schema() -> None:
    """Add backward-compatible columns missing from an existing local MVP database."""

    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    if "documents" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("documents")}
    additions = {
        "source_type": "VARCHAR(48) NOT NULL DEFAULT 'local_file'",
        "source_uri": "VARCHAR(1000) NOT NULL DEFAULT ''",
        "knowledge_base_id": "VARCHAR(48)",
        "local_path": "VARCHAR(1000) NOT NULL DEFAULT ''",
        "size_bytes": "INTEGER NOT NULL DEFAULT 0",
    }
    with engine.begin() as connection:
        for column_name, definition in additions.items():
            if column_name not in existing:
                connection.execute(
                    text(f"ALTER TABLE documents ADD COLUMN {column_name} {definition}")
                )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_documents_knowledge_base_id "
                "ON documents (knowledge_base_id)"
            )
        )


def get_session() -> Generator[Session, None, None]:
    """Yield a database session and always close it after the request."""

    with SessionLocal() as session:
        yield session
