"""Video rows, the 30-item page, and list order."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

PAGE_SIZE = 30

_EXCLUDED_AVAILABILITY = {"subscriber_only", "premium_only", "private", "needs_auth"}
_EXCLUDED_LIVE = {"is_live", "is_upcoming"}


@dataclass(frozen=True)
class Video:
    video_id: str
    title: str
    duration_seconds: int | None
    upload_date: date | None
    url: str


@dataclass(frozen=True)
class VideoPage:
    videos: list[Video]
    next_start: int | None


def format_duration(seconds: int | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_date(value: date | None) -> str:
    if value is None:
        return "—"
    return value.isoformat()


def title_matches(title: str, query: str) -> bool:
    folded = query.strip().casefold()
    if not folded:
        return True
    return folded in title.casefold()


def sort_videos(videos: list[Video], newest_first: bool) -> list[Video]:
    """Undated videos stay at the bottom. Equal dates keep their current order."""

    def key(video: Video) -> tuple[int, int]:
        if video.upload_date is None:
            return (1, 0)
        ordinal = video.upload_date.toordinal()
        return (0, -ordinal if newest_first else ordinal)

    return sorted(videos, key=key)


def displayed_videos(videos: list[Video], *, newest_first: bool, query: str) -> list[Video]:
    ordered = sort_videos(videos, newest_first)
    return [video for video in ordered if title_matches(video.title, query)]


def is_regular_video(info: dict | None) -> bool:
    """Keep a normal upload. Drop Shorts, live or upcoming items, and members-only videos."""
    if not info or not info.get("id"):
        return False
    if info.get("_type") == "playlist":
        return False
    url = " ".join(str(info.get(key) or "") for key in ("url", "webpage_url", "original_url"))
    if "/shorts/" in url:
        return False
    if info.get("live_status") in _EXCLUDED_LIVE:
        return False
    if info.get("availability") in _EXCLUDED_AVAILABILITY:
        return False
    return True


def parse_upload_date(info: dict) -> date | None:
    raw = info.get("upload_date") or info.get("release_date")
    if isinstance(raw, str) and len(raw) == 8 and raw.isdigit():
        return date(int(raw[0:4]), int(raw[4:6]), int(raw[6:8]))
    timestamp = info.get("timestamp") or info.get("release_timestamp")
    if isinstance(timestamp, (int, float)) and timestamp > 0:
        return datetime.fromtimestamp(timestamp, timezone.utc).date()
    return None


def video_from_info(info: dict) -> Video | None:
    if not is_regular_video(info):
        return None
    video_id = str(info["id"])
    title = str(info.get("title") or "").strip() or video_id
    duration = info.get("duration")
    duration_seconds = int(duration) if isinstance(duration, (int, float)) and duration >= 0 else None
    return Video(
        video_id=video_id,
        title=title,
        duration_seconds=duration_seconds,
        upload_date=parse_upload_date(info),
        url=f"https://www.youtube.com/watch?v={video_id}",
    )


def page_from_entries(entries, *, start: int, page_size: int = PAGE_SIZE) -> VideoPage:
    raw_count = 0
    videos: list[Video] = []
    seen: set[str] = set()
    for entry in entries:
        if not entry:
            continue
        raw_count += 1
        video = video_from_info(entry)
        if video is None or video.video_id in seen:
            continue
        seen.add(video.video_id)
        videos.append(video)
    next_start = start + page_size if raw_count >= page_size else None
    return VideoPage(videos=videos, next_start=next_start)


def merge_videos(existing: list[Video], extra: list[Video]) -> list[Video]:
    seen = {video.video_id for video in existing}
    merged = list(existing)
    for video in extra:
        if video.video_id in seen:
            continue
        seen.add(video.video_id)
        merged.append(video)
    return merged
