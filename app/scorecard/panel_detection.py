"""Panel detection and normalisation for scorecard images.

If the image was already warped by the frontend ``ImageWarpEditor``, this
module can be skipped.  Otherwise it tries to locate the rectangular
scorecard panel, score candidates, and perspective-warp it.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np

from ..image_preprocess import auto_detect_corners, order_corners, perspective_warp, Point
from .models import OcrToken


def _text_density_in_rect(
    tokens: List[OcrToken],
    x_min: float, y_min: float,
    x_max: float, y_max: float,
) -> float:
    """Fraction of *tokens* whose centre falls inside the rectangle."""
    if not tokens:
        return 0.0
    inside = sum(
        1 for t in tokens
        if x_min <= t.mid_x <= x_max and y_min <= t.mid_y <= y_max
    )
    return inside / len(tokens)


def _aspect_score(w: float, h: float) -> float:
    """Score how scorecard-like an aspect ratio is (ideal ~2.5-4:1)."""
    if h <= 0 or w <= 0:
        return 0.0
    ratio = max(w, h) / min(w, h)
    if 1.5 <= ratio <= 6.0:
        ideal = 3.0
        return max(0.0, 1.0 - abs(ratio - ideal) / 3.0)
    return 0.0


def _area_score(quad_area: float, img_area: float) -> float:
    """Larger panels relative to the image score higher, up to 0.95."""
    if img_area <= 0:
        return 0.0
    frac = quad_area / img_area
    if frac < 0.03:
        return 0.0
    return min(frac / 0.8, 1.0)


def detect_and_normalise(
    image_bytes: bytes,
    tokens: Optional[List[OcrToken]] = None,
    skip_if_warped: bool = False,
) -> Tuple[bytes, bool, float]:
    """Detect the scorecard panel and return a perspective-corrected crop.

    Returns
    -------
    (normalised_image_bytes, panel_was_detected, confidence)
    """
    if skip_if_warped:
        return image_bytes, False, 1.0

    corners = auto_detect_corners(image_bytes)
    if corners is None:
        return image_bytes, False, 0.0

    buf = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        return image_bytes, False, 0.0

    h, w = img.shape[:2]
    img_area = float(h * w)

    ordered = order_corners(corners)
    quad_area = float(cv2.contourArea(ordered))

    tl, tr, br, bl = ordered
    panel_w = float(np.linalg.norm(tr - tl))
    panel_h = float(np.linalg.norm(bl - tl))

    a_score = _area_score(quad_area, img_area)
    asp_score = _aspect_score(panel_w, panel_h)

    density = 0.5
    if tokens:
        density = _text_density_in_rect(
            tokens,
            float(min(tl[0], bl[0])), float(min(tl[1], tr[1])),
            float(max(tr[0], br[0])), float(max(bl[1], br[1])),
        )

    confidence = 0.4 * a_score + 0.3 * asp_score + 0.3 * min(density * 2, 1.0)

    try:
        warped = perspective_warp(image_bytes, corners)
    except Exception:
        return image_bytes, False, 0.0

    return warped, True, confidence
