#!/usr/bin/env bash
# Renders the scripted sessions from static/scenarios.js as PNG figures (dialog only, no page chrome).
# Requires a running server (default http://localhost:8027), google-chrome, and Python with Pillow.
# Usage: scripts/screenshots.sh [out-dir] [scenario ...]
# A scenario can carry further URL parameters under its own file name, e.g. offers:shopping&until=11&last=4
# writes prototype-offers.png from the first 11 steps of "shopping", showing the last four turns; crop=<px>
# cuts the figure to that height (in CSS pixels), or pads it to it, so that panels share their height.
set -euo pipefail
URL="${URL:-http://localhost:8027}"
WIDTH="${WIDTH:-820}"
OUT="${1:-../chiir27-dialog-first-figures}"
shift || true
SCENARIOS=("${@:-paper cards refine}")
mkdir -p "$OUT"
for spec in ${SCENARIOS[@]}; do
  name="${spec%%:*}"
  query="${spec#*:}"
  crop=$(sed -n 's/.*crop=\([0-9]*\).*/\1/p' <<<"$query")
  # With the input box (composer=1), the window is as high as the panel, so that the box sits at its bottom.
  height=4000
  [[ "$query" == *composer=1* && -n "$crop" ]] && height=$crop
  file="$OUT/prototype-$name.png"
  google-chrome --headless=new --disable-gpu --hide-scrollbars --window-size="$WIDTH","$height" \
    --force-device-scale-factor=2 --virtual-time-budget=10000 \
    --screenshot="$file" "$URL/?scenario=$query&figure=1" 2>/dev/null
  # Trim the empty space below the dialog.
  python3 - "$file" "${crop:-0}" <<'PY'
import sys
from PIL import Image, ImageChops
image = Image.open(sys.argv[1]).convert("RGB")
box = ImageChops.difference(image, Image.new("RGB", image.size, (255, 255, 255))).getbbox()
bottom = min(image.height, box[3] + 40)
crop = int(sys.argv[2]) * 2  # screenshots are taken at twice the resolution
if crop:
    bottom = min(bottom, crop)
image = image.crop((0, 0, image.width, bottom))
if crop and image.height < crop:  # panels of one figure share their height
    padded = Image.new("RGB", (image.width, crop), (255, 255, 255))
    padded.paste(image, (0, 0))
    image = padded
image.save(sys.argv[1])
PY
  echo "$file"
done
