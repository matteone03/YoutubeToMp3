"""Load one page of a channel's videos tab through yt-dlp."""

from __future__ import annotations

import logging

from yt_dlp import YoutubeDL

from youtubetomp3.videos import PAGE_SIZE, VideoPage, page_from_entries

logger = logging.getLogger(__name__)


class ChannelLoadError(Exception):
    """The channel page could not be read. The current list should stay as it is."""


def fetch_video_page(
    channel_videos_url: str,
    start: int,
    page_size: int = PAGE_SIZE,
) -> VideoPage:
    if start < 1:
        raise ValueError("start must be at least 1")
    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "lazy_playlist": True,
        "playliststart": start,
        "playlistend": start + page_size - 1,
        "skip_download": True,
        "ignoreerrors": True,
        "socket_timeout": 30,
        # The videos tab only publishes relative times ("3 days ago"). This asks
        # yt-dlp to turn that text into a date without opening each video.
        "extractor_args": {"youtubetab": {"approximate_date": ["true"]}},
    }
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(channel_videos_url, download=False)
    except Exception as exc:
        logger.warning("Channel list failed for %s", channel_videos_url, exc_info=True)
        raise ChannelLoadError(
            "Could not load that channel. Check the URL and try again."
        ) from exc
    if not info or "entries" not in info:
        raise ChannelLoadError("Could not load that channel. Check the URL and try again.")
    return page_from_entries(info.get("entries") or [], start=start, page_size=page_size)
