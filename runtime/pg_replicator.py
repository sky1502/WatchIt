from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Tuple

import psycopg
from psycopg.types.json import Json

from core.db import db
from core.config import settings
from pathlib import Path
from datetime import datetime
import re

log = logging.getLogger("watchit.pg_replicator")
LOG_DIR = Path(__file__).resolve().parent.parent / "logs" / "postgres_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_pg_logger: logging.Logger | None = None


def _next_pg_log_path() -> Path:
    today = datetime.now().strftime("%Y%m%d")
    pattern = re.compile(rf"{today}_replicator_(\d+)\.log")
    existing = sorted(LOG_DIR.glob(f"{today}_replicator_*.log"))
    next_idx = 1
    for path in existing:
        m = pattern.match(path.name)
        if m:
            next_idx = max(next_idx, int(m.group(1)) + 1)
    return LOG_DIR / f"{today}_replicator_{next_idx}.log"


def _get_pg_logger() -> logging.Logger:
    global _pg_logger
    if _pg_logger is not None:
        return _pg_logger
    handler = logging.FileHandler(_next_pg_log_path(), encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger = logging.getLogger("watchit.pg_replicator.file")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
    logger.info("=== New Postgres replicator session log started ===")
    _pg_logger = logger
    return logger


def _get_setting(key: str) -> Optional[str]:
    cur = db.conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    return row[0] if row else None


def _set_setting(key: str, value: str) -> None:
    cur = db.conn.cursor()
    cur.execute(
        "INSERT INTO settings(key,value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    db.conn.commit()


class PostgresReplicator:
    """
    Mirror SQLite rows to Postgres without impacting the fast local path.

    Usage:
        repl = PostgresReplicator(pg_dsn="postgresql://user:pass@host/db")
        asyncio.create_task(repl.run_forever())
    """

    def __init__(
        self,
        pg_dsn: str,
        poll_interval: float = 5.0,
        batch_size: int = 100,
    ):
        self.pg_dsn = pg_dsn
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self._stop_event = asyncio.Event()

    async def run_forever(self) -> None:
        """Continuously push new rows to Postgres."""
        log.info("Starting Postgres replicator (interval=%ss, batch=%s)", self.poll_interval, self.batch_size)
        file_logger = _get_pg_logger()
        file_logger.info("Starting Postgres replicator (interval=%ss, batch=%s)", self.poll_interval, self.batch_size)
        print(f"[watchit] Postgres replicator running (poll={self.poll_interval}s, batch={self.batch_size})")
        while not self._stop_event.is_set():
            try:
                events, decisions, children = self.sync_once()
                if events or decisions or children:
                    log.info("Synced %s events, %s decisions, %s children", events, decisions, children)
                    file_logger.info("Synced %s events, %s decisions, %s children", events, decisions, children)
            except Exception:
                log.exception("Postgres replication failed")
                file_logger.exception("Postgres replication failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
            except asyncio.TimeoutError:
                continue
        log.info("Postgres replicator stopped")
        file_logger.info("Postgres replicator stopped")

    def stop(self) -> None:
        self._stop_event.set()

    def sync_once(self) -> Tuple[int, int, int]:
        """Run a single replication cycle and return counts."""
        with psycopg.connect(self.pg_dsn, autocommit=True) as conn:
            self._ensure_schema(conn)
            children = self._sync_children(conn)
            events = self._sync_events(conn)
            decisions = self._sync_decisions(conn)
            return events, decisions, children

    # --- internal helpers -------------------------------------------------

    def _ensure_schema(self, conn: psycopg.Connection) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS watchit_events(
                    id TEXT PRIMARY KEY,
                    child_id TEXT,
                    ts BIGINT,
                    kind TEXT,
                    url TEXT,
                    title TEXT,
                    tab_id TEXT,
                    referrer TEXT,
                    data_json JSONB
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS watchit_decisions(
                    id TEXT PRIMARY KEY,
                    event_id TEXT REFERENCES watchit_events(id) ON DELETE CASCADE,
                    policy_version TEXT,
                    action TEXT,
                    reason TEXT,
                    details_json JSONB,
                    original_action TEXT,
                    manual_action TEXT,
                    manual_flagged BOOLEAN DEFAULT FALSE,
                    manual_processed BOOLEAN DEFAULT FALSE,
                    manual_updated_at BIGINT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
            cur.execute("ALTER TABLE watchit_decisions ADD COLUMN IF NOT EXISTS original_action TEXT")
            cur.execute("ALTER TABLE watchit_decisions ADD COLUMN IF NOT EXISTS manual_action TEXT")
            cur.execute("ALTER TABLE watchit_decisions ADD COLUMN IF NOT EXISTS manual_flagged BOOLEAN DEFAULT FALSE")
            cur.execute("ALTER TABLE watchit_decisions ADD COLUMN IF NOT EXISTS manual_processed BOOLEAN DEFAULT FALSE")
            cur.execute("ALTER TABLE watchit_decisions ADD COLUMN IF NOT EXISTS manual_updated_at BIGINT")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS watchit_children(
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    os_user TEXT,
                    timezone TEXT,
                    strictness TEXT,
                    age INTEGER,
                    created_at BIGINT
                );
                """
            )

    def _sync_children(self, conn: psycopg.Connection) -> int:
        cur = db.conn.cursor()
        cur.execute("SELECT id, name, os_user, timezone, strictness, age, created_at FROM child_profile")
        rows = cur.fetchall()
        if not rows:
            return 0
        payloads = [tuple(row) for row in rows]
        with conn.cursor() as pg_cur:
            pg_cur.executemany(
                """
                INSERT INTO watchit_children(id, name, os_user, timezone, strictness, age, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET
                    name=EXCLUDED.name,
                    os_user=EXCLUDED.os_user,
                    timezone=EXCLUDED.timezone,
                    strictness=EXCLUDED.strictness,
                    age=EXCLUDED.age,
                    created_at=EXCLUDED.created_at
                """,
                payloads,
            )
        return len(rows)

    def _sync_events(self, conn: psycopg.Connection) -> int:
        last_ts_raw = _get_setting("pg_last_event_ts")
        last_ts = int(last_ts_raw) if last_ts_raw else None
        cur = db.conn.cursor()
        if last_ts is None:
            cur.execute(
                "SELECT id, child_id, ts, kind, url, title, tab_id, referrer, data_json "
                "FROM event ORDER BY ts ASC LIMIT ?",
                (self.batch_size,),
            )
        else:
            cur.execute(
                "SELECT id, child_id, ts, kind, url, title, tab_id, referrer, data_json "
                "FROM event WHERE ts > ? ORDER BY ts ASC LIMIT ?",
                (last_ts, self.batch_size),
            )
        rows = cur.fetchall()
        if not rows:
            return 0
        payloads = [
            (
                r[0],
                r[1],
                r[2],
                r[3],
                r[4],
                r[5],
                r[6],
                r[7],
                Json(self._safe_json(r[8])),
            )
            for r in rows
        ]
        with conn.cursor() as pg_cur:
            pg_cur.executemany(
                """
                INSERT INTO watchit_events(id, child_id, ts, kind, url, title, tab_id, referrer, data_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO NOTHING
                """,
                payloads,
            )
        latest_ts = max(r[2] or 0 for r in rows)
        _set_setting("pg_last_event_ts", str(latest_ts))
        return len(rows)

    def _sync_decisions(self, conn: psycopg.Connection) -> int:
        last_ts_raw = _get_setting("pg_last_decision_ts")
        last_ts = int(last_ts_raw) if last_ts_raw else None
        cur = db.conn.cursor()
        if last_ts is None:
            cur.execute(
                """
                SELECT d.id,
                       d.event_id,
                       d.policy_version,
                       d.action,
                       d.reason,
                       d.details_json,
                       e.ts,
                       d.original_action,
                       d.manual_action,
                       d.manual_flagged,
                       d.manual_processed,
                       d.manual_updated_at,
                       MAX(e.ts, COALESCE(d.manual_updated_at, 0)) AS sync_ts
                FROM decision d
                JOIN event e ON e.id = d.event_id
                ORDER BY sync_ts ASC
                LIMIT ?
                """,
                (self.batch_size,),
            )
        else:
            cur.execute(
                """
                SELECT d.id,
                       d.event_id,
                       d.policy_version,
                       d.action,
                       d.reason,
                       d.details_json,
                       e.ts,
                       d.original_action,
                       d.manual_action,
                       d.manual_flagged,
                       d.manual_processed,
                       d.manual_updated_at,
                       MAX(e.ts, COALESCE(d.manual_updated_at, 0)) AS sync_ts
                FROM decision d
                JOIN event e ON e.id = d.event_id
                WHERE MAX(e.ts, COALESCE(d.manual_updated_at, 0)) > ?
                ORDER BY sync_ts ASC
                LIMIT ?
                """,
                (last_ts, self.batch_size),
            )
        rows = cur.fetchall()
        if not rows:
            return 0

        payloads = [
            (
                r[0],
                r[1],
                r[2],
                r[3],
                r[4],
                Json(self._safe_json(r[5])),
                r[7],
                r[8],
                bool(r[9]),
                bool(r[10]),
                r[11],
            )
            for r in rows
        ]
        with conn.cursor() as pg_cur:
            pg_cur.executemany(
                """
                INSERT INTO watchit_decisions(id, event_id, policy_version, action, reason, details_json, original_action, manual_action, manual_flagged, manual_processed, manual_updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET
                    action=EXCLUDED.action,
                    reason=EXCLUDED.reason,
                    details_json=EXCLUDED.details_json,
                    original_action=COALESCE(watchit_decisions.original_action, EXCLUDED.original_action),
                    manual_action=EXCLUDED.manual_action,
                    manual_flagged=EXCLUDED.manual_flagged,
                    manual_processed=EXCLUDED.manual_processed,
                    manual_updated_at=EXCLUDED.manual_updated_at
                """,
                payloads,
            )
        latest_ts = max(r[12] or 0 for r in rows)
        _set_setting("pg_last_decision_ts", str(latest_ts))
        return len(rows)

    @staticmethod
    def _safe_json(blob: Optional[str]) -> Optional[Dict[str, Any]]:
        if not blob:
            return None
        try:
            return json.loads(blob)
        except Exception:
            return None


_singleton: Optional[PostgresReplicator] = None


def sync_once_on_demand() -> Tuple[int, int, int]:
    """Run a single replication pass using settings-based DSN."""
    if not settings.pg_dsn:
        raise RuntimeError("WATCHIT_PG_DSN is not configured")
    global _singleton
    if _singleton is None or _singleton.pg_dsn != settings.pg_dsn:
        _singleton = PostgresReplicator(pg_dsn=settings.pg_dsn)
    return _singleton.sync_once()


async def _cli() -> None:
    import os
    import sys

    dsn = os.getenv("WATCHIT_PG_DSN")
    if not dsn:
        print("WATCHIT_PG_DSN environment variable is required for Postgres replication", file=sys.stderr)
        raise SystemExit(1)
    interval = float(os.getenv("WATCHIT_PG_INTERVAL", "5"))
    batch = int(os.getenv("WATCHIT_PG_BATCH", "100"))
    replicator = PostgresReplicator(pg_dsn=dsn, poll_interval=interval, batch_size=batch)
    try:
        await replicator.run_forever()
    except KeyboardInterrupt:
        replicator.stop()


if __name__ == "__main__":
    asyncio.run(_cli())
