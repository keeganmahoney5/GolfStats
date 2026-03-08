"""Extract capture date from image bytes using EXIF when available."""

from datetime import date
from io import BytesIO
from typing import Optional

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

# EXIF tag IDs for date/time
DATETIME_ORIGINAL = 36867  # when photo was taken
DATETIME = 306              # file modification / last modified


def _parse_exif_date(value: str) -> Optional[date]:
    """Parse EXIF date string 'YYYY:MM:DD HH:MM:SS' to date. Returns None if invalid."""
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    try:
        # EXIF format is "YYYY:MM:DD HH:MM:SS"
        date_part = value.split()[0] if value else ""
        if not date_part:
            return None
        # Replace colon with dash for ISO-like parsing
        normalized = date_part.replace(":", "-")
        return date.fromisoformat(normalized)
    except (ValueError, IndexError):
        return None


def get_image_date(image_bytes: bytes) -> Optional[date]:
    """
    Read EXIF from image bytes and return the capture date (date only) if present.
    Prefers DateTimeOriginal (capture time), falls back to DateTime (modification).
    Returns None if no EXIF date is found or if PIL is not available.
    """
    if not _HAS_PIL or not image_bytes:
        return None
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            exif = img.getexif()
            if exif is None:
                return None
            # Prefer DateTimeOriginal (when photo was taken), then DateTime
            for tag_id in (DATETIME_ORIGINAL, DATETIME):
                value = exif.get(tag_id)
                if value:
                    parsed = _parse_exif_date(str(value))
                    if parsed is not None:
                        return parsed
            return None
    except Exception:
        return None
