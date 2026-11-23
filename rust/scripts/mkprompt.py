#!/usr/bin/env python3
"""Build a code-review prompt for an external model.

The reviewer runs through `consult opencode --raw`, which does not read the
repository itself, so every file is inlined with line numbers to keep the
citations verifiable.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def numbered(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    width = len(str(len(lines)))
    body = "\n".join(f"{index:>{width}}| {line}" for index, line in enumerate(lines, 1))
    return f"```rust\n// {path.relative_to(ROOT)}\n{body}\n```"


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: mkprompt.py <output> <question-file> <file>...")
        return 2
    output, question, *files = sys.argv[1:]
    parts = [Path(question).read_text(encoding="utf-8"), ""]
    for name in files:
        parts.append(numbered(ROOT / name))
        parts.append("")
    Path(output).write_text("\n".join(parts), encoding="utf-8")
    print(f"{output}: {len(Path(output).read_text(encoding='utf-8'))} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
