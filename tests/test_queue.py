import threading
from datetime import date
from pathlib import Path

from youtubetomp3.downloader import DownloadResult
from youtubetomp3.queue import PARALLEL_DOWNLOADS, run_queue, summary_text
from youtubetomp3.videos import Video


def _video(video_id: str, title: str) -> Video:
    return Video(video_id, title, 30, date(2024, 1, 1), f"https://www.youtube.com/watch?v={video_id}")


def _run(videos, folder, **overrides):
    args = {
        "file_exists": lambda path: False,
        "ask_overwrite": lambda name: True,
        "download_file": lambda video, destination: DownloadResult("ok"),
        "should_cancel": lambda: False,
        "on_state": lambda *args: None,
        "on_progress": lambda *args: None,
    }
    args.update(overrides)
    return run_queue(videos, folder, **args)


def test_a_failure_does_not_stop_the_queue(tmp_path: Path):
    calls = []
    lock = threading.Lock()

    def download(video, destination):
        with lock:
            calls.append(video.video_id)
        if video.video_id == "a":
            return DownloadResult("fail", "removed")
        return DownloadResult("ok")

    summary = _run(
        [_video("a", "One"), _video("b", "Two")],
        tmp_path,
        download_file=download,
    )
    assert set(calls) == {"a", "b"}
    assert summary_text(summary) == "1 succeeded, 1 failed."


def test_declining_overwrite_cancels_the_rest(tmp_path: Path):
    calls = []

    def download(video, destination):
        calls.append(video.video_id)
        destination.write_bytes(b"mp3")
        return DownloadResult("ok")

    summary = _run(
        [_video("a", "One"), _video("b", "Two")],
        tmp_path,
        file_exists=lambda path: path.name.startswith("Two"),
        ask_overwrite=lambda name: False,
        download_file=download,
    )
    assert calls == ["a"]
    assert summary.cancelled is True
    assert summary.failed == 0
    assert summary.succeeded == 1
    assert summary_text(summary) == "Cancelled. 1 succeeded, 0 failed."


def test_declining_overwrite_lets_an_in_flight_download_finish(tmp_path: Path):
    started = threading.Event()
    release = threading.Event()

    def download(video, destination):
        started.set()
        assert release.wait(timeout=2)
        destination.write_bytes(b"mp3")
        return DownloadResult("ok")

    def ask_overwrite(filename):
        assert started.wait(timeout=2)
        release.set()
        return False

    summary = _run(
        [_video("a", "One"), _video("b", "Two")],
        tmp_path,
        file_exists=lambda path: path.name.startswith("Two"),
        ask_overwrite=ask_overwrite,
        download_file=download,
    )
    assert summary.cancelled is True
    assert summary.succeeded == 1
    assert summary.failed == 0
    assert (tmp_path / "One.mp3").read_bytes() == b"mp3"
    assert not (tmp_path / "Two.mp3").exists()


def test_cancel_does_not_count_the_current_file_as_a_failure(tmp_path: Path):
    summary = _run(
        [_video("a", "One"), _video("b", "Two")],
        tmp_path,
        download_file=lambda video, destination: DownloadResult("cancel"),
    )
    assert summary.succeeded == 0
    assert summary.failed == 0
    assert summary.cancelled is True


def test_three_downloads_run_at_the_same_time(tmp_path: Path):
    current = 0
    peak = 0
    lock = threading.Lock()
    opened = threading.Event()

    def download(video, destination):
        nonlocal current, peak
        with lock:
            current += 1
            peak = max(peak, current)
            if current >= PARALLEL_DOWNLOADS:
                opened.set()
        assert opened.wait(timeout=2)
        with lock:
            current -= 1
        return DownloadResult("ok")

    videos = [_video(str(index), f"Title {index}") for index in range(PARALLEL_DOWNLOADS + 2)]
    summary = _run(videos, tmp_path, download_file=download)
    assert summary.succeeded == len(videos)
    assert summary.failed == 0
    assert peak == PARALLEL_DOWNLOADS


def test_a_queued_video_does_not_start_after_cancel(tmp_path: Path):
    cancel = threading.Event()
    started = []
    lock = threading.Lock()

    def download(video, destination):
        with lock:
            started.append(video.video_id)
            count = len(started)
        if count >= PARALLEL_DOWNLOADS:
            cancel.set()
        else:
            assert cancel.wait(timeout=2)
        return DownloadResult("cancel")

    videos = [_video(str(index), f"Title {index}") for index in range(PARALLEL_DOWNLOADS + 1)]
    summary = _run(
        videos,
        tmp_path,
        download_file=download,
        should_cancel=cancel.is_set,
    )
    assert summary.cancelled is True
    assert summary.succeeded == 0
    assert summary.failed == 0
    assert str(PARALLEL_DOWNLOADS) not in started
    assert len(started) == PARALLEL_DOWNLOADS


def test_same_file_name_is_not_written_by_two_downloads_at_once(tmp_path: Path):
    current = 0
    peak = 0
    lock = threading.Lock()
    asked = []

    def download(video, destination):
        nonlocal current, peak
        with lock:
            current += 1
            peak = max(peak, current)
        try:
            destination.write_bytes(video.video_id.encode())
            return DownloadResult("ok")
        finally:
            with lock:
                current -= 1

    summary = _run(
        [_video("a", "Same"), _video("b", "Same")],
        tmp_path,
        file_exists=lambda path: path.exists(),
        ask_overwrite=lambda name: asked.append(name) or True,
        download_file=download,
    )
    assert peak == 1
    assert asked == ["Same.mp3"]
    assert summary.succeeded == 2
    assert summary.cancelled is False
    assert (tmp_path / "Same.mp3").read_bytes() == b"b"
