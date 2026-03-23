"""
SQLite database for persisting report records.
"""

import sqlite3
from datetime import datetime

from .runtime import get_database_path


def _connect() -> sqlite3.Connection:
    db_path = get_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                report_name TEXT    NOT NULL,
                date_range  TEXT    NOT NULL,
                report_date TEXT    NOT NULL,
                status      TEXT    NOT NULL DEFAULT 'pending',
                output_path TEXT,
                error       TEXT,
                created_at  TEXT    NOT NULL
            )
        """)
        conn.commit()


def create_report(report_name: str, date_range: str, report_date: str) -> int:
    """Insert a new report record with status=pending. Returns the new id."""
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO reports (report_name, date_range, report_date, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (report_name, date_range, report_date, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def update_report_completed(report_id: int, output_path: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE reports SET status='completed', output_path=? WHERE id=?",
            (output_path, report_id),
        )
        conn.commit()


def update_report_failed(report_id: int, error: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE reports SET status='failed', error=? WHERE id=?",
            (error, report_id),
        )
        conn.commit()


def list_reports() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM reports ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def get_report(report_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM reports WHERE id=?", (report_id,)
        ).fetchone()
        return dict(row) if row else None
