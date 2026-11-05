"""Accept a YouTube channel URL and point it at that channel's videos tab."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
_CHANNEL_KINDS = {"channel", "c", "user"}
_NOT_A_CHANNEL = {
    "watch",
    "playlist",
    "shorts",
    "live",
    "embed",
    "results",
    "feed",
    "feeds",
    "clip",
    "source",
}


class UrlError(ValueError):
    """The text in the box is not a channel URL."""


def normalize_channel_videos_url(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        raise UrlError("Paste a channel URL.")
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host not in _HOSTS:
        raise UrlError("That is not a YouTube channel URL.")

    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        raise UrlError("That is not a YouTube channel URL.")

    head = parts[0]
    if head in _NOT_A_CHANNEL:
        raise UrlError(
            "Paste a channel URL. This box does not take a video, playlist, or Shorts link."
        )
    if head.startswith("@") and len(head) > 1:
        base = f"/{head}"
    elif head in _CHANNEL_KINDS and len(parts) >= 2:
        base = f"/{head}/{parts[1]}"
    else:
        raise UrlError("That is not a YouTube channel URL.")

    return urlunparse(("https", "www.youtube.com", f"{base}/videos", "", "", ""))
