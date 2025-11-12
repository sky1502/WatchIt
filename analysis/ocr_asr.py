from __future__ import annotations
import io, base64
from typing import Optional
from PIL import Image
from paddleocr import PaddleOCR
import numpy as np

_OCR: Optional[PaddleOCR] = None

def _get_ocr() -> PaddleOCR:
    global _OCR
    if _OCR is None:
        _OCR = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
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
