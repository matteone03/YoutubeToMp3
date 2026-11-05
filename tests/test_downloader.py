import subprocess
from datetime import date
from pathlib import Path

from youtubetomp3.downloader import (
    CancelToken,
    build_command,
    download_to_file,
    parse_progress,
)
from youtubetomp3.videos import Video


def test_progress_lines():
    assert parse_progress("[download]  45.2% of 3.40MiB at 1.00MiB/s ETA 00:02") == 45
    assert parse_progress("[download] 100% of 3.40MiB") == 100
    assert parse_progress("[ExtractAudio] Destination: song.mp3") is None


def test_command_requests_a_192k_mp3_without_embedded_metadata():
    command = build_command("https://www.youtube.com/watch?v=abc", "audio.%(ext)s", "/ffmpeg")
    assert "--audio-format" in command and "mp3" in command
    assert "192K" in command
    assert "--embed-metadata" not in command
    assert "--embed-thumbnail" not in command
    assert command[-1] == "https://www.youtube.com/watch?v=abc"


def test_successful_download_moves_the_mp3_into_place(tmp_path: Path, monkeypatch):
    destination = tmp_path / "Interview.mp3"

    def fake_popen(command, **kwargs):
        template = command[command.index("--output") + 1]
        folder = Path(template).parent
        (folder / "audio.mp3").write_bytes(b"mp3")

        class Proc:
            pid = 4321
            returncode = 0
            stdout = iter(["[download]  50.0% of 1.00MiB\n", "[download] 100% of 1.00MiB\n"])

            def poll(self):
                return None

            def wait(self, timeout=None):
                self.returncode = 0
                return 0

        return Proc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("youtubetomp3.downloader.ffmpeg_executable", lambda: "/ffmpeg")
    seen = []
    result = download_to_file(
        Video("abc", "Interview", 10, date(2024, 1, 1), "https://www.youtube.com/watch?v=abc"),
        destination,
        seen.append,
        CancelToken(),
    )
    assert result.status == "ok"
    assert destination.read_bytes() == b"mp3"
    assert seen[-1] == 100
    assert not list(tmp_path.glob("*.partial"))


def test_yt_dlp_module_starts():
    completed = subprocess.run(
        [__import__("sys").executable, "-m", "yt_dlp", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip()
