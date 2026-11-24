#!/usr/bin/env bash
# Disk-usage guard for the DeepL-oFM Rust workspace.
#
# Prints free space plus the size of the directories that actually grow, and
# exits non-zero when free space drops below MIN_FREE_GIB (default: 10 GiB).
# Run it from anywhere; it locates the repository from its own path.
#
# Reclaim space with:  cd rust && ./cargo.sh clean
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUST_DIR="$REPO_ROOT/rust"
CARGO_HOME_DIR="$REPO_ROOT/.cargo-home"
VENV_DIR="$REPO_ROOT/windows/.venv"
MIN_FREE_GIB="${MIN_FREE_GIB:-10}"

size_of() {
    if [ -e "$1" ]; then
        du -sh "$1" 2>/dev/null | cut -f1
    else
        printf 'absent'
    fi
}

echo "== df -h $REPO_ROOT"
df -h "$REPO_ROOT"

echo
echo "== build output and caches"
printf '  %-22s %s\n' "rust/target" "$(size_of "$RUST_DIR/target")"
printf '  %-22s %s\n' "rust/target/debug" "$(size_of "$RUST_DIR/target/debug")"
printf '  %-22s %s\n' ".cargo-home" "$(size_of "$CARGO_HOME_DIR")"
printf '  %-22s %s\n' "windows/.venv" "$(size_of "$VENV_DIR")"

# df -Pk: POSIX output, 1024-byte blocks; field 4 is available blocks.
AVAIL_KB="$(df -Pk "$REPO_ROOT" | awk 'NR == 2 { print $4 }')"
AVAIL_GIB=$((AVAIL_KB / 1024 / 1024))

echo
if [ "$AVAIL_GIB" -lt "$MIN_FREE_GIB" ]; then
    echo "FAIL: ${AVAIL_GIB} GiB free, below the ${MIN_FREE_GIB} GiB floor." >&2
    echo "Reclaim: cd rust && ./cargo.sh clean (stop running cargo/rustc first)." >&2
    exit 1
fi

echo "OK: ${AVAIL_GIB} GiB free (floor ${MIN_FREE_GIB} GiB)."
