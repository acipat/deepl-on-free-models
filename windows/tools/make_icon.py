"""Convert the repository app icon (docs/app-icon.png) into a Windows .ico."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT.parent / "docs" / "app-icon.png"
TARGET = ROOT / "tools" / "app.ico"
SIZES = [16, 24, 32, 48, 64, 128, 256]


def main() -> int:
    if not SOURCE.exists():
        print(f"icon source not found: {SOURCE}", file=sys.stderr)
        return 1
    try:
        from PIL import Image
    except ImportError:
        print("Pillow is required: pip install pillow", file=sys.stderr)
        return 1
    image = Image.open(SOURCE).convert("RGBA")
    side = max(image.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    canvas.save(TARGET, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
