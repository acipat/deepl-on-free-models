#!/usr/bin/env python3
"""Check that the desktop shell, the controller and the frontend agree.

The Tauri crate cannot be compiled on a machine without the platform WebView
libraries, so this script does the part a compiler would do: it compares the
command names registered in `main.rs`, the functions declared in `commands.rs`
and the `invoke("…")` calls made by the frontend, and the settings/state field
names the frontend reads against the Rust structs.

Exit code 1 on any mismatch, so CI can gate on it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESKTOP = ROOT / "crates" / "desktop" / "src"
APP = ROOT / "crates" / "app" / "src"
UI = ROOT / "ui"

problems: list[str] = []
notes: list[str] = []


def read(path: Path) -> str:
    if not path.exists():
        problems.append(f"missing file: {path.relative_to(ROOT)}")
        return ""
    return path.read_text(encoding="utf-8")


def registered_commands() -> set[str]:
    """Names inside `tauri::generate_handler![…]`."""
    source = read(DESKTOP / "main.rs")
    match = re.search(r"generate_handler!\s*\[(.*?)\]", source, re.S)
    if not match:
        problems.append("main.rs: no generate_handler! block found")
        return set()
    return {
        name.split("::")[-1].strip()
        for name in re.findall(r"commands::([A-Za-z_][A-Za-z0-9_]*)", match.group(1))
    }


def declared_commands() -> dict[str, list[str]]:
    """`#[tauri::command]` functions and their parameter names."""
    source = read(DESKTOP / "commands.rs")
    commands: dict[str, list[str]] = {}
    # Split on the attribute so each block is one function.
    for block in re.split(r"#\[tauri::command\]", source)[1:]:
        signature = re.search(
            r"pub (?:async )?fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)\s*->", block, re.S
        )
        if not signature:
            continue
        name, params = signature.group(1), signature.group(2)
        # Drop the injected Tauri parameters before splitting on commas, or the
        # comma inside `State<'_, Shared>` would split one argument in two.
        params = re.sub(r"\b(?:mut )?[a-z_][a-z0-9_]*:\s*State<[^>]*>\s*,?", "", params)
        params = re.sub(r"\b(?:mut )?[a-z_][a-z0-9_]*:\s*(?:tauri::)?AppHandle\s*,?", "", params)
        arguments = []
        for raw in params.split(","):
            argument = raw.strip().split(":")[0].strip()
            if argument and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", argument):
                arguments.append(argument)
        commands[name] = arguments
    return commands


def invoked_commands() -> dict[str, set[str]]:
    """`invoke("name"` plus the argument keys of the same object literal."""
    source = strip_comments(read(UI / "app.js"))
    calls: dict[str, set[str]] = {}
    # The frontend funnels everything through `invoke(name, args)` or the
    # `send(name, args)` wrapper that reports errors as a toast.
    call_sites = r"(?:invoke|send)\("
    for match in re.finditer(call_sites + r"\s*[\"'`]([a-zA-Z0-9_]+)[\"'`]", source):
        calls.setdefault(match.group(1), set())
    # Argument keys: any `ident:` inside the argument object of the same call.
    for match in re.finditer(
        call_sites + r"\s*[\"'`]([a-zA-Z0-9_]+)[\"'`]\s*,\s*\{([^{}]*)\}", source, re.S
    ):
        name, body = match.group(1), match.group(2)
        for key in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", body):
            calls.setdefault(name, set()).add(key)
        for key in re.findall(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}", body):
            calls.setdefault(name, set()).add(key)
    return calls


def strip_comments(source: str) -> str:
    """Remove // and /* */ comments so prose about commands is not mistaken for a call."""
    without_block = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", without_block)


def mock_commands() -> set[str]:
    """Commands `mock.js` implements, so the standalone UI keeps working."""
    source = read(UI / "mock.js")
    return set(re.findall(r"(?m)^\s{2,}([a-z_][a-z0-9_]*)\s*\(", source))


def camel_to_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def state_fields() -> set[str]:
    """Public field names of `AppState` (Rust) as camelCase."""
    source = read(APP / "state.rs")
    block = re.search(r"pub struct AppState \{(.*?)\n\}", source, re.S)
    if not block:
        problems.append("state.rs: AppState not found")
        return set()
    return set(re.findall(r"pub ([a-z_][a-z0-9_]*):", block.group(1)))


def main() -> int:
    registered = registered_commands()
    declared = declared_commands()
    invoked = invoked_commands()

    missing_impl = sorted(registered - set(declared))
    if missing_impl:
        problems.append(
            "registered in main.rs but not defined in commands.rs: " + ", ".join(missing_impl)
        )
    unused = sorted(set(declared) - registered)
    if unused:
        notes.append("defined but not registered: " + ", ".join(unused))

    unknown = sorted(set(invoked) - set(declared) - {"get_state"})
    if unknown:
        problems.append(
            "invoked by the frontend but not implemented in Rust: " + ", ".join(unknown)
        )
    never = sorted(set(declared) - set(invoked) - {"get_state"})
    if never:
        notes.append("implemented but never invoked by the UI: " + ", ".join(never))

    # Argument names: Tauri converts camelCase wire keys to snake_case Rust
    # parameters, so `modelId` legitimately binds `model_id`.
    def to_snake(value: str) -> str:
        return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()

    for name, arguments in sorted(declared.items()):
        if name not in invoked:
            continue
        expected = {to_snake(argument) for argument in arguments}
        unknown_arguments = sorted(
            argument for argument in invoked[name] if to_snake(argument) not in expected
        )
        if unknown_arguments and arguments:
            problems.append(
                f"{name}: frontend sends {unknown_arguments}, Rust expects {arguments}"
            )

    # State fields the UI reads must exist.
    fields = state_fields()
    if fields:
        ui_source = strip_comments(read(UI / "app.js"))
        referenced = set(re.findall(r"state\.([a-zA-Z_][a-zA-Z0-9_]*)", ui_source))
        unknown_fields = sorted(
            field for field in referenced if camel_to_snake(field) not in fields
        )
        if unknown_fields:
            problems.append(
                "app.js reads state fields that AppState does not define: "
                + ", ".join(unknown_fields)
            )

    # The Tauri configuration must point at the real frontend.
    config = read(ROOT / "crates" / "desktop" / "tauri.conf.json")
    if config:
        try:
            parsed = json.loads(config)
        except json.JSONDecodeError as error:
            problems.append(f"tauri.conf.json is not valid JSON: {error}")
        else:
            dist = parsed.get("build", {}).get("frontendDist", "")
            if not (ROOT / "crates" / "desktop" / dist).resolve().joinpath("index.html").exists():
                problems.append(f"tauri.conf.json frontendDist does not resolve to index.html: {dist}")

    # Every command must also exist in the standalone mock, or the UI breaks
    # when it is opened in a browser without Tauri.
    mocked = mock_commands()
    unmocked = sorted(set(declared) - mocked - {"get_state"})
    if unmocked:
        notes.append("not stubbed in mock.js (standalone UI shows an error): " + ", ".join(unmocked))

    print(f"commands registered: {len(registered)}")
    print(f"commands defined:    {len(declared)}")
    print(f"commands invoked:    {len(invoked)}")
    for note in notes:
        print(f"note: {note}")
    if problems:
        for problem in problems:
            print(f"error: {problem}")
        return 1
    print("shell contract: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
