#!/usr/bin/env bash
#
# Builds and packages the DeepL-oFM Rust port on macOS.
#
# Produces, in <repo>/rust/dist:
#
#   DeepL-oFM_<version>_universal.dmg     universal (arm64 + x86_64) disk image
#   ofm-<version>-macos-universal         universal command-line binary
#   SHA256SUMS-macos-universal.txt        checksums of the two files above
#
# Requirements:
#   * Xcode Command Line Tools (xcode-select --install) for clang, lipo, codesign
#   * Rust stable 1.82+ via rustup, with both Apple targets installed:
#       rustup target add aarch64-apple-darwin x86_64-apple-darwin
#   * cargo-tauri 2.x:  cargo install tauri-cli --version "^2"
#
# Signing and notarization are optional:
#   APPLE_SIGNING_IDENTITY  "Developer ID Application: Name (TEAMID)" in the keychain
#   APPLE_ID                Apple ID used for notarization
#   APPLE_TEAM_ID           Apple Developer team id
#   APPLE_PASSWORD          app-specific password for that Apple ID
# Without them the DMG is unsigned and the script prints exact instructions.
#
# Usage:
#   ./build.sh                 # full build + package + optional signing
#   ./build.sh --skip-desktop  # CLI only
#   ./build.sh --stage-only    # assume the binaries/bundles already exist
#                              # (used by .github/workflows/release.yml after
#                              # tauri-action has built the app), only stage,
#                              # checksum and optionally notarize
#   ./build.sh --skip-notarize # sign but do not notarize

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUST_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="$(cd "$RUST_DIR/.." && pwd)"
DESKTOP_DIR="$RUST_DIR/crates/desktop"
TAURI_CONF="$DESKTOP_DIR/tauri.conf.json"
ICON_SOURCE="$REPO_ROOT/docs/app-icon.png"
ICON_DIR="$DESKTOP_DIR/icons"
DIST_DIR="$RUST_DIR/dist"
CLI_TARGETS=(aarch64-apple-darwin x86_64-apple-darwin)
UNIVERSAL_TARGET="universal-apple-darwin"

STAGE_ONLY=0
SKIP_DESKTOP=0
SKIP_NOTARIZE=0

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

  (no options)      Build the universal CLI and the Tauri app, sign when
                    APPLE_SIGNING_IDENTITY is set, package the DMG.
  --skip-desktop    Build and package the CLI only.
  --stage-only      Do not build. Stage and checksum the binaries and bundles
                    that already exist (the release workflow calls this after
                    tauri-action), then notarize when credentials are set.
  --skip-notarize   Sign (if possible) but do not submit to the notary service.
  -h, --help        Show this help.

Environment:
  APPLE_SIGNING_IDENTITY  Developer ID Application identity in the keychain
  APPLE_ID                Apple ID for notarization
  APPLE_TEAM_ID           Apple Developer team id
  APPLE_PASSWORD          app-specific password for APPLE_ID
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --stage-only)   STAGE_ONLY=1 ;;
        --skip-desktop) SKIP_DESKTOP=1 ;;
        --skip-notarize) SKIP_NOTARIZE=1 ;;
        -h|--help)      usage; exit 0 ;;
        *)              die "Unknown option: $1" "Run: $0 --help" ;;
    esac
    shift
done

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

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
# Preconditions
# ---------------------------------------------------------------------------

section "Checking the platform and the Xcode Command Line Tools"

[ "$(uname -s)" = "Darwin" ] || die "This script must run on macOS (uname -s reports $(uname -s))." \
    "Use packaging/windows/build.ps1 or packaging/linux/build.sh instead."

if ! xcode-select -p >/dev/null 2>&1; then
    die "The Xcode Command Line Tools are not installed." \
        "Install them:  xcode-select --install" \
        "Then re-run this script."
fi
ok "Command Line Tools at $(xcode-select -p)"

for tool in lipo codesign xcrun; do
    command -v "$tool" >/dev/null 2>&1 || die "$tool was not found." \
        "Install the Xcode Command Line Tools:  xcode-select --install"
