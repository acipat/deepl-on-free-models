"""Application entry point: Qt bootstrap, theme, window, tray and global hotkeys.

Counterpart of ``Sources/HyMT/DeepL-oFMApp.swift``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QDeadlineTimer, Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from . import APP_ID, APP_NAME, __version__
from .controller import AppController
from .i18n import t
from .ui import icons
from .ui.main_window import MainWindow
from .ui.theme import Theme

log = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="DeepL-oFM",
        description="DeepL-oFM for Windows",
        epilog=(
            "Startup actions run once the window and event loop are ready: "
            "--open-file/--translate-file, --write-text, --translate-clipboard, "
            "--connect, --catalog and --load-fallback-models."
        ),
    )
    parser.add_argument(
        "--prefill", metavar="TEXT", default="", help="start with this source text"
    )
    parser.add_argument(
        "--tab",
        choices=["translate", "files", "write", "history"],
        default=None,
        help="open this tab on startup",
    )
    parser.add_argument(
        "--open-file",
        metavar="PATH",
        default=None,
        help="open the Files tab and translate this document",
    )
    parser.add_argument(
        "--translate-file",
        metavar="PATH",
        default=None,
        help="alias of --open-file",
    )
    parser.add_argument(
        "--write-text",
        metavar="TEXT",
        default=None,
        help="open the Write tab and put this text in its editor",
    )
    parser.add_argument(
        "--translate-clipboard",
        action="store_true",
        help="translate the clipboard once the window is ready",
    )
    parser.add_argument(
        "--connect",
        action="store_true",
        help="connect to the provider and refresh the model list",
    )
    parser.add_argument(
        "--catalog",
        action="store_true",
        help="open the model catalog after the window appears",
    )
    parser.add_argument(
        "--load-fallback-models",
        action="store_true",
        help="probe the fallback provider and load its model list",
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="start the full application, then quit after a moment (diagnostics)",
    )
    return parser.parse_args(argv)


def _log_directory() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home() / ".config"))
    return base / "DeepL-oFM" / "logs"


def _configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug or os.environ.get("DEEPLOFM_DEBUG") else logging.INFO
    handlers: list[logging.Handler] = []
    try:
        from logging.handlers import RotatingFileHandler

        directory = _log_directory()
        directory.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                directory / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
            )
        )
    except OSError:  # a read-only profile must not stop the app
        pass
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    if not handlers:
        # pythonw.exe has no stderr and the profile may be read-only.
        handlers.append(logging.NullHandler())
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=handlers,
    )


SINGLE_INSTANCE_KEY = "DeepL-oFM-instance"
_INSTANCE_ACK = b"ack\n"

#: Command-line actions a second launch forwards to the running instance.
_ACTION_FIELDS = (
    "prefill",
    "tab",
    "open_file",
    "translate_file",
    "write_text",
    "translate_clipboard",
    "connect",
    "catalog",
    "load_fallback_models",
)
_ACTION_DEFAULTS: dict[str, object] = {
    "prefill": "",
    "tab": None,
    "open_file": None,
    "translate_file": None,
    "write_text": None,
    "translate_clipboard": False,
    "connect": False,
    "catalog": False,
    "load_fallback_models": False,
}


def _action_payload(args: argparse.Namespace) -> dict[str, object]:
    """The startup actions of *args*, ready to travel over the socket."""
    return {name: getattr(args, name, _ACTION_DEFAULTS[name]) for name in _ACTION_FIELDS}


def _actions_from_payload(payload: dict[str, object]) -> argparse.Namespace:
    """Rebuild an argparse-like namespace from a second-instance message."""
    values = dict(_ACTION_DEFAULTS)
    for name in _ACTION_FIELDS:
        if name in payload:
            values[name] = payload[name]
    return argparse.Namespace(**values)


def _notify_running_instance(payload: dict[str, object]) -> bool | None:
    """Return delivery status, or None if no instance accepted the connection."""
    socket = QLocalSocket()
    socket.connectToServer(SINGLE_INSTANCE_KEY)
    if not socket.waitForConnected(250):
        return None
    try:
        message = json.dumps({"show": True, **payload}, ensure_ascii=False)
        frame = message.encode("utf-8") + b"\n"
        if socket.write(frame) != len(frame):
            return False
        socket.flush()
        if socket.bytesToWrite():
            socket.waitForBytesWritten(1000)

        # Even when the local write buffer is empty, the peer may not have
        # read the named pipe yet. Only its acknowledgement confirms delivery.
        deadline = QDeadlineTimer(2000)
        while not socket.canReadLine():
            remaining = deadline.remainingTime()
            if remaining <= 0 or not socket.waitForReadyRead(remaining):
                break
        return bytes(socket.readLine()) == _INSTANCE_ACK
    finally:
        socket.disconnectFromServer()


def _apply_startup_state(window, args) -> None:
    """Prefill and tab selection, shared by a first and a second launch."""
    if args.prefill:
        window.set_source_text(args.prefill, translate=True)
    if args.tab:
        window.select_tab(args.tab)


def _apply_actions(window, controller: AppController, args) -> None:
    """Apply a launch's actions to an already running window."""
    _apply_startup_state(window, args)
    _schedule_startup_actions(window, controller, args)


