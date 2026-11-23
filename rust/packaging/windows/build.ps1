#Requires -Version 5.1
<#
.SYNOPSIS
    Builds and packages the DeepL-oFM Rust port on Windows.

.DESCRIPTION
    Produces, in <repo>/rust/dist:

        DeepL-oFM-<version>-windows-x64.zip   portable DeepL-oFM.exe, the NSIS
                                              installer, the MSI, ofm.exe and a
                                              SHA256SUMS file listing those
        SHA256SUMS-windows-x64.txt            SHA-256 of the .zip itself, so a
                                              downloaded archive can be checked
                                              before it is opened. With
                                              -SkipArchive it lists the staged
                                              files instead.

    The staged (unzipped) files live in rust/target/release-stage/windows.

    Requirements:
      * Rust stable 1.82+ with the *-pc-windows-msvc host triple
      * Visual Studio Build Tools with the "Desktop development with C++"
        workload (MSVC linker + Windows SDK)
      * WebView2 runtime (needed to *run* the app; Windows 11 has it)
      * cargo-tauri 2.x:  cargo install tauri-cli --version "^2"

    Signing is optional. Set both environment variables to sign with
    Authenticode:
        CODESIGN_CERT      path to a .pfx file
        CODESIGN_PASSWORD  the .pfx password
    When they are unset the artifacts stay unsigned and the script says so.

.PARAMETER OutputDirectory
    Where the final archives are written. Default: <repo>/rust/dist.

