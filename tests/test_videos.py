from datetime import date

from youtubetomp3.videos import (
    Video,
    displayed_videos,
    format_date,
    format_duration,
    is_regular_video,
    page_from_entries,
    sort_videos,
    title_matches,
    video_from_info,
)


def _info(**overrides):
    base = {
        "id": "abc",
        "title": "A regular video",
        "duration": 95,
        "upload_date": "20240131",
        "url": "https://www.youtube.com/watch?v=abc",
        "live_status": "not_live",
        "availability": "public",
    }
    base.update(overrides)
    return base


def test_regular_video_is_kept_including_a_short_duration():
    video = video_from_info(_info(duration=12, title="Brief"))
    assert video is not None
    assert video.duration_seconds == 12
    assert video.upload_date == date(2024, 1, 31)
    assert format_duration(12) == "0:12"
    assert format_duration(3661) == "1:01:01"
    assert format_date(None) == "—"


def test_shorts_live_upcoming_and_members_only_are_dropped():
    assert is_regular_video(_info(url="https://www.youtube.com/shorts/abc")) is False
    assert is_regular_video(_info(live_status="is_live")) is False
    assert is_regular_video(_info(live_status="is_upcoming")) is False
    assert is_regular_video(_info(availability="subscriber_only")) is False
    assert is_regular_video(_info(live_status="was_live")) is True


def test_page_stops_when_a_short_page_comes_back():
    entries = [_info(id="a", title="One"), _info(id="b", title="Two", url="https://www.youtube.com/shorts/b")]
    page = page_from_entries(entries, start=1, page_size=30)
    assert [video.video_id for video in page.videos] == ["a"]
    assert page.next_start is None


def test_full_page_exposes_the_next_start():
    entries = [_info(id=str(index), title=f"Video {index}") for index in range(30)]
    page = page_from_entries(entries, start=31, page_size=30)
    assert len(page.videos) == 30
    assert page.next_start == 61


def test_sort_and_filter():
    videos = [
        Video("old", "Old talk", 10, date(2020, 1, 1), "u"),
        Video("new", "New talk", 10, date(2024, 1, 1), "u"),
        Video("none", "Undated", 10, None, "u"),
    ]
    ordered = sort_videos(videos, newest_first=True)
    assert [video.video_id for video in ordered] == ["new", "old", "none"]
    assert title_matches("New Talk", "talk") is True
    shown = displayed_videos(videos, newest_first=False, query="talk")
    assert [video.video_id for video in shown] == ["old", "new"]