done

if command -v cargo >/dev/null 2>&1; then
    dim "cargo: $(cargo --version 2>/dev/null || echo unknown)"
else
    die "cargo was not found in PATH." \
        "Install Rust from https://rustup.rs (stable, 1.82 or newer)."
fi

section "Checking the Rust targets"

if [ "$STAGE_ONLY" -eq 0 ]; then
    command -v rustup >/dev/null 2>&1 || die "rustup was not found in PATH." \
        "Install Rust through rustup:  https://rustup.rs"

    INSTALLED_TARGETS="$(rustup target list --installed)"
    for target in "${CLI_TARGETS[@]}"; do
        case " $INSTALLED_TARGETS " in
            *" $target "*) ok "$target" ;;
            *) die "The Rust target $target is not installed." \
                   "Install it:  rustup target add $target" ;;
        esac
    done

    if ! ( cd "$RUST_DIR" && cargo tauri --version >/dev/null 2>&1 ); then
        die "cargo tauri is not available." \
            "Install the Tauri CLI once:" \
            "  cargo install tauri-cli --version \"^2\"" \
            "Then re-run this script."
    fi
    dim "cargo tauri: $( cd "$RUST_DIR" && cargo tauri --version 2>/dev/null | head -n 1 )"
else
    info "Skipping the rustup and target checks: --stage-only does not build."
fi

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

