"""Open at login.

Ported from the ``SMAppService.mainApp`` login-item controls in
``Sources/HyMT/Views/SettingsView.swift``.  The operating system owns the
state, so nothing is stored in ``settings.json``:

* Windows -- the ``DeepL-oFM`` value under
  ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``;
* macOS -- ``~/Library/LaunchAgents/ua.admin.hymt.plist`` driven by
  ``launchctl``;
* Linux -- ``~/.config/autostart/deepl-ofm.desktop``.

:func:`status` never raises: a broken registry, plist or permissions problem
degrades to ``disabled`` (or ``unsupported`` on an unknown platform), exactly
so opening Settings cannot crash the application.  :func:`set_enabled` reports
failures through :class:`StartupError` with the same localised template as the
Swift app.
"""
from __future__ import annotations

import logging
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import Any

from .. import APP_ID, APP_NAME
from ..i18n import tf

logger = logging.getLogger(__name__)

#: Subkey of ``HKEY_CURRENT_USER`` used by the Windows implementation.
WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
#: Name of the value inside :data:`WINDOWS_RUN_KEY`.
WINDOWS_VALUE_NAME = APP_NAME
#: Windows Settings page that lists startup applications.
WINDOWS_STARTUP_APPS_URI = "ms-settings:startupapps"

#: launchd label; matches the bundle identifier used by the macOS app.
MACOS_AGENT_LABEL = APP_ID
#: Login-item pane opened by the "Open System Settings" button.
MACOS_LOGIN_ITEMS_URL = (
    "x-apple.systempreferences:com.apple.LoginItems-Settings.extension"
)
#: LaunchAgent path.  A test can replace it with a path under ``tmp_path``.
MACOS_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{APP_ID}.plist"

#: XDG autostart entry.  A test can replace it with a path under ``tmp_path``.
LINUX_AUTOSTART_PATH = Path.home() / ".config" / "autostart" / "deepl-ofm.desktop"

_MODULE = "deepl_ofm"
_COMMAND_TIMEOUT = 5.0
_UNSUPPORTED_DETAIL = "Not supported on this system."


