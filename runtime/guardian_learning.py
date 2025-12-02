from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List

from langchain_ollama import ChatOllama
from langchain.schema import HumanMessage, SystemMessage

from core.config import settings
from core.db import db


class GuardianLearningLoop:
    """Background job that analyzes manual overrides and distills guardian intent."""

    def __init__(self, interval_seconds: float = 3600.0):
        self.interval = interval_seconds
        self.logger = logging.getLogger("watchit.guardian_learning")
        self.client = ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0,
        )

    async def run_forever(self) -> None:
        while True:
            try:
                await self.process_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.exception("Guardian learning loop failed")
            await asyncio.sleep(self.interval)

    async def process_once(self) -> None:
        overrides = db.fetch_unprocessed_overrides(100)
        if not overrides:
            return
        guidance = await asyncio.to_thread(self._infer_guidance, overrides)
        payload = {
            "generated_at": int(time.time()),
            "guidance": guidance.get("guidance") if isinstance(guidance, dict) else guidance,
            "patterns": guidance.get("patterns") if isinstance(guidance, dict) else [],
            "sample_count": len(overrides),
        }
        db.set_setting("guardian_feedback", json.dumps(payload))
        db.mark_override_processed([ov["id"] for ov in overrides])
        self.logger.info("Updated guardian feedback using %s overrides", len(overrides))

    def _infer_guidance(self, overrides: List[Dict[str, Any]]) -> Dict[str, Any]:
        sample_lines = []
        for o in overrides[:15]:
            sample_lines.append(
                f"- URL:{o.get('url')} title:{o.get('title')} original:{o.get('original_action')} manual:{o.get('manual_action') or o.get('action')}"
            )
        prompt = "\n".join(sample_lines) or "No overrides."
        messages = [
            SystemMessage(
                content=(
                    "You review guardian overrides of a parental-control system. "
                    "Infer likely reasons (maturity, educational purpose, harmless fun, etc.) why a guardian corrected decisions."
                    "Respond in JSON with keys 'guidance' (short paragraph) and 'patterns' (array of short bullet strings)."
                )
            ),
            HumanMessage(
                content=(
                    "Recent overrides (each line: url/title/original->manual action):\n"
                    f"{prompt}\n\nSummarize motivations so the model can improve future moderation."
                )
            ),
        ]
        try:
            resp = self.client.invoke(messages)
            raw = resp.content.strip()
        except Exception as exc:
            self.logger.exception("Guardian insight model failed")
            return {"guidance": f"LLM feedback unavailable: {exc}", "patterns": []}
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except Exception:
            self.logger.warning("Guardian feedback JSON parse failed, returning raw text")
        return {"guidance": raw, "patterns": []}
