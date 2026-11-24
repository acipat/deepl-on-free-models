"""Tests for :mod:`deepl_ofm.services.documents`.

Fixtures are generated on the fly: a TXT/Markdown file, a minimal DOCX package
built with ``zipfile`` and a PDF built with ``reportlab``.  No network, no Qt.
"""

from __future__ import annotations

import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from deepl_ofm.services import documents
from deepl_ofm.services.documents import (
    DocumentError,
    DocumentKind,
    DocumentTranslator,
)

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

CONTENT_TYPES = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b'<Default Extension="xml" ContentType="application/xml"/>'
    b'<Default Extension="bin" ContentType="application/octet-stream"/>'
    b'<Override PartName="/word/document.xml" ContentType="application/vnd.'
    b'openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    b"</Types>"
)

RELS = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
    b'2006/relationships/officeDocument" Target="word/document.xml"/>'
    b"</Relationships>"
)

STYLES = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    b'<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
    b"</w:styles>"
)

DOCUMENT_XML = (
    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:document xmlns:w="{WORD_NS}" '
    f'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    f'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
    f'mc:Ignorable="w14"><w:body>'
    f"<w:p><w:pPr><w:pStyle w:val=\"Heading1\"/></w:pPr>"
    f"<w:r><w:rPr><w:b/></w:rPr><w:t>Hello </w:t></w:r>"
    f"<w:r><w:t>world</w:t></w:r></w:p>"
    f"<w:p><w:r><w:t>Second paragraph</w:t></w:r></w:p>"
    f"<w:p/>"
    f"</w:body></w:document>"
).encode()

IMAGE_BYTES = bytes(range(256)) * 3


def _target(code: str = "uk") -> SimpleNamespace:
    """Stand-in for ``core.languages.Language`` (only ``.code`` is used)."""
    return SimpleNamespace(code=code)


