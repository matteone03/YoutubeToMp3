"""Run the selected videos one at a time."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from youtubetomp3.downloader import DownloadResult
from youtubetomp3.filenames import mp3_name
from youtubetomp3.videos import Video


@dataclass(frozen=True)
class RunSummary:
    succeeded: int
    failed: int
    cancelled: bool


def summary_text(summary: RunSummary) -> str:
    counts = f"{summary.succeeded} succeeded, {summary.failed} failed."
    if summary.cancelled:
        return f"Cancelled. {counts}"
    return counts


def run_queue(
    videos: list[Video],
    folder: Path,
    *,
    file_exists,
    ask_overwrite,
    download_file,
    should_cancel,
    on_state,
    on_progress,
) -> RunSummary:
    succeeded = 0
    failed = 0
    for video in videos:
        if should_cancel():
            return RunSummary(succeeded, failed, True)
        filename = mp3_name(video.title, video.video_id)
        destination = folder / filename
        if file_exists(destination):
            if not ask_overwrite(filename):
                return RunSummary(succeeded, failed, True)
        if should_cancel():
            return RunSummary(succeeded, failed, True)
        on_state(video.video_id, "working", "")
        on_progress(video.video_id, 0)
        result: DownloadResult = download_file(video, destination)
        if result.status == "cancel" or should_cancel():
            on_state(video.video_id, "", "")
            return RunSummary(succeeded, failed, True)
        if result.status == "ok":
            succeeded += 1
            on_state(video.video_id, "done", "")
            on_progress(video.video_id, 100)
        else:
            failed += 1
            on_state(video.video_id, "failed", result.detail or "Download failed.")
    return RunSummary(succeeded, failed, False)
