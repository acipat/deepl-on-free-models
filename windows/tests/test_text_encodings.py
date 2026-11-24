"""Windows text encodings: BOM handling and cp1251/cp1252 disambiguation."""

from __future__ import annotations

from pathlib import Path

import pytest

from deepl_ofm.services.documents import DocumentTranslator


def _read(path: Path) -> str:
    document = DocumentTranslator.read(path)
    return document.source_text or "\n".join(document.paragraphs)


@pytest.mark.parametrize(
    ("name", "payload", "expected"),
    [
        ("utf8.txt", "Привіт, світе!\nДругий рядок.".encode(), "Привіт, світе!"),
        ("utf8-bom.txt", b"\xef\xbb\xbf" + "Привіт!".encode(), "Привіт!"),
        ("cp1251-ru.txt", "Привет, мир! Это проверка.".encode("cp1251"), "Привет, мир! Это проверка."),
        ("cp1251-uk.txt", "Привіт, світе! Це перевірка.".encode("cp1251"), "Привіт, світе! Це перевірка."),
        ("utf16.txt", "Привіт!".encode("utf-16"), "Привіт!"),
        ("cp1252-de.txt", "Grüße aus München.".encode("cp1252"), "Grüße aus München."),
        ("cp1252-fr.txt", "Très bien, ça va.".encode("cp1252"), "Très bien, ça va."),
        ("ascii.txt", b"Plain text, no accents.", "Plain text, no accents."),
    ],
)
def test_text_decoding(tmp_path: Path, name: str, payload: bytes, expected: str) -> None:
    path = tmp_path / name
    path.write_bytes(payload)
    assert _read(path).splitlines()[0] == expected


def test_written_text_is_utf8(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("Привіт!\n\nДругий абзац.", encoding="utf-8", newline="")
    document = DocumentTranslator.read(source)
    output = DocumentTranslator.suggested_path(source, _ukrainian())
    DocumentTranslator.write(document, output, lambda line: line.upper())
    assert output.read_bytes().decode("utf-8").startswith("ПРИВІТ!")


def _ukrainian():
    from deepl_ofm.core.languages import get_language

    return get_language("uk")
