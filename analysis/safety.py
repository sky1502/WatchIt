from __future__ import annotations
import json, re
from typing import Dict, Any, List
from core.config import settings
from .ocr_asr import ocr_image_b64, asr_audio_b64

class SafetyAnalyzer:
    def __init__(self):
        self.violence = ["kill","shoot","gun","fight","blood","weapon"]
        self.sexual   = ["sex","porn","nude","xxx","18+","adult only"]
        self.profanity= ["damn","shit","fuck","bitch"]

        self.re_v = re.compile(r"\b(" + "|".join(map(re.escape, self.violence)) + r")\b", re.I)
        self.re_s = re.compile(r"\b(" + "|".join(map(re.escape, self.sexual)) + r")\b", re.I)
        self.re_p = re.compile(r"\b(" + "|".join(map(re.escape, self.profanity)) + r")\b", re.I)

    def analyze_text(self, text: str) -> Dict[str, float]:
        if not text:
            return {"violence":0.0,"sexual":0.0,"profanity":0.0}
        words = max(1, len(text.split()))
        v = len(self.re_v.findall(text)) / words * 5.0
        s = len(self.re_s.findall(text)) / words * 5.0
        p = len(self.re_p.findall(text)) / words * 5.0
        return {
            "violence": round(min(1.0, v), 3),
            "sexual":   round(min(1.0, s), 3),
            "profanity":round(min(1.0, p), 3),
        }
    
    def analyze_event_fast(self, event: Dict[str, Any]) -> Dict[str, float]:
        text = ""
        data = {}
        if event.get("data_json"):
            try: data = json.loads(event["data_json"])
            except Exception: data = {}

        # DOM / title / search
        if "dom_sample" in data: text += " " + data["dom_sample"]
        if "text" in data:       text += " " + data["text"]
        if event.get("kind") == "search" and event.get("title"):
            text += " " + event["title"]

        # OCR (if screenshots or inline images present & OCR enabled)
        if settings.enable_ocr:
            # Expect base64 screenshots in data["screenshots_b64"] (list), OR hashed images with b64 in cache
            for b64 in (data.get("screenshots_b64") or []):
                try:
                    text += " " + ocr_image_b64(b64)
                except Exception:
                    pass

        # ASR (if audio snippets provided & ASR enabled)
        if settings.enable_asr:
            for b64 in (data.get("audio_b64") or []):
                try:
                    text += " " + asr_audio_b64(b64)
                except Exception:
                    pass

        return self.analyze_text(text)
