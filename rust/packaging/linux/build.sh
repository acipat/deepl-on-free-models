#!/usr/bin/env bash
#
# Builds and packages the DeepL-oFM Rust port on Linux.
#
# Default (CLI only) produces, in <repo>/rust/dist:
#
#   ofm-<version>-linux-<arch>.tar.gz     ofm binary, a .desktop entry, an icon
#                                         and a short README
#   SHA256SUMS-linux-<arch>.txt           checksum of the tarball
#
# With --with-desktop it also runs `cargo tauri build`, copies the .deb,
# .AppImage and .rpm bundles into rust/dist, and adds the ofm-desktop binary to
# the tarball so the shipped .desktop entry has something to launch.
#
# The desktop shell (Tauri v2) needs these build dependencies:
#
#   sudo apt-get install -y libwebkit2gtk-4.1-dev libgtk-3-dev \
#                           libayatana-appindicator3-dev libssl-dev \
#                           build-essential curl wget file
#
# (and at runtime: libwebkit2gtk-4.1-0, libgtk-3-0, libayatana-appindicator3-1).
# The CLI needs none of them, which is why it is the only Linux artifact the
# release workflow builds.
#
# Usage:
#   ./build.sh                 # CLI tarball
#   ./build.sh --with-desktop  # CLI tarball + .deb/.AppImage/.rpm

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUST_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="$(cd "$RUST_DIR/.." && pwd)"
DESKTOP_DIR="$RUST_DIR/crates/desktop"
TAURI_CONF="$DESKTOP_DIR/tauri.conf.json"
ICON_DIR="$DESKTOP_DIR/icons"
DIST_DIR="$RUST_DIR/dist"
APP_ID="ua.admin.hymt"
DESKTOP_FILE="ua.admin.hymt.desktop"
ICON_NAME="deepl-ofm"

WITH_DESKTOP=0

if [ -t 1 ] && command -v tput >/dev/null 2>&1 && [ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]; then
    C_SECTION="$(tput bold)$(tput setaf 6)"
    C_OK="$(tput setaf 2)"
    C_WARN="$(tput setaf 3)"
    C_ERR="$(tput setaf 1)"
    C_DIM="$(tput setaf 8)"
    C_OFF="$(tput sgr0)"
else
    C_SECTION=""; C_OK=""; C_WARN=""; C_ERR=""; C_DIM=""; C_OFF=""
fi

section() { printf '\n%s==> %s%s\n' "$C_SECTION" "$1" "$C_OFF"; }
info()    { printf '    %s\n' "$1"; }
ok()      { printf '    %sOK: %s%s\n' "$C_OK" "$1" "$C_OFF"; }
warn()    { printf '    %sWARNING: %s%s\n' "$C_WARN" "$1" "$C_OFF"; }
dim()     { printf '    %s%s%s\n' "$C_DIM" "$1" "$C_OFF"; }

die() {
    printf '\n%sERROR: %s%s\n' "$C_ERR" "$1" "$C_OFF" >&2
    shift || true
    for line in "$@"; do
        printf '  -> %s\n' "$line" >&2
    done
    printf '\n' >&2
    exit 1
}

usage() {
    cat <<'EOF'
Usage: build.sh [options]

  (no options)      Build the CLI and package the tarball.
  --with-desktop    Also run `cargo tauri build` and copy the .deb, .AppImage
                    and .rpm bundles into rust/dist.
  -h, --help        Show this help.

Build dependencies for the desktop shell:
  sudo apt-get install -y libwebkit2gtk-4.1-dev libgtk-3-dev \
                          libayatana-appindicator3-dev
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --with-desktop) WITH_DESKTOP=1 ;;
        -h|--help)      usage; exit 0 ;;
        *)              die "Unknown option: $1" "Run: $0 --help" ;;
    esac
    shift
done

# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------

section "Checking the platform and the Rust toolchain"

[ "$(uname -s)" = "Linux" ] || die "This script must run on Linux (uname -s reports $(uname -s))." \
    "Use packaging/windows/build.ps1 or packaging/macos/build.sh instead."

command -v cargo >/dev/null 2>&1 || die "cargo was not found in PATH." \
    "Install Rust from https://rustup.rs (stable, 1.82 or newer), or use your distribution's rustc package."
