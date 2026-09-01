#!/usr/bin/env bash
# Build "PDF Tool.app" with PyInstaller.
# Run from the project root with the venv activated:  ./build.sh
set -euo pipefail

APP_NAME="Music Printer"

rm -rf build dist

pyinstaller \
  --name "$APP_NAME" \
  --windowed \
  --noconfirm \
  main.py

# Note on universal2 (Intel + Apple Silicon in one bundle):
# add  --target-arch universal2  above, but that only works if the Python
# *and every installed wheel* (pikepdf, its libqpdf) are universal2. If a
# wheel is single-arch you'll get an error — then either ship an
# arm64-only build or set up a universal2 venv.

echo
echo "Built: dist/${APP_NAME}.app"
echo "Run it:  open \"dist/${APP_NAME}.app\""
