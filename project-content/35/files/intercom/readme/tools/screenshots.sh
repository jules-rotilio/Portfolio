#!/bin/sh
# Takes the README's screenshots again, into readme/images/.
#
#   sh readme/tools/screenshots.sh          (from anywhere; Linux with PipeWire)
#
# It uses a demo setup in a temporary folder (demo_setup.py), so the pictures
# never show your own sounds or settings, and plays a test tune into a
# speaker nobody hears (test_tone.py), so "Capture program audio" has
# something to capture. Intercom's snapshot mode (README, Part 3) takes the
# pictures; ppm_to_png.py converts them. Everything it creates is removed at
# the end, even after an error.
#
# Your microphone is opened like on any start: the mic meter shows the room.
set -eu

tools=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$tools/../.." && pwd)
images="$root/readme/images"
work=$(mktemp -d)
module=""
player=""

cleanup() {
    [ -n "$player" ] && kill "$player" 2>/dev/null || true
    [ -n "$module" ] && pactl unload-module "$module" 2>/dev/null || true
    rm -rf "$work"
}
trap cleanup EXIT INT TERM

python3 "$tools/demo_setup.py" "$work"

module=$(pactl load-module module-null-sink sink_name=intercom_screenshots \
    'sink_properties=device.description="Intercom screenshots"')
python3 "$tools/test_tone.py" | pacat --playback --device=intercom_screenshots \
    --rate=48000 --channels=2 --format=s16le --client-name="Music Player" &
player=$!

# XDG_DATA_HOME too: the window opens at its default size, not yours.
cd "$root"
XDG_CONFIG_HOME="$work/config" XDG_DATA_HOME="$work/data" \
    INTERCOM_SNAPSHOT="$work/shots" INTERCOM_SNAPSHOT_WAIT=4 \
    INTERCOM_SNAPSHOT_PLAY=Num5 INTERCOM_SNAPSHOT_PROGRAM=pacat INTERCOM_SNAPSHOT_MAXIMIZED=1 \
    cargo run --quiet

python3 "$tools/ppm_to_png.py" "$work"/shots/*.ppm --out "$images"
