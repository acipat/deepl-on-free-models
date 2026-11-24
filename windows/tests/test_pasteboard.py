"""Tests for the rich-clipboard conversion in :mod:`deepl_ofm.support.pasteboard`.

Ports the paste behaviour of ``Sources/HyMT/Support/RichTextPasteboard.swift``
and the paste hook in ``Sources/HyMT/Views/SourceTextEditor.swift``.  The HTML
and RTF cases cover what a browser or word processor puts on the clipboard;
the final tests drive a real ``QMimeData`` through the Qt paste path.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QMimeData
from PySide6.QtGui import QGuiApplication

from deepl_ofm.controller import AppController
from deepl_ofm.core.languages import AppLanguage
from deepl_ofm.core.settings import AppSettings
from deepl_ofm.i18n import current_language, set_language
from deepl_ofm.services.history import HistoryStore
from deepl_ofm.support import pasteboard
from deepl_ofm.support.pasteboard import (
    html_to_markdown,
    looks_like_html,
    mime_to_markdown,
    rtf_to_markdown,
)
from deepl_ofm.ui.translate_view import TranslateView
from deepl_ofm.ui.write_view import WriteView


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #


def test_headings() -> None:
    assert html_to_markdown("<h1>Title</h1><h3>Sub</h3>") == "# Title\n\n### Sub"
    assert html_to_markdown("<h6>Deep</h6>") == "###### Deep"


def test_paragraphs_and_br() -> None:
    assert (
        html_to_markdown("<p>First line<br>second</p><p>Next</p>")
        == "First line\nsecond\n\nNext"
    )
    assert html_to_markdown("<div>One</div><div>Two</div>") == "One\n\nTwo"


def test_bold_italic_and_inline_code() -> None:
    html = (
        "<p><strong>Bold</strong> and <em>italic</em> and "
        "<code>x = 1</code> plus <tt>tt</tt></p>"
    )
    assert (
        html_to_markdown(html)
        == "**Bold** and *italic* and `x = 1` plus `tt`"
    )
    assert html_to_markdown("<p><b>B</b> <i>I</i></p>") == "**B** *I*"


def test_links_and_javascript_dropped() -> None:
    assert (
        html_to_markdown('<p><a href="https://example.com">Example</a></p>')
        == "[Example](https://example.com)"
    )
    assert (
        html_to_markdown('<p><a href="mailto:x@example.com">Mail</a></p>')
        == "[Mail](mailto:x@example.com)"
    )
    assert (
        html_to_markdown('<p><a href="/docs/intro">Docs</a></p>')
        == "[Docs](/docs/intro)"
    )
    assert (
        html_to_markdown('<p><a href="javascript:alert(1)">Bad</a></p>')
        == "Bad"
    )


def test_nested_bullet_list() -> None:
    html = "<ul><li>One<ul><li>Nested</li></ul></li><li>Two</li></ul>"
    assert html_to_markdown(html) == "- One\n  - Nested\n- Two"


def test_nested_numbered_list() -> None:
    html = "<ol><li>First<ol><li>Sub</li></ol></li><li>Second</li></ol>"
    assert html_to_markdown(html) == "1. First\n  1. Sub\n2. Second"


def test_blockquote() -> None:
    assert html_to_markdown("<blockquote>Quoted</blockquote>") == "> Quoted"
    assert (
        html_to_markdown("<blockquote><p>One</p><p>Two</p></blockquote>")
        == "> One\n>\n> Two"
    )


def test_fenced_pre_preserves_whitespace() -> None:
    html = "<pre>def f():\n    return 1</pre>"
    assert html_to_markdown(html) == "```\ndef f():\n    return 1\n```"
    wrapped = "<pre><code>a &lt; b</code></pre>"
    assert html_to_markdown(wrapped) == "```\na < b\n```"


def test_table_falls_back_to_tabs() -> None:
    html = (
        "<table><tr><th>Name</th><th>Age</th></tr>"
        "<tr><td>Ann</td><td>30</td></tr></table>"
    )
    assert html_to_markdown(html) == "Name\tAge\nAnn\t30"


def test_entities_are_decoded() -> None:
    html = "<p>Tom &amp; Jerry&nbsp;&mdash; &#8212;</p>"
    assert html_to_markdown(html) == "Tom & Jerry — —"


def test_script_and_style_are_stripped() -> None:
    html = "<p>Keep</p><script>var x = '<p>no</p>';</script><style>p{}</style><p>This</p>"
    assert html_to_markdown(html) == "Keep\n\nThis"


def test_hr_and_blank_line_collapse() -> None:
    assert html_to_markdown("<p>A</p><hr><p>B</p>") == "A\n\n---\n\nB"
    assert html_to_markdown("<p>A</p>\n\n\n\n<p>B</p>") == "A\n\nB"


def test_images_and_deleted_text() -> None:
    html = (
        '<p><img src="https://example.com/a.png" alt="Pic"> '
        '<img src="data:image/png;base64,AAAA" alt="Skipped"> '
        "<del>gone</del></p>"
    )
    assert html_to_markdown(html) == "![Pic](https://example.com/a.png) ~~gone~~"


def test_realistic_browser_fragment() -> None:
    html = """\
