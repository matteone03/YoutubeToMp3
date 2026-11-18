# YoutubeToMp3

A personal desktop app. Paste a YouTube channel URL, review that channel's videos, and save the ones you pick as 192 kbps MP3 files in a folder you choose.

It is for one person on their own Windows or Mac computer. Behavior is defined in `PROJECT_SCOPE.txt`.

## Run on Windows

In PowerShell, from this folder:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
youtubetomp3
```

## Run on macOS

In Terminal, from this folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
youtubetomp3
```

Python 3.11 or newer is required. `yt-dlp` and `ffmpeg` are installed with the app. You do not install them separately, and you do not need a YouTube API key.

Dates on the channel page are the ones YouTube shows there, such as "3 days ago", turned into a calendar day. Opening every video for an exact timestamp is not part of this version.

## Use

1. Paste a channel URL, such as `https://www.youtube.com/@channel`, and press Search.
2. Sort by date or filter by title. Show more loads the next 30 videos.
3. Tick the videos you want, or use Select all for the ones that match the filter.
4. Press Download selected, choose a folder, and wait. Up to three videos download at a time.
5. Cancel stops the downloads in progress and does not start the rest. If a file is already in the folder, you are asked before it is overwritten. No means nothing further starts; downloads already running finish.

When the run finishes, the window shows how many downloads succeeded and how many failed.

## Tests

```bash
pytest
```
