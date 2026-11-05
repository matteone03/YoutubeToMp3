"""Start the YoutubeToMp3 window."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from youtubetomp3.window import MainWindow


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName("YoutubeToMp3")
    window = MainWindow()
    window.show()
    return app.exec()
