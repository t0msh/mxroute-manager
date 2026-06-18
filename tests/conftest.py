"""Shared pytest configuration and fixtures.

Environment variables and sys.path are configured here *before* importing app
code, so models.db picks up the throwaway DATABASE_FILE instead of a real DB.
"""
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_TEST_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TEST_DB.close()
os.environ["DATABASE_FILE"] = _TEST_DB.name
os.environ.setdefault("RESET_PORTAL_CNAME_TARGET", "manager.example.com")
os.environ.setdefault("CF_API_TOKEN", "test-cf-token")
os.environ.setdefault("CF_ACCOUNT_ID", "test-cf-account")
os.environ.setdefault("NPM_API_URL", "https://npm.example.com")
os.environ.setdefault("NPM_IDENTITY", "admin@example.com")
os.environ.setdefault("NPM_SECRET", "secret")
os.environ.setdefault("NPM_FORWARD_HOST", "192.168.68.150")
os.environ.setdefault("NPM_FORWARD_PORT", "5000")

from app import app  # noqa: E402
from models import db  # noqa: E402

import pytest  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    try:
        os.unlink(_TEST_DB.name)
    except OSError:
        pass


@pytest.fixture
def fresh_db():
    """Create tables in the session temp DB. Call at the start of DB-backed tests."""
    db.init_db()
    return db


@pytest.fixture
def client():
    """Flask test client — exercises routes without running a real server."""
    return app.test_client()


@pytest.fixture
def db_connection():
    """Raw SQLite connection for tests that tweak rows directly (e.g. expiry)."""
    conn = sqlite3.connect(_TEST_DB.name)
    yield conn
    conn.close()