command -v rustc >/dev/null 2>&1 || die "rustc was not found in PATH." \
    "Install Rust from https://rustup.rs (stable, 1.82 or newer)."
dim "cargo: $(cargo --version 2>/dev/null || echo unknown)"
dim "rustc: $(rustc --version 2>/dev/null || echo unknown)"

ARCH="$(uname -m)"
case "$ARCH" in
    x86_64|aarch64) ;;
    *) warn "Untested architecture '$ARCH'; the artifact name will use it as-is." ;;
esac

[ -f "$TAURI_CONF" ] || die "tauri.conf.json was not found at $TAURI_CONF" \
    "Run this script from a checkout of the repository."

read_version() {
    if command -v python3 >/dev/null 2>&1; then
        python3 - "$TAURI_CONF" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    print(json.load(fh)["version"])
PY
    else
        sed -n 's/^[[:space:]]*"version": "\([^"]*\)".*/\1/p' "$TAURI_CONF" | head -n 1
    fi
}

VERSION="$(read_version)"
[ -n "$VERSION" ] || die "Could not read the version from $TAURI_CONF"
dim "DeepL-oFM version: $VERSION"

# ---------------------------------------------------------------------------
# Desktop build prerequisites
# ---------------------------------------------------------------------------

section "WebKitGTK / GTK requirements for the desktop shell"

dim "Build:   libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev"
dim "Runtime: libwebkit2gtk-4.1-0 libgtk-3-0 libayatana-appindicator3-1"
dim "Install: sudo apt-get install -y libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev"

if [ "$WITH_DESKTOP" -eq 1 ]; then
    command -v pkg-config >/dev/null 2>&1 || die "pkg-config was not found." \
        "Install it:  sudo apt-get install -y pkg-config"
    missing=""
    for pkg in webkit2gtk-4.1 gtk+-3.0 ayatana-appindicator3-0.1; do
        if pkg-config --exists "$pkg" 2>/dev/null; then
            ok "$pkg"
        else
            missing="$missing $pkg"
        fi
    done
    if [ -n "$missing" ]; then
        die "Missing desktop build dependencies:$missing" \
            "sudo apt-get install -y libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev"
    fi
    if ! ( cd "$RUST_DIR" && cargo tauri --version >/dev/null 2>&1 ); then
        die "cargo tauri is not available." \
            "Install the Tauri CLI once:" \
            "  cargo install tauri-cli --version \"^2\""
    fi
else
    info "Skipping the check: the CLI does not link against WebKitGTK."
fi

# ---------------------------------------------------------------------------
# Build the CLI
# ---------------------------------------------------------------------------

section "Building the CLI (ofm-cli, release)"
( cd "$RUST_DIR" && cargo build --release -p ofm-cli )