class StartupStatus(str, Enum):
    """Login-startup states, mirroring ``SMAppService.Status``."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    REQUIRES_APPROVAL = "requires_approval"
    UNSUPPORTED = "unsupported"


class StartupError(Exception):
    """A failed login-startup change with a user-facing, localised message."""


# ---------------------------------------------------------------------------
# Small helpers


def _platform() -> str:
    """Current platform; tests replace this to exercise every branch."""
    return sys.platform


def _is_supported(platform: str) -> bool:
    return platform == "win32" or platform == "darwin" or platform.startswith("linux")


def _failure(detail: str) -> StartupError:
    return StartupError(tf("Could not change Open at login. %@", detail))


def _describe(error: BaseException) -> str:
    """A short reason suitable for ``%@``; localised by the OS where possible."""
    text = str(error).strip()
    if isinstance(error, OSError):
        text = (error.strerror or text).strip()
    return text or type(error).__name__


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _invocation() -> list[str]:
    """The command that starts the application (no platform quoting)."""
    executable = str(getattr(sys, "executable", "") or "")
    if not executable:
        raise OSError("The application path is unknown.")
    if _is_frozen():
        return [executable]
    return [executable, "-m", _MODULE]


def _windows_command() -> str:
    """Registry command line, quoted with the Windows shell rules."""
    return subprocess.list2cmdline(_invocation())


def _desktop_quote(value: str) -> str:
    """Quote one ``Exec`` argument for a desktop entry."""
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
        .replace("%", "%%")
    )
    return f'"{escaped}"'


def _desktop_exec() -> str:
    return " ".join(_desktop_quote(part) for part in _invocation())


def _run(argv: Sequence[str]) -> subprocess.CompletedProcess[str] | None:
    """Run a command without ever raising; ``None`` means it could not start."""
    try:
        return subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        logger.warning("could not run %s: %s", argv[0] if argv else "?", error)
        return None


def _spawn(argv: Sequence[str]) -> bool:
    """Start a detached GUI helper; ``False`` when it could not be launched."""
    try:
        subprocess.Popen(
            list(argv),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        logger.warning("could not start %s: %s", argv[0] if argv else "?", error)
        return False
    return True


def _atomic_write(path: Path, payload: bytes, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None and os.name != "nt":
            os.chmod(temp_name, mode)
        os.replace(temp_path, path)
        if mode is not None and os.name != "nt":
            try:
                os.chmod(path, mode)
            except OSError:
                pass
    except BaseException:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Public API


def status() -> StartupStatus:
    """Return the current login-startup state.  This never raises."""
    platform = ""
    try:
        platform = _platform()
        if platform == "win32":
            return _windows_status()
        if platform == "darwin":
            return _macos_status()
        if platform.startswith("linux"):
            return _linux_status()
        return StartupStatus.UNSUPPORTED
    except Exception:  # noqa: BLE001 - status must never break the dialog
        logger.exception("could not read the Open at login status")
        if _is_supported(platform):
            return StartupStatus.DISABLED
        return StartupStatus.UNSUPPORTED


def set_enabled(enabled: bool) -> None:
    """Enable or disable login startup, raising :class:`StartupError` on failure."""
    platform = ""
    try:
        platform = _platform()
        if platform == "win32":
            _windows_set(bool(enabled))
            return
        if platform == "darwin":
            _macos_set(bool(enabled))
            return
        if platform.startswith("linux"):
            _linux_set(bool(enabled))
            return
        raise _failure(_UNSUPPORTED_DETAIL)
    except StartupError:
        raise
    except Exception as error:  # noqa: BLE001 - reported by the settings dialog
        logger.warning("could not change Open at login: %s", error)
        raise _failure(_describe(error)) from error


def open_settings() -> bool:
    """Open the OS page that manages login items; ``False`` when it failed."""
    platform = ""
    try:
        platform = _platform()
        if platform == "win32":
            os.startfile(WINDOWS_STARTUP_APPS_URI)  # type: ignore[attr-defined]
            return True
        if platform == "darwin":
            return _spawn(["open", MACOS_LOGIN_ITEMS_URL])
        if platform.startswith("linux"):
            return _open_linux_settings()
    except Exception as error:  # noqa: BLE001 - a button must not break the dialog
        logger.warning("could not open the login-item settings: %s", error)
    return False


# ---------------------------------------------------------------------------
# Windows: HKCU\...\Run


def _winreg_module() -> Any:
    """The ``winreg`` module, or ``None`` outside Windows."""
    try:
        import winreg
    except ImportError:
        return None
    return winreg


def _windows_status() -> StartupStatus:
    winreg = _winreg_module()
    if winreg is None:
        return StartupStatus.UNSUPPORTED
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_READ
        ) as key:
            value, _kind = winreg.QueryValueEx(key, WINDOWS_VALUE_NAME)
    except FileNotFoundError:
        return StartupStatus.DISABLED
    except OSError as error:
        logger.warning("could not read the Open at login registry value: %s", error)
        return StartupStatus.DISABLED
    return StartupStatus.ENABLED if str(value or "").strip() else StartupStatus.DISABLED


def _windows_set(enabled: bool) -> None:
    winreg = _winreg_module()
    if winreg is None:
        raise _failure(_UNSUPPORTED_DETAIL)
    if enabled:
        command = _windows_command()
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, WINDOWS_VALUE_NAME, 0, winreg.REG_SZ, command)
        return
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, WINDOWS_VALUE_NAME)
    except FileNotFoundError:
        # Already disabled: the Run key or the value does not exist.
        return


# ---------------------------------------------------------------------------
# macOS: ~/Library/LaunchAgents/ua.admin.hymt.plist


def _user_id() -> int:
    getuid = getattr(os, "getuid", None)
    return int(getuid()) if callable(getuid) else 0


def _macos_plist_document() -> dict[str, Any]:
    return {
        "Label": MACOS_AGENT_LABEL,
        "ProgramArguments": _invocation(),
        "RunAtLoad": True,
        "LimitLoadToSessionType": "Aqua",
    }


def _macos_status() -> StartupStatus:
    path = Path(MACOS_PLIST_PATH)
    try:
        if not path.is_file():
            return StartupStatus.DISABLED
        document = plistlib.loads(path.read_bytes())
    except Exception as error:  # noqa: BLE001 - a corrupt plist means "off"
        logger.warning("could not read the LaunchAgent %s: %s", path, error)
        return StartupStatus.DISABLED
    if not isinstance(document, dict) or document.get("Label") != MACOS_AGENT_LABEL:
        logger.warning("the LaunchAgent %s has an unexpected label", path)
        return StartupStatus.DISABLED
    if _macos_disabled_by_user():
        return StartupStatus.REQUIRES_APPROVAL
    return StartupStatus.ENABLED


def _macos_disabled_by_user() -> bool:
    """Whether macOS has switched the LaunchAgent off in Login Items."""
    result = _run(["launchctl", "print-disabled", f"gui/{_user_id()}"])
    if result is None or result.returncode != 0:
        return False
    return _disabled_output_contains_label(result.stdout)


def _disabled_output_contains_label(output: str) -> bool:
    for line in (output or "").splitlines():
        if MACOS_AGENT_LABEL not in line:
            continue
        lowered = line.lower()
        if "=> false" in lowered or "=> enabled" in lowered:
            return False
        if "=> true" in lowered or "disabled" in lowered:
            return True
    return False


def _macos_load(path: Path) -> None:
    result = _run(
        ["launchctl", "bootstrap", f"gui/{_user_id()}", str(path)]
    )
    if result is None:
        logger.warning(
            "launchctl is unavailable; the LaunchAgent will load at the next login"
        )
    elif result.returncode != 0:
        # A disabled login item is expected to require approval; keep the plist
        # either way so the next login still starts the application.
        logger.warning(
            "launchctl bootstrap failed for %s: %s",
            path,
            (result.stderr or result.stdout or "").strip(),
        )


def _macos_unload() -> None:
    result = _run(
        ["launchctl", "bootout", f"gui/{_user_id()}/{MACOS_AGENT_LABEL}"]
    )
    if result is not None and result.returncode != 0:
        logger.debug(
            "launchctl bootout for %s returned %s: %s",
            MACOS_AGENT_LABEL,
            result.returncode,
            (result.stderr or result.stdout or "").strip(),
        )


def _macos_set(enabled: bool) -> None:
    path = Path(MACOS_PLIST_PATH)
    if enabled:
        payload = plistlib.dumps(
            _macos_plist_document(), fmt=plistlib.FMT_XML, sort_keys=False
        )
        _atomic_write(path, payload, mode=0o644)
        _macos_load(path)
        return
    if not path.exists():
        return
    _macos_unload()
    try:
        path.unlink()
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# Linux: ~/.config/autostart/deepl-ofm.desktop


def _linux_desktop_entry() -> str:
    return "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Version=1.0",
            f"Name={APP_NAME}",
            "Comment=Start DeepL-oFM when you sign in",
            f"Exec={_desktop_exec()}",
            "Terminal=false",
            "X-GNOME-Autostart-enabled=true",
            "",
        ]
    )


def _linux_status() -> StartupStatus:
    path = Path(LINUX_AUTOSTART_PATH)
    try:
        if not path.is_file():
            return StartupStatus.DISABLED
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        logger.warning("could not read the autostart entry %s: %s", path, error)
        return StartupStatus.DISABLED
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key = key.strip()
        value = value.strip().lower()
        if key == "Hidden" and value == "true":
            return StartupStatus.DISABLED
        if key == "X-GNOME-Autostart-enabled" and value in {"false", "0", "no"}:
            return StartupStatus.DISABLED
    return StartupStatus.ENABLED


def _linux_set(enabled: bool) -> None:
    path = Path(LINUX_AUTOSTART_PATH)
    if enabled:
        _atomic_write(path, _linux_desktop_entry().encode("utf-8"), mode=0o644)
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _open_linux_settings() -> bool:
    """Best effort: the desktop has no single cross-distro login-item page."""
    candidates = (
        ("gnome-session-properties",),
        ("systemsettings5", "kcm_autostart"),
        ("systemsettings", "kcm_autostart"),
        ("xfce4-session-settings",),
        ("gnome-control-center", "applications"),
    )
    for command in candidates:
        executable = shutil.which(command[0])
        if executable:
            return _spawn([executable, *command[1:]])
    xdg_open = shutil.which("xdg-open")
    if xdg_open:
        return _spawn([xdg_open, str(LINUX_AUTOSTART_PATH.parent)])
    return False
