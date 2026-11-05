import time
from datetime import date

from PySide6.QtCore import Qt

from youtubetomp3.downloader import DownloadResult
from youtubetomp3.videos import Video, VideoPage
from youtubetomp3.window import MainWindow


def _videos():
    return [
        Video("old", "Old talk", 65, date(2020, 1, 1), "https://www.youtube.com/watch?v=old"),
        Video("new", "New talk", 12, date(2024, 6, 1), "https://www.youtube.com/watch?v=new"),
    ]


def test_a_video_link_does_not_change_the_list(qt_app):
    def list_page(*args, **kwargs):
        raise AssertionError("search should not fetch")

    window = MainWindow(list_page=list_page)
    window.url_edit.setText("https://www.youtube.com/watch?v=abc")
    window.on_search()
    assert window.table.rowCount() == 0
    assert "channel URL" in window.message.text()
    window.close()


def test_search_show_more_filter_and_select_all(qt_app):
    calls = []

    def list_page(url, start, page_size=30):
        calls.append(start)
        if start == 1:
            return VideoPage(_videos(), 31)
        return VideoPage(
            [Video("more", "More talk", 40, date(2023, 1, 1), "https://www.youtube.com/watch?v=more")],
            None,
        )

    window = MainWindow(list_page=list_page)
    window.url_edit.setText("https://www.youtube.com/@demo")
    window.on_search()
    _wait(qt_app, lambda: window.table.rowCount() == 2)
    assert calls == [1]
    assert window.table.item(0, 1).text() == "New talk"
    assert window.table.item(0, 2).text() == "0:12"
    assert window.more_button.isEnabled()

    window.on_show_more()
    _wait(qt_app, lambda: window.table.rowCount() == 3)
    assert calls == [1, 31]
    assert window.more_button.isEnabled() is False

    window.filter_edit.setText("old")
    window.select_all_matching()
    checked = _checked_titles(window)
    assert checked == {"Old talk"}

    window.filter_edit.setText("")
    chosen = [video.title for video in window._selected_videos()]
    assert chosen == ["Old talk"]
    window.close()


def test_download_reports_success_and_stops_when_overwrite_is_declined(qt_app, tmp_path):
    saved = []

    def download_file(video, destination, on_progress, cancel):
        on_progress(40)
        destination.write_bytes(b"mp3")
        saved.append(destination.name)
        return DownloadResult("ok")

    window = MainWindow(
        list_page=lambda url, start, page_size=30: VideoPage(_videos(), None),
        download_file=download_file,
    )
    window.choose_folder = lambda: str(tmp_path)
    window.ask_overwrite = lambda filename: False
    window.url_edit.setText("https://www.youtube.com/@demo")
    window.on_search()
    _wait(qt_app, lambda: window.table.rowCount() == 2)
    window.select_all_matching()
    (tmp_path / "Old talk.mp3").write_bytes(b"old")

    window.on_download()
    _wait(qt_app, lambda: window._running is False and window.message.text().startswith("Cancelled"))
    assert saved == ["New talk.mp3"]
    assert (tmp_path / "Old talk.mp3").read_bytes() == b"old"
    assert "1 succeeded, 0 failed" in window.message.text()
    window.close()


def _checked_titles(window):
    titles = set()
    for row in range(window.table.rowCount()):
        item = window.table.item(row, 0)
        if item.checkState() == Qt.CheckState.Checked:
            titles.add(window.table.item(row, 1).text())
    return titles


def _wait(qt_app, ready, timeout=3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        qt_app.processEvents()
        if ready():
            qt_app.processEvents()
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for the window")
