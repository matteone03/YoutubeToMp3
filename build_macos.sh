#!/bin/bash
# Build an Apple Silicon macOS app that contains Python, Qt, yt-dlp, and ffmpeg.

set -euo pipefail

cd "$(dirname "$0")"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "This builds an Apple Silicon Mac app and has to run on an Apple Silicon Mac."
  echo "This computer is $(uname -s) $(uname -m)."
  exit 1
fi

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]" pyinstaller

pyinstaller \
  --noconfirm \
  --windowed \
  --name YoutubeToMp3 \
  --osx-bundle-identifier com.youtubetomp3.app \
  --paths src \
  --hidden-import imageio_ffmpeg \
  --collect-all yt_dlp \
  --collect-all imageio_ffmpeg \
  src/youtubetomp3/app.py

codesign --force --deep --sign - dist/YoutubeToMp3.app

rm -rf dist/dmg
mkdir -p dist/dmg
cp -R dist/YoutubeToMp3.app dist/dmg/
hdiutil create \
  -volname YoutubeToMp3 \
  -srcfolder dist/dmg \
  -ov \
  -format UDZO \
  dist/YoutubeToMp3.dmg

echo "Built dist/YoutubeToMp3.app and dist/YoutubeToMp3.dmg"