<article>
  <h2>Release notes</h2>
  <p>Version <strong>2.0</strong> adds <em>dark mode</em> and
     <a href="https://example.com/docs">docs</a>.</p>
  <ul>
    <li>Faster startup</li>
    <li>Better search
      <ul><li>Fuzzy matching</li></ul>
    </li>
  </ul>
  <blockquote>Ship it.</blockquote>
  <pre><code>pip install app</code></pre>
</article>
"""
    assert html_to_markdown(html) == (
        "## Release notes\n\n"
        "Version **2.0** adds *dark mode* and [docs](https://example.com/docs).\n\n"
        "- Faster startup\n"
        "- Better search\n"
        "  - Fuzzy matching\n\n"
        "> Ship it.\n\n"
        "```\n"
        "pip install app\n"
        "```"
    )


def test_looks_like_html() -> None:
    assert looks_like_html("<p>Hello</p>")
    assert looks_like_html("</div>")
    assert looks_like_html("<!DOCTYPE html>")
    assert not looks_like_html("plain text")
    assert not looks_like_html("a < b and c > d")
    assert not looks_like_html("")


def test_empty_html() -> None:
    assert html_to_markdown("") == ""
    assert html_to_markdown("   \n\t") == ""


# --------------------------------------------------------------------------- #
# RTF
# --------------------------------------------------------------------------- #


def test_rtf_bold_and_italic_runs() -> None:
    rtf = (
        r"{\rtf1\ansi{\fonttbl{\f0 Arial;}}\f0\fs24 Hello "
        r"\b bold\b0  and \i italic\i0 !\par}"
    )
    assert rtf_to_markdown(rtf) == "Hello **bold** and *italic*!"


def test_rtf_underline() -> None:
    rtf = r"{\rtf1\ul underlined\ulnone  plain}"
    assert rtf_to_markdown(rtf) == "_underlined_ plain"


def test_rtf_paragraphs_line_and_tab() -> None:
    assert rtf_to_markdown(r"{\rtf1 First\par Second\par}") == "First\n\nSecond"
    assert rtf_to_markdown(r"{\rtf1 one\line two}") == "one\ntwo"
    assert rtf_to_markdown(r"{\rtf1 a\tab b}") == "a\tb"


def test_rtf_unicode_escapes() -> None:
    rtf = r"{\rtf1 \u1055?\u1088?\u1080?\u1074?\u1077?\u1090?}"
    assert rtf_to_markdown(rtf) == "Привет"
    assert rtf_to_markdown(r"{\rtf1 \u8212?}") == "—"


def test_rtf_cyrillic_byte_escapes() -> None:
    rtf = r"{\rtf1\ansi\ansicpg1251 \'cf\'f0\'e8\'e2\'e5\'f2}"
    assert rtf_to_markdown(rtf) == "Привет"
    # Without a declared codepage the cp1251 heuristic still picks Cyrillic.
    assert rtf_to_markdown(r"{\rtf1\ansi \'cf\'f0\'e8\'e2\'e5\'f2}") == "Привет"


def test_rtf_cp1252_byte_escapes() -> None:
    assert rtf_to_markdown(r"{\rtf1 caf\'e9}") == "café"


def test_rtf_skips_font_table_color_table_and_generator() -> None:
    rtf = (
        r"{\rtf1{\fonttbl{\f0 Times New Roman;}}"
        r"{\colortbl;\red0\green0\blue0;}"
        r"{\*\generator Riched20;}\f0 Visible text}"
    )
    assert rtf_to_markdown(rtf) == "Visible text"


def test_rtf_malformed_input_degrades_to_text() -> None:
    assert rtf_to_markdown("") == ""
    assert rtf_to_markdown("plain text") == "plain text"
    malformed = r"{\rtf1 \b broken"
    result = rtf_to_markdown(malformed)
    assert "broken" in result
    assert "\\" not in result


# --------------------------------------------------------------------------- #
# QMimeData dispatch
# --------------------------------------------------------------------------- #


def test_mime_prefers_html(qapp) -> None:
    mime = QMimeData()
    mime.setHtml("<h2>Title</h2><p>Body</p>")
    mime.setText("Title Body")
    assert mime_to_markdown(mime) == "## Title\n\nBody"


def test_mime_html_that_is_plain_text_falls_back(qapp) -> None:
    mime = QMimeData()
    mime.setHtml("not markup")
    mime.setText("plain")
    assert mime_to_markdown(mime) == "plain"


def test_mime_rtf_only(qapp) -> None:
    mime = QMimeData()
    rtf = r"{\rtf1 Hello \b bold\b0!}"
    mime.setData("text/rtf", rtf.encode("latin-1"))
    assert mime_to_markdown(mime) == "Hello **bold**!"


def test_mime_text_only_and_empty(qapp) -> None:
    text = QMimeData()
    text.setText("Hello")
    assert mime_to_markdown(text) == "Hello"

    assert mime_to_markdown(QMimeData()) == ""


def test_mime_empty_html_conversion_falls_back(qapp) -> None:
    mime = QMimeData()
    mime.setHtml("<script>var x = 1;</script>")
    mime.setText("fallback")
    assert mime_to_markdown(mime) == "fallback"


def test_mime_rtf_parser_error_falls_back(qapp, monkeypatch) -> None:
    mime = QMimeData()
    mime.setData("text/rtf", b"{\\rtf1 broken")
    mime.setText("plain fallback")

    def explode(_value: str) -> str:
        raise ValueError("bad RTF")

    monkeypatch.setattr(pasteboard, "rtf_to_markdown", explode)
    assert mime_to_markdown(mime) == "plain fallback"


# --------------------------------------------------------------------------- #
# Widget paste paths
# --------------------------------------------------------------------------- #


def _controller(tmp_path: Path) -> AppController:
    settings = AppSettings(path=tmp_path / "settings.json")
    settings.model = "hy-mt2:7b"
    settings.auto_translate = False
    settings.interface_language = AppLanguage.EN
    return AppController(
        settings=settings,
        history=HistoryStore(path=tmp_path / "history.json"),
    )


@pytest.fixture(autouse=True)
def _isolated_clipboard(qapp):
    """Keep the global clipboard clean so no Qt-owned data outlives a test."""
    QGuiApplication.clipboard().clear()
    yield
    QGuiApplication.clipboard().clear()
    qapp.processEvents()


@pytest.fixture
def controller(qapp, tmp_path):
    previous_language = current_language()
    value = _controller(tmp_path)
    try:
        yield value
    finally:
        value.deleteLater()
        set_language(previous_language)
        qapp.processEvents()


@pytest.fixture
def translate_view(qapp, controller):
    widget = TranslateView(controller)
    widget.resize(1180, 760)
    widget.show()
    qapp.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    qapp.processEvents()


def test_paste_html_into_translate_editor(qapp, translate_view, controller) -> None:
    # `insertFromMimeData` is the hook Qt's Paste action calls; injecting the
    # data directly avoids handing a Python-owned QMimeData to the global
    # clipboard, which crashes at Qt teardown under the offscreen platform.
    mime = QMimeData()
    mime.setHtml("<h2>Pasted</h2><p>With <strong>bold</strong>.</p>")
    mime.setText("Pasted With bold.")

    translate_view._editor.setFocus()
    translate_view._editor.insertFromMimeData(mime)
    qapp.processEvents()

    expected = "## Pasted\n\nWith **bold**."
    assert translate_view._editor.toPlainText() == expected
    assert controller.source_text == expected


def test_paste_html_into_write_editor(qapp, controller) -> None:
    view = WriteView(controller)
    try:
        mime = QMimeData()
        mime.setHtml("<p>Make this <em>better</em>.</p>")
        mime.setText("Make this better.")
        view.editor.insertFromMimeData(mime)
        qapp.processEvents()
        assert view.editor.toPlainText() == "Make this *better*."
    finally:
        view.deleteLater()
        qapp.processEvents()
