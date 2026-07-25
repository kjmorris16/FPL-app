import sqlite3
from contextlib import contextmanager

import pytest

from src.db import SCHEMA


@pytest.fixture
def db_conn():
    """In-memory SQLite connection with the app schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    yield conn
    conn.close()
