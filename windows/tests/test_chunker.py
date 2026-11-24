"""Tests for :mod:`deepl_ofm.core.chunker`.

Ports ``Tests/HyMTTests/TextChunkerTests.swift`` one-to-one (the Swift
``separatorBefore`` is ``TextChunk.separator_before`` here) and covers the
layout guarantees of ``compose``, Markdown prefixes and fenced code blocks.
"""

from __future__ import annotations

import pytest

from deepl_ofm.core.chunker import TextChunk, TextChunker


def test_blank_line_is_preserved() -> None:
    """TextChunkerTests.testBlankLineIsPreserved."""
    chunks = TextChunker.split("One\n\nTwo")
    assert len(chunks) == 2
    assert chunks[0].text == "One"
    assert chunks[0].separator_before == ""
    assert chunks[1].text == "Two"
    assert chunks[1].separator_before == "\n\n"


def test_single_line_break() -> None:
    """TextChunkerTests.testSingleLineBreak."""
    chunks = TextChunker.split("One\nTwo")
    assert len(chunks) == 2
    assert chunks[1].separator_before == "\n"


def test_multiple_blank_lines() -> None:
    """TextChunkerTests.testMultipleBlankLines."""
    chunks = TextChunker.split("One\n\n\nTwo")
    assert len(chunks) == 2
    assert chunks[1].separator_before == "\n\n\n"


def test_trailing_blank_lines_ignored() -> None:
    """TextChunkerTests.testTrailingBlankLinesIgnored."""
    chunks = TextChunker.split("One\n\n")
    assert len(chunks) == 1
    assert chunks[0].text == "One"


def test_long_line_splits_into_pieces() -> None:
    """TextChunkerTests.testLongLineSplitsIntoPieces."""
    line = "word " * 800
    chunks = TextChunker.split(line)
    assert len(chunks) > 1
    assert chunks[1].separator_before == " "


def test_windows_line_endings_are_normalized() -> None:
    """TextChunkerTests.testWindowsLineEndingsAreNormalized."""
    chunks = TextChunker.split("One\r\n\r\nTwo\r\nThree")
    assert len(chunks) == 3
    assert chunks[0].text == "One"
    assert chunks[1].separator_before == "\n\n"
    assert chunks[2].separator_before == "\n"
    assert not any("\r" in chunk.text for chunk in chunks)


def test_sentence_splitter() -> None:
    """TextChunkerTests.testSentenceSplitter."""
    assert TextChunker.split_sentences(
        "First sentence. Second sentence! Third one?"
    ) == ["First sentence.", "Second sentence!", "Third one?"]


# --------------------------------------------------------------------------- #
# Additional edge cases
# --------------------------------------------------------------------------- #


def test_empty_string_keeps_one_empty_chunk() -> None:
    chunks = TextChunker.split("")
    assert len(chunks) == 1
    assert chunks[0].text == ""
    assert chunks[0].prefix == ""
    assert TextChunker.compose(chunks, [""]) == ""


def test_whitespace_only_input_is_preserved() -> None:
    chunks = TextChunker.split("   \n  ")
    assert len(chunks) == 1
    assert TextChunker.compose(chunks, [chunks[0].text]) == "   \n  "


def test_normalize_handles_mixed_line_endings() -> None:
    assert TextChunker.normalize("a\r\nb\rc\nd\r\n\r\ne") == "a\nb\nc\nd\n\ne"


def test_normalize_is_idempotent() -> None:
    value = "One\r\nTwo\rThree\nFour"
    assert TextChunker.normalize(TextChunker.normalize(value)) == "One\nTwo\nThree\nFour"


def test_markdown_prefixes_are_extracted() -> None:
    source = "# Title\n## Section\n- item\n1. step\n> quote\n- [ ] task\n* star"
    chunks = TextChunker.split(source)
    assert [(chunk.prefix, chunk.text) for chunk in chunks] == [
        ("# ", "Title"),
        ("## ", "Section"),
        ("- ", "item"),
        ("1. ", "step"),
        ("> ", "quote"),
        ("- [ ] ", "task"),
        ("* ", "star"),
    ]
    assert [chunk.is_heading for chunk in chunks] == [
        True,
        True,
        False,
        False,
        False,
        False,
        False,
    ]


def test_checkbox_variants_are_prefixes() -> None:
    chunks = TextChunker.split("- [x] done\n- [X] also done")
    assert chunks[0].prefix == "- [x] "
    assert chunks[1].prefix == "- [X] "