def _make_docx(path: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", RELS)
        archive.writestr("word/document.xml", DOCUMENT_XML)
        archive.writestr("word/styles.xml", STYLES)
        stored = zipfile.ZipInfo("word/media/image1.bin", (2024, 1, 2, 3, 4, 6))
        stored.compress_type = zipfile.ZIP_STORED
        archive.writestr(stored, IMAGE_BYTES)


def _make_pdf(path: Path, pages: list[list[str]]) -> None:
    """Write a PDF; an empty page list produces a graphics-only page."""
    pdf = canvas.Canvas(str(path), pagesize=(400, 300))
    for lines in pages:
        if not lines:
            pdf.setStrokeColorRGB(0.8, 0.1, 0.1)
            pdf.setLineWidth(2)
            pdf.rect(30, 200, 80, 40, stroke=1, fill=0)
        else:
            pdf.setFont("Helvetica", 14)
            baseline = 250
            for line in lines:
                pdf.drawString(50, baseline, line)
                baseline -= 30
        pdf.showPage()
    pdf.save()


def _encrypted_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret")
    with path.open("wb") as stream:
        writer.write(stream)


def test_from_path_is_case_insensitive_and_unknown_extensions_are_none() -> None:
    assert DocumentKind.from_path(Path("Report.PDF")) is DocumentKind.PDF
    assert DocumentKind.from_path(Path("notes.Docx")) is DocumentKind.DOCX
    assert DocumentKind.from_path(Path("readme.MD")) is DocumentKind.MARKDOWN
    assert DocumentKind.from_path(Path("note.TXT")) is DocumentKind.TEXT
    assert DocumentKind.from_path(Path("archive.tar.gz")) is None
    assert DocumentKind.TEXT.pattern == "*.txt"
    assert DocumentKind.MARKDOWN.pattern == "*.md"
    assert DocumentKind.PDF.pattern == "*.pdf"
    assert DocumentKind.DOCX.pattern == "*.docx"
    # Output names use the canonical lower-case extension, like the Swift app.
    assert (
        DocumentTranslator.suggested_path(Path("report.PDF"), _target("de"))
        == Path("report_de.pdf")
    )


def test_txt_roundtrip_preserves_blank_lines_and_reports_progress(tmp_path: Path) -> None:
    source = tmp_path / "Note.TXT"
    source.write_text("Hello\n\nWorld\n", encoding="utf-8", newline="")

    document = DocumentTranslator.read(source)
    assert document.kind is DocumentKind.TEXT
    assert document.source_text == "Hello\n\nWorld\n"
    assert document.paragraphs == []
    assert document.text == "Hello\n\nWorld\n"

    output = DocumentTranslator.suggested_path(source, _target("uk"))
    assert output == tmp_path / "Note_uk.txt"

    progress: list[tuple[int, int]] = []
    calls: list[str] = []

    def translate(text: str) -> str:
        calls.append(text)
        return text.upper()

    returned = DocumentTranslator.write(
        document,
        output,
        translate,
        on_progress=lambda done, total: progress.append((done, total)),
    )
    assert returned == output
    assert calls == ["Hello", "World"]
    assert output.read_text(encoding="utf-8") == "HELLO\n\nWORLD\n"
    assert source.read_text(encoding="utf-8") == "Hello\n\nWorld\n"
    assert progress == [(1, 2), (2, 2)]


def test_text_units_group_lines_like_the_swift_original() -> None:
    source = (
        "\r\nTitle\r\nline 2\r\n \r\n\r\n````swift\r\n\r\n```\r\nlet n = 10\r\n"
        "````\r\nNext\r\n"
    )
    units = documents._text_units(source, markdown=True)
    assert [unit.text for unit in units if unit.translate] == ["Title\r\nline 2", "Next"]
    assert "".join(unit.text for unit in units) == source

    unclosed = "Start\n~~~sh\n\nprintf 'hello'\n"
    units = documents._text_units(unclosed, markdown=True)
    assert [unit.text for unit in units if unit.translate] == ["Start"]
    assert "".join(unit.text for unit in units) == unclosed


def test_markdown_keeps_fenced_code_and_blank_lines(tmp_path: Path) -> None:
    source = tmp_path / "page.md"
    source.write_text(
        "# Title\n\n```python\nprint('hi')\n```\n\nBody\n",
        encoding="utf-8",
    )
    document = DocumentTranslator.read(source)
    assert document.kind is DocumentKind.MARKDOWN
    assert document.source_text is not None

    translations: list[str] = []
    progress: list[tuple[int, int]] = []

    def translate(text: str) -> str:
        translations.append(text)
        return text.upper()

    output = tmp_path / "page_uk.md"
    DocumentTranslator.write(
        document,
        output,
        translate,
        on_progress=lambda done, total: progress.append((done, total)),
    )
    assert translations == ["# Title", "Body"]
    assert output.read_text(encoding="utf-8") == (
        "# TITLE\n\n```python\nprint('hi')\n```\n\nBODY\n"
    )
    assert progress == [(1, 2), (2, 2)]


def test_markdown_keeps_crlf_and_unclosed_fences(tmp_path: Path) -> None:
    source_text = (
        "\r\nTitle\r\nline 2\r\n \r\n\r\n````swift\r\n\r\n```\r\nlet n = 10\r\n"
        "````\r\nNext\r\n"
    )
    expected = (
        "\r\nTITLE\r\nLINE 2\r\n \r\n\r\n````swift\r\n\r\n```\r\nlet n = 10\r\n"
        "````\r\nNEXT\r\n"
    )
    source = tmp_path / "crlf.md"
    source.write_bytes(source_text.encode("utf-8"))
    output = tmp_path / "crlf_uk.md"
    DocumentTranslator.write(
        DocumentTranslator.read(source), output, lambda text: text.upper()
    )
    assert output.read_bytes() == expected.encode("utf-8")

    unclosed = "Start\n~~~sh\n\nprintf 'hello'\n"
    source.write_bytes(unclosed.encode("utf-8"))
    DocumentTranslator.write(
        DocumentTranslator.read(source), output, lambda text: text.upper()
    )
    assert output.read_text(encoding="utf-8") == "START\n~~~sh\n\nprintf 'hello'\n"


def test_docx_roundtrip_keeps_package_and_formatting(tmp_path: Path) -> None:
    source = tmp_path / "Sample.Docx"
    _make_docx(source)

    document = DocumentTranslator.read(source)
    assert document.kind is DocumentKind.DOCX
    assert document.paragraphs == ["Hello world", "Second paragraph", ""]
    assert document.text == "Hello world\nSecond paragraph\n"

    calls: list[str] = []
    progress: list[tuple[int, int]] = []

    def translate(text: str) -> str:
        calls.append(text)
        return text.upper()

    assert DocumentTranslator.suggested_path(source, _target()) == tmp_path / "Sample_uk.docx"
    output = tmp_path / "Sample_uk.Docx"
    DocumentTranslator.write(
        document,
        output,
        translate,
        on_progress=lambda done, total: progress.append((done, total)),
    )
    # Whitespace-only paragraphs are left alone and are not translation units,
    # so progress only counts the two paragraphs that reach the model.
    assert calls == ["Hello world", "Second paragraph"]
    assert progress == [(1, 2), (2, 2)]

    assert DocumentTranslator.read(output).paragraphs == [
        "HELLO WORLD",
        "SECOND PARAGRAPH",
        "",
    ]

    with zipfile.ZipFile(source) as original, zipfile.ZipFile(output) as translated:
        assert translated.namelist() == original.namelist()
        for name in original.namelist():
            if name == "word/document.xml":
                continue
            assert translated.read(name) == original.read(name), name
            assert (
                translated.getinfo(name).compress_type
                == original.getinfo(name).compress_type
            ), name
        xml = translated.read("word/document.xml").decode("utf-8")

    assert "<w:b" in xml
    assert "<w:pStyle" in xml
    assert 'xml:space="preserve"' in xml
    assert 'mc:Ignorable="w14"' in xml
    assert "xmlns:w14=" in xml
    assert ">HELLO </w:t>" in xml
    assert ">WORLD</w:t>" in xml


def test_docx_without_text_raises_no_text(tmp_path: Path) -> None:
    source = tmp_path / "empty.docx"
    xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{WORD_NS}"><w:body>'
        f"<w:p><w:r><w:t>   </w:t></w:r></w:p>"
        f"</w:body></w:document>"
    ).encode()
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("word/document.xml", xml)

    with pytest.raises(DocumentError) as info:
        DocumentTranslator.read(source)
    assert info.value.kind == "no_text"
    assert info.value.message()


