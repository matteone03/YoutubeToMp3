"""The desktop window: channel search, the video table, and the download queue."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from youtubetomp3.downloader import CancelToken, DownloadResult, download_to_file
from youtubetomp3.listing import ChannelLoadError, fetch_video_page
from youtubetomp3.queue import run_queue, summary_text
from youtubetomp3.urls import UrlError, normalize_channel_videos_url
from youtubetomp3.videos import (
    Video,
    displayed_videos,
    format_date,
    format_duration,
    merge_videos,
    sort_videos,
    title_matches,
)

# Cursor's dark theme: near-black surfaces, light gray text, a light primary button.
_TEXT = "#e6e6e6"
_MUTED = "#9a9a9a"
_WINDOW = "#181818"
_CARD = "#262626"
_ROW = "#202020"
_BUTTON = "#2a2a2a"
_BORDER = "#3c3c3c"
_ACCENT = "#e8e8e8"
_PROGRESS = "#4c8dff"
_ERROR = "#f14c4c"
_INK = QBrush(QColor(_TEXT))
_PROGRESS_STYLE = (
    f"QProgressBar {{ color: {_TEXT}; background: {_BUTTON}; border: none; border-radius: 3px; }}"
    f"QProgressBar::chunk {{ background: {_PROGRESS}; border-radius: 3px; }}"
)


def _dark_palette() -> QPalette:
    """Black window and light text for every color group, including dialogs."""
    text = QColor(_TEXT)
    muted = QColor(_MUTED)
    window = QColor(_WINDOW)
    card = QColor(_CARD)
    button = QColor(_BUTTON)
    palette = QPalette()
    for group in (
        QPalette.ColorGroup.Active,
        QPalette.ColorGroup.Inactive,
        QPalette.ColorGroup.Disabled,
    ):
        ink = muted if group == QPalette.ColorGroup.Disabled else text
        palette.setColor(group, QPalette.ColorRole.Window, window)
        palette.setColor(group, QPalette.ColorRole.WindowText, ink)
        palette.setColor(group, QPalette.ColorRole.Base, card)
        palette.setColor(group, QPalette.ColorRole.AlternateBase, QColor(_ROW))
        palette.setColor(group, QPalette.ColorRole.Text, ink)
        palette.setColor(group, QPalette.ColorRole.Button, button)
        palette.setColor(group, QPalette.ColorRole.ButtonText, ink)
        palette.setColor(group, QPalette.ColorRole.PlaceholderText, muted)
        palette.setColor(group, QPalette.ColorRole.ToolTipBase, button)
        palette.setColor(group, QPalette.ColorRole.ToolTipText, text)
        palette.setColor(group, QPalette.ColorRole.Highlight, QColor("#264f78"))
        palette.setColor(group, QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    return palette


class ListWorker(QThread):
    succeeded = Signal(object, object)
    failed = Signal(str)

    def __init__(self, list_page, url: str, start: int) -> None:
        super().__init__()
        self._list_page = list_page
        self._url = url
        self._start = start

    def run(self) -> None:
        try:
            page = self._list_page(self._url, self._start)
        except ChannelLoadError as exc:
            self.failed.emit(str(exc))
            return
        except Exception:
            self.failed.emit("Could not load that channel. Check the URL and try again.")
            return
        self.succeeded.emit(page.videos, page.next_start)


class DownloadWorker(QThread):
    state = Signal(str, str, str)
    progress = Signal(str, int)
    overwrite_requested = Signal(str)
    finished_summary = Signal(object)

    def __init__(self, videos: list[Video], folder: Path, download_file) -> None:
        super().__init__()
        self._videos = videos
        self._folder = folder
        self._download_file = download_file
        self._cancel = CancelToken()
        self._overwrite_event = threading.Event()
        self._overwrite_allow = False

    def request_cancel(self) -> None:
        self._cancel.cancel()
        self.answer_overwrite(False)

    def answer_overwrite(self, allow: bool) -> None:
        if self._cancel.is_set():
            allow = False
        self._overwrite_allow = allow
        self._overwrite_event.set()

    def run(self) -> None:
        def ask_overwrite(filename: str) -> bool:
            self._overwrite_event.clear()
            self._overwrite_allow = False
            self.overwrite_requested.emit(filename)
            self._overwrite_event.wait()
            return self._overwrite_allow

        def download_file(video: Video, destination: Path):
            if self._cancel.is_set():
                return DownloadResult("cancel")
            return self._download_file(
                video,
                destination,
                lambda percent, video_id=video.video_id: self.progress.emit(video_id, percent),
                self._cancel,
            )

        summary = run_queue(
            self._videos,
            self._folder,
            file_exists=lambda path: path.exists(),
            ask_overwrite=ask_overwrite,
            download_file=download_file,
            should_cancel=self._cancel.is_set,
            on_state=lambda video_id, state, detail: self.state.emit(video_id, state, detail),
            on_progress=lambda video_id, percent: self.progress.emit(video_id, percent),
        )
        self.finished_summary.emit(summary)


class MainWindow(QMainWindow):
    def __init__(self, list_page=fetch_video_page, download_file=download_to_file) -> None:
        super().__init__()
        self._list_page = list_page
        self._download_file = download_file
        self._videos: list[Video] = []
        self._checked: set[str] = set()
        self._status: dict[str, str] = {}
        self._details: dict[str, str] = {}
        self._progress: dict[str, int] = {}
        self._row_of: dict[str, int] = {}
        self._channel_url = ""
        self._next_start: int | None = None
        self._loading = False
        self._running = False
        self._updating_table = False
        self._list_worker: ListWorker | None = None
        self._download_worker: DownloadWorker | None = None

        self.setWindowTitle("YoutubeToMp3")
        self.resize(980, 680)
        self.setMinimumSize(760, 520)
        self._build()
        self._apply_style()
        self._set_idle_message()

    def choose_folder(self) -> str:
        return QFileDialog.getExistingDirectory(self, "Choose a folder for the MP3 files")

    def ask_overwrite(self, filename: str) -> bool:
        answer = QMessageBox.question(
            self,
            "Overwrite file",
            f'"{filename}" is already in this folder. Overwrite it?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _build(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        title = QLabel("YoutubeToMp3")
        title.setStyleSheet(f"font-size: 22px; font-weight: 600; color: {_TEXT};")
        subtitle = QLabel("Paste a channel URL, pick videos, and save them as 192 kbps MP3 files.")
        subtitle.setStyleSheet(f"color: {_MUTED};")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        url_row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/@channel")
        self.url_edit.returnPressed.connect(self.on_search)
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.on_search)
        url_row.addWidget(self.url_edit, 1)
        url_row.addWidget(self.search_button)
        layout.addLayout(url_row)

        tools = QHBoxLayout()
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by title")
        self.filter_edit.textChanged.connect(self._apply_filter)
        self.sort_box = QComboBox()
        self.sort_box.addItems(["Newest first", "Oldest first"])
        self.sort_box.currentIndexChanged.connect(self._on_sort_changed)
        self.select_button = QPushButton("Select all")
        self.select_button.clicked.connect(self.select_all_matching)
        self.more_button = QPushButton("Show more")
        self.more_button.clicked.connect(self.on_show_more)
        self.more_button.setEnabled(False)
        tools.addWidget(self.filter_edit, 1)
        tools.addWidget(self.sort_box)
        tools.addWidget(self.select_button)
        tools.addWidget(self.more_button)
        layout.addLayout(tools)

        self.hint = QLabel("Paste a channel URL and press Search.")
        self.hint.setStyleSheet(f"color: {_MUTED};")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["", "Title", "Duration", "Uploaded", "Status", "Progress"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self._on_item_changed)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setColumnWidth(0, 64)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 90)
        self.table.setColumnWidth(5, 150)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.download_button = QPushButton("Download selected")
        self.download_button.clicked.connect(self.on_download)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.on_cancel)
        actions.addWidget(self.download_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.message = QLabel("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)

    def _apply_style(self) -> None:
        palette = _dark_palette()
        self.setPalette(palette)
        self.centralWidget().setAutoFillBackground(True)
        self.centralWidget().setPalette(palette)
        qt_app = QApplication.instance()
        if qt_app is not None:
            qt_app.setPalette(palette)
        # Style the controls themselves. A stylesheet on the window makes the
        # table draw its checkboxes as wide empty boxes.
        field = (
            f"background: {_CARD}; color: {_TEXT}; border: 1px solid {_BORDER}; "
            "border-radius: 6px; padding: 6px; "
            "selection-background-color: #264f78; selection-color: #ffffff;"
        )
        button = (
            f"QPushButton {{ background: {_BUTTON}; color: {_TEXT}; border: 1px solid {_BORDER}; "
            "border-radius: 6px; padding: 8px 14px; }"
            "QPushButton:hover { background: #333333; }"
            f"QPushButton:disabled {{ background: {_BUTTON}; color: #6e6e6e; border-color: #2e2e2e; }}"
        )
        self.url_edit.setStyleSheet(field)
        self.filter_edit.setStyleSheet(field)
        self.sort_box.setStyleSheet(
            f"QComboBox {{ {field} }}"
            f"QComboBox QAbstractItemView {{ background: {_CARD}; color: {_TEXT}; "
            "selection-background-color: #264f78; selection-color: #ffffff; "
            f"border: 1px solid {_BORDER}; }}"
        )
        for button_widget in (self.search_button, self.select_button, self.more_button, self.cancel_button):
            button_widget.setStyleSheet(button)
        self.download_button.setStyleSheet(
            f"QPushButton {{ background: {_ACCENT}; color: {_WINDOW}; border: none; "
            "border-radius: 6px; padding: 8px 14px; font-weight: 600; }"
            "QPushButton:hover { background: #f4f4f4; }"
            "QPushButton:disabled { background: #3a3a3a; color: #8b8b8b; }"
        )
        self.table.setStyleSheet(
            f"""
            QTableWidget {{
                background: {_CARD};
                color: {_TEXT};
                alternate-background-color: {_ROW};
                border: 1px solid {_BORDER};
                border-radius: 6px;
                padding: 0;
            }}
            QHeaderView::section {{
                background: {_WINDOW};
                color: {_MUTED};
                border: none;
                border-bottom: 1px solid {_BORDER};
                padding: 8px;
                font-weight: 600;
            }}
            QTableWidget::item {{ color: {_TEXT}; padding: 2px 6px; }}
            """
        )

    def on_search(self) -> None:
        if self._loading or self._running:
            return
        try:
            url = normalize_channel_videos_url(self.url_edit.text())
        except UrlError as exc:
            self._show_message(str(exc), error=True)
            return
        self._channel_url = url
        self._start_list(start=1, append=False)

    def on_show_more(self) -> None:
        if self._loading or self._running or self._next_start is None or not self._channel_url:
            return
        self._start_list(start=self._next_start, append=True)

    def _start_list(self, *, start: int, append: bool) -> None:
        self._loading = True
        self._sync_controls()
        self._show_message("Loading more videos…" if append else "Loading videos…")
        worker = ListWorker(self._list_page, self._channel_url, start)
        worker.succeeded.connect(lambda videos, nxt, append=append: self._on_listed(videos, nxt, append))
        worker.failed.connect(self._on_list_failed)
        worker.finished.connect(self._forget_list_worker)
        self._list_worker = worker
        worker.start()

    def _on_listed(self, videos: list[Video], next_start: int | None, append: bool) -> None:
        self._loading = False
        if append:
            self._videos = merge_videos(self._videos, list(videos))
        else:
            self._videos = list(videos)
            self._checked.clear()
            self._status.clear()
            self._details.clear()
            self._progress.clear()
        self._next_start = next_start
        self._videos = sort_videos(self._videos, self._newest_first())
        self._rebuild_table()
        count = len(self._videos)
        noun = "video" if count == 1 else "videos"
        self._show_message(f"Loaded {count} {noun}.")
        self._sync_controls()
        self._refresh_hint()

    def _on_list_failed(self, text: str) -> None:
        self._loading = False
        self._show_message(text, error=True)
        self._sync_controls()

    def on_download(self) -> None:
        if self._running or self._loading:
            return
        chosen = self._selected_videos()
        if not chosen:
            self._show_message("Select at least one video.", error=True)
            return
        folder = self.choose_folder()
        if not folder:
            return
        self._running = True
        self._sync_controls()
        self._show_message("Downloading…")
        worker = DownloadWorker(chosen, Path(folder), self._download_file)
        worker.state.connect(self._on_state)
        worker.progress.connect(self._on_progress)
        worker.overwrite_requested.connect(self._on_overwrite)
        worker.finished_summary.connect(self._on_finished)
        worker.finished.connect(self._forget_download_worker)
        self._download_worker = worker
        worker.start()

    def on_cancel(self) -> None:
        if self._download_worker is not None and self._download_worker.isRunning():
            self._download_worker.request_cancel()
        box = self.findChild(QMessageBox)
        if box is not None:
            box.reject()

    def _on_overwrite(self, filename: str) -> None:
        worker = self._download_worker
        if worker is None:
            return
        worker.answer_overwrite(self.ask_overwrite(filename))

    def _on_state(self, video_id: str, state: str, detail: str) -> None:
        self._status[video_id] = state
        if state == "failed" and detail:
            self._details[video_id] = detail
        elif state != "failed":
            self._details.pop(video_id, None)
        self._paint_row(video_id)

    def _on_progress(self, video_id: str, percent: int) -> None:
        self._progress[video_id] = percent
        self._paint_row(video_id)

    def _on_finished(self, summary) -> None:
        self._running = False
        self._show_message(summary_text(summary), error=summary.failed > 0 and not summary.cancelled)
        self._sync_controls()

    def select_all_matching(self) -> None:
        if self._running or self._loading:
            return
        self._updating_table = True
        try:
            for row in range(self.table.rowCount()):
                if self.table.isRowHidden(row):
                    continue
                item = self.table.item(row, 0)
                item.setCheckState(Qt.CheckState.Checked)
                self._checked.add(item.data(Qt.ItemDataRole.UserRole))
        finally:
            self._updating_table = False

    def _selected_videos(self) -> list[Video]:
        visible = {
            video.video_id
            for video in displayed_videos(
                self._videos,
                newest_first=self._newest_first(),
                query=self.filter_edit.text(),
            )
        }
        ordered = displayed_videos(
            self._videos,
            newest_first=self._newest_first(),
            query=self.filter_edit.text(),
        )
        return [video for video in ordered if video.video_id in self._checked and video.video_id in visible]

    def _on_sort_changed(self) -> None:
        if self._running:
            return
        self._videos = sort_videos(self._videos, self._newest_first())
        self._rebuild_table()

    def _apply_filter(self) -> None:
        query = self.filter_edit.text()
        visible = 0
        for row in range(self.table.rowCount()):
            title = self._videos[row].title if row < len(self._videos) else ""
            hide = not title_matches(title, query)
            self.table.setRowHidden(row, hide)
            if not hide:
                visible += 1
        self._refresh_hint(visible)

    def _refresh_hint(self, visible: int | None = None) -> None:
        if not self._videos:
            self.hint.setText("Paste a channel URL and press Search.")
            self.hint.setVisible(True)
            return
        if visible is None:
            visible = sum(1 for row in range(self.table.rowCount()) if not self.table.isRowHidden(row))
        if visible == 0:
            self.hint.setText("No titles match that filter.")
            self.hint.setVisible(True)
            return
        self.hint.setText("")
        self.hint.setVisible(False)

    def _rebuild_table(self) -> None:
        self._updating_table = True
        self._row_of.clear()
        self.table.clearContents()
        self.table.setRowCount(0)
        self.table.setRowCount(len(self._videos))
        for row, video in enumerate(self._videos):
            self._row_of[video.video_id] = row
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(
                Qt.CheckState.Checked if video.video_id in self._checked else Qt.CheckState.Unchecked
            )
            check.setData(Qt.ItemDataRole.UserRole, video.video_id)
            self.table.setItem(row, 0, check)

            title = QTableWidgetItem(video.title)
            title.setFlags(Qt.ItemFlag.ItemIsEnabled)
            title.setForeground(_INK)
            self.table.setItem(row, 1, title)

            duration = QTableWidgetItem(format_duration(video.duration_seconds))
            duration.setFlags(Qt.ItemFlag.ItemIsEnabled)
            duration.setForeground(_INK)
            duration.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, duration)

            uploaded = QTableWidgetItem(format_date(video.upload_date))
            uploaded.setFlags(Qt.ItemFlag.ItemIsEnabled)
            uploaded.setForeground(_INK)
            self.table.setItem(row, 3, uploaded)

            status = QTableWidgetItem(self._status.get(video.video_id, ""))
            status.setFlags(Qt.ItemFlag.ItemIsEnabled)
            status.setForeground(_INK)
            status.setToolTip(self._details.get(video.video_id, ""))
            self.table.setItem(row, 4, status)

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setStyleSheet(_PROGRESS_STYLE)
            self.table.setCellWidget(row, 5, bar)
            self._paint_progress(bar, video.video_id)
        self._updating_table = False
        self._apply_filter()
        if self._running:
            self._set_checks_enabled(False)

    def _paint_row(self, video_id: str) -> None:
        row = self._row_of.get(video_id)
        if row is None:
            return
        status = self.table.item(row, 4)
        if status is not None:
            status.setText(self._status.get(video_id, ""))
            status.setToolTip(self._details.get(video_id, ""))
        bar = self.table.cellWidget(row, 5)
        if isinstance(bar, QProgressBar):
            self._paint_progress(bar, video_id)

    def _paint_progress(self, bar: QProgressBar, video_id: str) -> None:
        state = self._status.get(video_id, "")
        if state == "working":
            bar.setTextVisible(True)
            bar.setValue(self._progress.get(video_id, 0))
            return
        if state == "done":
            bar.setTextVisible(True)
            bar.setValue(100)
            return
        bar.setTextVisible(False)
        bar.setValue(0)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_table or item.column() != 0:
            return
        video_id = item.data(Qt.ItemDataRole.UserRole)
        if not video_id or self._running:
            return
        if item.checkState() == Qt.CheckState.Checked:
            self._checked.add(video_id)
        else:
            self._checked.discard(video_id)

    def _set_checks_enabled(self, enabled: bool) -> None:
        flags = Qt.ItemFlag.ItemIsEnabled
        if enabled:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        self._updating_table = True
        try:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item is not None:
                    item.setFlags(flags)
        finally:
            self._updating_table = False

    def _sync_controls(self) -> None:
        busy = self._loading or self._running
        self.url_edit.setEnabled(not busy)
        self.search_button.setEnabled(not self._loading and not self._running)
        self.more_button.setEnabled(not busy and self._next_start is not None)
        self.filter_edit.setEnabled(not self._running)
        self.sort_box.setEnabled(not self._running)
        self.select_button.setEnabled(not busy and bool(self._videos))
        self.download_button.setEnabled(not busy and bool(self._videos))
        self.cancel_button.setEnabled(self._running)
        self._set_checks_enabled(not self._running)

    def _newest_first(self) -> bool:
        return self.sort_box.currentIndex() == 0

    def _set_idle_message(self) -> None:
        self._show_message("")

    def _show_message(self, text: str, *, error: bool = False) -> None:
        self.message.setText(text)
        color = _ERROR if error else _TEXT
        self.message.setStyleSheet(f"color: {color}; font-size: 14px;")

    def _forget_list_worker(self) -> None:
        self._list_worker = None

    def _forget_download_worker(self) -> None:
        self._download_worker = None

    def closeEvent(self, event) -> None:
        worker = self._download_worker
        if worker is not None and worker.isRunning():
            worker.request_cancel()
            worker.wait(4000)
        list_worker = self._list_worker
        if list_worker is not None and list_worker.isRunning():
            list_worker.wait(2000)
        event.accept()