def test_nested_list_indentation_is_kept_in_the_prefix() -> None:
    chunks = TextChunker.split("  - nested")
    assert chunks[0].prefix == "  - "
    assert chunks[0].text == "nested"


def test_compose_restores_blank_lines_and_prefixes() -> None:
    source = "## Title\n\n- one\n1. two\n\n> quote"
    chunks = TextChunker.split(source)
    translated = [chunk.text.upper() for chunk in chunks]
    assert TextChunker.compose(chunks, translated) == (
        "## TITLE\n\n- ONE\n1. TWO\n\n> QUOTE"
    )
    assert TextChunker.compose(chunks, [chunk.text for chunk in chunks]) == source


def test_compose_does_not_add_a_trailing_newline() -> None:
    chunks = TextChunker.split("One\nTwo\n\n")
    assert TextChunker.compose(chunks, ["1", "2"]) == "1\n2"


def test_compose_leading_blank_line() -> None:
    chunks = TextChunker.split("One\nTwo")
    assert TextChunker.compose(chunks, ["One", "Two"], leading_blank_line=True) == (
        "\nOne\nTwo"
    )


def test_compose_rejects_mismatched_lengths() -> None:
    chunks = TextChunker.split("One\nTwo")
    with pytest.raises(ValueError):
        TextChunker.compose(chunks, ["only one"])


def test_indices_are_sequential() -> None:
    chunks = TextChunker.split("One\n\nTwo\n\nThree")
    assert [chunk.index for chunk in chunks] == [0, 1, 2]


def test_fenced_code_block_is_one_chunk() -> None:
    source = "Before\n```python\nx = 1\n\nprint(x)\n```\nAfter"
    chunks = TextChunker.split(source)
    assert len(chunks) == 3
    assert [chunk.is_code for chunk in chunks] == [False, True, False]
    assert chunks[1].text == "```python\nx = 1\n\nprint(x)\n```"
    assert chunks[1].separator_before == "\n"
    assert chunks[2].separator_before == "\n"
    assert TextChunker.compose(chunks, [chunk.text for chunk in chunks]) == source


def test_unclosed_fence_consumes_the_rest() -> None:
    source = "Intro\n```\ncode line\nmore code"
    chunks = TextChunker.split(source)
    assert len(chunks) == 2
    assert chunks[1].is_code
    assert chunks[1].text == "```\ncode line\nmore code"


def test_tilde_fenced_block() -> None:
    source = "~~~\na\n~~~"
    chunks = TextChunker.split(source)
    assert len(chunks) == 1
    assert chunks[0].is_code
    assert chunks[0].text == source


def test_code_block_blank_lines_are_not_separators() -> None:
    source = "```\na\n\nb\n```"
    chunks = TextChunker.split(source)
    assert len(chunks) == 1
    assert chunks[0].text == source


def test_long_markdown_line_keeps_its_prefix_on_the_first_piece() -> None:
    source = "## " + "word " * 800
    chunks = TextChunker.split(source)
    assert len(chunks) > 1
    assert chunks[0].prefix == "## "
    assert chunks[0].is_heading
    assert all(chunk.prefix == "" for chunk in chunks[1:])
    assert chunks[1].separator_before == " "


def test_split_sentences_edges() -> None:
    assert TextChunker.split_sentences("") == []
    assert TextChunker.split_sentences("   ") == []
    assert TextChunker.split_sentences("No terminator here") == [
        "No terminator here"
    ]
    assert TextChunker.split_sentences("One. Two.") == ["One.", "Two."]
    assert TextChunker.split_sentences("Mr. Smith went home. He slept.") == [
        "Mr. Smith went home.",
        "He slept.",
    ]
    assert TextChunker.split_sentences('He said "Go." Then left.') == [
        'He said "Go."',
        "Then left.",
    ]


def test_sentence_split_keeps_ellipsis_and_closers() -> None:
    assert TextChunker.split_sentences("Wait... Really?! Yes.") == [
        "Wait...",
        "Really?!",
        "Yes.",
    ]


def test_prefix_only_line_is_translatable_text() -> None:
    chunks = TextChunker.split("##")
    assert chunks[0].prefix == ""
    assert chunks[0].text == "##"


def test_trailing_whitespace_is_dropped_like_swift() -> None:
    chunks = TextChunker.split("One   \nTwo\t")
    assert chunks[0].text == "One"
    assert chunks[1].text == "Two"


def test_text_chunk_defaults() -> None:
    chunk = TextChunk(prefix="", text="Hi", is_heading=False, index=0)
    assert chunk.separator_before == "\n"
    assert chunk.is_code is False
