# Packaging — DeepL-oFM (Rust port)

Release tooling for the workspace in `rust/`: library crates `ofm-*`, the CLI
binary **`ofm`** from `ofm-cli`, and the Tauri v2 shell `ofm-desktop` (product
**DeepL-oFM**, identifier `ua.admin.hymt`, static frontend `rust/ui/` with
`frontendDist: ../ui`).

Each script writes its artifacts to `rust/dist/`. Windows and Linux stage the
package tree under `rust/target/release-stage/windows` and
`rust/target/release-stage/linux` (macOS has no staging tree; `lipo` writes
straight into `dist/`). `.github/workflows/release.yml` runs the same scripts,
so a CI release and a hand-made one produce the same files.

```
rust/packaging/windows/build.ps1    Windows  (PowerShell 5.1+)
rust/packaging/macos/build.sh       macOS    (Xcode Command Line Tools)
rust/packaging/linux/build.sh       Linux
```

## What each script produces

| Script | In `rust/dist/` |
|---|---|
| `windows/build.ps1` | `DeepL-oFM-<ver>-windows-x64.zip` — contains `DeepL-oFM.exe` (portable), the NSIS `DeepL-oFM_<ver>_x64-setup.exe`, the WiX `*.msi`, `ofm.exe` and a `SHA256SUMS` listing those files. Plus `SHA256SUMS-windows-x64.txt`, the SHA-256 **of the zip**, so a download can be checked before it is opened. |
| `macos/build.sh` | `ofm-<ver>-macos-universal` (lipo of arm64 + x86_64), the DMG that Tauri produced (`DeepL-oFM_<ver>_universal.dmg`), and `SHA256SUMS-macos-universal.txt` covering both. |
| `linux/build.sh` | `ofm-<ver>-linux-<arch>.tar.gz` — contains `ofm`, `README.md`, `LICENSE`, `share/applications/ua.admin.hymt.desktop` and `share/icons/hicolor/256x256/apps/deepl-ofm.png`. Plus `SHA256SUMS-linux-<arch>.txt` covering the tarball. With `--with-desktop` the tarball also carries `ofm-desktop`, and the `.deb`, `.AppImage` and `.rpm` bundles are copied into `rust/dist/`. |

Flags: `build.ps1` takes `-SkipBuild` (reuse what tauri-action built),
`-SkipIconGeneration`, `-SkipDesktop` (CLI only), `-SkipSign`, `-SkipArchive`,
`-RequireWebView2` (fail instead of warn when the runtime is absent) and
`-OutputDirectory`. `macos/build.sh` takes `--stage-only` (stage/checksum what
already exists, used after tauri-action), `--skip-desktop` and `--skip-notarize`.
`linux/build.sh` takes `--with-desktop`. Every script has `--help`.

### Icons

`docs/app-icon.png` (256×256 RGBA) is the only icon source. The icon set is
generated once and is **build output**:

```bash
cd rust && cargo tauri icon ../docs/app-icon.png --output crates/desktop/icons
```

The scripts and the workflow run that command (the scripts pass absolute
paths) only when `crates/desktop/icons/icon.ico` or `icon.icns` is missing.
`tauri.conf.json` lists `icons/32x32.png`, `128x128.png`, `128x128@2x.png`,
`icon.ico` and `icon.icns`, so the shell cannot be bundled before this runs.

## Signed release: the secrets a maintainer must set

All eight are optional. With none of them the workflows still build, upload
unsigned artifacts and print the manual signing steps; no job fails because a
secret is missing.

| GitHub secret | Platform | Consumed by | Meaning |
|---|---|---|---|
| `WINDOWS_CERT_PFX_BASE64` | Windows | *Stage the Windows artifacts* step | Base64 of a `.pfx` with an Authenticode code-signing certificate |
| `WINDOWS_CERT_PASSWORD` | Windows | same step | Password of that `.pfx` |
| `APPLE_CERT_P12_BASE64` | macOS | *Prepare the macOS signing identity* step | Base64 of a Developer ID Application `.p12` |
| `APPLE_CERT_PASSWORD` | macOS | same step | Password of that `.p12` |
| `APPLE_SIGNING_IDENTITY` | macOS | tauri-action, through `GITHUB_ENV` | e.g. `Developer ID Application: Name (TEAMID)`; detected from the imported certificate when omitted |
| `APPLE_ID` | macOS | *Stage the macOS artifacts* step | Apple ID for notarization |
| `APPLE_TEAM_ID` | macOS | same step | Apple Developer team id |
| `APPLE_PASSWORD` | macOS | same step | App-specific password for `APPLE_ID` (not the account password) |

Linux artifacts are not signed; publish the `SHA256SUMS-linux-*.txt` next to them.

The scripts themselves read **environment variables**, never GitHub secrets:

```bash
# windows/build.ps1
$env:CODESIGN_CERT     = "C:\certs\deepl-ofm.pfx"   # path to the .pfx
$env:CODESIGN_PASSWORD = "..."                      # required when CODESIGN_CERT is set

# macos/build.sh
export APPLE_SIGNING_IDENTITY="Developer ID Application: Name (TEAMID)"
export APPLE_ID="you@example.com"
export APPLE_TEAM_ID="TEAMID"
export APPLE_PASSWORD="xxxx-xxxx-xxxx-xxxx"         # app-specific password
```

