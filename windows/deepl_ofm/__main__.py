"""`python -m deepl_ofm` entry point."""

from __future__ import annotations

import sys

from . import require_supported_python

if __name__ == "__main__":
    require_supported_python()
    from .app import main

    sys.exit(main())
