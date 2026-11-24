"""DeepL-oFM for Windows — a PySide6 port of the macOS SwiftUI app."""

__version__ = "2.0.1"
APP_NAME = "DeepL-oFM"
APP_ID = "ua.admin.hymt"


MINIMUM_PYTHON = (3, 10)


def require_supported_python() -> None:
    """Explain the requirement instead of failing inside a dependency import."""
    import sys

    if sys.version_info < MINIMUM_PYTHON:
        current = ".".join(str(part) for part in sys.version_info[:3])
        sys.stderr.write(
            f"DeepL-oFM needs Python 3.10 or newer; this interpreter is {current}.\n"
            "Install Python 3.12 from https://www.python.org/downloads/windows/\n"
            'and tick "Add python.exe to PATH", then run run.bat again.\n'
        )
        raise SystemExit(2)
