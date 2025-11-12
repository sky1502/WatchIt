from __future__ import annotations

from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row

from core.config import settings


def _require_pg_conn():
    if not settings.pg_dsn:
        raise RuntimeError("WATCHIT_PG_DSN is not configured")
    return psycopg.connect(settings.pg_dsn, row_factory=dict_row)


def fetch_recent_events(child_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
    conn = _require_pg_conn()
    with conn, conn.cursor() as cur:
        if child_id:
            cur.execute(
                "SELECT * FROM watchit_events WHERE child_id=%s ORDER BY ts DESC LIMIT %s",
                (child_id, limit),
            )
        else:
            cur.execute(
                "SELECT * FROM watchit_events ORDER BY ts DESC LIMIT %s",
                (limit,),
            )
        return cur.fetchall()


def fetch_recent_decisions(child_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
    conn = _require_pg_conn()
    with conn, conn.cursor() as cur:
        if child_id:
            cur.execute(
                """
                SELECT d.*, e.url, e.title, e.ts
                FROM watchit_decisions d
                JOIN watchit_events e ON e.id = d.event_id
                WHERE e.child_id=%s
                ORDER BY e.ts DESC
                LIMIT %s
                """,
                (child_id, limit),
            )
        else:
            cur.execute(
                """
                SELECT d.*, e.url, e.title, e.ts
                FROM watchit_decisions d
                JOIN watchit_events e ON e.id = d.event_id
                ORDER BY e.ts DESC
                LIMIT %s
                """,
                (limit,),
            )
        rows = cur.fetchall()
        return rows


def fetch_children() -> List[Dict[str, Any]]:
    conn = _require_pg_conn()
    with conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, timezone, strictness, age, created_at FROM watchit_children ORDER BY created_at ASC"
        )
        return cur.fetchall()


def upsert_child(child_id: str, strictness: Optional[str] = None, age: Optional[int] = None):
    conn = _require_pg_conn()
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO watchit_children(id, strictness, age)
            VALUES (%s, COALESCE(%s, 'standard'), COALESCE(%s, 12))
            ON CONFLICT (id) DO UPDATE SET
                strictness=COALESCE(EXCLUDED.strictness, watchit_children.strictness),
                age=COALESCE(EXCLUDED.age, watchit_children.age)
            """,
            (child_id, strictness, age),
        )
