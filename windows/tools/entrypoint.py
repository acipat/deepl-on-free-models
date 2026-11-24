"""Frozen-application entry point (PyInstaller imports this as ``__main__``)."""

from __future__ import annotations

import multiprocessing
import sys

from deepl_ofm import require_supported_python

if __name__ == "__main__":
    require_supported_python()
    multiprocessing.freeze_support()

    from deepl_ofm.app import main

    sys.exit(main())
