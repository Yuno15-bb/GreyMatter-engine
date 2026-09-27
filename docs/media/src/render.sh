#!/usr/bin/env bash
# Renders a drawn README visual at 2x.
#   docs/media/src/render.sh where-it-lands 940 386
#   docs/media/src/render.sh recall 880 FIT     (height read from the page itself)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd -P)"
chrome="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
h="$3"
if [ "$h" = "FIT" ]; then   # the page writes its own height into <body data-h>
  h="$("$chrome" --headless=new --disable-gpu --window-size="$2,4000" --dump-dom \
        "file://$here/$1.html" 2>/dev/null | sed -n 's/.*data-h="\([0-9]*\)".*/\1/p' | head -1)"
  [ -n "$h" ] || { echo "no data-h in $1.html" >&2; exit 1; }
fi
"$chrome" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
  --default-background-color=00000000 --window-size="$2,$h" \
  --screenshot="$here/../$1.png" "file://$here/$1.html" 2>/dev/null
echo "docs/media/$1.png  ${2}x${h} @2x"