.PARAMETER SkipBuild
    Do not call cargo. Use the binaries and bundles that already exist (this is
    how the release workflow reuses tauri-action's output) and only stage,
    sign and checksum them.

.PARAMETER SkipIconGeneration
    Never call `cargo tauri icon`, even when icons/icon.ico is missing.

.PARAMETER SkipDesktop
    Build and package the CLI only.

.PARAMETER SkipSign
    Do not sign, even when CODESIGN_CERT is set.

.PARAMETER SkipArchive
    Do not create the .zip; stage the files only.

.PARAMETER RequireWebView2
    Fail instead of warning when the WebView2 runtime is missing.

.EXAMPLE
    pwsh -File rust/packaging/windows/build.ps1

.EXAMPLE
    # Reuse a build that tauri-action already produced, then sign and zip it.
    pwsh -File rust/packaging/windows/build.ps1 -SkipBuild -SkipIconGeneration

.NOTES
    PowerShell 5.1 compatible. Must run on Windows.
#>
[CmdletBinding()]
param(
    [string] $OutputDirectory = '',
    [switch] $SkipBuild,
    [switch] $SkipIconGeneration,
    [switch] $SkipDesktop,
    [switch] $SkipSign,
    [switch] $SkipArchive,
    [switch] $RequireWebView2
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-StrictMode -Version 2.0
$LASTEXITCODE = 0

# --------------------------------------------------------------------------
# Paths and helpers
# --------------------------------------------------------------------------

$PackagingDir = Split-Path -Parent $PSScriptRoot            # rust/packaging
$RustDir      = Split-Path -Parent $PackagingDir            # rust
$RepoRoot     = Split-Path -Parent $RustDir                 # repository root
$DesktopDir   = Join-Path $RustDir 'crates\desktop'
$TauriConf    = Join-Path $DesktopDir 'tauri.conf.json'
$IconDir      = Join-Path $DesktopDir 'icons'
$IconSource   = Join-Path $RepoRoot 'docs\app-icon.png'
$Pf86         = [System.Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
$ProgramFiles = [System.Environment]::GetEnvironmentVariable('ProgramFiles')

function Write-Section {
    param([string] $Text)
    Write-Host ''
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Write-Note {
    param([string] $Text)
    Write-Host "    $Text" -ForegroundColor DarkGray
}

function Write-Ok {
    param([string] $Text)
    Write-Host "    OK: $Text" -ForegroundColor Green
}

function Write-Warn {
    param([string] $Text)
    Write-Host "    WARNING: $Text" -ForegroundColor Yellow
}

function Stop-Build {
    param([string] $Message, [string[]] $Remedy = @())
    Write-Host ''
    Write-Host "ERROR: $Message" -ForegroundColor Red
    foreach ($line in $Remedy) {
        Write-Host "  -> $line" -ForegroundColor Yellow
    }
    Write-Host ''
    exit 1
}

function Join-Native {
    param([string] $Root, [string] $Child)
    return [System.IO.Path]::Combine($Root, $Child)
}

# Reading $env:Foo for an unset variable is fragile under Set-StrictMode; go
# through the .NET API so a missing variable is simply an empty string.
function Get-Env {
    param([string] $Name)
    return [System.Environment]::GetEnvironmentVariable($Name)
}

# --------------------------------------------------------------------------
# Preconditions
# --------------------------------------------------------------------------

if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    Stop-Build 'This script must run on Windows.' @('Use packaging/macos/build.sh or packaging/linux/build.sh instead.')
}

Write-Section 'Checking the Rust toolchain'
if ($null -eq (Get-Command cargo -ErrorAction SilentlyContinue)) {
    Stop-Build 'cargo was not found in PATH.' @(
        'Install Rust from https://rustup.rs (stable, 1.82 or newer) and open a new terminal.'
    )
}
if ($null -eq (Get-Command rustc -ErrorAction SilentlyContinue)) {
    Stop-Build 'rustc was not found in PATH.' @('Install the stable MSVC toolchain: rustup default stable-msvc')
}

$rustcInfo = & rustc -vV
if ($LASTEXITCODE -ne 0) {
    Stop-Build 'rustc -vV failed.' @('Check that the Rust installation is healthy: rustup show')
}
$hostLine = $rustcInfo | Where-Object { $_ -like 'host:*' } | Select-Object -First 1
if (-not $hostLine) {
    Stop-Build 'Could not determine the rustc host triple from rustc -vV.' @('Run rustc -vV manually and check the output.')
}
$hostTriple = ($hostLine -replace '^host:\s*', '').Trim()
Write-Note "rustc host triple: $hostTriple"
if ($hostTriple -notmatch 'pc-windows-msvc$') {
    Stop-Build "The active Rust toolchain targets '$hostTriple' instead of MSVC." @(
        'Tauri and the MSVC linker need the MSVC toolchain:',
        '  rustup toolchain install stable-x86_64-pc-windows-msvc',
        '  rustup default stable-x86_64-pc-windows-msvc'
    )
}

Write-Section 'Checking the MSVC build tools'
$msvcPath = $null
$vswhere = $null
if ($Pf86) {
    $candidate = Join-Native $Pf86 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path -LiteralPath $candidate) { $vswhere = $candidate }
}
if ($vswhere) {
    $msvcPath = & $vswhere -latest -products * `
        -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
        -property installationPath
    if ($msvcPath) { $msvcPath = ([string]$msvcPath).Trim() }
}
if (-not $msvcPath) {
    # A "Developer Command Prompt" already has the compiler on PATH.
    if (Get-Command link.exe -ErrorAction SilentlyContinue) {
        Write-Note 'link.exe is on PATH (Visual Studio Developer Command Prompt); using it.'
    }
    else {
        Stop-Build 'The MSVC C++ build tools were not found.' @(
            'Install "Desktop development with C++" from the Visual Studio Build Tools:',
            '  https://visualstudio.microsoft.com/vs/community/',
            '  https://visualstudio.microsoft.com/visual-cpp-build-tools/',
            'Then open a new terminal and re-run this script.',
            'Check what is installed with:',
            '  & "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -property installationPath'
        )
    }
}
else {
    Write-Ok "Visual Studio C++ tools at $msvcPath"
}

Write-Section 'Checking the WebView2 runtime'
$webView2Keys = @(
    'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'SOFTWARE\Microsoft\EdgeUpdate\Dev\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
)
$webView2Version = $null
foreach ($key in $webView2Keys) {
    foreach ($hive in @('HKLM:', 'HKCU:')) {
        $fullKey = $hive + '\' + $key
        if (-not (Test-Path -LiteralPath $fullKey)) { continue }
        $item = Get-ItemProperty -LiteralPath $fullKey -ErrorAction SilentlyContinue
        if ($null -eq $item) { continue }
        $prop = $item.PSObject.Properties['pv']
        if ($null -eq $prop) { continue }
        $value = [string]$prop.Value
        if (-not [string]::IsNullOrWhiteSpace($value) -and $value -ne '0.0.0.0') {
            $webView2Version = $value
            break
        }
    }
    if ($webView2Version) { break }
}
if (-not $webView2Version) {
    $roots = @()
    if ($Pf86) { $roots += (Join-Native $Pf86 'Microsoft\EdgeWebView\Application') }
    if ($ProgramFiles) { $roots += (Join-Native $ProgramFiles 'Microsoft\EdgeWebView\Application') }
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        $dirs = @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending)
        if ($dirs.Count -gt 0) {
            $webView2Version = $dirs[0].Name
            break
        }
    }
}

if ($webView2Version) {
    Write-Ok "WebView2 runtime $webView2Version"
}
else {
    Write-Warn 'The WebView2 runtime was not found.'
    Write-Note 'Building still works, but DeepL-oFM cannot start without it.'
    Write-Note 'Windows 11 ships it. On Windows 10 install the Evergreen Bootstrapper:'
    Write-Note '  https://developer.microsoft.com/microsoft-edge/webview2/'
    Write-Note 'Or: winget install --id Microsoft.EdgeWebView2Runtime'
    if ($RequireWebView2) {
        Stop-Build 'The WebView2 runtime is required and was not found.' @(
            'Install it: winget install --id Microsoft.EdgeWebView2Runtime',
            'Then re-run this script.'
        )
    }
}

# --------------------------------------------------------------------------
# Version, target dir and output dirs
# --------------------------------------------------------------------------

if (-not (Test-Path -LiteralPath $TauriConf)) {
    Stop-Build "tauri.conf.json was not found at $TauriConf." @('Run this script from a checkout of the repository.')
}
$conf = Get-Content -LiteralPath $TauriConf -Raw | ConvertFrom-Json
$version = [string]$conf.version
if ([string]::IsNullOrWhiteSpace($version)) {
    Stop-Build 'Could not read "version" from crates/desktop/tauri.conf.json.'
}
Write-Note "DeepL-oFM version: $version"

$targetDir = Join-Path $RustDir 'target'
if (Get-Env 'CARGO_TARGET_DIR') {
    $targetDir = Get-Env 'CARGO_TARGET_DIR'
    if (-not [System.IO.Path]::IsPathRooted($targetDir)) {
        $targetDir = Join-Native $RustDir $targetDir
    }
}
$releaseDir = Join-Native $targetDir 'release'
$stageDir   = Join-Native $targetDir 'release-stage\windows'

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $RustDir 'dist'
}
if (-not [System.IO.Path]::IsPathRooted($OutputDirectory)) {
    $OutputDirectory = Join-Native $RustDir $OutputDirectory
}
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)

# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------

if (-not $SkipBuild) {
    Write-Section 'Checking the Tauri CLI'
    $tauriOutput = $null
    try {
        $tauriOutput = & cargo tauri --version 2>$null
    }
    catch {
        $tauriOutput = $null
    }
    if ($LASTEXITCODE -ne 0 -or -not $tauriOutput) {
        Stop-Build 'cargo tauri is not available.' @(
            'Install the Tauri CLI once:',
            '  cargo install tauri-cli --version "^2"',
            'Then re-run this script.'
        )
    }
    Write-Ok "cargo tauri: $($tauriOutput | Select-Object -First 1)"

    if (-not $SkipIconGeneration) {
        $iconIco  = Join-Path $IconDir 'icon.ico'
        $iconIcns = Join-Path $IconDir 'icon.icns'
        if ((Test-Path -LiteralPath $iconIco) -and (Test-Path -LiteralPath $iconIcns)) {
            Write-Note 'The icon set is already present; skipping cargo tauri icon.'
        }
        else {
            if (-not (Test-Path -LiteralPath $IconSource)) {
                Stop-Build "The icon source was not found at $IconSource." @(
                    'docs/app-icon.png in the repository root is the square source icon.'
                )
            }
            Write-Section 'Generating the icon set (cargo tauri icon)'
            Push-Location -LiteralPath $RustDir
            try {
                & cargo tauri icon $IconSource --output $IconDir
                if ($LASTEXITCODE -ne 0) {
                    Stop-Build 'cargo tauri icon failed.' @(
                        'The source icon must be a square PNG: docs/app-icon.png'
                    )
                }
            }
            finally {
                Pop-Location
            }
        }
    }

    Write-Section 'Building the CLI (ofm-cli, release)'
    Push-Location -LiteralPath $RustDir
    try {
        & cargo build --release -p ofm-cli
        if ($LASTEXITCODE -ne 0) {
            Stop-Build 'cargo build -p ofm-cli failed.' @('Fix the compiler errors and re-run.')
        }
    }
    finally {
        Pop-Location
    }

    if (-not $SkipDesktop) {
        Write-Section 'Building the desktop shell (ofm-desktop, release)'
        Push-Location -LiteralPath $RustDir
        try {
            & cargo build --release -p ofm-desktop
            if ($LASTEXITCODE -ne 0) {
                Stop-Build 'cargo build -p ofm-desktop failed.' @(
                    'The Tauri shell needs the MSVC toolchain and the WebView2 development files.',
                    'See https://tauri.app/start/prerequisites/ for the Windows prerequisites.'
                )
            }
        }
        finally {
            Pop-Location
        }

        Write-Section 'Bundling the installers (cargo tauri build)'
        Push-Location -LiteralPath $DesktopDir
        try {
            & cargo tauri build
            if ($LASTEXITCODE -ne 0) {
                Stop-Build 'cargo tauri build failed.' @(
                    'The first run downloads the NSIS and WiX tooling; check the network.',
                    "Bundles are expected under: $releaseDir\bundle"
                )
            }
        }
        finally {
            Pop-Location
        }
    }
}

# --------------------------------------------------------------------------
# Collect the artifacts
# --------------------------------------------------------------------------

Write-Section 'Collecting the artifacts'
$cliExe = Join-Path $releaseDir 'ofm.exe'
if (-not (Test-Path -LiteralPath $cliExe)) {
    Stop-Build "The CLI binary was not found at $cliExe." @('Build it with: cargo build --release -p ofm-cli')
}

# Tauri v2 names the bundle after productName ("DeepL-oFM.app"/"DeepL-oFM.exe"),
# while cargo keeps the crate artifact at target/release/ofm-desktop.exe. Accept
# both so the script does not depend on which of the two Tauri leaves behind.
$desktopExe = $null
if (-not $SkipDesktop) {
    foreach ($candidate in @('ofm-desktop.exe', 'DeepL-oFM.exe')) {
        $path = Join-Path $releaseDir $candidate
        if (Test-Path -LiteralPath $path) { $desktopExe = $path; break }
    }
    if (-not $desktopExe) {
        Stop-Build "The desktop binary was not found under $releaseDir (looked for ofm-desktop.exe and DeepL-oFM.exe)." @(
            'Build it with: cargo build --release -p ofm-desktop',
            'or let tauri-action build it before calling this script with -SkipBuild.'
        )
    }
}

$installer = $null
$msi = $null
if (-not $SkipDesktop) {
    $nsisDir = Join-Native $releaseDir 'bundle\nsis'
    $msiDir  = Join-Native $releaseDir 'bundle\msi'
    if (Test-Path -LiteralPath $nsisDir) {
        $installer = Get-ChildItem -LiteralPath $nsisDir -Filter '*.exe' -File -ErrorAction SilentlyContinue |
            Sort-Object Name | Select-Object -Last 1
    }
    if (Test-Path -LiteralPath $msiDir) {
        $msi = Get-ChildItem -LiteralPath $msiDir -Filter '*.msi' -File -ErrorAction SilentlyContinue |
            Sort-Object Name | Select-Object -Last 1
    }
    if ($null -eq $installer) {
        Stop-Build 'No NSIS installer was produced.' @(
            "Expected an .exe under $nsisDir",
            'cargo tauri build must finish successfully; the first run downloads NSIS.'
        )
    }
    if ($null -eq $msi) {
        Stop-Build 'No MSI installer was produced.' @(
            "Expected an .msi under $msiDir",
            'cargo tauri build must finish successfully; the first run downloads WiX.'
        )
    }
}

if (Test-Path -LiteralPath $stageDir) {
    Remove-Item -LiteralPath $stageDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stageDir | Out-Null

$portableName = 'DeepL-oFM.exe'
if (-not $SkipDesktop) {
    Copy-Item -LiteralPath $desktopExe -Destination (Join-Path $stageDir $portableName) -Force
    Copy-Item -LiteralPath $installer.FullName -Destination (Join-Native $stageDir $installer.Name) -Force
    Copy-Item -LiteralPath $msi.FullName -Destination (Join-Native $stageDir $msi.Name) -Force
}
Copy-Item -LiteralPath $cliExe -Destination (Join-Path $stageDir 'ofm.exe') -Force

# --------------------------------------------------------------------------
# Optional Authenticode signing
# --------------------------------------------------------------------------

$artifactsSigned = $false
if (-not $SkipSign) {
    Write-Section 'Signing (Authenticode, optional)'
    $cert = Get-Env 'CODESIGN_CERT'
    $password = Get-Env 'CODESIGN_PASSWORD'
    if ([string]::IsNullOrWhiteSpace($cert)) {
        Write-Warn 'CODESIGN_CERT is not set; the artifacts stay unsigned.'
        Write-Note 'To sign: $env:CODESIGN_CERT="C:\path\to\cert.pfx"; $env:CODESIGN_PASSWORD="..."'
    }
    elseif (-not (Test-Path -LiteralPath $cert)) {
        Write-Warn "CODESIGN_CERT points to '$cert', which does not exist; skipping signing."
    }
    elseif ([string]::IsNullOrEmpty($password)) {
        # A .pfx with a password and an empty /p argument fails with a confusing
        # signtool error, so say what is actually wrong.
        Stop-Build 'CODESIGN_CERT is set but CODESIGN_PASSWORD is empty.' @(
            'Set the .pfx password:  $env:CODESIGN_PASSWORD="..."',
            'or unset CODESIGN_CERT, or run with -SkipSign.'
        )
    }
    else {
        $signtool = $null
        $signtoolCmd = Get-Command 'signtool.exe' -ErrorAction SilentlyContinue
        if ($signtoolCmd) {
            $signtool = $signtoolCmd.Source
        }
        else {
            $kitRoots = @()
            if ($Pf86) { $kitRoots += (Join-Native $Pf86 'Windows Kits\10\bin') }
            if ($ProgramFiles) { $kitRoots += (Join-Native $ProgramFiles 'Windows Kits\10\bin') }
            foreach ($root in $kitRoots) {
                if (-not (Test-Path -LiteralPath $root)) { continue }
                $candidate = Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
                    Sort-Object Name -Descending |
                    ForEach-Object { Join-Native $_.FullName 'x64\signtool.exe' } |
                    Where-Object { Test-Path -LiteralPath $_ } |
                    Select-Object -First 1
                if ($candidate) { $signtool = $candidate; break }
            }
        }

        if (-not $signtool) {
            Write-Warn 'signtool.exe was not found (Windows SDK); skipping signing.'
            Write-Note 'Install the Windows SDK, or unset CODESIGN_CERT to silence this warning.'
        }
        else {
            $toSign = @(Get-ChildItem -LiteralPath $stageDir -File |
                Where-Object { $_.Extension -eq '.exe' -or $_.Extension -eq '.msi' } |
                Sort-Object Name)
            foreach ($file in $toSign) {
                Write-Note "Signing $($file.Name)"
                & $signtool sign /fd SHA256 /td SHA256 /tr 'http://timestamp.digicert.com' `
                    /f $cert /p $password $file.FullName
                if ($LASTEXITCODE -ne 0) {
                    Stop-Build "signtool failed for $($file.Name)." @(
                        'A signing certificate was provided, so signing is treated as required.',
                        'Check CODESIGN_CERT / CODESIGN_PASSWORD, or run with -SkipSign.'
                    )
                }
            }
            $artifactsSigned = $true
            Write-Ok "Signed $($toSign.Count) file(s) with $cert"
        }
    }
}

