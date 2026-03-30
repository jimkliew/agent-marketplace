"""Database — SQLite with WAL mode, exclusive transactions for money safety."""

import sqlite3
import asyncio
from contextlib import contextmanager
from pathlib import Path
from backend.config import DB_FULL_PATH

_schema_path = Path(__file__).parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_FULL_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    DB_FULL_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_schema_path.read_text())
        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_db():
    """Standard transaction — commits on success, rolls back on error."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_db_exclusive():
    """EXCLUSIVE transaction — prevents concurrent writes to the same rows.
    Use this for any operation that reads-then-writes a balance.
    SQLite EXCLUSIVE locks the entire database during the transaction,
    preventing double-spend race conditions."""
    conn = get_connection()
    try:
        conn.execute("BEGIN EXCLUSIVE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def db_fetchone(sql: str, params: tuple = ()) -> dict | None:
    def _fetch():
        with get_db() as conn:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None
    return await asyncio.to_thread(_fetch)


async def db_fetchall(sql: str, params: tuple = ()) -> list[dict]:
    def _fetch():
        with get_db() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
    return await asyncio.to_thread(_fetch)
