#!/usr/bin/env bash
# Regenerate the verification screenshots with a headless Chromium.
# Requires no npm: the page is plain HTML/CSS/JS plus mock.js.
set -euo pipefail
cd "$(dirname "$0")"

BROWSER="${BROWSER:-}"
if [ -z "$BROWSER" ]; then
  # `chromium-browser` is a broken snap stub in some containers; prefer Chrome.
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

BASE="file://$PWD/index.html"
SHOTS="$(mktemp -d)"

shoot() {
  local out="$1" size="$2" url="$3" profile
  profile="$(mktemp -d)"
  printf '  %-30s %-10s %s\n' "$out" "$size" "$url"
  "$BROWSER" --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
    --no-first-run --user-data-dir="$profile" --window-size="$size" \
    --screenshot="$PWD/$out" "$url" >/dev/null 2>&1 || {
      rm -rf "$profile"
      echo "  failed: $out" >&2
      return 1
    }
  rm -rf "$profile"
}

echo "Rendering DeepL-oFM screenshots with $BROWSER"

# Every tab, light and dark, at the default window size (1180x800).
shoot docs-translate.png           1180,800 "$BASE?still=1#translate"
shoot docs-files.png               1180,800 "$BASE?still=1#files"
shoot docs-write.png               1180,800 "$BASE?still=1#write"
shoot docs-history.png             1180,800 "$BASE?still=1#history"
shoot docs-translate-dark.png      1180,800 "$BASE?theme=dark&still=1#translate"
shoot docs-files-dark.png          1180,800 "$BASE?theme=dark&still=1#files"
shoot docs-write-dark.png          1180,800 "$BASE?theme=dark&still=1#write"
shoot docs-history-dark.png        1180,800 "$BASE?theme=dark&still=1#history"

# Dialogs and transient states.
shoot docs-settings.png            1180,800 "$BASE?still=1#settings-model"
shoot docs-settings-generation.png 1180,800 "$BASE?still=1#settings-generation"
shoot docs-settings-behaviour.png  1180,800 "$BASE?still=1#settings-behaviour"
shoot docs-settings-hotkeys.png    1180,800 "$BASE?still=1#settings-hotkeys"
shoot docs-settings-about.png      1180,800 "$BASE?still=1#settings-about"
shoot docs-settings-dark.png       1180,800 "$BASE?theme=dark&still=1#settings-model"
shoot docs-catalog.png             1180,800 "$BASE?still=1#catalog"
shoot docs-menu.png                1180,800 "$BASE?still=1#menu"
shoot docs-catalog-dark.png        1180,800 "$BASE?theme=dark&still=1#catalog"
shoot docs-progress.png            1180,800 "$BASE?still=1#progress"
shoot docs-error.png               1180,800 "$BASE?still=1#error"
shoot docs-empty.png               1180,800 "$BASE?still=1#empty"
shoot docs-markdown.png            1180,800 "$BASE?still=1#markdown"
shoot docs-text.png                1180,800 "$BASE?still=1#text"
shoot docs-source-markdown.png     1180,800 "$BASE?still=1#source-markdown"
shoot docs-source-preview.png      1180,800 "$BASE?still=1#source-preview"
shoot docs-source-preview-dark.png 1180,800 "$BASE?theme=dark&still=1#source-preview"
shoot docs-files-empty.png         1180,800 "$BASE?still=1#files-empty"
shoot docs-files-progress.png      1180,800 "$BASE?still=1#files-progress"
shoot docs-files-error.png         1180,800 "$BASE?still=1#files-error"
shoot docs-write-busy.png          1180,800 "$BASE?still=1#write-busy"
shoot docs-write-warning.png       1180,800 "$BASE?still=1#write-warning"
shoot docs-settings-missing.png    1180,800 "$BASE?still=1#settings-missing"
shoot docs-history-empty.png       1180,800 "$BASE?still=1#history-empty"

# Ukrainian interface (?lang=uk is a mock-only switch).
shoot docs-uk-translate.png 1180,800 "$BASE?lang=uk&still=1#translate"
shoot docs-uk-files.png     1180,800 "$BASE?lang=uk&still=1#files"
shoot docs-uk-write.png     1180,800 "$BASE?lang=uk&still=1#write"
shoot docs-uk-history.png   1180,800 "$BASE?lang=uk&still=1#history"
shoot docs-uk-settings.png  1180,800 "$BASE?lang=uk&still=1#settings-model"
shoot docs-uk-catalog.png   1180,800 "$BASE?lang=uk&still=1#catalog"

# Minimum supported window (960x620) and a wide window (1440x900).
for tab in translate files write history; do
  shoot "docs-960-$tab.png" 960,620 "$BASE?still=1#$tab"
  shoot "docs-960-$tab-dark.png" 960,620 "$BASE?theme=dark&still=1#$tab"
  shoot "docs-1440-$tab.png" 1440,900 "$BASE?still=1#$tab"
done
shoot docs-960-settings.png 960,620 "$BASE?still=1#settings-model"
shoot docs-960-settings-dark.png 960,620 "$BASE?theme=dark&still=1#settings-model"
shoot docs-960-catalog.png  960,620 "$BASE?still=1#catalog"
shoot docs-960-catalog-dark.png 960,620 "$BASE?theme=dark&still=1#catalog"
shoot docs-960-write-warning.png 960,620 "$BASE?still=1#write-warning"
shoot docs-1440-settings.png 1440,900 "$BASE?still=1#settings-model"

# Command-line actions surfaced by get_startup (mock-only query switch).
shoot docs-startup-write.png 1180,800 "$BASE?still=1&startup=write#translate"
shoot docs-startup-catalog.png 1180,800 "$BASE?still=1&startup=catalog#translate"

rm -rf "$SHOTS"
echo "Done."
