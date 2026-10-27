#!/bin/sh
# Renders an SVG to PNG with headless Firefox, to check a diagram the way a
# browser (and GitHub) shows it. ImageMagick's own SVG renderer drops the
# arrows and the borders, so it can't be trusted for this.
#
#   sh readme/tools/svg_to_png.sh <file.svg> <out.png> [width] [height]
#
# A throwaway profile is used, so a Firefox you have open is left alone.
set -eu
[ $# -ge 2 ] || { echo "usage: $0 <file.svg> <out.png> [width] [height]" >&2; exit 2; }
svg=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
out=$(cd "$(dirname "$2")" && pwd)/$(basename "$2")
# The size of the picture: from the SVG's own width and height unless given.
width=${3:-$(sed -n 's/.*<svg[^>]* width="\([0-9]*\)".*/\1/p' "$svg" | head -1)}
height=${4:-$(sed -n 's/.*<svg[^>]* height="\([0-9]*\)".*/\1/p' "$svg" | head -1)}
profile=$(mktemp -d)
trap 'rm -rf "$profile"' EXIT
firefox="firefox"
command -v firefox >/dev/null || firefox="firefox-esr"
"$firefox" --headless --no-remote --profile "$profile" \
    --window-size="$width,$height" --screenshot "$out" "file://$svg" >/dev/null 2>&1
echo "$out"
