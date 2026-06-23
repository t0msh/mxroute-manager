import os
import sqlite3
from contextlib import contextmanager


def get_env_config(key, default=None):
    return os.getenv(key, default)


def _database_file():
    from models import db as db_module

    return db_module.DATABASE_FILE


@contextmanager
def get_conn():
    """Yield a SQLite connection that is always closed, even on exceptions."""
    conn = sqlite3.connect(_database_file())
    try:
        yield conn
    finally:
        conn.close()
