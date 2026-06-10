"""
PDF to text conversion library.

Page classification (per page):
  text   — native text layer is substantial → extract with PyMuPDF
  images — no/little text but embedded image objects exist → OCR each image
  raster — no text and no images → render page to pixmap → OCR

Script detection:
  Native-text pages : Unicode character-distribution across CJK ranges
  Image/raster pages: Tesseract OSD (image_to_osd) — fast script probe,
                      no full OCR pass needed

OCR routing:
  CJK-dominated     → PaddleOCR (handles CJK, skewed layouts, mixed scripts)
  Latin-dominated   → Tesseract
  PaddleOCR absent  → Tesseract with user-supplied lang code as fallback

Install PaddleOCR support:
  pip install paddlepaddle paddleocr        # CPU
  pip install paddlepaddle-gpu paddleocr    # GPU
"""

from __future__ import annotations

import io
import unicodedata
from pathlib import Path
from typing import Any, Union

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

# ---------------------------------------------------------------------------
# Optional PaddleOCR import
# ---------------------------------------------------------------------------
try:
    from paddleocr import PaddleOCR as _PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_CHARS_THRESHOLD = 20   # native text chars needed before skipping OCR
CJK_RATIO_THRESHOLD = 0.15 # fraction of non-whitespace chars that are CJK
RASTER_DPI = 300

# CJK Unicode block ranges (inclusive)
_CJK_RANGES: list[tuple[int, int]] = [
    (0x4E00, 0x9FFF),    # CJK Unified Ideographs
    (0x3400, 0x4DBF),    # Extension A
    (0x20000, 0x2A6DF),  # Extension B
    (0x2A700, 0x2CEAF),  # Extensions C–F
    (0xF900, 0xFAFF),    # CJK Compatibility Ideographs
    (0xFF01, 0xFF60),    # Fullwidth Forms (punctuation, letters)
]
_HIRAGANA = (0x3040, 0x309F)
_KATAKANA  = (0x30A0, 0x30FF)
_HANGUL    = (0xAC00, 0xD7AF)

# Tesseract → PaddleOCR lang fallback map (used when PaddleOCR absent)
_PADDLE_TO_TESS_FALLBACK: dict[str, str] = {
    "ch":     "chi_tra+chi_sim",
    "japan":  "jpn",
    "korean": "kor",
    "en":     "eng",
}

# Common PDF ligatures and encoding artefacts
_NORMALIZE_MAP: dict[str, str] = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
    "ﬅ": "st", "ﬆ": "st",
    "­": "",   # soft hyphen
    "\x00":   "",   # null byte
    "�": "",   # replacement character
}

# ---------------------------------------------------------------------------
# Script detection
# ---------------------------------------------------------------------------

def _char_cjk_class(cp: int) -> str | None:
    """Return 'han', 'hiragana', 'katakana', 'hangul', or None."""
    if _HIRAGANA[0] <= cp <= _HIRAGANA[1]:
        return "hiragana"
    if _KATAKANA[0] <= cp <= _KATAKANA[1]:
        return "katakana"
    if _HANGUL[0] <= cp <= _HANGUL[1]:
        return "hangul"
    if any(lo <= cp <= hi for lo, hi in _CJK_RANGES):
        return "han"
    return None


def _detect_script_from_text(text: str) -> tuple[str, str]:
    """
    Analyse Unicode character distribution.

    Returns (broad_script, paddle_lang):
      broad_script : 'cjk' or 'latin'
      paddle_lang  : 'ch', 'japan', 'korean', or 'en'
    """
    counts: dict[str, int] = {"han": 0, "hiragana": 0, "katakana": 0, "hangul": 0, "other": 0}
    for c in text:
        if c.isspace():
            continue
        cls = _char_cjk_class(ord(c))
        counts[cls if cls else "other"] += 1

    total = sum(counts.values())
    if total == 0:
        return "latin", "en"

    cjk_total = counts["han"] + counts["hiragana"] + counts["katakana"] + counts["hangul"]
    if cjk_total / total < CJK_RATIO_THRESHOLD:
        return "latin", "en"

    # Determine dominant CJK sub-script
    if counts["hangul"] >= counts["hiragana"] + counts["katakana"] and counts["hangul"] > 0:
        return "cjk", "korean"
    if counts["hiragana"] + counts["katakana"] > 0:
        return "cjk", "japan"
    return "cjk", "ch"


