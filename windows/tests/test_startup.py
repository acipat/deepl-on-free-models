"""Tests for ``deepl_ofm.services.startup`` (Open at login).

Every test points the macOS/Linux paths at ``tmp_path`` and injects a fake
``winreg``/``launchctl``, so the real user profile is never touched.
"""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from deepl_ofm.core.languages import AppLanguage
from deepl_ofm.i18n import set_language, tf
from deepl_ofm.services import startup
from deepl_ofm.services.startup import StartupError, StartupStatus


@pytest.fixture(autouse=True)
def reset_language() -> Iterator[None]:
    set_language(AppLanguage.EN)
    yield
    set_language(AppLanguage.EN)


@pytest.fixture
def temp_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect both file-based login-item locations into the test tree."""
    monkeypatch.setattr(
        startup,
        "MACOS_PLIST_PATH",
        tmp_path / "LaunchAgents" / "ua.admin.hymt.plist",
    )
    monkeypatch.setattr(
        startup,
        "LINUX_AUTOSTART_PATH",
        tmp_path / "autostart" / "deepl-ofm.desktop",
    )
    return tmp_path


def use_platform(monkeypatch: pytest.MonkeyPatch, platform: str) -> None:
    monkeypatch.setattr(startup, "_platform", lambda: platform)


class FakeRunner:
    """Minimal ``launchctl`` stand-in capturing every invocation."""

    def __init__(self, *, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(argv))
        return subprocess.CompletedProcess(
            list(argv), self.returncode, self.stdout, self.stderr
        )


class _FakeKey:
    def __init__(self, registry: "FakeWinreg") -> None:
        self._registry = registry

    def __enter__(self) -> "_FakeKey":
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False


class FakeWinreg:
    """Dictionary-backed ``winreg`` module with the entry points we use."""

    HKEY_CURRENT_USER = object()
    KEY_READ = 0x20019
    KEY_SET_VALUE = 0x0002
    REG_SZ = 1

    def __init__(self, *, fail_read: bool = False, fail_write: bool = False) -> None:
        self.values: dict[str, str] = {}
        self.fail_read = fail_read
        self.fail_write = fail_write

    def OpenKey(self, _root: object, _path: str, _reserved: int = 0, _access: int = 0):
        if self.fail_read:
            raise PermissionError("Access is denied")
        return _FakeKey(self)

    def CreateKeyEx(
        self, _root: object, _path: str, _reserved: int = 0, _access: int = 0
    ) -> _FakeKey:
        if self.fail_write:
            raise PermissionError("Access is denied")
        return _FakeKey(self)

    def QueryValueEx(self, _key: _FakeKey, name: str) -> tuple[str, int]:
        if self.fail_read:
            raise PermissionError("Access is denied")
        if name not in self.values:
            raise FileNotFoundError(2, "The system cannot find the file specified")
        return self.values[name], self.REG_SZ

    def SetValueEx(
        self,
        _key: _FakeKey,
        name: str,
        _reserved: int,
        _kind: int,
        value: str,
    ) -> None:
        if self.fail_write:
            raise PermissionError("Access is denied")
        self.values[name] = value

    def DeleteValue(self, _key: _FakeKey, name: str) -> None:
        if name not in self.values:
            raise FileNotFoundError(2, "The system cannot find the file specified")
        del self.values[name]


def use_windows(
    monkeypatch: pytest.MonkeyPatch, fake: FakeWinreg
) -> FakeWinreg:
    monkeypatch.setattr(startup, "_winreg_module", lambda: fake)
    use_platform(monkeypatch, "win32")
    return fake


# ---------------------------------------------------------------------------
# Linux


def test_status_values_and_paths_match_the_contract() -> None:
    assert [status.value for status in StartupStatus] == [
        "enabled",
        "disabled",
        "requires_approval",
        "unsupported",
    ]
    assert startup.WINDOWS_RUN_KEY == (
        r"Software\Microsoft\Windows\CurrentVersion\Run"
    )
    assert startup.MACOS_PLIST_PATH.name == "ua.admin.hymt.plist"
    assert startup.MACOS_PLIST_PATH.parent.name == "LaunchAgents"


def test_linux_is_disabled_without_an_autostart_entry(
    monkeypatch: pytest.MonkeyPatch, temp_paths: Path
) -> None:
    use_platform(monkeypatch, "linux")
    assert startup.status() is StartupStatus.DISABLED


def test_linux_enable_writes_the_desktop_entry_and_disable_removes_it(
    monkeypatch: pytest.MonkeyPatch, temp_paths: Path
) -> None:
    use_platform(monkeypatch, "linux")
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", "/opt/My Apps/DeepL/python")

    startup.set_enabled(True)

    path = startup.LINUX_AUTOSTART_PATH
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("[Desktop Entry]\n")
    assert 'Exec="/opt/My Apps/DeepL/python" "-m" "deepl_ofm"' in text
    assert "X-GNOME-Autostart-enabled=true" in text
    assert startup.status() is StartupStatus.ENABLED

    startup.set_enabled(True)
    assert path.read_text(encoding="utf-8") == text  # second enable is a no-op

    startup.set_enabled(False)
    assert not path.exists()
    assert startup.status() is StartupStatus.DISABLED
    startup.set_enabled(False)  # disabling twice is safe


def test_linux_hidden_entry_counts_as_disabled(
    monkeypatch: pytest.MonkeyPatch, temp_paths: Path
) -> None:
    use_platform(monkeypatch, "linux")
    path = startup.LINUX_AUTOSTART_PATH
    path.parent.mkdir(parents=True)
    path.write_text("[Desktop Entry]\nHidden=true\n", encoding="utf-8")
    assert startup.status() is StartupStatus.DISABLED


# ---------------------------------------------------------------------------
# Windows


def test_windows_is_disabled_without_a_run_value(
    monkeypatch: pytest.MonkeyPatch, temp_paths: Path
) -> None:
    fake = use_windows(monkeypatch, FakeWinreg())
    assert startup.status() is StartupStatus.DISABLED
    assert fake.values == {}


def test_windows_frozen_run_registers_the_quoted_executable(
    monkeypatch: pytest.MonkeyPatch, temp_paths: Path
) -> None:
    fake = use_windows(monkeypatch, FakeWinreg())
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        sys, "executable", r"C:\Program Files\DeepL-oFM\DeepL-oFM.exe"
    )

    startup.set_enabled(True)

    expected = '"C:\\Program Files\\DeepL-oFM\\DeepL-oFM.exe"'
    assert fake.values[startup.WINDOWS_VALUE_NAME] == expected
    assert startup.status() is StartupStatus.ENABLED

    startup.set_enabled(True)
    assert fake.values[startup.WINDOWS_VALUE_NAME] == expected  # idempotent

    startup.set_enabled(False)
    assert startup.status() is StartupStatus.DISABLED
    assert startup.WINDOWS_VALUE_NAME not in fake.values


def test_windows_source_run_registers_the_interpreter_and_module(
    monkeypatch: pytest.MonkeyPatch, temp_paths: Path
) -> None:
    fake = use_windows(monkeypatch, FakeWinreg())
    monkeypatch.delattr(sys, "frozen", raising=False)
    interpreter = r"C:\Users\V V\DeepL-oFM\.venv\Scripts\python.exe"
    monkeypatch.setattr(sys, "executable", interpreter)

    startup.set_enabled(True)

    assert fake.values[startup.WINDOWS_VALUE_NAME] == (
        '"C:\\Users\\V V\\DeepL-oFM\\.venv\\Scripts\\python.exe" -m deepl_ofm'
    )


def test_windows_command_line_for_frozen_and_source_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys, "executable", r"C:\Program Files\DeepL-oFM\DeepL-oFM.exe"
    )
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert startup._windows_command() == (
        '"C:\\Program Files\\DeepL-oFM\\DeepL-oFM.exe"'
    )

    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(
        sys, "executable", r"C:\Users\V V\DeepL-oFM\.venv\Scripts\python.exe"
    )
    assert startup._windows_command() == (
        '"C:\\Users\\V V\\DeepL-oFM\\.venv\\Scripts\\python.exe" -m deepl_ofm'
    )


def test_windows_write_failure_is_a_localised_startup_error(
    monkeypatch: pytest.MonkeyPatch, temp_paths: Path
) -> None:
    use_windows(monkeypatch, FakeWinreg(fail_write=True))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\DeepL-oFM\DeepL-oFM.exe")
    set_language(AppLanguage.DE)

    with pytest.raises(StartupError) as raised:
        startup.set_enabled(True)

    expected = tf("Could not change Open at login. %@", "Access is denied")
    assert str(raised.value) == expected
    assert "konnte nicht geändert werden" in str(raised.value)


def test_windows_status_never_raises_when_the_registry_is_unreadable(
    monkeypatch: pytest.MonkeyPatch, temp_paths: Path
) -> None:
    use_windows(monkeypatch, FakeWinreg(fail_read=True))
    assert startup.status() is StartupStatus.DISABLED


# ---------------------------------------------------------------------------
# macOS


def _uid() -> int:
    getuid = getattr(os, "getuid", None)
    return int(getuid()) if callable(getuid) else 0


def test_macos_enable_writes_the_plist_and_loads_the_agent(
    monkeypatch: pytest.MonkeyPatch, temp_paths: Path
) -> None:
    use_platform(monkeypatch, "darwin")
    runner = FakeRunner()
    monkeypatch.setattr(startup, "_run", runner)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", "/Users/V V/DeepL/.venv/bin/python")

    assert startup.status() is StartupStatus.DISABLED
    assert runner.calls == []

    startup.set_enabled(True)

    path = startup.MACOS_PLIST_PATH
    document = plistlib.loads(path.read_bytes())
    assert document == {
        "Label": "ua.admin.hymt",
        "ProgramArguments": [
            "/Users/V V/DeepL/.venv/bin/python",
            "-m",
            "deepl_ofm",
        ],
        "RunAtLoad": True,
        "LimitLoadToSessionType": "Aqua",
    }
    assert runner.calls[0] == [
        "launchctl",
        "bootstrap",
        f"gui/{_uid()}",
        str(path),
    ]
    assert startup.status() is StartupStatus.ENABLED
    assert runner.calls[-1][:2] == ["launchctl", "print-disabled"]


def test_macos_disable_unloads_the_agent_and_removes_the_plist(
    monkeypatch: pytest.MonkeyPatch, temp_paths: Path
) -> None:
    use_platform(monkeypatch, "darwin")
    runner = FakeRunner()
    monkeypatch.setattr(startup, "_run", runner)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", "/usr/local/bin/python3")

    startup.set_enabled(True)
    path = startup.MACOS_PLIST_PATH
    startup.set_enabled(True)  # idempotent: the same file is rewritten
    assert path.is_file()

    startup.set_enabled(False)

    assert not path.exists()
    assert [
        "launchctl",
        "bootout",
        f"gui/{_uid()}/ua.admin.hymt",
    ] in runner.calls
    assert startup.status() is StartupStatus.DISABLED


def test_macos_entry_disabled_in_system_settings_requires_approval(
    monkeypatch: pytest.MonkeyPatch, temp_paths: Path
) -> None:
    use_platform(monkeypatch, "darwin")
    runner = FakeRunner()
    monkeypatch.setattr(startup, "_run", runner)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", "/usr/local/bin/python3")

    startup.set_enabled(True)
    runner.stdout = 'disabled services = {\n\t"ua.admin.hymt" => true\n}'
    assert startup.status() is StartupStatus.REQUIRES_APPROVAL

    runner.stdout = 'disabled services = {\n\t"ua.admin.hymt" => false\n}'
    assert startup.status() is StartupStatus.ENABLED


def test_macos_corrupt_plist_is_disabled_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch, temp_paths: Path
) -> None:
    use_platform(monkeypatch, "darwin")
    monkeypatch.setattr(startup, "_run", FakeRunner())
    path = startup.MACOS_PLIST_PATH
    path.parent.mkdir(parents=True)
    path.write_text("not a property list", encoding="utf-8")
    assert startup.status() is StartupStatus.DISABLED


def test_macos_bootstrap_failure_keeps_the_agent_for_the_next_login(
    monkeypatch: pytest.MonkeyPatch, temp_paths: Path
) -> None:
    use_platform(monkeypatch, "darwin")
    runner = FakeRunner(returncode=5, stderr="Input/output error")
    monkeypatch.setattr(startup, "_run", runner)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", "/usr/local/bin/python3")

    startup.set_enabled(True)

    assert startup.MACOS_PLIST_PATH.is_file()
    assert startup.status() is StartupStatus.ENABLED


# ---------------------------------------------------------------------------
# Supported-platform dispatch


def test_status_never_raises_when_the_platform_probe_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode() -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr(startup, "_platform", explode)
    assert startup.status() is StartupStatus.UNSUPPORTED


def test_unsupported_platform(
    monkeypatch: pytest.MonkeyPatch, temp_paths: Path
) -> None:
    use_platform(monkeypatch, "plan9")
    assert startup.status() is StartupStatus.UNSUPPORTED
    assert startup.open_settings() is False
    with pytest.raises(StartupError) as raised:
        startup.set_enabled(True)
    assert str(raised.value) == tf(
        "Could not change Open at login. %@", "Not supported on this system."
    )


def test_open_settings_uses_the_macos_login_items_pane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(startup, "_spawn", lambda argv: calls.append(list(argv)) or True)
    use_platform(monkeypatch, "darwin")

    assert startup.open_settings() is True
    assert calls == [
        [
            "open",
            "x-apple.systempreferences:com.apple.LoginItems-Settings.extension",
        ]
    ]


def test_open_settings_windows_opens_the_startup_apps_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(startup.os, "startfile", calls.append, raising=False)
    use_platform(monkeypatch, "win32")

    assert startup.open_settings() is True
    assert calls == ["ms-settings:startupapps"]


def test_open_settings_never_raises_when_the_helper_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(_argv: list[str]) -> bool:
        raise OSError("no helper")

    monkeypatch.setattr(startup, "_spawn", explode)
    use_platform(monkeypatch, "darwin")
    assert startup.open_settings() is False
