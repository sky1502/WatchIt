from __future__ import annotations
import os, json, uuid, time
from typing import Any, Dict, Optional, List, Tuple
import logging
from pathlib import Path
from datetime import datetime
import re
from pysqlcipher3 import dbapi2 as sqlcipher
from .config import settings

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
SQLITE_LOG_DIR = LOG_DIR / "sqlite_logs"
SQLITE_LOG_DIR.mkdir(parents=True, exist_ok=True)

_sqlite_logger: logging.Logger | None = None


def _next_sqlite_log_path() -> Path:
    today = datetime.now().strftime("%Y%m%d")
    pattern = re.compile(rf"{today}_sqlite_(\d+)\.log")
    existing = sorted(SQLITE_LOG_DIR.glob(f"{today}_sqlite_*.log"))
    next_idx = 1
    for path in existing:
        m = pattern.match(path.name)
        if m:
            next_idx = max(next_idx, int(m.group(1)) + 1)
    return SQLITE_LOG_DIR / f"{today}_sqlite_{next_idx}.log"


def _get_sqlite_logger() -> logging.Logger:
    global _sqlite_logger
    if _sqlite_logger is not None:
        return _sqlite_logger
    handler = logging.FileHandler(_next_sqlite_log_path(), encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger = logging.getLogger("watchit.sqlite")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
    logger.info("=== New SQLite session log started ===")
    _sqlite_logger = logger
    return logger


class Database:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.db_path
        self.conn: Optional[sqlcipher.Connection] = None
        self.logger = _get_sqlite_logger()

    def connect(self):
        if self.conn:
            return
        if os.path.dirname(self.db_path):
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlcipher.connect(self.db_path, check_same_thread=False)
        cur = self.conn.cursor()
        cur.execute(f"PRAGMA key = '{settings.db_key}';")
        cur.execute("PRAGMA foreign_keys = ON;")
        cur.execute("PRAGMA cipher_memory_security = ON;")
        cur.execute("PRAGMA kdf_iter = 256000;")
        self.conn.commit()
        self.logger.info("Connected to SQLite DB at %s", self.db_path)

    def init_schema(self):
        cur = self.conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS child_profile(
          id TEXT PRIMARY KEY,
          name TEXT,
          os_user TEXT,
          timezone TEXT,
          strictness TEXT DEFAULT 'standard',
          age INTEGER DEFAULT 12,
          created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS event(
          id TEXT PRIMARY KEY,
          child_id TEXT,
          ts INTEGER,
          kind TEXT,
          url TEXT,
          title TEXT,
          tab_id TEXT,
          referrer TEXT,
          data_json TEXT,
          FOREIGN KEY(child_id) REFERENCES child_profile(id)
        );
        CREATE TABLE IF NOT EXISTS analysis(
          id TEXT PRIMARY KEY,
          event_id TEXT,
          model TEXT,
          version TEXT,
          scores_json TEXT,
          label TEXT,
          latency_ms INTEGER,
          FOREIGN KEY(event_id) REFERENCES event(id)
        );
        CREATE TABLE IF NOT EXISTS decision(
          id TEXT PRIMARY KEY,
          event_id TEXT,
          policy_version TEXT,
          action TEXT,
          reason TEXT,
          details_json TEXT,
          original_action TEXT,
          manual_action TEXT,
          manual_flagged INTEGER DEFAULT 0,
          manual_processed INTEGER DEFAULT 0,
          manual_updated_at INTEGER,
          FOREIGN KEY(event_id) REFERENCES event(id)
        );
        CREATE TABLE IF NOT EXISTS settings(
          key TEXT PRIMARY KEY,
          value TEXT
        );
        """)
        self.conn.commit()
        # Ensure new columns exist for older databases
        cur.execute("PRAGMA table_info(child_profile)")
        cols = {row[1] for row in cur.fetchall()}
        if "strictness" not in cols:
            cur.execute("ALTER TABLE child_profile ADD COLUMN strictness TEXT DEFAULT 'standard'")
        if "age" not in cols:
            cur.execute("ALTER TABLE child_profile ADD COLUMN age INTEGER DEFAULT 12")
        cur.execute("PRAGMA table_info(decision)")
        decision_cols = {row[1] for row in cur.fetchall()}
        if "original_action" not in decision_cols:
            cur.execute("ALTER TABLE decision ADD COLUMN original_action TEXT")
        if "manual_action" not in decision_cols:
            cur.execute("ALTER TABLE decision ADD COLUMN manual_action TEXT")
        if "manual_flagged" not in decision_cols:
            cur.execute("ALTER TABLE decision ADD COLUMN manual_flagged INTEGER DEFAULT 0")
        if "manual_processed" not in decision_cols:
            cur.execute("ALTER TABLE decision ADD COLUMN manual_processed INTEGER DEFAULT 0")
        if "manual_updated_at" not in decision_cols:
            cur.execute("ALTER TABLE decision ADD COLUMN manual_updated_at INTEGER")
        cur.execute("UPDATE decision SET original_action = action WHERE original_action IS NULL")
        self.conn.commit()

    def add_child_profile(self, child_id: str, name="", os_user="", timezone="", strictness: str = "standard", age: int = 12):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO child_profile(id, name, os_user, timezone, strictness, age, created_at) VALUES (?, ?, ?, ?, ?, ?, strftime('%s','now')*1000)",
            (child_id, name, os_user, timezone, strictness, age),
        )
        self.conn.commit()
        self.logger.info("Ensured child profile exists id=%s strictness=%s age=%s", child_id, strictness, age)

    def get_child_profile(self, child_id: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM child_profile WHERE id=?", (child_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))

    def update_child_profile(self, child_id: str, strictness: Optional[str] = None, age: Optional[int] = None):
        updates = []
        params: List[Any] = []
        if strictness is not None:
            updates.append("strictness=?")
            params.append(strictness)
        if age is not None:
            updates.append("age=?")
            params.append(age)
        if not updates:
            return
        params.append(child_id)
        cur = self.conn.cursor()
        cur.execute(f"UPDATE child_profile SET {', '.join(updates)} WHERE id=?", params)
        self.conn.commit()
        self.logger.info("Updated child profile id=%s strictness=%s age=%s", child_id, strictness, age)

    def add_event(self, event: Dict[str, Any]) -> str:
        event_id = event.get("id") or f"evt_{uuid.uuid4().hex}"
        child_id = event.get("child_id", "child_default")
        self.add_child_profile(child_id)
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO event(id, child_id, ts, kind, url, title, tab_id, referrer, data_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                child_id,
                event.get("ts"),
                event.get("kind"),
                event.get("url"),
                event.get("title"),
                event.get("tab_id"),
                event.get("referrer"),
                event.get("data_json") or "",
            ),
        )
        self.conn.commit()
        self.logger.info("Inserted event id=%s child_id=%s kind=%s url=%s", event_id, child_id, event.get("kind"), event.get("url"))
        return event_id

    def update_event_data_json(self, event_id: str, data_json: str):
        cur = self.conn.cursor()
        cur.execute("UPDATE event SET data_json=? WHERE id=?", (data_json or "", event_id))
        self.conn.commit()
        self.logger.info("Updated event data_json id=%s", event_id)

    def add_analysis(self, event_id: str, model: str, version: str, scores: Dict[str, Any], label: str = "", latency_ms: Optional[int] = None) -> str:
        analysis_id = f"ana_{uuid.uuid4().hex}"
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO analysis(id, event_id, model, version, scores_json, label, latency_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (analysis_id, event_id, model, version, json.dumps(scores), label, latency_ms),
        )
        self.conn.commit()
        self.logger.info("Recorded analysis id=%s event_id=%s model=%s", analysis_id, event_id, model)
        return analysis_id

    def add_decision(self, event_id: str, policy_version: str, action: str, reason: str = "", details: Optional[Dict[str, Any]] = None) -> str:
        decision_id = f"dec_{uuid.uuid4().hex}"
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO decision(id, event_id, policy_version, action, reason, details_json, original_action, manual_flagged, manual_processed) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0)",
            (decision_id, event_id, policy_version, action, reason, json.dumps(details or {}), action),
        )
        self.conn.commit()
        self.logger.info("Stored decision id=%s event_id=%s action=%s", decision_id, event_id, action)
        return decision_id

    def get_recent_events(self, child_id: Optional[str], limit: int):
        cur = self.conn.cursor()
        if child_id:
            cur.execute("SELECT * FROM event WHERE child_id=? ORDER BY ts DESC LIMIT ?", (child_id, limit))
        else:
            cur.execute("SELECT * FROM event ORDER BY ts DESC LIMIT ?", (limit,))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def get_decision_with_event(self, decision_id: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT d.*, e.url, e.title, e.ts, e.child_id
            FROM decision d JOIN event e ON d.event_id=e.id
            WHERE d.id=?
            """,
            (decision_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        data = dict(zip(cols, row))
        if data.get("details_json"):
            try:
                data["details_json"] = json.loads(data["details_json"])
            except Exception:
                data["details_json"] = {}
        return data

    def override_decision(self, decision_id: str, new_action: str) -> Optional[Dict[str, Any]]:
        now_ms = int(time.time() * 1000)
        cur = self.conn.cursor()
        cur.execute(
            """
            UPDATE decision
            SET action=?, manual_action=?, manual_flagged=1, manual_processed=0, manual_updated_at=?
            WHERE id=?
            """,
            (new_action, new_action, now_ms, decision_id),
        )
        if cur.rowcount == 0:
            self.conn.commit()
            return None
        self.conn.commit()
        self.logger.info("Decision override id=%s new_action=%s", decision_id, new_action)
        return self.get_decision_with_event(decision_id)

    def fetch_unprocessed_overrides(self, limit: int = 50) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT d.*, e.url, e.title, e.ts, e.child_id
            FROM decision d
            JOIN event e ON d.event_id = e.id
            WHERE d.manual_flagged=1 AND d.manual_processed=0
            ORDER BY d.manual_updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        cols = [c[0] for c in cur.description]
        results = []
        for row in rows:
            data = dict(zip(cols, row))
            if data.get("details_json"):
                try:
                    data["details_json"] = json.loads(data["details_json"])
                except Exception:
                    data["details_json"] = {}
            results.append(data)
        return results

    def mark_override_processed(self, decision_ids: List[str]) -> None:
        if not decision_ids:
            return
        cur = self.conn.cursor()
        placeholders = ",".join("?" for _ in decision_ids)
        cur.execute(
            f"UPDATE decision SET manual_processed=1 WHERE id IN ({placeholders})",
            tuple(decision_ids),
        )
        self.conn.commit()

    def get_setting(self, key: str) -> Optional[str]:
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else None

    def set_setting(self, key: str, value: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO settings(key,value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    def get_recent_decisions(self, child_id: Optional[str], limit: int):
        cur = self.conn.cursor()
        base_query = """
            SELECT
                d.id,
                d.event_id,
                d.policy_version,
                d.action,
                d.reason,
                d.details_json,
                d.original_action,
                d.manual_action,
                d.manual_flagged,
                d.manual_processed,
                d.manual_updated_at,
                e.url,
                e.title,
                e.ts,
                e.child_id
            FROM decision d
            JOIN event e ON d.event_id = e.id
        """
        if child_id:
            cur.execute(
                base_query + " WHERE e.child_id=? ORDER BY e.ts DESC LIMIT ?",
                (child_id, limit),
            )
        else:
            cur.execute(
                base_query + " ORDER BY e.ts DESC LIMIT ?",
                (limit,),
            )
        cols = [c[0] for c in cur.description]
        rows = []
        for r in cur.fetchall():
            data = dict(zip(cols, r))
            if data.get("details_json"):
                try:
                    data["details_json"] = json.loads(data["details_json"])
                except Exception:
                    data["details_json"] = {}
            rows.append(data)
        return rows

    def get_active_child_id(self) -> Optional[str]:
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key='active_child_id'")
        row = cur.fetchone()
        return row[0] if row else None

    def set_active_child_id(self, child_id: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO settings(key,value) VALUES('active_child_id', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (child_id,),
        )
        self.conn.commit()

db = Database()
db.connect()
db.init_schema()