def _detect_script_from_image(img: Image.Image) -> tuple[str, str]:
    """
    Use Tesseract OSD to probe the script of an image without a full OCR pass.

    Returns (broad_script, paddle_lang). Falls back to ('latin', 'en') on failure.
    """
    try:
        osd = pytesseract.image_to_osd(img, config="--psm 0 -c min_characters_to_try=5")
        for line in osd.splitlines():
            if not line.startswith("Script:"):
                continue
            s = line.split(":", 1)[1].strip().lower()
            if "hangul" in s or "korean" in s:
                return "cjk", "korean"
            if "hiragana" in s or "katakana" in s or "japanese" in s:
                return "cjk", "japan"
            if "han" in s or "chinese" in s:
                return "cjk", "ch"
            return "latin", "en"
    except Exception:
        pass
    return "latin", "en"

# ---------------------------------------------------------------------------
# OCR engines
# ---------------------------------------------------------------------------

_paddle_cache: dict[str, Any] = {}


def _get_paddle(lang: str) -> Any:
    if lang not in _paddle_cache:
        _paddle_cache[lang] = _PaddleOCR(lang=lang)
    return _paddle_cache[lang]


_PADDLE_MAX_SIDE = 960  # pixels — matches PaddleOCR det model's internal default; 1600 causes OOM on CPU
_PADDLE_SCORE_THRESH = 0.75  # drop low-confidence detections (garbled logo fragments etc.)
# Fraction of image width/height that defines the top-left logo exclusion zone.
# Boxes that fall entirely within this corner are suppressed regardless of score,
# because company logos in that region read as real words (e.g. "Health").
_LOGO_ZONE_X = 0.15
_LOGO_ZONE_Y = 0.06


def _resize_for_paddle(img: Image.Image) -> Image.Image:
    w, h = img.size
    long_side = max(w, h)
    if long_side <= _PADDLE_MAX_SIDE:
        return img
    scale = _PADDLE_MAX_SIDE / long_side
    return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def _ocr_paddle(img: Image.Image, lang: str) -> str:
    import numpy as np
    arr = np.array(_resize_for_paddle(img))
    ih, iw = arr.shape[:2]
    logo_x = iw * _LOGO_ZONE_X
    logo_y = ih * _LOGO_ZONE_Y

    results = _get_paddle(lang).predict(arr)
    if not results:
        return ""
    texts = []
    for item in results:
        try:
            data = item.json["res"]
            for text, score, box in zip(data["rec_texts"], data["rec_scores"], data["rec_boxes"]):
                if score < _PADDLE_SCORE_THRESH:
                    continue
                # box is [x0, y0, x1, y1]
                x0, y0, x1, y1 = box
                if x1 <= logo_x and y1 <= logo_y:
                    continue  # entirely within top-left logo zone
                texts.append(text)
        except (KeyError, AttributeError, TypeError):
            pass
    return "\n".join(texts)


def _ocr_tesseract(img: Image.Image, lang: str) -> str:
    return pytesseract.image_to_string(img, lang=lang).strip()


def _ocr_auto(
    img: Image.Image,
    broad_script: str,
    paddle_lang: str,
    tesseract_lang: str,
) -> tuple[str, str]:
    """
    Route to the best OCR engine for the detected script.

    Returns (text, engine_name).
    """
    if broad_script == "cjk" and PADDLEOCR_AVAILABLE:
        try:
            return _ocr_paddle(img, paddle_lang), "paddleocr"
        except Exception:
            pass  # OOM or model error — fall through to Tesseract

    # Fallback: Tesseract — if CJK detected but PaddleOCR absent, try to
    # use a matching Tesseract lang pack rather than the caller's 'eng' default
    if broad_script == "cjk":
        tess_lang = _PADDLE_TO_TESS_FALLBACK.get(paddle_lang, tesseract_lang)
    else:
        tess_lang = tesseract_lang

    try:
        return _ocr_tesseract(img, tess_lang), "tesseract"
    except Exception:
        # Lang pack may not be installed; retry with caller's original lang
        return _ocr_tesseract(img, tesseract_lang), "tesseract"

# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    for old, new in _NORMALIZE_MAP.items():
        text = text.replace(old, new)
    return "".join(
        c for c in text
        if unicodedata.category(c)[0] != "C" or c in "\n\t\r "
    )

# ---------------------------------------------------------------------------
# Page-level helpers
# ---------------------------------------------------------------------------

def _classify_page(page: fitz.Page) -> str:
    native = page.get_text().strip()
    if len(native) >= MIN_CHARS_THRESHOLD:
        return "text"
    if page.get_images(full=True):
        return "images"
    return "raster"


def _text_from_page_native(page: fitz.Page) -> str:
    blocks = page.get_text("blocks", sort=True)
    lines = [b[4].rstrip() for b in blocks if b[6] == 0 and b[4].strip()]
    return _normalize("\n".join(lines))


def _pil_from_pixmap(pix: fitz.Pixmap) -> Image.Image:
    return Image.open(io.BytesIO(pix.tobytes("png")))


def _embedded_pil_images(doc: fitz.Document, page: fitz.Page) -> list[Image.Image]:
    images = []
    for info in page.get_images(full=True):
        try:
            base = doc.extract_image(info[0])
            images.append(Image.open(io.BytesIO(base["image"])))
        except Exception:
            pass
    return images

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def convert_pdf_to_text(
    source: Union[str, Path, bytes],
    ocr_lang: str = "eng",
    page_separator: str = "\n\f\n",
) -> dict:
    """
    Convert a PDF to text.

    Args:
        source:         File path (str/Path) or raw PDF bytes.
        ocr_lang:       Tesseract language code used when Tesseract handles OCR
                        (e.g. "eng", "chi_tra", "eng+chi_tra"). Ignored when
                        PaddleOCR is selected for the page.
        page_separator: String inserted between pages in the combined output.

    Returns:
        {
          text       (str)        : full concatenated text
          pages      (list[dict]) : per-page: number, method, script,
                                    ocr_engine, text
          page_count (int)        : total pages
        }
    """
    pdf_bytes: bytes = (
        Path(source).read_bytes() if isinstance(source, (str, Path)) else source
    )

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_info: list[dict] = []

    for idx in range(len(doc)):
        page = doc[idx]
        kind = _classify_page(page)

        if kind == "text":
            text = _text_from_page_native(page)
            broad_script, _ = _detect_script_from_text(text)
            pages_info.append({
                "number":     idx + 1,
                "method":     "native",
                "script":     broad_script,
                "ocr_engine": None,
                "text":       text,
            })

        elif kind == "images":
            imgs = _embedded_pil_images(doc, page)
            segments: list[str] = []
            engine_used = "tesseract"
            for img in imgs:
                broad_script, paddle_lang = _detect_script_from_image(img)
                seg, eng = _ocr_auto(img, broad_script, paddle_lang, ocr_lang)
                segments.append(seg)
                engine_used = eng  # last engine wins for metadata
            # Infer dominant script from combined text if any
            combined = "\n".join(s for s in segments if s)
            broad_script, _ = _detect_script_from_text(combined) if combined else ("latin", "en")
            pages_info.append({
                "number":     idx + 1,
                "method":     "ocr-images",
                "script":     broad_script,
                "ocr_engine": engine_used,
                "text":       combined,
            })

        else:  # raster
            pix = page.get_pixmap(dpi=RASTER_DPI, colorspace=fitz.csRGB)
            img = _pil_from_pixmap(pix)
            broad_script, paddle_lang = _detect_script_from_image(img)
            text, engine_used = _ocr_auto(img, broad_script, paddle_lang, ocr_lang)
            pages_info.append({
                "number":     idx + 1,
                "method":     "ocr-raster",
                "script":     broad_script,
                "ocr_engine": engine_used,
                "text":       text,
            })

    doc.close()

    full_text = page_separator.join(p["text"] for p in pages_info)
    return {
        "text":       full_text,
        "pages":      pages_info,
        "page_count": len(pages_info),
    }