def test_pdf_overlay_keeps_page_count_and_original_text_layer(tmp_path: Path) -> None:
    source = tmp_path / "Report.PDF"
    _make_pdf(source, [["Hello world", "Second line"], ["Another page"]])

    document = DocumentTranslator.read(source)
    assert document.kind is DocumentKind.PDF
    assert "Hello world" in document.paragraphs
    assert "Another page" in document.paragraphs
    assert "Hello world" in document.text

    assert DocumentTranslator.suggested_path(source, _target()) == tmp_path / "Report_uk.pdf"
    progress: list[tuple[int, int]] = []
    output = tmp_path / "Report_uk.PDF"
    DocumentTranslator.write(
        document,
        output,
        lambda text: text.upper(),
        on_progress=lambda done, total: progress.append((done, total)),
    )

    translated = PdfReader(str(output))
    assert len(translated.pages) == 2

    first = translated.pages[0].extract_text() or ""
    assert "Hello world" in first  # the original text layer is still there
    assert "HELLO" in first and "WORLD" in first
    assert "SECOND" in first and "LINE" in first

    second = translated.pages[1].extract_text() or ""
    assert "Another page" in second
    assert "ANOTHER" in second and "PAGE" in second

    assert progress[-1] == (len(document.paragraphs), len(document.paragraphs))
    assert source.read_bytes() != output.read_bytes()


