"""
Google Cloud Vision OCR. Used when GOOGLE_APPLICATION_CREDENTIALS is set.
Returns None when Vision is unavailable or errors so the caller can handle gracefully.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

try:
    from google.cloud import vision
    from google.api_core.exceptions import GoogleAPIError
except ImportError:
    vision = None
    GoogleAPIError = Exception  # noqa: A001

_PREFIX = "[Vision OCR]"


@dataclass
class WordBox:
    """A single word detected by Vision, with its bounding-box midpoint."""
    text: str
    mid_x: float
    mid_y: float
    min_y: float
    max_y: float


def _log(msg: str) -> None:
    """Print to stderr so it always shows in the terminal."""
    print(_PREFIX, msg, file=sys.stderr, flush=True)


def _get_client_and_validate() -> Optional[object]:
    if vision is None:
        _log("Skipped: google-cloud-vision not installed or import failed")
        return None
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path:
        _log("Skipped: GOOGLE_APPLICATION_CREDENTIALS is not set")
        return None
    if not os.path.isfile(creds_path):
        _log(f"Skipped: GOOGLE_APPLICATION_CREDENTIALS path is not a file: {creds_path}")
        return None
    return vision.ImageAnnotatorClient()


def _call_vision(image_bytes: bytes) -> Optional[object]:
    """Send image to Vision API and return the response, or None on failure."""
    client = _get_client_and_validate()
    if client is None:
        return None
    try:
        image = vision.Image(content=image_bytes)
        response = client.document_text_detection(image=image)
        if response.error.message:
            _log(f"Vision API error: {response.error.message}")
            return None
        return response
    except (GoogleAPIError, OSError, ValueError) as e:
        _log(f"Failed: {e}")
        return None


def extract_text_from_image_bytes(image_bytes: bytes) -> Optional[str]:
    """
    Run Google Cloud Vision document_text_detection on image bytes.
    Returns extracted text string, or None if Vision is unavailable or errors.
    """
    response = _call_vision(image_bytes)
    if response is None:
        return None
    if response.full_text_annotation is None:
        _log("Vision API returned no text for this image")
        return None
    text = response.full_text_annotation.text.strip() or None
    if not text:
        _log("Vision API returned empty text")
    return text


def extract_word_boxes_v2(image_bytes: bytes) -> Tuple[Optional[str], list]:
    """Like extract_word_boxes but returns dicts with full bounding geometry.

    Each dict has: text, mid_x, mid_y, min_x, max_x, min_y, max_y, confidence.
    Used by scorecard parse v2 when richer token data is needed.
    """
    response = _call_vision(image_bytes)
    if response is None:
        return None, []

    full_text: Optional[str] = None
    if response.full_text_annotation:
        full_text = response.full_text_annotation.text.strip() or None

    words: list = []
    for page in getattr(response.full_text_annotation, "pages", []):
        for block in page.blocks:
            for paragraph in block.paragraphs:
                for word in paragraph.words:
                    text = "".join(s.text for s in word.symbols)
                    verts = word.bounding_box.vertices
                    xs = [v.x for v in verts]
                    ys = [v.y for v in verts]
                    conf = getattr(word, "confidence", 1.0) or 1.0
                    words.append({
                        "text": text,
                        "mid_x": (min(xs) + max(xs)) / 2,
                        "mid_y": (min(ys) + max(ys)) / 2,
                        "min_x": min(xs),
                        "max_x": max(xs),
                        "min_y": min(ys),
                        "max_y": max(ys),
                        "confidence": float(conf),
                    })
    return full_text, words


def extract_word_boxes(image_bytes: bytes) -> Tuple[Optional[str], List[WordBox]]:
    """
    Run Vision OCR and return (full_text, list_of_word_boxes).
    Each WordBox carries the word text and its bounding-box midpoint so we can
    reconstruct the visual grid layout of a scorecard.
    """
    response = _call_vision(image_bytes)
    if response is None:
        return None, []

    full_text: Optional[str] = None
    if response.full_text_annotation:
        full_text = response.full_text_annotation.text.strip() or None

    words: List[WordBox] = []
    for page in getattr(response.full_text_annotation, "pages", []):
        for block in page.blocks:
            for paragraph in block.paragraphs:
                for word in paragraph.words:
                    text = "".join(s.text for s in word.symbols)
                    verts = word.bounding_box.vertices
                    xs = [v.x for v in verts]
                    ys = [v.y for v in verts]
                    words.append(WordBox(
                        text=text,
                        mid_x=(min(xs) + max(xs)) / 2,
                        mid_y=(min(ys) + max(ys)) / 2,
                        min_y=min(ys),
                        max_y=max(ys),
                    ))
    return full_text, words
