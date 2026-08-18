#!/usr/bin/env bash
# Record docs/demo.gif: Playwright drives the live stack, ffmpeg-static encodes.
# Needs docker compose up with real model keys. SPEED=n compresses time (default 3x).
set -euo pipefail
cd "$(dirname "$0")/.."
speed="${SPEED:-7}"

(cd web && node e2e/record-demo.mjs)
src="$(ls -t web/e2e/recordings/*.webm | head -1)"

ffmpeg="web/node_modules/ffmpeg-static/ffmpeg"
# Thought streaming keeps every frame busy, so the encode leans small:
# 6fps at 800px keeps a two-minute take under GitHub's 10MB render limit.
filters="setpts=PTS/${speed},fps=6,scale=800:-1:flags=lanczos"
palette="$(mktemp -d)/palette.png"
"$ffmpeg" -y -loglevel error -i "$src" -vf "${filters},palettegen=stats_mode=diff" "$palette"
"$ffmpeg" -y -loglevel error -i "$src" -i "$palette" \
  -lavfi "${filters}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
  docs/demo.gif
ls -lh docs/demo.gif