`cargo tauri build` signs the `.app`; `macos/build.sh` then notarizes and
staples the **DMG** with `xcrun notarytool` + `stapler`, so the downloaded DMG
carries the ticket. With only `APPLE_SIGNING_IDENTITY` set the result is signed
but not notarized and the script prints the three commands to finish by hand.
On Windows the `.exe`/`.msi` files are signed with `signtool` after staging; the
NSIS payload inside the installer keeps the signature it was built with.

## Running a release by hand

```bash
# 1. Version — keep these three in sync, then commit.
#      rust/Cargo.toml               [workspace.package] version
#      rust/crates/desktop/tauri.conf.json   "version"
#      CHANGELOG.md

# 2. Build on each machine (each writes rust/dist/).
pwsh rust/packaging/windows/build.ps1
rust/packaging/macos/build.sh
rust/packaging/linux/build.sh --with-desktop

# 3. Check what you are about to ship.
cd rust/dist
sha256sum -c SHA256SUMS-linux-x86_64.txt
shasum -a 256 -c SHA256SUMS-macos-universal.txt
# Windows: unzip, then inside the extracted directory
#   Get-FileHash DeepL-oFM.exe, ofm.exe -Algorithm SHA256   # compare to SHA256SUMS

# 4. Tag and push — the tag drives the workflow.
git tag -a rust-v2.0.1 -m "DeepL-oFM 2.0.1 (Rust)"
git push origin rust-v2.0.1

# 5. Review the draft release, then publish it.
gh release view rust-v2.0.1 --web
```

A dry run without a real tag goes through `workflow_dispatch`:

```bash
gh workflow run release.yml --repo <owner>/<repo> -f tag=rust-v2.0.1-rc1
```

The `tag` input defaults to `rust-v<version from tauri.conf.json>`. The workflow
creates the tag at the dispatched commit if it does not exist, accepts
`rust-v...-rc1`-style tags, and only warns when a tag does not match the version
in `tauri.conf.json`.

## What the workflow does

* `metadata` — reads the version from `rust/crates/desktop/tauri.conf.json`,
  resolves the tag, rejects anything that does not start with `rust-v`.
* `build` (matrix: `windows-x64`, `macos-universal`, `linux-x86_64`) — installs
  `cargo-tauri`, generates the icons, builds `ofm-cli` (both Apple targets on
  macOS), bundles the shell with `tauri-apps/tauri-action`
  (`--target universal-apple-darwin` on macOS), then calls the platform script
  to stage, sign when secrets exist, checksum and upload a workflow artifact.
  Linux builds the CLI tarball only.
* `publish` — verifies every `SHA256SUMS-*.txt` with `sha256sum -c --strict`,
  writes an aggregate `SHA256SUMS.txt` for all assets, creates (or reuses) a
  **draft** release and uploads everything with `gh release upload --clobber`.

## The limitation: the desktop shell needs the platform WebView

The Tauri shell is not a portable binary: it is a thin Rust binary that loads
the system WebView.

* **Windows** — needs the MSVC toolchain and the Windows SDK to build, and the
  **WebView2 runtime** to run (Windows 11 ships it; Windows 10 needs the
  [Evergreen Bootstrapper](https://developer.microsoft.com/microsoft-edge/webview2/)).
  `build.ps1` checks the runtime (registry, then the EdgeWebView directory) and
  warns; `-RequireWebView2` turns that into an error.
* **macOS** — needs the Xcode Command Line Tools; a universal DMG needs both
  `aarch64-apple-darwin` and `x86_64-apple-darwin` installed, because the CLI is
  built twice and merged with `lipo` while `cargo tauri build --target
  universal-apple-darwin` does the app part. Running it needs the system WebKit.
* **Linux** — needs `libwebkit2gtk-4.1-dev`, `libgtk-3-dev` and
  `libayatana-appindicator3-dev` at build time, and the matching runtime
  libraries (`libwebkit2gtk-4.1-0`, `libgtk-3-0`, `libayatana-appindicator3-1`).

Therefore **the desktop shell cannot be built on a machine without those
libraries — including this repository's Linux container, where it cannot be
built at all.** Here `pkg-config --exists` reports `webkit2gtk-4.1`, `gtk+-3.0`
and `ayatana-appindicator3-0.1` as missing, so `cargo build -p ofm-desktop` and
`cargo tauri build` both fail before compiling; only `ofm-cli` and the library
crates build and test. Nothing in this directory pretends otherwise:
`cargo tauri build` was **not** run while writing this tooling and no installer,
DMG or AppImage was produced. What *was* verified: `bash -n` on both shell
scripts; a stubbed end-to-end run of `linux/build.sh` (tarball, `.desktop`
accepted by `desktop-file-validate`, checksums verified); a PyYAML parse of the
workflow and `bash -n` on every `run:` block in it; and a line-by-line review of
every cmdlet and parameter in `build.ps1`, because no PowerShell is installed
here. The macOS build and both Tauri bundles remain unexecuted.

Two further caveats:

* `cargo tauri build` downloads the NSIS/WiX tooling (Windows) and the AppImage
  tooling (Linux) on first use; the scripts do not vendor it, so the first
  release build needs network access.
* `rust/target/` and `.cargo-home/` are git-ignored, but `rust/dist/` and
  `rust/crates/desktop/icons/` are not yet — add both to `.gitignore`; they are
  build output and must not be committed.