TARGET_ROOT="$RUST_DIR/target"
if [ -n "${CARGO_TARGET_DIR:-}" ]; then
    case "$CARGO_TARGET_DIR" in
        /*) TARGET_ROOT="$CARGO_TARGET_DIR" ;;
        *)  TARGET_ROOT="$RUST_DIR/$CARGO_TARGET_DIR" ;;
    esac
fi
RELEASE_DIR="$TARGET_ROOT/$UNIVERSAL_TARGET/release"

if [ "$STAGE_ONLY" -eq 0 ]; then
    section "Building the CLI for both architectures"
    ( cd "$RUST_DIR" && cargo build --release -p ofm-cli --target aarch64-apple-darwin )
    ( cd "$RUST_DIR" && cargo build --release -p ofm-cli --target x86_64-apple-darwin )
    ok "ofm-cli built for arm64 and x86_64"

    if [ "$SKIP_DESKTOP" -eq 0 ]; then
        if [ ! -f "$ICON_DIR/icon.icns" ] || [ ! -f "$ICON_DIR/icon.ico" ]; then
            [ -f "$ICON_SOURCE" ] || die "The icon source was not found at $ICON_SOURCE" \
                "docs/app-icon.png in the repository root is the square source icon."
            section "Generating the icon set (cargo tauri icon)"
            ( cd "$RUST_DIR" && cargo tauri icon "$ICON_SOURCE" --output "$ICON_DIR" )
        else
            dim "The icon set is already present; skipping cargo tauri icon."
        fi

        section "Bundling the universal app and DMG (cargo tauri build)"
        dim "Signing identity: ${APPLE_SIGNING_IDENTITY:-<unset, unsigned build>}"
        # Notarization is done explicitly below with notarytool, so the Tauri
        # CLI must not try it on its own (it would need the same credentials).
        ( cd "$DESKTOP_DIR" && env \
            -u APPLE_ID -u APPLE_PASSWORD -u APPLE_TEAM_ID \
            cargo tauri build --target "$UNIVERSAL_TARGET" )
    fi
fi

# ---------------------------------------------------------------------------
# Collect
# ---------------------------------------------------------------------------

section "Collecting the artifacts"

APP_BUNDLE="$RELEASE_DIR/bundle/macos/DeepL-oFM.app"
DMG_PATH="$(find "$RELEASE_DIR/bundle/dmg" -maxdepth 1 -name '*.dmg' -print -quit 2>/dev/null || true)"

if [ "$SKIP_DESKTOP" -eq 0 ] && [ -z "$DMG_PATH" ]; then
    die "No DMG was produced under $RELEASE_DIR/bundle/dmg" \
        "cargo tauri build must finish successfully." \
        "Check that the icons exist and that it was run with --target $UNIVERSAL_TARGET."
fi

# The DMG is the artifact people download, so check that the app inside it was
# actually merged by lipo instead of trusting the target name.
if [ "$SKIP_DESKTOP" -eq 0 ] && [ -d "$APP_BUNDLE" ]; then
    APP_BIN=""
    for candidate in "$APP_BUNDLE/Contents/MacOS/ofm-desktop" "$APP_BUNDLE/Contents/MacOS/DeepL-oFM"; do
        if [ -f "$candidate" ]; then APP_BIN="$candidate"; break; fi
    done
    if [ -n "$APP_BIN" ]; then
        APP_ARCHS="$(lipo -archs "$APP_BIN" 2>/dev/null || true)"
        case "$APP_ARCHS" in
            *arm64*x86_64*|*x86_64*arm64*) ok "The app binary is universal ($APP_ARCHS)" ;;
            *) warn "The app binary is not universal (lipo -archs: ${APP_ARCHS:-unknown}); expected arm64 and x86_64." ;;
        esac
    else
        warn "Could not find the Mach-O binary inside $APP_BUNDLE to check its architectures."
    fi
fi

ARM_CLI="$TARGET_ROOT/aarch64-apple-darwin/release/ofm"
X86_CLI="$TARGET_ROOT/x86_64-apple-darwin/release/ofm"
if [ ! -f "$ARM_CLI" ] || [ ! -f "$X86_CLI" ]; then
    die "The per-architecture CLI binaries are missing." \
        "Build them first:" \
        "  cargo build --release -p ofm-cli --target aarch64-apple-darwin" \
        "  cargo build --release -p ofm-cli --target x86_64-apple-darwin"
fi

# Refuse to clean anything that is not the dist directory this script owns.
[ "$DIST_DIR" = "$RUST_DIR/dist" ] || die "Refusing to clean an unexpected directory: $DIST_DIR"
rm -rf -- "$DIST_DIR"
mkdir -p "$DIST_DIR"

CLI_NAME="ofm-$VERSION-macos-universal"
lipo -create -output "$DIST_DIR/$CLI_NAME" "$ARM_CLI" "$X86_CLI"
lipo -info "$DIST_DIR/$CLI_NAME"
CLI_ARCHS="$(lipo -archs "$DIST_DIR/$CLI_NAME" 2>/dev/null || true)"
case "$CLI_ARCHS" in
    *arm64*x86_64*|*x86_64*arm64*) ;;
    *) die "lipo did not produce a universal CLI binary (archs: ${CLI_ARCHS:-unknown})." \
           "Both inputs must exist and be Mach-O binaries for arm64 and x86_64." ;;
esac
chmod +x "$DIST_DIR/$CLI_NAME"
ok "Universal CLI: $CLI_NAME ($CLI_ARCHS)"

DMG_NAME=""
if [ "$SKIP_DESKTOP" -eq 0 ]; then
    DMG_NAME="$(basename "$DMG_PATH")"
    cp -f "$DMG_PATH" "$DIST_DIR/$DMG_NAME"
    ok "DMG: $DMG_NAME"
fi

# ---------------------------------------------------------------------------
# Signing and notarization report (signing itself is done by cargo tauri)
# ---------------------------------------------------------------------------

print_signing_instructions() {
    local dmg_ref="${DMG_NAME:-DeepL-oFM_${VERSION}_universal.dmg}"
    warn "The DMG is UNSIGNED and NOT NOTARIZED."
    cat <<EOF

To ship a signed and notarized DMG by hand:

  1. Install a "Developer ID Application" certificate in your login keychain and
     rebuild with the identity exported (the Tauri CLI signs the .app for you):

       export APPLE_SIGNING_IDENTITY="Developer ID Application: Your Name (TEAMID)"
       ( cd "$DESKTOP_DIR" && cargo tauri build --target $UNIVERSAL_TARGET )

  2. Notarize the DMG (create an app-specific password at https://appleid.apple.com):

       xcrun notarytool submit "$DIST_DIR/$dmg_ref" \\
         --apple-id "you@example.com" --team-id "TEAMID" \\
         --password "xxxx-xxxx-xxxx-xxxx" --wait

  3. Staple the ticket and verify what Gatekeeper will see:

       xcrun stapler staple "$DIST_DIR/$dmg_ref"
       xcrun stapler validate "$DIST_DIR/$dmg_ref"
       spctl --assess --type open --context context:primary-signature -v "$DIST_DIR/$dmg_ref"

  Or export APPLE_ID / APPLE_TEAM_ID / APPLE_PASSWORD and re-run this script:
  it notarizes and staples the DMG for you.

EOF
}

if [ "$SKIP_DESKTOP" -eq 0 ]; then
    section "Signing and notarization (optional)"

    # An Apple-silicon build is always at least ad-hoc signed, so look for a
    # real Developer ID authority instead of trusting `codesign --verify`.
    APP_SIGNED=0
    if [ -d "$APP_BUNDLE" ] && codesign -dv --verbose=2 "$APP_BUNDLE" >/dev/null 2>&1; then
        if codesign -dv --verbose=2 "$APP_BUNDLE" 2>&1 | grep -q 'Authority=Developer ID Application'; then
            APP_SIGNED=1
        fi
    fi

    if [ "$APP_SIGNED" -eq 1 ]; then
        ok "The app bundle is signed with a Developer ID"
        if [ "$SKIP_NOTARIZE" -eq 1 ]; then
            warn "Notarization skipped (--skip-notarize); the DMG is signed but not notarized."
        elif [ -n "${APPLE_ID:-}" ] && [ -n "${APPLE_TEAM_ID:-}" ] && [ -n "${APPLE_PASSWORD:-}" ]; then
            info "Submitting $DMG_NAME to the Apple notary service (this can take a few minutes)"
            xcrun notarytool submit "$DIST_DIR/$DMG_NAME" \
                --apple-id "$APPLE_ID" \
                --team-id "$APPLE_TEAM_ID" \
                --password "$APPLE_PASSWORD" \
                --wait
            xcrun stapler staple "$DIST_DIR/$DMG_NAME"
            xcrun stapler validate "$DIST_DIR/$DMG_NAME"
            if ! spctl --assess --type open --context context:primary-signature -v "$DIST_DIR/$DMG_NAME"; then
                warn "spctl did not accept the DMG yet; Gatekeeper may need a moment to refresh its cache."
            fi
            ok "The DMG is notarized and stapled"
        else
            warn "APPLE_ID / APPLE_TEAM_ID / APPLE_PASSWORD are not all set; not notarizing."
            info "The DMG is signed but not notarized: macOS will warn on first launch."
            print_signing_instructions
        fi
    else
        warn "The app bundle is not signed (APPLE_SIGNING_IDENTITY is not set)."
        print_signing_instructions
    fi
fi

# ---------------------------------------------------------------------------
# Checksums
# ---------------------------------------------------------------------------

section "Writing SHA256SUMS"

SUM_TOOL=""
if command -v shasum >/dev/null 2>&1; then
    SUM_TOOL="shasum -a 256"
elif command -v sha256sum >/dev/null 2>&1; then
    SUM_TOOL="sha256sum"
else
    die "Neither shasum nor sha256sum is available."
fi

SUMS_NAME="SHA256SUMS-macos-universal.txt"
(
    cd "$DIST_DIR"
    if [ "$SKIP_DESKTOP" -eq 0 ]; then
        # shellcheck disable=SC2086
        $SUM_TOOL "$DMG_NAME" "$CLI_NAME" > "$SUMS_NAME"
    else
        # shellcheck disable=SC2086
        $SUM_TOOL "$CLI_NAME" > "$SUMS_NAME"
    fi
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
