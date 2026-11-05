from datetime import date
from pathlib import Path

from youtubetomp3.downloader import DownloadResult
from youtubetomp3.queue import run_queue, summary_text
from youtubetomp3.videos import Video


def _video(video_id: str, title: str) -> Video:
    return Video(video_id, title, 30, date(2024, 1, 1), f"https://www.youtube.com/watch?v={video_id}")


def test_a_failure_does_not_stop_the_queue(tmp_path: Path):
    calls = []

    def download(video, destination):
        calls.append(video.video_id)
        if video.video_id == "a":
            return DownloadResult("fail", "removed")
        return DownloadResult("ok")

    summary = run_queue(
        [_video("a", "One"), _video("b", "Two")],
        tmp_path,
        file_exists=lambda path: False,
        ask_overwrite=lambda name: True,
        download_file=download,
        should_cancel=lambda: False,
        on_state=lambda *args: None,
        on_progress=lambda *args: None,
    )
    assert calls == ["a", "b"]
    assert summary_text(summary) == "1 succeeded, 1 failed."


def test_declining_overwrite_cancels_the_rest(tmp_path: Path):
    calls = []

    def download(video, destination):
        calls.append(video.video_id)
        return DownloadResult("ok")

    summary = run_queue(
        [_video("a", "One"), _video("b", "Two")],
        tmp_path,
        file_exists=lambda path: path.name.startswith("Two"),
        ask_overwrite=lambda name: False,
        download_file=download,
        should_cancel=lambda: False,
        on_state=lambda *args: None,
        on_progress=lambda *args: None,
    )
    assert calls == ["a"]
    assert summary.cancelled is True
    assert summary.failed == 0
    assert summary_text(summary) == "Cancelled. 1 succeeded, 0 failed."


def test_cancel_does_not_count_the_current_file_as_a_failure(tmp_path: Path):
    summary = run_queue(
        [_video("a", "One"), _video("b", "Two")],
        tmp_path,
        file_exists=lambda path: False,
        ask_overwrite=lambda name: True,
        download_file=lambda video, destination: DownloadResult("cancel"),
        should_cancel=lambda: False,
        on_state=lambda *args: None,
        on_progress=lambda *args: None,
    )
    assert summary.succeeded == 0
    assert summary.failed == 0
    assert summary.cancelled is True
