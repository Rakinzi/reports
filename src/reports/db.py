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
                slides_dir  TEXT,
                edits       TEXT,
                created_at  TEXT    NOT NULL
            )
        """)
        # Safe migration for existing databases
        for col, coldef in [("slides_dir", "TEXT"), ("edits", "TEXT"), ("stage", "TEXT")]:
            try:
                conn.execute(f"ALTER TABLE reports ADD COLUMN {col} {coldef}")
            except Exception:
                pass  # Column already exists

        conn.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                label               TEXT    NOT NULL,
                slug                TEXT    NOT NULL UNIQUE,
                pptx_path           TEXT    NOT NULL,
                slide_count         INTEGER NOT NULL DEFAULT 0,
                ga4_property_id     TEXT    NOT NULL DEFAULT '',
                gsc_url             TEXT    NOT NULL DEFAULT '',
                is_seven_slide      INTEGER NOT NULL DEFAULT 0,
                field_map           TEXT    NOT NULL DEFAULT '[]',
                preview_dir         TEXT,
                created_at          TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS template_shapes (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id     INTEGER NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
                slide_index     INTEGER NOT NULL,
                shape_name      TEXT    NOT NULL,
                shape_type      TEXT    NOT NULL,
                placeholder_text TEXT   NOT NULL DEFAULT '',
                left_emu        INTEGER,
                top_emu         INTEGER,
                width_emu       INTEGER,
                height_emu      INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS template_property_sections (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id     INTEGER NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
                section_name    TEXT    NOT NULL DEFAULT '',
                start_slide     INTEGER NOT NULL,
                end_slide       INTEGER NOT NULL,
                ga4_property_id TEXT    NOT NULL DEFAULT '',
                gsc_url         TEXT    NOT NULL DEFAULT '',
                sort_order      INTEGER NOT NULL DEFAULT 0
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


def update_report_slides_dir(report_id: int, slides_dir: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE reports SET slides_dir=? WHERE id=?",
            (slides_dir, report_id),
        )
        conn.commit()


def update_report_stage(report_id: int, stage: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE reports SET stage=? WHERE id=?",
            (stage, report_id),
        )
        conn.commit()


def delete_report(report_id: int) -> bool:
    """Delete a report record. Returns True if a row was deleted."""
    with _connect() as conn:
        cur = conn.execute("DELETE FROM reports WHERE id=?", (report_id,))
        conn.commit()
        return cur.rowcount > 0


def fail_orphaned_reports() -> None:
    """Mark any pending reports as failed on startup — they lost their worker thread."""
    with _connect() as conn:
        conn.execute(
            "UPDATE reports SET status='failed', error='Interrupted: app was closed during generation' WHERE status='pending'"
        )
        conn.commit()


def update_report_edits(report_id: int, edits: str) -> None:
    """edits is a JSON string of {field_id: new_text}."""
    with _connect() as conn:
        conn.execute(
            "UPDATE reports SET edits=? WHERE id=?",
            (edits, report_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Template CRUD
# ---------------------------------------------------------------------------

def create_template(label: str, slug: str, pptx_path: str, slide_count: int) -> int:
    """Insert a new template row. Returns the new id."""
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO templates (label, slug, pptx_path, slide_count, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (label, slug, pptx_path, slide_count, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def get_template(template_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM templates WHERE id=?", (template_id,)
        ).fetchone()
        return dict(row) if row else None


def get_template_by_slug(slug: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM templates WHERE slug=?", (slug,)
        ).fetchone()
        return dict(row) if row else None


def list_templates() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM templates ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def update_template_config(
    template_id: int,
    ga4_property_id: str,
    gsc_url: str,
    is_seven_slide: bool,
    field_map: str,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE templates
            SET ga4_property_id=?, gsc_url=?, is_seven_slide=?, field_map=?
            WHERE id=?
            """,
            (ga4_property_id, gsc_url, int(is_seven_slide), field_map, template_id),
        )
        conn.commit()


def update_template_preview_dir(template_id: int, preview_dir: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE templates SET preview_dir=? WHERE id=?",
            (preview_dir, template_id),
        )
        conn.commit()


def delete_template(template_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM templates WHERE id=?", (template_id,))
        conn.commit()
        return cur.rowcount > 0


def upsert_template_shapes(template_id: int, shapes: list[dict]) -> None:
    """Replace all shapes for a template (delete + re-insert)."""
    with _connect() as conn:
        conn.execute("DELETE FROM template_shapes WHERE template_id=?", (template_id,))
        conn.executemany(
            """
            INSERT INTO template_shapes
                (template_id, slide_index, shape_name, shape_type, placeholder_text,
                 left_emu, top_emu, width_emu, height_emu)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    template_id,
                    s["slide_index"],
                    s["shape_name"],
                    s["shape_type"],
                    s.get("placeholder_text", ""),
                    s.get("left_emu"),
                    s.get("top_emu"),
                    s.get("width_emu"),
                    s.get("height_emu"),
                )
                for s in shapes
            ],
        )
        conn.commit()


def list_template_shapes(template_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM template_shapes WHERE template_id=? ORDER BY slide_index, top_emu, left_emu",
            (template_id,),
        ).fetchall()
        return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Template property sections CRUD
# ---------------------------------------------------------------------------

def upsert_template_sections(template_id: int, sections: list[dict]) -> None:
    """Replace all property sections for a template (delete + re-insert)."""
    with _connect() as conn:
        conn.execute(
            "DELETE FROM template_property_sections WHERE template_id=?",
            (template_id,),
        )
        conn.executemany(
            """
            INSERT INTO template_property_sections
                (template_id, section_name, start_slide, end_slide,
                 ga4_property_id, gsc_url, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    template_id,
                    s.get("section_name", ""),
                    int(s["start_slide"]),
                    int(s["end_slide"]),
                    s.get("ga4_property_id", ""),
                    s.get("gsc_url", ""),
                    int(s.get("sort_order", i)),
                )
                for i, s in enumerate(sections)
            ],
        )
        conn.commit()


def list_template_sections(template_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM template_property_sections
            WHERE template_id=? ORDER BY sort_order, start_slide
            """,
            (template_id,),
        ).fetchall()
        return [dict(row) for row in rows]
