from __future__ import annotations
import os, json, uuid
from typing import Any, Dict, Optional, List
from pysqlcipher3 import dbapi2 as sqlcipher
from .config import settings

class Database:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.db_path
        self.conn: Optional[sqlcipher.Connection] = None

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
        self.conn.commit()

    def add_child_profile(self, child_id: str, name="", os_user="", timezone="", strictness: str = "standard", age: int = 12):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO child_profile(id, name, os_user, timezone, strictness, age, created_at) VALUES (?, ?, ?, ?, ?, ?, strftime('%s','now')*1000)",
            (child_id, name, os_user, timezone, strictness, age),
        )
        self.conn.commit()

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
        return event_id

    def update_event_data_json(self, event_id: str, data_json: str):
        cur = self.conn.cursor()
        cur.execute("UPDATE event SET data_json=? WHERE id=?", (data_json or "", event_id))
        self.conn.commit()

    def add_analysis(self, event_id: str, model: str, version: str, scores: Dict[str, Any], label: str = "", latency_ms: Optional[int] = None) -> str:
        analysis_id = f"ana_{uuid.uuid4().hex}"
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO analysis(id, event_id, model, version, scores_json, label, latency_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (analysis_id, event_id, model, version, json.dumps(scores), label, latency_ms),
        )
        self.conn.commit()
        return analysis_id

    def add_decision(self, event_id: str, policy_version: str, action: str, reason: str = "", details: Optional[Dict[str, Any]] = None) -> str:
        decision_id = f"dec_{uuid.uuid4().hex}"
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO decision(id, event_id, policy_version, action, reason, details_json) VALUES (?, ?, ?, ?, ?, ?)",
            (decision_id, event_id, policy_version, action, reason, json.dumps(details or {})),
        )
        self.conn.commit()
        return decision_id

    def get_recent_events(self, child_id: Optional[str], limit: int):
        cur = self.conn.cursor()
        if child_id:
            cur.execute("SELECT * FROM event WHERE child_id=? ORDER BY ts DESC LIMIT ?", (child_id, limit))
        else:
            cur.execute("SELECT * FROM event ORDER BY ts DESC LIMIT ?", (limit,))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def get_recent_decisions(self, child_id: Optional[str], limit: int):
        cur = self.conn.cursor()
        if child_id:
            cur.execute(
                """SELECT d.action, d.reason, d.details_json, e.url, e.title, e.ts
                   FROM decision d JOIN event e ON d.event_id=e.id
                   WHERE e.child_id=? ORDER BY e.ts DESC LIMIT ?""", (child_id, limit)
            )
        else:
            cur.execute(
                """SELECT d.action, d.reason, d.details_json, e.url, e.title, e.ts
                   FROM decision d JOIN event e ON d.event_id=e.id
                   ORDER BY e.ts DESC LIMIT ?""", (limit,)
            )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

db = Database()
db.connect()
db.init_schema()