def test_pdf_graphics_only_page_is_left_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "mixed.pdf"
    _make_pdf(source, [["First page"], [], ["Third page"]])

    document = DocumentTranslator.read(source)
    assert document.paragraphs == ["First page", "Third page"]

    output = tmp_path / "mixed_uk.pdf"
    DocumentTranslator.write(document, output, lambda text: text.upper())

    reader = PdfReader(str(output))
    assert len(reader.pages) == 3
    assert (reader.pages[1].extract_text() or "").strip() == ""
    assert "FIRST" in (reader.pages[0].extract_text() or "")
    assert "THIRD" in (reader.pages[2].extract_text() or "")


def test_pdf_without_text_raises_no_text(tmp_path: Path) -> None:
    source = tmp_path / "graphics.pdf"
    _make_pdf(source, [[]])

    with pytest.raises(DocumentError) as info:
        DocumentTranslator.read(source)
    assert info.value.kind == "no_text"


def test_pdf_uses_cid_font_for_chinese(tmp_path: Path) -> None:
    source = tmp_path / "chinese.pdf"
    _make_pdf(source, [["Hello world"]])

    output = tmp_path / "chinese_uk.pdf"
    DocumentTranslator.write(
        DocumentTranslator.read(source), output, lambda text: "你好世界"
    )
    extracted = PdfReader(str(output)).pages[0].extract_text() or ""
    assert "你好世界" in extracted


@pytest.mark.skipif(
    not documents._system_font_paths(False),
    reason="no Unicode TrueType font available on this system",
)
def test_pdf_uses_unicode_font_for_cyrillic(tmp_path: Path) -> None:
    source = tmp_path / "cyrillic.pdf"
    _make_pdf(source, [["Hello world"]])

    output = tmp_path / "cyrillic_uk.pdf"
    DocumentTranslator.write(
        DocumentTranslator.read(source), output, lambda text: "Привіт світе"
    )
    extracted = PdfReader(str(output)).pages[0].extract_text() or ""
    assert "Привіт" in extracted
    assert "світе" in extracted


def test_encrypted_pdf_raises_encrypted(tmp_path: Path) -> None:
    source = tmp_path / "secret.pdf"
    _encrypted_pdf(source)

    with pytest.raises(DocumentError) as info:
        DocumentTranslator.read(source)
    assert info.value.kind == "encrypted"
    assert isinstance(info.value.message(), str)
    assert info.value.message()


def test_unsupported_extension_raises_unsupported(tmp_path: Path) -> None:
    source = tmp_path / "data.xyz"
    source.write_text("hello", encoding="utf-8", newline="")

    with pytest.raises(DocumentError) as info:
        DocumentTranslator.read(source)
    assert info.value.kind == "unsupported"
    assert isinstance(info.value.message(), str)
    assert info.value.message()


def test_blank_text_file_raises_no_text(tmp_path: Path) -> None:
    source = tmp_path / "blank.txt"
    source.write_text(" \n\n\t", encoding="utf-8", newline="")

    with pytest.raises(DocumentError) as info:
        DocumentTranslator.read(source)
    assert info.value.kind == "no_text"


def test_cancellation_aborts_between_paragraphs(tmp_path: Path) -> None:
    source = tmp_path / "cancel.txt"
    source.write_text("One\n\nTwo\n\nThree\n", encoding="utf-8", newline="")
    document = DocumentTranslator.read(source)
    output = tmp_path / "cancel_uk.txt"

    cancel = threading.Event()
    calls: list[str] = []

    def translate(text: str) -> str:
        calls.append(text)
        cancel.set()
        return text.upper()

    with pytest.raises(DocumentError) as info:
        DocumentTranslator.write(document, output, translate, cancel=cancel)
    assert info.value.kind == "cancelled"
    assert calls == ["One"]
    assert not output.exists()

    already = threading.Event()
    already.set()
    with pytest.raises(DocumentError) as info:
        DocumentTranslator.write(
            document,
            output,
            lambda text: pytest.fail("translate must not run after cancellation"),
            cancel=already,
        )
    assert info.value.kind == "cancelled"
    assert not output.exists()