def _handle_instance_message(window, controller: AppController, raw: bytes) -> bool:
    """Apply one newline-framed JSON message and report whether it was accepted."""
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        log.warning("ignoring a malformed second-instance message")
        return False
    if not isinstance(payload, dict):
        log.warning("ignoring a non-object second-instance message")
        return False
    try:
        _apply_actions(window, controller, _actions_from_payload(payload))
    except Exception:  # noqa: BLE001 - a bad payload must not kill the server
        log.exception("could not apply second-instance actions")
        return False
    return True


def _install_instance_server(window, controller: AppController) -> QLocalServer:
    """Listen for a second launch and apply the actions it brought along."""
    QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
    server = QLocalServer(window)
    server.listen(SINGLE_INSTANCE_KEY)
    buffers: dict[int, bytes] = {}

    def on_connection() -> None:
        connection = server.nextPendingConnection()
        if connection is None:
            return
        key = id(connection)
        buffers[key] = b""

        def read_message() -> None:
            data = buffers.get(key, b"") + bytes(connection.readAll())
            while b"\n" in data:
                line, data = data.split(b"\n", 1)
                if line.strip() and _handle_instance_message(window, controller, line):
                    connection.write(_INSTANCE_ACK)
                    connection.flush()
            buffers[key] = data

        def closed() -> None:
            buffers.pop(key, None)
            connection.deleteLater()

        connection.readyRead.connect(read_message)
        connection.disconnected.connect(closed)
        window.present()
        if connection.bytesAvailable():
            read_message()

    server.newConnection.connect(on_connection)
    return server


class _Hotkeys:
    """Binds the configured combos to controller commands (Windows RegisterHotKey)."""

    def __init__(self, controller: AppController) -> None:
        self.controller = controller
        self.manager = None
        self._registered: dict[str, object] = {}
        self._pending = False
        try:
            from .services.hotkeys import HotkeyManager

            self.manager = HotkeyManager()
            self.manager.triggered.connect(self._on_triggered)
            self.manager.error.connect(self._on_error)
        except Exception:  # noqa: BLE001 - hotkeys are optional
            log.debug("hotkey manager unavailable", exc_info=True)

    def register_all(self) -> None:
        if self.manager is None:
            self.controller.hotkey_message = t("Global hotkeys are only available on Windows.")
            self.controller.hotkeyStatusChanged.emit("translate", self.controller.hotkey_message)
            return

        settings = self.controller.settings
        combos = {
            "translate": settings.hot_key,
            "selection": settings.selection_hot_key,
        }
        if combos == self._registered:
            return
        previous = dict(self._registered)
        # Settings changed: release the old bindings before claiming the new ones,
        # otherwise RegisterHotKey fails with "already registered" for the same id.
        self.manager.unregister_all()
        self._registered = dict(combos)
        failed = False
        for action, combo in combos.items():
            ok = self.manager.register(action, combo)
            failed = failed or not ok
            message = "" if ok else t("Hotkey does not work")
            if action == "translate":
                self.controller.hotkey_message = message
            else:
                self.controller.selection_hotkey_message = message
            self.controller.hotkeyStatusChanged.emit(action, message)

        if failed and previous:
            # Keep a working shortcut instead of losing both bindings.
            log.warning("new hotkeys failed; restoring the previous combination")
            self.manager.unregister_all()
            for action, combo in previous.items():
                self.manager.register(action, combo)
            self._registered = previous

    def schedule_reregister(self) -> None:
        """Coalesce settings changes and re-register once the UI settles."""
        if self._pending or self.manager is None:
            return
        from PySide6.QtCore import QTimer

        self._pending = True
        QTimer.singleShot(250, self._reregister)

    def _reregister(self) -> None:
        self._pending = False
        try:
            self.register_all()
        except Exception:  # noqa: BLE001 - a hotkey problem must not kill the app
            log.debug("hotkey re-registration failed", exc_info=True)

    def _on_triggered(self, action: str) -> None:
        if action == "translate":
            self.controller.translate_clipboard()
        elif action == "selection":
            self.controller.translate_selection()

    def _on_error(self, message: str) -> None:
        log.warning("hotkey error: %s", message)

    def stop(self) -> None:
        if self.manager is not None:
            self.manager.unregister_all()


