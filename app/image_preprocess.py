"""Perspective-correction helpers for scorecard images.

Provides:
- auto_detect_corners: finds the largest quadrilateral in the image
- order_corners: sorts 4 arbitrary points into TL, TR, BR, BL order
- perspective_warp: applies a 4-point perspective transform
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np


Point = Tuple[float, float]


def order_corners(pts: List[Point]) -> np.ndarray:
    """Return 4 points ordered as [top-left, top-right, bottom-right, bottom-left].

    Uses sum (x+y) for TL/BR and difference (y-x) for TR/BL.
    """
    arr = np.array(pts, dtype=np.float32)
    ordered = np.zeros((4, 2), dtype=np.float32)

    s = arr.sum(axis=1)
    d = np.diff(arr, axis=1).ravel()

    ordered[0] = arr[np.argmin(s)]   # top-left: smallest x+y
    ordered[2] = arr[np.argmax(s)]   # bottom-right: largest x+y
    ordered[1] = arr[np.argmin(d)]   # top-right: smallest y-x
    ordered[3] = arr[np.argmax(d)]   # bottom-left: largest y-x

    return ordered


def _output_size(ordered: np.ndarray) -> Tuple[int, int]:
    """Compute output (width, height) from ordered corner points."""
    tl, tr, br, bl = ordered

    w_top = np.linalg.norm(tr - tl)
    w_bot = np.linalg.norm(br - bl)
    width = int(max(w_top, w_bot))

    h_left = np.linalg.norm(bl - tl)
    h_right = np.linalg.norm(br - tr)
    height = int(max(h_left, h_right))

    return max(width, 1), max(height, 1)


def perspective_warp(
    image_bytes: bytes,
    corners: List[Point],
) -> bytes:
    """Warp *image_bytes* so that *corners* become a rectangle.

    Parameters
    ----------
    image_bytes : raw image file bytes (JPEG/PNG)
    corners : exactly 4 (x, y) points in pixel coordinates

    Returns
    -------
    JPEG-encoded bytes of the corrected image.
    """
    buf = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image")

    ordered = order_corners(corners)
    w, h = _output_size(ordered)

    dst = np.array([
        [0, 0],
        [w - 1, 0],
        [w - 1, h - 1],
        [0, h - 1],
    ], dtype=np.float32)

    matrix = cv2.getPerspectiveTransform(ordered, dst)
    warped = cv2.warpPerspective(img, matrix, (w, h))

    ok, encoded = cv2.imencode(".jpg", warped, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise RuntimeError("Failed to encode corrected image")
    return bytes(encoded)


def _scan_outside_in(gray: np.ndarray) -> Optional[List[Point]]:
    """Find the screen rectangle by scanning inward from each image edge.

    For each of the four sides, walks inward looking for the first strong
    brightness transition (dark room -> bright screen).  Fits a line for each
    side, then intersects adjacent lines to get the four corners.

    Only works when there is a visible dark border around at least part of
    the bright screen area.
    """
    h, w = gray.shape[:2]
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Median brightness of a thin border strip to establish the "dark" baseline
    border = max(int(min(h, w) * 0.03), 4)
    strips = [
        blurred[:border, :],           # top strip
        blurred[h - border:, :],       # bottom strip
        blurred[:, :border],           # left strip
        blurred[:, w - border:],       # right strip
    ]
    dark_level = float(np.median(np.concatenate([s.ravel() for s in strips])))
    bright_level = float(np.median(blurred[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4]))

    # Need meaningful contrast between border and center
    if bright_level - dark_level < 30:
        return None

    threshold = dark_level + (bright_level - dark_level) * 0.4

    # Sample a set of scan lines for each side and record where they cross
    n_samples = 40

    def _find_edge_from_top() -> List[Tuple[float, float]]:
        pts = []
        for xi in np.linspace(w * 0.1, w * 0.9, n_samples):
            col = int(xi)
            column = blurred[:, col].astype(np.float64)
            indices = np.where(column > threshold)[0]
            if len(indices) > 0:
                pts.append((float(col), float(indices[0])))
        return pts

    def _find_edge_from_bottom() -> List[Tuple[float, float]]:
        pts = []
        for xi in np.linspace(w * 0.1, w * 0.9, n_samples):
            col = int(xi)
            column = blurred[:, col].astype(np.float64)
            indices = np.where(column > threshold)[0]
            if len(indices) > 0:
                pts.append((float(col), float(indices[-1])))
        return pts

    def _find_edge_from_left() -> List[Tuple[float, float]]:
        pts = []
        for yi in np.linspace(h * 0.1, h * 0.9, n_samples):
            row = int(yi)
            line = blurred[row, :].astype(np.float64)
            indices = np.where(line > threshold)[0]
            if len(indices) > 0:
                pts.append((float(indices[0]), float(row)))
        return pts

    def _find_edge_from_right() -> List[Tuple[float, float]]:
        pts = []
        for yi in np.linspace(h * 0.1, h * 0.9, n_samples):
            row = int(yi)
            line = blurred[row, :].astype(np.float64)
            indices = np.where(line > threshold)[0]
            if len(indices) > 0:
                pts.append((float(indices[-1]), float(row)))
        return pts

    edges_top = _find_edge_from_top()
    edges_bottom = _find_edge_from_bottom()
    edges_left = _find_edge_from_left()
    edges_right = _find_edge_from_right()

    min_pts = 6
    if any(len(e) < min_pts for e in [edges_top, edges_bottom, edges_left, edges_right]):
        return None

    def _fit_line(pts: List[Tuple[float, float]]) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Fit a robust line using RANSAC-style outlier rejection via cv2.fitLine."""
        arr = np.array(pts, dtype=np.float32)
        # cv2.fitLine returns (vx, vy, x0, y0) -- a direction and a point
        line = cv2.fitLine(arr, cv2.DIST_HUBER, 0, 0.01, 0.01)
        vx, vy, x0, y0 = line.ravel()
        point = np.array([x0, y0], dtype=np.float64)
        direction = np.array([vx, vy], dtype=np.float64)
        return point, direction

    def _intersect(
        p1: np.ndarray, d1: np.ndarray,
        p2: np.ndarray, d2: np.ndarray,
    ) -> Optional[Tuple[float, float]]:
        """Intersection of two lines defined by point + direction."""
        # Solve: p1 + t*d1 = p2 + s*d2
        # => t*d1 - s*d2 = p2 - p1
        A = np.column_stack([d1, -d2])
        b = p2 - p1
        det = A[0, 0] * A[1, 1] - A[0, 1] * A[1, 0]
        if abs(det) < 1e-6:
            return None
        t = (b[0] * A[1, 1] - b[1] * A[0, 1]) / det
        pt = p1 + t * d1
        return (float(pt[0]), float(pt[1]))

    line_top = _fit_line(edges_top)
    line_bottom = _fit_line(edges_bottom)
    line_left = _fit_line(edges_left)
    line_right = _fit_line(edges_right)

    if any(l is None for l in [line_top, line_bottom, line_left, line_right]):
        return None

    pt_top, dt = line_top  # type: ignore[misc]
    pt_bot, db = line_bottom  # type: ignore[misc]
    pt_left, dl = line_left  # type: ignore[misc]
    pt_right, dr = line_right  # type: ignore[misc]

    tl = _intersect(pt_top, dt, pt_left, dl)
    tr = _intersect(pt_top, dt, pt_right, dr)
    br = _intersect(pt_bot, db, pt_right, dr)
    bl = _intersect(pt_bot, db, pt_left, dl)

    if any(c is None for c in [tl, tr, br, bl]):
        return None

    corners = [tl, tr, br, bl]  # type: ignore[list-item]

    # Sanity check: corners should form a reasonable quad inside/near the image
    for cx, cy in corners:
        if cx < -w * 0.15 or cx > w * 1.15 or cy < -h * 0.15 or cy > h * 1.15:
            return None

    # Check area is reasonable (at least 3% of image)
    area = cv2.contourArea(order_corners(corners))
    if area < h * w * 0.03:
        return None

    return corners