def test_translation_errors_propagate_without_output(tmp_path: Path) -> None:
    source = tmp_path / "error.txt"
    source.write_text("One\n\nTwo\n", encoding="utf-8", newline="")
    document = DocumentTranslator.read(source)
    output = tmp_path / "error_uk.txt"

    def translate(text: str) -> str:
        raise RuntimeError("provider failed")

    with pytest.raises(RuntimeError, match="provider failed"):
        DocumentTranslator.write(document, output, translate)
    assert not output.exists()


def test_pdf_samples_shaded_block_background_and_line_pitch(tmp_path: Path) -> None:
    source = tmp_path / "shaded.pdf"
    pdf = canvas.Canvas(str(source), pagesize=(400, 300))
    pdf.setFillColorRGB(0.2, 0.4, 0.6)
    pdf.rect(40, 200, 240, 80, stroke=0, fill=1)
    pdf.setFillColorRGB(0, 0, 0)
    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, 250, "Line one")
    pdf.drawString(50, 234, "Line two")
    pdf.showPage()
    pdf.save()

    document = DocumentTranslator.read(source)
    assert len(document.payload.blocks) == 1
    block = document.payload.blocks[0]
    assert block.text == "Line one Line two"
    assert block.background == pytest.approx((0.2, 0.4, 0.6))
    assert block.line_pitch == pytest.approx(16.0, abs=0.6)
    assert documents._pdf_leading(block, 12.0) == pytest.approx(16.0, abs=0.6)
    # The source was black on this panel and still contrasts, so it stays black.
    assert block.text_color == pytest.approx((0.0, 0.0, 0.0))
    assert documents._pdf_text_color(block.background, block.text_color) == pytest.approx(
        (0.0, 0.0, 0.0)
    )
    # Near-black surfaces fall back to white glyphs, like the Swift contrast rule.
    assert documents._pdf_text_color((0.05, 0.05, 0.05), (0.0, 0.0, 0.0)) == pytest.approx(
        (1.0, 1.0, 1.0)
    )


def test_pdf_white_page_background_and_single_line_leading(tmp_path: Path) -> None:
    source = tmp_path / "plain.pdf"
    _make_pdf(source, [["Hello world"]])

    block = DocumentTranslator.read(source).payload.blocks[0]
    assert block.background == pytest.approx((1.0, 1.0, 1.0))
    assert block.line_pitch == 0.0
    assert documents._pdf_leading(block, 12.0) == pytest.approx(14.4)
    assert documents._pdf_text_color(block.background, block.text_color) == pytest.approx(
        (0.0, 0.0, 0.0)
    )


def test_pdf_colour_parsing_handles_gray_rgb_cmyk_and_255_scale() -> None:
    assert documents._pdf_color(None) is None
    assert documents._pdf_color(0.5) == pytest.approx((0.5, 0.5, 0.5))
    assert documents._pdf_color((0.2, 0.4, 0.6)) == pytest.approx((0.2, 0.4, 0.6))
    assert documents._pdf_color((0.0, 0.5, 0.5, 0.0)) == pytest.approx((1.0, 0.5, 0.5))
    assert documents._pdf_color((128, 128, 128)) == pytest.approx((128 / 255,) * 3)
    assert documents._pdf_color((1.0, 0.0)) is None


def test_pdf_keeps_link_annotations(tmp_path: Path) -> None:
    source = tmp_path / "link.pdf"
    pdf = canvas.Canvas(str(source), pagesize=(400, 300))
    pdf.setFont("Helvetica", 14)
    pdf.drawString(50, 250, "Hello world")
    pdf.linkURL("https://example.com/", (45, 235, 220, 275), relative=0)
    pdf.showPage()
    pdf.save()

    output = tmp_path / "link_uk.pdf"
    DocumentTranslator.write(
        DocumentTranslator.read(source), output, lambda text: text.upper()
    )

    annotations = PdfReader(str(output)).pages[0].get("/Annots")
    assert annotations
    links = [annotation.get_object() for annotation in annotations]
    assert any(link.get("/Subtype") == "/Link" for link in links)
    assert any(
        str(link.get("/A", {}).get("/URI", "")) == "https://example.com/" for link in links
    )
