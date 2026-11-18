"""Download the selected videos, up to three at a time."""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from youtubetomp3.downloader import DownloadResult
from youtubetomp3.filenames import mp3_name
from youtubetomp3.videos import Video

PARALLEL_DOWNLOADS = 3


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
    cancelled = False
    lock = threading.Lock()
    reserved: dict[Path, threading.Event] = {}
    reserved_lock = threading.Lock()

    def mark_cancelled() -> None:
        nonlocal cancelled
        with lock:
            cancelled = True

    def run_one(video: Video, destination: Path, finished: threading.Event) -> None:
        nonlocal succeeded, failed
        try:
            if should_cancel():
                mark_cancelled()
                return
            on_state(video.video_id, "working", "")
            on_progress(video.video_id, 0)
            result: DownloadResult = download_file(video, destination)
            if result.status == "cancel":
                on_state(video.video_id, "", "")
                mark_cancelled()
                return
            if result.status == "ok":
                with lock:
                    succeeded += 1
                on_state(video.video_id, "done", "")
                on_progress(video.video_id, 100)
                return
            with lock:
                failed += 1
            on_state(video.video_id, "failed", result.detail or "Download failed.")
        finally:
            finished.set()
            with reserved_lock:
                if reserved.get(destination) is finished:
                    reserved.pop(destination, None)

    futures: list[Future[None]] = []
    with ThreadPoolExecutor(max_workers=PARALLEL_DOWNLOADS) as pool:
        for video in videos:
            if should_cancel():
                mark_cancelled()
                break
            filename = mp3_name(video.title, video.video_id)
            destination = folder / filename
            while True:
                with reserved_lock:
                    pending = reserved.get(destination)
                if pending is None:
                    break
                pending.wait()
            if should_cancel():
                mark_cancelled()
                break
            if file_exists(destination):
                if not ask_overwrite(filename):
                    mark_cancelled()
                    break
            if should_cancel():
                mark_cancelled()
                break
            finished = threading.Event()
            with reserved_lock:
                reserved[destination] = finished
            try:
                futures.append(pool.submit(run_one, video, destination, finished))
            except Exception:
                finished.set()
                with reserved_lock:
                    if reserved.get(destination) is finished:
                        reserved.pop(destination, None)
                raise
        for future in futures:
            future.result()
    return RunSummary(succeeded, failed, cancelled)
