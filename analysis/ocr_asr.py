from __future__ import annotations
import io, json, base64
from typing import Dict, Any, Optional, Tuple, List
from PIL import Image
import pytesseract
from faster_whisper import WhisperModel

from core.config import settings

_whisper: Optional[WhisperModel] = None
def _get_whisper():
    global _whisper
    if _whisper is None:
        _whisper = WhisperModel(settings.whisper_model, device="auto", compute_type="int8")
    return _whisper

def ocr_image_b64(b64: str, lang: str = "eng") -> str:
    raw = base64.b64decode(b64)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    text = pytesseract.image_to_string(img, lang=lang)
    return text.strip()

def asr_audio_b64(b64: str) -> str:
    # Expect a short WAV/MP3/MP4 chunk base64; faster-whisper supports file path or audio array.
    # For simplicity, write to temp buffer.
    import tempfile
    raw = base64.b64decode(b64)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
        f.write(raw); f.flush()
        model = _get_whisper()
        segments, info = model.transcribe(f.name, beam_size=1, vad_filter=True)
        text = " ".join(seg.text.strip() for seg in segments if seg.text)
        return text.strip()
