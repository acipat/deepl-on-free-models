#!/usr/bin/env bash
# Wrapper so every cargo invocation uses a workspace-local CARGO_HOME.
# The harness sandbox keeps ~/.cargo read-only, so the registry cache must live
# inside the workspace. Use this script instead of calling cargo directly.
set -euo pipefail
export CARGO_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../.cargo-home"
exec cargo "$@"