def _open_file(window, controller: AppController, path: str) -> None:
    """Show the Files tab and start translating *path*."""
    window.select_tab("files")
    controller.start_file_translation(Path(path))


def _write_text(window, text: str) -> None:
    """Show the Write tab and put *text* into its editor."""
    window.select_tab("write")
    view = window.pages.get("write")
    if view is None:
        return
    setter = getattr(view, "set_source_text", None)
    if callable(setter):
        setter(text)
        return
    # Older builds only expose the editor; keep the flag working with them.
    editor = getattr(view, "editor", None)
    if editor is not None:
        editor.setPlainText(text)


def _schedule_startup_actions(window, controller: AppController, args) -> None:
    """Queue command-line actions that need the window and a running event loop."""
    from PySide6.QtCore import QTimer

    file_path = args.open_file or args.translate_file
    if file_path:
        QTimer.singleShot(0, lambda: _open_file(window, controller, file_path))
    if args.write_text:
        QTimer.singleShot(0, lambda: _write_text(window, args.write_text))
    if args.translate_clipboard:
        QTimer.singleShot(0, controller.translate_clipboard)
    if args.connect:
        QTimer.singleShot(0, controller.connect_and_load_models)
    if args.catalog:
        QTimer.singleShot(0, window.open_catalog)
    if args.load_fallback_models:
        QTimer.singleShot(0, controller.load_fallback_models)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _configure_logging(args.debug)

    QApplication.setAttribute(Qt.AA_DontUseNativeMenuBar, False)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("ua.admin.hymt")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(APP_ID)

    delivered = _notify_running_instance(_action_payload(args))
    if delivered is not None:
        if delivered:
            log.info("another DeepL-oFM instance is running; sent it this launch's actions")
            return 0
        log.error("the running DeepL-oFM instance did not acknowledge this launch's actions")
        return 1

    Theme.apply(app)
    icon = icons.icon("translate", size=128)
    if not icon.isNull():
        app.setWindowIcon(icon)

    controller = AppController()
    window = MainWindow(controller)
    instance_server = _install_instance_server(window, controller)  # noqa: F841 - kept alive by Qt

    tray = None
    try:
        from .ui.tray import TrayIcon

        tray = TrayIcon(controller, window)
        controller.interfaceLanguageChanged.connect(lambda _code: tray.retranslate_ui())
        controller.settingsChanged.connect(tray.retranslate_ui)
        tray.retranslate_ui()
        tray.settingsRequested.connect(window.open_settings)
        tray.quitRequested.connect(app.quit)
        window.tray = tray

        def apply_tray_setting() -> None:
            visible = bool(controller.settings.show_in_menu_bar)
            if visible:
                tray.show()
            else:
                tray.hide()
            app.setQuitOnLastWindowClosed(not visible)

        apply_tray_setting()
        controller.settingsChanged.connect(apply_tray_setting)
    except Exception:  # noqa: BLE001 - tray may be unavailable in a bare session
        log.debug("tray unavailable", exc_info=True)

    hotkeys = _Hotkeys(controller)
    hotkeys.register_all()
    controller.settingsChanged.connect(hotkeys.schedule_reregister)

    controller.windowRequested.connect(window.present)

    _apply_startup_state(window, args)

    window.show()
    window.focus_translate()
    controller.bootstrap()
    _schedule_startup_actions(window, controller, args)
    if args.self_test:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(1500, app.quit)

    try:
        exit_code = app.exec()
    finally:
        hotkeys.stop()
        controller.shutdown()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
