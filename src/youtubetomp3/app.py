"""Start the YoutubeToMp3 window."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from youtubetomp3.window import MainWindow


def main() -> int:
    # A bundled app has no Python interpreter. Downloads start this same executable again.
    if getattr(sys, "frozen", False) and len(sys.argv) > 1 and sys.argv[1] == "--yt-dlp":
        from yt_dlp import main as yt_dlp_main

        sys.argv = [sys.argv[0], *sys.argv[2:]]
        yt_dlp_main()
        return 0
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName("YoutubeToMp3")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
