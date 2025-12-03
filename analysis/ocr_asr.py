from __future__ import annotations
import io, base64, os
from pathlib import Path
from typing import Optional
from PIL import Image
import numpy as np

# PaddleOCR tries to download models into $HOME/.paddleocr. Force a project-local
# cache so we don't depend on a writable HOME in sandboxed setups.
cache_dir = Path(__file__).resolve().parents[1] / ".paddleocr_cache"
cache_dir.mkdir(parents=True, exist_ok=True)
os.environ["HOME"] = str(cache_dir)
os.environ["PPOCR_HOME"] = str(cache_dir)

from paddleocr import PaddleOCR

_OCR: Optional[PaddleOCR] = None

def _get_ocr() -> PaddleOCR:
    global _OCR
    if _OCR is None:
        # Older paddleocr versions do not accept show_log; keep args minimal for compatibility.
        _OCR = PaddleOCR(use_angle_cls=True, lang='en')
    return _OCR

def ocr_image_b64(b64: str) -> str:
    raw = base64.b64decode(b64)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    arr = np.array(img)
    ocr = _get_ocr()
    res = ocr.ocr(arr, cls=True)
    lines = []
    for page in res or []:
        for it in page or []:
            try:
                txt = it[1][0]
            except Exception:
                txt = None
            if txt:
                lines.append(txt)
    return " ".join(lines).strip()
