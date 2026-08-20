"""Pytest bootstrap that keeps test writes away from the developer database."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import uuid


TEST_DATABASE_PATH = (
    Path(tempfile.gettempdir())
    / f"ai-test-tool-pytest-{os.getpid()}-{uuid.uuid4().hex}.db"
)

# Test modules import the FastAPI app at collection time, so this must be set
# before those imports create the SQLAlchemy engine.
os.environ["AI_TEST_DATABASE_PATH"] = str(TEST_DATABASE_PATH)


def pytest_sessionfinish() -> None:
    """Remove the isolated SQLite file after the test session completes."""

    from app.database import engine

    engine.dispose()
    TEST_DATABASE_PATH.unlink(missing_ok=True)
    Path(f"{TEST_DATABASE_PATH}-shm").unlink(missing_ok=True)
    Path(f"{TEST_DATABASE_PATH}-wal").unlink(missing_ok=True)
