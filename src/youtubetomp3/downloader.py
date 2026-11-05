"""Download one video as a 192 kbps MP3 in a child process."""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from youtubetomp3.videos import Video

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DownloadResult:
    status: str
    detail: str = ""


class CancelToken:
    """Set from the UI thread. The download process is killed when this trips."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    def is_set(self) -> bool:
        return self._event.is_set()

    def attach(self, proc: subprocess.Popen[str]) -> None:
        with self._lock:
            self._proc = proc
            already = self._event.is_set()
        if already:
            terminate_process(proc)

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            proc = self._proc
        if proc is not None:
            terminate_process(proc)


def build_command(video_url: str, output_template: str, ffmpeg: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "yt_dlp",
        "--newline",
        "--no-playlist",
        "--no-warnings",
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "192K",
        "--ffmpeg-location",
        ffmpeg,
        "--output",
        output_template,
        "--force-overwrites",
        video_url,
    ]


def parse_progress(line: str) -> int | None:
    marker = "[download]"
    if marker not in line or "%" not in line:
        return None
    after = line.split(marker, 1)[1]
    token = after.strip().split("%", 1)[0].strip()
    try:
        value = float(token.split()[-1])
    except (ValueError, IndexError):
        return None
    return max(0, min(100, int(value)))


def ffmpeg_executable() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def download_to_file(
    video: Video,
    destination: Path,
    on_progress,
    cancel: CancelToken,
) -> DownloadResult:
    """Write the MP3 only after the encode finishes. A cancel leaves no partial MP3."""
    if cancel.is_set():
        return DownloadResult("cancel")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".partial")
    lines: list[str] = []
    try:
        ffmpeg = ffmpeg_executable()
    except Exception:
        logger.exception("ffmpeg is not available")
        return DownloadResult("fail", "ffmpeg is not available.")

    with tempfile.TemporaryDirectory(prefix="youtubetomp3-") as temp_dir:
        template = str(Path(temp_dir) / "audio.%(ext)s")
        command = build_command(video.url, template, ffmpeg)
        popen_kwargs: dict = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "bufsize": 1,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        try:
            proc = subprocess.Popen(command, **popen_kwargs)
        except OSError as exc:
            logger.warning("Could not start yt-dlp: %s", exc)
            return DownloadResult("fail", "Could not start the download.")
        cancel.attach(proc)
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            if cancel.is_set():
                terminate_process(proc)
                break
            percent = parse_progress(line)
            if percent is not None:
                on_progress(percent)
        return_code = proc.wait()
        if cancel.is_set():
            _remove(partial)
            return DownloadResult("cancel")
        mp3_files = sorted(Path(temp_dir).glob("*.mp3"))
        if return_code == 0 and len(mp3_files) == 1:
            shutil.move(str(mp3_files[0]), partial)
            os.replace(partial, destination)
            on_progress(100)
            return DownloadResult("ok")
        _remove(partial)
        return DownloadResult("fail", _failure_detail(lines))


def terminate_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            check=False,
        )
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            proc.kill()
        proc.wait(timeout=3)


def _failure_detail(lines: list[str]) -> str:
    for line in reversed(lines):
        text = line.strip()
        if not text or parse_progress(text) is not None:
            continue
        return text[:180]
    return "Download failed."


def _remove(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        logger.warning("Could not remove incomplete file %s", path)
