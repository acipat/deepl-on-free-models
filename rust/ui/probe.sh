#!/usr/bin/env bash
# Run the defect probes against the standalone UI in headless Chrome.
#
# No npm and no test framework: probe-defects.html drives app.js exactly as a
# browser does, through the mock installed by mock.js, and prints its assertions
# into the page. This script fails unless every check passed.
set -euo pipefail
cd "$(dirname "$0")"

BROWSER="${BROWSER:-}"
if [ -z "$BROWSER" ]; then
  for candidate in google-chrome google-chrome-stable chromium chromium-browser; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" --version >/dev/null 2>&1; then
      BROWSER="$candidate"
      break
    fi
  done
fi
if [ -z "$BROWSER" ]; then
  echo "No Chromium/Chrome binary found (tried google-chrome, chromium)." >&2
  exit 1
fi

PROFILE="$(mktemp -d)"
OUTPUT="$(mktemp)"
trap 'rm -rf "$PROFILE" "$OUTPUT"' EXIT

"$BROWSER" --headless=new --disable-gpu --no-sandbox \
  --allow-file-access-from-files --no-first-run \
  --user-data-dir="$PROFILE" --virtual-time-budget=15000 \
  --dump-dom "file://$PWD/probe-defects.html" >"$OUTPUT" 2>/dev/null || {
    echo "headless Chrome failed to render the probe" >&2
    exit 1
  }

python3 - "$OUTPUT" <<'PY'
import html
import json
import re
import sys

document = open(sys.argv[1], encoding="utf-8", errors="replace").read()
match = re.search(r'<pre id="out">(.*?)</pre>', document, re.S)
if not match:
    sys.exit("probe page produced no result block")
raw = html.unescape(match.group(1))
try:
    result = json.loads(raw)
except json.JSONDecodeError:
    sys.exit("probe result is not JSON:\n" + raw)

checks = result.get("results", [])
for item in checks:
    print(("PASS " if item.get("ok") else "FAIL ") + str(item.get("name", "")))
if not result.get("ok"):
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(1)
print(f"browser probe: ok ({len(checks)} checks)")
PY
