from __future__ import annotations
from typing import Dict, Any, List
from urllib.parse import urlparse
from datetime import datetime, time
import zoneinfo
from core.config import settings
from core.db import db

def _parse_time_range(spec: str) -> tuple[time, time]:
    # "21:00-07:00"
    a,b = spec.split("-")
    ah,am = map(int, a.split(":"))
    bh,bm = map(int, b.split(":"))
    return time(ah,am), time(bh,bm)

def _in_quiet_hours(now: datetime, days_csv: str, quiet_spec: str) -> bool:
    days = [d.strip() for d in days_csv.split(",") if d.strip()]
    dow = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][now.weekday()]
    if dow not in days:
        return False
    start, end = _parse_time_range(quiet_spec)
    t = now.time()
    if start <= end:
        return start <= t <= end
    else:
        # wraps midnight
        return not (end < t < start)

def _paused_until() -> int | None:
    cur = db.conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key='paused_until'")
    row = cur.fetchone()
    if not row: return None
    try: return int(row[0])
    except: return None

class PolicyEngine:
    def __init__(self):
        self.policy_version = settings.policy_version
        self.allow_domains = {"wikipedia.org", "khanacademy.org", ".edu"}
        self.block_domains = {"pornhub.com", "xvideos.com", "redtube.com"}
        self.block_threshold = 0.9
        self.warn_threshold  = 0.75

    def decide(self, event: Dict[str, Any], fast_scores: Dict[str, float], judge_json: Dict[str, Any]) -> Dict[str, Any]:
        # Global pause check
        now_ms = int(datetime.now().timestamp()*1000)
        paused = _paused_until()
        if paused and now_ms < paused:
            return {"action":"allow", "reason":"paused", "categories":[]}

        # Schedule (local device timezone)
        now = datetime.now()
        if _in_quiet_hours(now, settings.sched_days, settings.sched_quiet):
            # During quiet hours, allow only educational domains; block others
            url = event.get("url") or ""
            dom = (urlparse(url).netloc or "").lower()
            if not any(a in dom for a in self.allow_domains):
                return {"action":"block", "reason":"schedule quiet hours", "categories":["schedule"]}

        url = event.get("url") or ""
        domain = (urlparse(url).netloc or "").lower()

        # allowlist first
        for a in self.allow_domains:
            if a in domain:
                return {"action":"allow","reason":f"allowlist {a}","categories":[]}

        # hard blocklist next
        for b in self.block_domains:
            if b in domain:
                return {"action":"block","reason":f"blocklist {b}","categories":["adult"]}

        # deterministic thresholds
        if fast_scores.get("sexual",0)>=self.block_threshold:
            return {"action":"block","reason":"sexual score high","categories":["sexual"]}
        if fast_scores.get("violence",0)>=self.warn_threshold or fast_scores.get("profanity",0)>=self.warn_threshold:
            cats=[c for c in ("violence","profanity") if fast_scores.get(c,0)>=self.warn_threshold]
            return {"action":"warn","reason":"prefilter high", "categories":cats}

        # LLM judge
        if judge_json:
            act = judge_json.get("action","allow")
            cats = judge_json.get("categories",[])
            sev  = judge_json.get("severity","low")
            reason = f"llm:{sev}"
            return {"action": act, "reason": reason, "categories": cats}

        return {"action":"allow","reason":"default allow","categories":[]}