# --------------------------------------------------------------------------
# Checksums and archive
# --------------------------------------------------------------------------

Write-Section 'Writing SHA256SUMS'
[string[]] $sumLines = @()
foreach ($file in (Get-ChildItem -LiteralPath $stageDir -File | Sort-Object Name)) {
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $sumLines += ($hash + '  ' + $file.Name)
}
$sumPath = Join-Path $stageDir 'SHA256SUMS'
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
# LF line endings so the file also works with `sha256sum -c` after the zip is
# extracted on Linux or macOS.
[System.IO.File]::WriteAllText($sumPath, (($sumLines -join "`n") + "`n"), $utf8NoBom)
Write-Ok "SHA256SUMS covers $($sumLines.Count) file(s)"

if (-not (Test-Path -LiteralPath $OutputDirectory)) {
    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
}

$zipPath = Join-Path $OutputDirectory ("DeepL-oFM-$version-windows-x64.zip")
if (-not $SkipArchive) {
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction SilentlyContinue
    if ($null -eq ('System.IO.Compression.ZipFile' -as [type])) {
        Stop-Build 'System.IO.Compression.ZipFile is not available in this PowerShell.' @(
            'Use PowerShell 5.1 or newer, or re-run with -SkipArchive and zip the staging directory yourself.'
        )
    }
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $stageDir,
        $zipPath,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $false
    )
    $archive = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        $entryCount = @($archive.Entries).Count
    }
    finally {
        $archive.Dispose()
    }
    Write-Ok "Archive: $zipPath ($entryCount entries)"
}

