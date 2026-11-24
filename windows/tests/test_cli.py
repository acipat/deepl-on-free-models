"""Command-line flags of the Windows entry point (parsing only, no GUI)."""

from __future__ import annotations

import pytest

from deepl_ofm.app import _parse_args


def test_defaults_keep_the_existing_behaviour() -> None:
    args = _parse_args([])
    assert args.prefill == ""
    assert args.tab is None
    assert args.open_file is None
    assert args.translate_file is None
    assert args.write_text is None
    assert args.translate_clipboard is False
    assert args.connect is False
    assert args.catalog is False
    assert args.load_fallback_models is False
    assert args.debug is False
    assert args.self_test is False


@pytest.mark.parametrize("flag", ["--open-file", "--translate-file"])
def test_file_actions_take_a_path(flag: str) -> None:
    args = _parse_args([flag, "report.pdf"])
    name = flag[2:].replace("-", "_")
    assert getattr(args, name) == "report.pdf"


def test_write_text_takes_the_text() -> None:
    args = _parse_args(["--write-text", "hello\n世界"])
    assert args.write_text == "hello\n世界"


def test_boolean_startup_actions() -> None:
    args = _parse_args(
        [
            "--translate-clipboard",
            "--connect",
            "--catalog",
            "--load-fallback-models",
        ]
    )
    assert args.translate_clipboard is True
    assert args.connect is True
    assert args.catalog is True
    assert args.load_fallback_models is True


def test_flags_combine_with_prefill_and_tab() -> None:
    args = _parse_args(
        [
            "--prefill",
            "source",
            "--tab",
            "write",
            "--open-file",
            "a.docx",
            "--write-text",
            "draft",
        ]
    )
    assert args.prefill == "source"
    assert args.tab == "write"
    assert args.open_file == "a.docx"
    assert args.write_text == "draft"


def test_help_mentions_every_new_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        _parse_args(["--help"])
    assert excinfo.value.code == 0
    output = capsys.readouterr().out
    for flag in (
        "--open-file",
        "--translate-file",
        "--write-text",
        "--translate-clipboard",
        "--connect",
        "--catalog",
        "--load-fallback-models",
    ):
        assert flag in output


def test_unwanted_keep_history_flag_is_rejected() -> None:
    with pytest.raises(SystemExit):
        _parse_args(["--keep-history-off"])
