"""Shared pytest fixtures: a headless Qt application for widget and job tests."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _clipboard_teardown():
    """Flush the Qt clipboard before the interpreter shuts down.

    ``QClipboard.setMimeData`` hands a Python-owned object to Qt; the offscreen
    platform plugin then frees it during QApplication destruction and the
    process dies with SIGSEGV *after* the tests have passed.  Clearing the
    clipboard while the application is still alive releases it safely.
    """
    yield
    app = QApplication.instance()
    if app is None:
        return
    try:
        app.clipboard().clear()
        app.processEvents()
    except Exception:  # noqa: BLE001 - teardown must never fail a run
        pass


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole session (Qt forbids a second instance)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def wait_until(predicate, timeout: float = 3.0, step: float = 0.01) -> bool:
    """Spin the Qt event loop until ``predicate()`` is true or the timeout expires."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        QApplication.processEvents()
        time.sleep(step)
    return bool(predicate())