TARGET_ROOT="$RUST_DIR/target"
if [ -n "${CARGO_TARGET_DIR:-}" ]; then
    case "$CARGO_TARGET_DIR" in
        /*) TARGET_ROOT="$CARGO_TARGET_DIR" ;;
        *)  TARGET_ROOT="$RUST_DIR/$CARGO_TARGET_DIR" ;;
    esac
fi
CLI_BIN="$TARGET_ROOT/release/ofm"
[ -f "$CLI_BIN" ] || die "The CLI binary was not found at $CLI_BIN" \
    "cargo build --release -p ofm-cli must succeed."
ok "ofm built"

DESKTOP_BIN=""
if [ "$WITH_DESKTOP" -eq 1 ]; then
    section "Bundling the desktop shell (cargo tauri build)"
    if [ ! -f "$ICON_DIR/icon.ico" ] || [ ! -f "$ICON_DIR/icon.icns" ]; then
        [ -f "$REPO_ROOT/docs/app-icon.png" ] || die \
            "The icon source was not found at $REPO_ROOT/docs/app-icon.png" \
            "docs/app-icon.png in the repository root is the square source icon."
        ( cd "$RUST_DIR" && cargo tauri icon "$REPO_ROOT/docs/app-icon.png" --output "$ICON_DIR" )
    else
        dim "The icon set is already present; skipping cargo tauri icon."
    fi
    ( cd "$DESKTOP_DIR" && cargo tauri build )
    # Tauri leaves the crate artifact in target/release; the bundle directories
    # hold copies. Accept either name in case Tauri ever renames it.
    for candidate in "$TARGET_ROOT/release/ofm-desktop" "$TARGET_ROOT/release/DeepL-oFM"; do
        if [ -f "$candidate" ]; then DESKTOP_BIN="$candidate"; break; fi
    done
    if [ -z "$DESKTOP_BIN" ]; then
        die "The desktop binary was not found under $TARGET_ROOT/release." \
            "cargo tauri build must finish successfully."
    fi
    ok "Desktop binary: $DESKTOP_BIN"
fi

# ---------------------------------------------------------------------------
# Assemble the tarball
# ---------------------------------------------------------------------------

section "Assembling the CLI package"

[ -n "$DIST_DIR" ] && [ "$DIST_DIR" = "$RUST_DIR/dist" ] || die "Refusing to clean an unexpected directory: ${DIST_DIR:-<empty>}"
rm -rf -- "$DIST_DIR"
mkdir -p "$DIST_DIR"
SUMS_NAME="SHA256SUMS-linux-$ARCH.txt"

STAGE_DIR="$TARGET_ROOT/release-stage/linux"
PKG_NAME="ofm-$VERSION-linux-$ARCH"
PKG_ROOT="$STAGE_DIR/$PKG_NAME"
rm -rf -- "$STAGE_DIR"
mkdir -p "$PKG_ROOT/share/applications" \
         "$PKG_ROOT/share/icons/hicolor/256x256/apps"

install -m 0755 "$CLI_BIN" "$PKG_ROOT/ofm"
if [ -n "$DESKTOP_BIN" ]; then
    install -m 0755 "$DESKTOP_BIN" "$PKG_ROOT/ofm-desktop"
    ok "ofm-desktop packed next to the CLI"
fi

# Icon: the 512x512 PNG that `cargo tauri icon` generates, else the source.
PKG_ICON=""
for candidate in "$ICON_DIR/icon.png" "$ICON_DIR/128x128@2x.png" "$REPO_ROOT/docs/app-icon.png"; do
    if [ -f "$candidate" ]; then PKG_ICON="$candidate"; break; fi
done
if [ -n "$PKG_ICON" ]; then
    install -m 0644 "$PKG_ICON" "$PKG_ROOT/share/icons/hicolor/256x256/apps/$ICON_NAME.png"
    ok "Icon: $PKG_ICON"
else
    warn "No icon was found; the tarball has no icon."
fi

# Launcher for the Tauri shell. The .deb/.AppImage/.rpm bundles ship their own
# entry with the right Exec=; this one is for the tarball, which carries
# ofm-desktop only when the package was built with --with-desktop.
cat > "$PKG_ROOT/share/applications/$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=DeepL-oFM
GenericName=Translator
Comment=Translate text and documents with local or cloud models
# This entry launches the Tauri shell (ofm-desktop). Adjust Exec= if it is
# installed under another path (for example /usr/bin/DeepL-oFM).
Exec=ofm-desktop %U
TryExec=ofm-desktop
Icon=$ICON_NAME
Terminal=false
Categories=Utility;TextTools;
Keywords=translate;translation;deepl;ollama;openrouter;groq;
StartupWMClass=DeepL-oFM
X-GNOME-UsesNotifications=true
EOF
ok "Launcher entry: share/applications/$DESKTOP_FILE"

if command -v desktop-file-validate >/dev/null 2>&1; then
    if desktop-file-validate "$PKG_ROOT/share/applications/$DESKTOP_FILE"; then
        ok "desktop-file-validate: clean"
    else
        warn "desktop-file-validate reported problems in $DESKTOP_FILE"
    fi
else
    dim "desktop-file-validate is not installed; the .desktop entry is unchecked."
fi

INSTALL_NOTE=""
if [ -n "$DESKTOP_BIN" ]; then
    INSTALL_NOTE="

    sudo install -Dm755 ofm-desktop /usr/local/bin/ofm-desktop"
fi

FILES_NOTE="$(printf '    %-49s %s' 'ofm' 'the headless CLI')"
if [ -n "$DESKTOP_BIN" ]; then
    FILES_NOTE="$FILES_NOTE
$(printf '    %-49s %s' 'ofm-desktop' 'the Tauri desktop shell (GUI)')"
fi
FILES_NOTE="$FILES_NOTE
$(printf '    %-49s %s' "share/applications/$DESKTOP_FILE" 'launcher for the desktop shell')
$(printf '    %-49s %s' "share/icons/hicolor/256x256/apps/$ICON_NAME.png" 'launcher icon')
$(printf '    %-49s %s' 'LICENSE' 'MIT')"

cat > "$PKG_ROOT/README.md" <<EOF
# DeepL-oFM $VERSION - Linux

Command-line build of DeepL-oFM$( [ -n "$DESKTOP_BIN" ] && printf ', plus the Tauri desktop shell' ).

## Install

    sudo install -Dm755 ofm /usr/local/bin/ofm
    ofm --help$INSTALL_NOTE

## Files

$FILES_NOTE

The SHA-256 of this tarball is published as $SUMS_NAME next to it.

## Desktop launcher

    sudo install -Dm644 share/applications/$DESKTOP_FILE \\
        /usr/share/applications/$DESKTOP_FILE
    sudo install -Dm644 share/icons/hicolor/256x256/apps/$ICON_NAME.png \\
        /usr/share/icons/hicolor/256x256/apps/$ICON_NAME.png

The launcher runs \`ofm-desktop\` from PATH. The shell needs libwebkit2gtk-4.1,
libgtk-3 and libayatana-appindicator3 at runtime, and the WebView libraries are
not bundled here: install them with your distribution's package manager.
EOF
ok "README.md"

if [ -f "$REPO_ROOT/LICENSE" ]; then
    install -m 0644 "$REPO_ROOT/LICENSE" "$PKG_ROOT/LICENSE"
fi

TARBALL_NAME="$PKG_NAME.tar.gz"
tar -czf "$DIST_DIR/$TARBALL_NAME" -C "$STAGE_DIR" "$PKG_NAME"
ok "Tarball: $TARBALL_NAME"

# ---------------------------------------------------------------------------
# Optional desktop bundles
# ---------------------------------------------------------------------------

DESKTOP_ARTIFACTS=()
if [ "$WITH_DESKTOP" -eq 1 ]; then
    section "Collecting the desktop bundles"
    BUNDLE_DIR="$TARGET_ROOT/release/bundle"
    for kind in deb appimage rpm; do
        [ -d "$BUNDLE_DIR/$kind" ] || continue
        while IFS= read -r -d '' artifact; do
            cp -f "$artifact" "$DIST_DIR/"
            DESKTOP_ARTIFACTS+=("$(basename "$artifact")")
            ok "$(basename "$artifact")"
        done < <(find "$BUNDLE_DIR/$kind" -maxdepth 1 -type f \
                     \( -name '*.deb' -o -name '*.AppImage' -o -name '*.rpm' \) -print0)
    done
    if [ "${#DESKTOP_ARTIFACTS[@]}" -eq 0 ]; then
        warn "cargo tauri build produced no .deb/.AppImage/.rpm bundle."
    fi
fi

# ---------------------------------------------------------------------------
# Checksums
# ---------------------------------------------------------------------------

section "Writing SHA256SUMS"

SUM_TOOL=""
if command -v sha256sum >/dev/null 2>&1; then
    SUM_TOOL="sha256sum"
elif command -v shasum >/dev/null 2>&1; then
    SUM_TOOL="shasum -a 256"
else
    die "Neither sha256sum nor shasum is available."
fi

(
    cd "$DIST_DIR"
    # shellcheck disable=SC2086
    $SUM_TOOL "$TARBALL_NAME" "${DESKTOP_ARTIFACTS[@]+"${DESKTOP_ARTIFACTS[@]}"}" > "$SUMS_NAME"
)
ok "$SUMS_NAME"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

section "Done"
dim "Version: $VERSION"
dim "Output:  $DIST_DIR"
printf '\n'
( cd "$DIST_DIR" && ls -lh )
printf '\n'
