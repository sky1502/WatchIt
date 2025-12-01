from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Iterable, Mapping, Any

from core.config import settings

logger = logging.getLogger("watchit.screenshot_store")
_BASE_DIR = Path(__file__).resolve().parent.parent


def _resolve_dir() -> Path:
    raw = Path(settings.screenshots_dir).expanduser()
    path = raw if raw.is_absolute() else _BASE_DIR / raw
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_batch(event_id: str, screenshots: Iterable[str], metadata: Mapping[str, Any] | None) -> None:
    base_dir = _resolve_dir() / str(event_id)
    base_dir.mkdir(parents=True, exist_ok=True)
    for idx, b64 in enumerate(screenshots, start=1):
        try:
            blob = base64.b64decode(b64)
        except Exception:
            logger.warning("Skipping invalid screenshot payload for event %s (index %s)", event_id, idx)
            continue
        target = base_dir / f"{idx:02d}.png"
        target.write_bytes(blob)
    if metadata:
        meta_path = base_dir / "metadata.json"
        try:
            meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("Failed to write metadata for event %s", event_id)


async def persist_screenshots_async(event_id: str, screenshots: Iterable[str], metadata: Mapping[str, Any] | None) -> None:
    await asyncio.to_thread(_save_batch, event_id, list(screenshots), metadata or {})