$distSumPath = Join-Path $OutputDirectory 'SHA256SUMS-windows-x64.txt'
if ($SkipArchive) {
    # No .zip was written, so publish the per-file hashes of the staging tree.
    Copy-Item -LiteralPath $sumPath -Destination $distSumPath -Force
    Write-Note 'No archive was written (-SkipArchive); SHA256SUMS-windows-x64.txt lists the staged files.'
}
else {
    # Same convention as the macOS and Linux scripts: the release-level checksum
    # file covers the archive that is actually downloaded. The per-file hashes
    # for the archive contents travel inside it, in SHA256SUMS.
    $zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    # LF line endings: this file is consumed by `sha256sum -c` on Linux too.
    [System.IO.File]::WriteAllText(
        $distSumPath,
        ($zipHash + '  ' + [System.IO.Path]::GetFileName($zipPath) + "`n"),
        $utf8NoBom
    )
}
Write-Ok "Release checksums: $distSumPath"

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------

Write-Section 'Done'
Write-Note "Version:  $version"
Write-Note "Staging:  $stageDir"
Write-Note "Output:   $OutputDirectory"
Write-Host ''
foreach ($file in (Get-ChildItem -LiteralPath $OutputDirectory -File | Sort-Object Name)) {
    Write-Host ("    {0,12}  {1}" -f $file.Length, $file.Name) -ForegroundColor Gray
}
Write-Host ''
if (-not $artifactsSigned) {
    Write-Note 'The artifacts are UNSIGNED. Windows SmartScreen will warn until they are signed.'
}
Write-Note 'The desktop shell needs the WebView2 runtime on the target machine.'
