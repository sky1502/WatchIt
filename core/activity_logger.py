from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_logger: logging.Logger | None = None


def _next_session_path() -> Path:
    today = datetime.now().strftime("%Y%m%d")
    pattern = re.compile(rf"{today}_session_(\d+)\.log")
    existing = sorted(LOG_DIR.glob(f"{today}_session_*.log"))
    next_idx = 1
    for path in existing:
        m = pattern.match(path.name)
        if m:
            next_idx = max(next_idx, int(m.group(1)) + 1)
    return LOG_DIR / f"{today}_session_{next_idx}.log"


def _get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    log_path = _next_session_path()
    logger = logging.getLogger("watchit.activity")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    _logger = logger
    logger.info("=== New WatchIt session log started: %s ===", log_path.name)
    return logger


def log_step(step: str, event: Dict[str, Any], details: Dict[str, Any] | None = None) -> None:
    logger = _get_logger()
    url = event.get("url") or ""
    title = event.get("title") or ""
    payload = details or {}
    try:
        extra = json.dumps(payload, ensure_ascii=False, default=str, indent=2)
    except Exception:
        extra = str(payload)
    logger.info("step=%s\nurl=%s\ntitle=%s\nDETAILS:\n%s\n", step, url, title, extra[:4000])


def log_service_event(event: str, details: Dict[str, Any] | None = None) -> None:
    logger = _get_logger()
    payload = details or {}
    try:
        extra = json.dumps(payload, ensure_ascii=False, default=str, indent=2)
    except Exception:
        extra = str(payload)
    logger.info("service=%s\nDETAILS:\n%s\n", event, extra[:4000])


def log_service_shutdown(details: Dict[str, Any] | None = None) -> None:
    logger = _get_logger()
    payload = details or {}
    try:
        extra = json.dumps(payload, ensure_ascii=False, default=str, indent=2)
    except Exception:
        extra = str(payload)
    logger.info("=== Service shutdown ===\nDETAILS:\n%s\n", extra[:4000])