def _best_quad_from_contours(
    contours: list,
    min_area: float,
) -> Optional[np.ndarray]:
    """Find the largest ~quadrilateral contour.

    Tries multiple approxPolyDP epsilon values and accepts 4-6 sided polygons
    (using minAreaRect as fallback for >4 sides).
    """
    best_rect: Optional[np.ndarray] = None
    best_area = 0.0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area <= best_area:
            continue

        peri = cv2.arcLength(cnt, True)

        # Try progressively looser approximations
        for eps_mult in (0.015, 0.02, 0.03, 0.04, 0.05):
            approx = cv2.approxPolyDP(cnt, eps_mult * peri, True)
            if len(approx) == 4:
                best_rect = approx
                best_area = area
                break

        if best_area >= area:
            continue

        # For contours that don't simplify to 4 points, use minAreaRect
        if len(cnt) >= 4:
            rect = cv2.minAreaRect(cnt)
            box = cv2.boxPoints(rect)
            box_area = cv2.contourArea(box.astype(np.int32))
            if box_area > min_area and box_area > best_area:
                best_rect = box.reshape(4, 1, 2).astype(np.int32)
                best_area = box_area

    return best_rect


def auto_detect_corners(
    image_bytes: bytes,
) -> Optional[List[Point]]:
    """Detect the bright rectangular scorecard/monitor region in the image.

    Uses multiple strategies in order of reliability:
    1. Brightness threshold (Otsu) -- bright monitor against dark background
    2. Adaptive threshold -- handles uneven lighting
    3. Canny edge detection -- general fallback

    For each binary mask the largest roughly-rectangular contour is sought.
    If no 4-point polygon is found, minAreaRect of the biggest contour is used.

    Returns 4 (x, y) pixel-coordinate points or None.
    """
    buf = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        return None

    h, w = img.shape[:2]
    min_area = h * w * 0.03
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)

    # Strategy 0: Outside-in scan -- most robust for phone-photo-of-monitor
    outside_in = _scan_outside_in(gray)
    if outside_in is not None:
        return outside_in

    # Strategy 1: Otsu threshold -- ideal for bright screen on dark background
    _, otsu_mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    otsu_mask = cv2.morphologyEx(otsu_mask, cv2.MORPH_CLOSE, kernel, iterations=3)
    otsu_mask = cv2.morphologyEx(otsu_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    contours_otsu, _ = cv2.findContours(otsu_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    result = _best_quad_from_contours(contours_otsu, min_area)
    if result is not None:
        return [(float(p[0][0]), float(p[0][1])) for p in result]

    # Strategy 2: Adaptive threshold -- handles partial brightness / edge-of-frame shots
    adapt = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, -10)
    adapt = cv2.morphologyEx(adapt, cv2.MORPH_CLOSE, kernel, iterations=3)
    contours_adapt, _ = cv2.findContours(adapt, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    result = _best_quad_from_contours(contours_adapt, min_area)
    if result is not None:
        return [(float(p[0][0]), float(p[0][1])) for p in result]

    # Strategy 3: Canny edges (original approach, but more lenient)
    for lo, hi in [(30, 100), (50, 150), (75, 200)]:
        edges = cv2.Canny(blurred, lo, hi)
        edges = cv2.dilate(edges, kernel, iterations=2)
        contours_edge, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        result = _best_quad_from_contours(contours_edge, min_area)
        if result is not None:
            return [(float(p[0][0]), float(p[0][1])) for p in result]

    # Strategy 4: last resort -- biggest contour's minAreaRect from the Otsu pass
    if contours_otsu:
        biggest = max(contours_otsu, key=cv2.contourArea)
        if cv2.contourArea(biggest) > min_area and len(biggest) >= 4:
            rect = cv2.minAreaRect(biggest)
            box = cv2.boxPoints(rect)
            return [(float(x), float(y)) for x, y in box]

    return None
