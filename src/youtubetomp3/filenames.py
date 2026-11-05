"""Turn a video title into a file name that Windows and macOS can store."""

from __future__ import annotations

import re

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
_MAX_STEM = 150


def sanitize_filename(title: str, fallback: str) -> str:
    """Return a file stem. The title shown in the list is left unchanged."""
    cleaned = _ILLEGAL.sub(" ", title or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        cleaned = (fallback or "video").strip(" .") or "video"
    if len(cleaned) > _MAX_STEM:
        cleaned = cleaned[:_MAX_STEM].rstrip(" .")
    if cleaned.upper() in _WINDOWS_RESERVED:
        cleaned = f"{cleaned}_"
    return cleaned


def mp3_name(title: str, fallback: str) -> str:
    return f"{sanitize_filename(title, fallback)}.mp3"
