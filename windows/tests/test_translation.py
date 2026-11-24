"""Tests for :mod:`deepl_ofm.services.translation` — no sockets, fake session.

The fake session implements just enough of ``requests.Session`` for the
streaming code: ``post``/``get`` returning prepared responses and recording the
request bodies.  Responses can raise connection errors, carry HTTP error codes,
yield malformed NDJSON/SSE frames, stop early or trigger cancellation.
"""

from __future__ import annotations

import json
import threading
import time

import pytest
import requests

from deepl_ofm.core.languages import LanguageTable
from deepl_ofm.core.prompts import TranslationStyle, TranslationTone
from deepl_ofm.core.providers import BackendConfig, BackendKind
from deepl_ofm.services.translation import (
    TranslationCancelled,
    TranslationError,
    Translator,
    _OutputBudget,
)


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class FakeResponse:
    """Minimal ``requests.Response`` for the streaming reader."""

    def __init__(
        self,
        lines: list[bytes | str] | None = None,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        json_body: object = None,
    ) -> None:
        self._lines = [
            line if isinstance(line, bytes) else str(line).encode() for line in lines or []
        ]
        self.status_code = status_code
        self.headers = headers or {}
        self._json_body = json_body
        self.closed = False
        self.consumed = 0

    def iter_lines(self, *args, **kwargs):
        for line in self._lines:
            if self.closed:
                return
            self.consumed += 1
            yield line

    def close(self) -> None:
        self.closed = True

    def json(self):
        if self._json_body is None:
            raise ValueError("no JSON body")
        return self._json_body


class CancellingResponse(FakeResponse):
    """Sets the cancellation event after the first streamed line."""

    def __init__(self, event: threading.Event, lines, **kwargs) -> None:
        super().__init__(lines, **kwargs)
        self.event = event

    def iter_lines(self, *args, **kwargs):
        for index, line in enumerate(self._lines):
            if index == 1:
                self.event.set()
            if self.closed:
                return
            self.consumed += 1
            yield line


class FakeSession:
    """Records requests and dispatches to a handler (or raises)."""

    def __init__(self, post_handler=None, get_handler=None) -> None:
        self.post_handler = post_handler
        self.get_handler = get_handler
        self.requests: list[dict] = []
        self.closed = False

    def post(self, url: str, **kwargs):
        self.requests.append({"method": "POST", "url": url, **kwargs})
        if self.post_handler is None:
            raise requests.exceptions.ConnectionError("no route")
        return self.post_handler(url, kwargs)

    def get(self, url: str, **kwargs):
        self.requests.append({"method": "GET", "url": url, **kwargs})
        if self.get_handler is None:
            raise requests.exceptions.ConnectionError("no route")
        return self.get_handler(url, kwargs)

    def close(self) -> None:
        self.closed = True


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def language(code: str):
    value = LanguageTable.get(code)
    assert value is not None, f"missing language {code}"
    return value


def ollama_lines(*pieces: str, done_reason: str = "stop") -> list[bytes]:
    lines = [
        json.dumps({"message": {"content": piece}, "done": False}).encode()
        for piece in pieces
    ]
    lines.append(
        json.dumps(
            {
                "done": True,
                "done_reason": done_reason,
                "eval_count": max(1, len(pieces)),
                "eval_duration": 500_000_000,
            }
        ).encode()
    )
    return lines


def sse_lines(*pieces: str, finish: str = "stop") -> list[bytes]:
    lines: list[bytes] = []
    for piece in pieces:
        frame = {"choices": [{"delta": {"content": piece}, "finish_reason": None}]}
        lines.append(("data: " + json.dumps(frame)).encode())
        lines.append(b"")
    lines.append(
        (
            "data: "
            + json.dumps({"choices": [{"delta": {}, "finish_reason": finish}]})
        ).encode()
    )
    lines.append(b"data: [DONE]")
    return lines


def config(
    kind: BackendKind = BackendKind.OLLAMA,
    base_url: str = "http://127.0.0.1:11434",
    model: str = "hy-mt2:7b",
    **kwargs,
) -> BackendConfig:
    return BackendConfig(kind=kind, base_url=base_url, model=model, **kwargs)


def translate_with(session: FakeSession, text: str, **kwargs):
    return Translator(session).translate(
        text,
        source=kwargs.pop("source", language("uk")),
        target=kwargs.pop("target", language("en")),
        style=kwargs.pop("style", TranslationStyle.AUTO),
        tone=kwargs.pop("tone", TranslationTone.STANDARD),
        config=kwargs.pop("config", config()),
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# 1. Streaming protocols agree
# --------------------------------------------------------------------------- #


def test_ollama_and_openai_streams_produce_the_same_text():
    ollama_response = FakeResponse(ollama_lines("Hello ", "world."))
    ollama_session = FakeSession(lambda url, kwargs: ollama_response)
    progress: list[tuple[int, int]] = []
    partials: list[str] = []

    ollama = translate_with(
        ollama_session,
        "Привіт, світе.",
        on_progress=lambda done, total: progress.append((done, total)),
        on_partial=partials.append,
    )

    openai_session = FakeSession(lambda url, kwargs: FakeResponse(sse_lines("Hello ", "world.")))
    openai = translate_with(
        openai_session,
        "Привіт, світе.",
        config=config(
            BackendKind.OPENAI,
            "https://api.example.test",
            "gpt-test",
            api_key="secret",
        ),
    )

    assert ollama.text == "Hello world."
    assert openai.text == "Hello world."
    assert ollama.warnings == 0
    assert openai.warnings == 0
    assert progress == [(0, 1), (1, 1)]
    assert partials[-1] == "Hello world."
    assert isinstance(ollama.duration_ms, int)
    assert ollama.tokens_per_second == pytest.approx(4.0)
    assert ollama.used_fallback is False

    assert ollama_session.requests[0]["url"].endswith("/api/chat")
    assert openai_session.requests[0]["url"].endswith("/v1/chat/completions")
    assert ollama_session.requests[0]["json"]["stream"] is True
    options = ollama_session.requests[0]["json"]["options"]
    assert options["num_ctx"] == 8192
    assert options["repeat_penalty"] == 1.05
    assert options["num_predict"] == 4096
    assert openai_session.requests[0]["json"]["temperature"] == 0.7
    assert openai_session.requests[0]["headers"]["Authorization"] == "Bearer secret"


def test_openai_base_with_v1_is_not_doubled():
    session = FakeSession(lambda url, kwargs: FakeResponse(sse_lines("Hi.")))
    translate_with(
        session,
        "Привіт.",
        config=config(BackendKind.OPENAI, "https://api.example.test/v1/", "gpt-test"),
    )
    assert session.requests[0]["url"] == "https://api.example.test/v1/chat/completions"


def test_malformed_chunks_and_keep_alives_are_skipped():
    ollama = FakeResponse(
        [b"not json at all", *ollama_lines("Hello ", "world."), b"{broken"]
    )
    result = translate_with(FakeSession(lambda url, kwargs: ollama), "Привіт, світе.")
    assert result.text == "Hello world."

    sse = FakeResponse(
        [
            b": keep-alive",
            b"event: message",
            b"data: {broken json",
            *sse_lines("Hello ", "world."),
        ]
    )
    result = translate_with(
        FakeSession(lambda url, kwargs: sse),
        "Привіт, світе.",
        config=config(BackendKind.OPENAI, "https://api.example.test", "gpt-test"),
    )
    assert result.text == "Hello world."


# --------------------------------------------------------------------------- #
# 2. Marker truncation
# --------------------------------------------------------------------------- #


def test_marker_truncation_stops_the_block():
    response = FakeResponse(
        [
            b'{"message": {"content": "Hello"}, "done": false}',
            b'{"message": {"content": "hy_end"}, "done": false}',
            b'{"message": {"content": " ignored"}, "done": false}',
            b'{"done": true}',
        ]
    )
    result = translate_with(FakeSession(lambda url, kwargs: response), "Привіт.")
    # The source ends with a period; TokenRestorer preserves it.
    assert result.text == "Hello."
    assert response.consumed == 2
    assert response.closed is True


def test_stream_chat_stops_on_marker_without_validation():
    response = FakeResponse(
        [
            b'{"message": {"content": "Hello"}, "done": false}',
            b'{"message": {"content": "hy_end"}, "done": false}',
            b'{"message": {"content": " ignored"}, "done": false}',
            b'{"done": true}',
        ]
    )
    text, _ = Translator(FakeSession(lambda url, kwargs: response)).stream_chat(
        [{"role": "user", "content": "Hi"}], config()
    )
    assert text == "Hello"


def test_server_closing_early_is_interrupted():
    with pytest.raises(TranslationError) as info:
        translate_with(
            FakeSession(
                lambda url, kwargs: FakeResponse(
                    [b'{"message": {"content": "partial"}, "done": false}']
                )
            ),
            "Привіт, світе.",
        )
    assert info.value.kind == "interrupted"

    with pytest.raises(TranslationError) as info:
        translate_with(
            FakeSession(
                lambda url, kwargs: FakeResponse(
                    [b'data: {"choices":[{"delta":{"content":"Hi"}}]}']
                )
            ),
            "Привіт, світе.",
            config=config(BackendKind.OPENAI, "https://api.example.test", "gpt-test"),
        )
    assert info.value.kind == "interrupted"


# --------------------------------------------------------------------------- #
# 3. Empty output → retry ladder → warning
# --------------------------------------------------------------------------- #


def test_empty_output_runs_the_retry_ladder_and_counts_a_warning():
    def handler(url, kwargs):
        prompt = kwargs["json"]["messages"][0]["content"]
        if "Другий" in prompt:
            return FakeResponse(ollama_lines("Second line."))
        return FakeResponse([json.dumps({"done": True}).encode()])

    session = FakeSession(handler)
    session_config = config(temperature=0.7)
    result = translate_with(
        session,
        "Привіт.\nДругий рядочок.",
        config=session_config,
    )

    first_block = [
        request
        for request in session.requests
        if "Привіт." in request["json"]["messages"][0]["content"]
    ]
    second_block = [
        request
        for request in session.requests
        if "Другий рядочок." in request["json"]["messages"][0]["content"]
    ]
    # A short sentence (terminal punctuation) now uses the normal three-prompt
    # ladder: 3 attempts for prompt 0, 2 for each fallback.  The sentence
    # fallback cannot help a one-sentence block.
    assert len(first_block) == 7
    assert len(second_block) == 1
    assert first_block[1]["json"]["options"]["temperature"] == pytest.approx(0.3)
    assert session_config.temperature == pytest.approx(0.7)
    assert result.text == "Привіт.\nSecond line."
    assert result.warnings == 1


def test_all_empty_blocks_return_the_source_with_a_warning():
    session = FakeSession(
        lambda url, kwargs: FakeResponse([json.dumps({"done": True}).encode()])
    )
    result = translate_with(session, "Привіт.")
    assert result.text == "Привіт."
    assert result.warnings == 1
    assert result.used_fallback is False


def test_all_empty_blocks_switch_to_the_fallback():
    state = {"calls": 0}

    def handler(url, kwargs):
        state["calls"] += 1
        if kwargs["json"]["model"] == "primary":
            return FakeResponse([json.dumps({"done": True}).encode()])
        return FakeResponse(ollama_lines("Fallback text."))

    session = FakeSession(handler)
    result = translate_with(
        session,
        "Привіт.",
        config=config(model="primary"),
        fallback=config(model="backup"),
    )
    assert result.used_fallback is True
    assert result.text == "Fallback text."
    assert result.warnings == 0


def test_replacement_character_is_rejected_before_token_cleanup():
    calls = {"count": 0}

    def handler(url, kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return FakeResponse(ollama_lines("Hello\ufffd"))
        return FakeResponse(ollama_lines("Hello"))

    result = translate_with(FakeSession(handler), "Привіт.")
    # The raw U+FFFD must trigger a retry instead of being stripped silently.
    assert calls["count"] == 2
    assert result.text == "Hello."


def test_sentence_fallback_translates_long_failing_block():
    def handler(url, kwargs):
        prompt = kwargs["json"]["messages"][0]["content"]
        if "Перше речення." in prompt and "Друге речення." in prompt:
            return FakeResponse([json.dumps({"done": True}).encode()])
        if "Перше речення." in prompt:
            return FakeResponse(ollama_lines("First sentence."))
        if "Друге речення." in prompt:
            return FakeResponse(ollama_lines("Second sentence."))
        return FakeResponse([json.dumps({"done": True}).encode()])

    result = translate_with(FakeSession(handler), "Перше речення. Друге речення.")
    assert result.text == "First sentence. Second sentence."
    assert result.warnings == 0


# --------------------------------------------------------------------------- #
# 4. Fallback config
# --------------------------------------------------------------------------- #


def test_fallback_config_is_used_on_connection_error():
    state = {"calls": 0}

    def handler(url, kwargs):
        state["calls"] += 1
        if state["calls"] == 1:
            raise requests.exceptions.ConnectionError("server is down")
        return FakeResponse(sse_lines("Fallback works."))

    session = FakeSession(handler)
    primary = config(BackendKind.OPENAI, "https://primary.example.test", "primary")
    fallback = config(BackendKind.OPENAI, "https://fallback.example.test", "backup")
    result = translate_with(
        session,
        "Привіт, світе.",
        config=primary,
        fallback=fallback,
    )

    assert result.used_fallback is True
    assert result.text == "Fallback works."
    assert [request["json"]["model"] for request in session.requests] == [
        "primary",
        "backup",
    ]


def test_primary_failure_without_fallback_is_raised():
    with pytest.raises(TranslationError) as info:
        translate_with(FakeSession(lambda url, kwargs: FakeResponse(status_code=500)), "Привіт.")
    assert info.value.kind == "server"


# --------------------------------------------------------------------------- #
# 5. Cancellation
# --------------------------------------------------------------------------- #


def test_cancellation_before_the_request_raises_quickly():
    cancel = threading.Event()
    cancel.set()
    session = FakeSession(lambda url, kwargs: FakeResponse(ollama_lines("Hello")))
    started = time.monotonic()
    with pytest.raises(TranslationCancelled):
        translate_with(session, "Привіт.", cancel=cancel)
    assert time.monotonic() - started < 0.5
    assert session.requests == []


def test_cancellation_during_streaming_raises_quickly():
    cancel = threading.Event()
    response = CancellingResponse(
        cancel, [b'{"message": {"content": "Hello"}, "done": false}', *ollama_lines("x")]
    )
    started = time.monotonic()
    with pytest.raises(TranslationCancelled):
        translate_with(
            FakeSession(lambda url, kwargs: response),
            "Привіт, світе.",
            cancel=cancel,
        )
    assert time.monotonic() - started < 1.0
    assert response.closed is True


# --------------------------------------------------------------------------- #
# 6. HTTP error mapping
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (401, "unauthorized"),
        (403, "unauthorized"),
        (429, "rate_limit"),
        (500, "server"),
        (503, "server"),
        (400, "http"),
        (404, "http"),
    ],
)
def test_http_status_mapping(status: int, kind: str):
    headers = {"Retry-After": "12"} if status == 429 else {}
    session = FakeSession(
        lambda url, kwargs: FakeResponse(status_code=status, headers=headers)
    )
    with pytest.raises(TranslationError) as info:
        translate_with(session, "Привіт.")
    assert info.value.kind == kind
    assert info.value.status == status


def test_rate_limit_message_is_localised():
    session = FakeSession(lambda url, kwargs: FakeResponse(status_code=429))
    with pytest.raises(TranslationError) as info:
        translate_with(session, "Привіт.")
    assert "Too many requests" in info.value.message("en")


def test_selected_model_and_missing_key_are_checked_before_the_request():
    session = FakeSession(lambda url, kwargs: FakeResponse(ollama_lines("Hi")))
    with pytest.raises(TranslationError) as info:
        translate_with(session, "Привіт.", config=config(model=""))
    assert info.value.kind == "model"
    assert info.value.message("en") == "Choose a model in Settings."

    with pytest.raises(TranslationError) as info:
        translate_with(
            session,
            "Привіт.",
            config=config(requires_api_key=True, api_key=""),
        )
    assert info.value.kind == "unauthorized"
    assert info.value.message("en") == "Add your API key in Settings."
    assert session.requests == []


def test_invalid_base_url_maps_to_invalid_url():
    with pytest.raises(TranslationError) as info:
        translate_with(
            FakeSession(lambda url, kwargs: FakeResponse(ollama_lines("Hi"))),
            "Привіт.",
            config=config(base_url="not a url"),
        )
    assert info.value.kind == "invalid_url"
    assert "Invalid server URL" in info.value.message("en")


# --------------------------------------------------------------------------- #
# 7. Multi-line input with prefixes
# --------------------------------------------------------------------------- #


def test_multiline_input_keeps_line_count_and_prefixes():
    def handler(url, kwargs):
        prompt = kwargs["json"]["messages"][0]["content"]
        translations = {
            "Заголовок": "Title",
            "Пункт перший": "First item",
            "Другий пункт": "Second item",
        }
        for source, translated in translations.items():
            if source in prompt:
                return FakeResponse(ollama_lines(translated))
        return FakeResponse(ollama_lines("?"))

    result = translate_with(
        FakeSession(handler),
        "# Заголовок\n\n- Пункт перший\n1. Другий пункт",
    )
    assert result.text.splitlines() == ["# Title", "", "- First item", "1. Second item"]
    assert len(result.text.splitlines()) == 4


# --------------------------------------------------------------------------- #
# 8. Rewrite (DeepL Write) and warm-up / model listing
# --------------------------------------------------------------------------- #


def test_rewrite_uses_the_editor_instruction():
    seen: list[dict] = []
    progress: list[tuple[int, int]] = []

    def handler(url, kwargs):
        seen.append(kwargs)
        return FakeResponse(sse_lines("Improved text."))

    result = Translator(FakeSession(handler)).rewrite(
        "some text",
        target=language("en"),
        config=config(BackendKind.OPENAI, "https://api.example.test", "gpt-test"),
        on_progress=lambda done, total: progress.append((done, total)),
    )

    assert result.text == "Improved text."
    assert progress == [(0, 1), (1, 1)]
    prompt = seen[0]["json"]["messages"][0]["content"]
    assert prompt.startswith("You are an editor.")
    assert "Rewrite the following text in English." in prompt
    assert prompt.endswith("some text")


def test_rewrite_uses_fallback_after_an_http_error():
    def handler(url, kwargs):
        if kwargs["json"]["model"] == "primary":
            return FakeResponse(status_code=503)
        return FakeResponse(sse_lines("Improved by fallback."))

    result = Translator(FakeSession(handler)).rewrite(
        "some text",
        target=language("en"),
        config=config(BackendKind.OPENAI, "https://api.example.test", "primary"),
        fallback=config(BackendKind.OPENAI, "https://api.example.test", "backup"),
    )
    assert result.used_fallback is True
    assert result.text == "Improved by fallback."


def test_warm_up_returns_true_only_for_200():
    session = FakeSession(lambda url, kwargs: FakeResponse([], status_code=200))
    assert Translator(session).warm_up(config()) is True
    assert session.requests[0]["json"]["stream"] is False
    assert session.requests[0]["json"]["options"]["num_predict"] == 1

    failed = FakeSession(lambda url, kwargs: FakeResponse([], status_code=503))
    assert Translator(failed).warm_up(config()) is False


def test_list_models_delegates_to_probe():
    response = FakeResponse(json_body={"models": [{"name": "hy-mt2:7b"}, {"model": "x"}]})
    session = FakeSession(get_handler=lambda url, kwargs: response)
    assert Translator(session).list_models(config()) == ["hy-mt2:7b", "x"]
    assert session.requests[0]["url"].endswith("/api/tags")


# --------------------------------------------------------------------------- #
# 9. Output budget parity with the Swift unit tests
# --------------------------------------------------------------------------- #


def test_output_budget_detects_a_marker_split_across_unicode():
    expected = "é" * 80 + " • 👩🏽‍💻 cafe\u0301"
    output = _OutputBudget(1_000)
    assert output.append(expected + "<") is True
    assert output.append("｜hy_ending") is False
    assert output.text == expected


def test_output_budget_rejects_instead_of_cutting_an_emoji():
    output = _OutputBudget(4)
    assert output.append("éé") is True
    assert output.append("😀") is False
    assert output.exceeded_limit is True
    assert output.text == "éé"

    exact = _OutputBudget(4)
    assert exact.append("ééHY_END") is False
    assert exact.exceeded_limit is False
    assert exact.text == "éé"


def test_output_budget_flags_a_marker_past_the_cap():
    """A marker behind the cap means the cap cut the answer, not the model."""
    output = _OutputBudget(10)
    assert output.append("abcdefghij") is True
    assert output.append("KL<") is False
    assert output.exceeded_limit is True, "a marker past the cap must flag an overflow"
    assert output.text == "abcdefghij"

    past = _OutputBudget(10)
    assert past.append("abcdefghijk<") is False
    assert past.exceeded_limit is True

    # A marker exactly at the cap is the model finishing on its own.
    exact = _OutputBudget(4)
    assert exact.append("ééHY_END") is False
    assert exact.exceeded_limit is False
    assert exact.text == "éé"


# --------------------------------------------------------------------------- #
# 7-8. Prompt selection: structural headings and explicit source language
# --------------------------------------------------------------------------- #


def _first_prompt(session: FakeSession) -> str:
    return session.requests[0]["json"]["messages"][0]["content"]


def test_short_sentence_keeps_the_style_and_tone_prompt():
    """A short sentence is not a heading: style and tone stay in the prompt."""
    session = FakeSession(
        lambda url, kwargs: FakeResponse(
            ollama_lines("Könnten Sie mir den Bericht schicken?")
        )
    )
    result = translate_with(
        session,
        "Could you send me the report?",
        source=language("en"),
        target=language("de"),
        style=TranslationStyle.LITERAL,
        tone=TranslationTone.FORMAL,
        source_explicit=False,
    )

    prompt = _first_prompt(session)
    assert prompt.startswith("Please translate the following text into German.")
    assert "[literal, word for word; formal and professional]" in prompt
    assert "Translate this heading" not in prompt
    assert result.text == "Könnten Sie mir den Bericht schicken?"


def test_markdown_heading_keeps_the_heading_prompt():
    session = FakeSession(
        lambda url, kwargs: FakeResponse(ollama_lines("Bericht"))
    )
    translate_with(
        session,
        "# Report",
        source=language("en"),
        target=language("de"),
        style=TranslationStyle.LITERAL,
        tone=TranslationTone.FORMAL,
        source_explicit=False,
    )

    prompt = _first_prompt(session)
    assert prompt.startswith("Please translate this heading into German.")
    assert prompt.endswith("\n\nReport")
    assert "[literal, word for word; formal and professional]" in prompt


def test_short_title_without_terminal_punctuation_is_a_heading():
    session = FakeSession(
        lambda url, kwargs: FakeResponse(ollama_lines("Bericht"))
    )
    translate_with(
        session,
        "Report",
        source=language("en"),
        target=language("de"),
        style=TranslationStyle.LITERAL,
        tone=TranslationTone.FORMAL,
        source_explicit=False,
    )

    prompt = _first_prompt(session)
    assert prompt.startswith("Please translate this heading into German.")
    assert "[literal, word for word; formal and professional]" in prompt


def test_explicit_source_language_is_asserted_to_the_model():
    session = FakeSession(lambda url, kwargs: FakeResponse(ollama_lines("Hello.")))
    translate_with(
        session,
        "مرحبا بالعالم.",
        source=language("ar"),
        target=language("en"),
        source_explicit=True,
    )

    assert _first_prompt(session).startswith("The source language is Arabic. ")


def test_detected_source_language_is_not_asserted_to_the_model():
    session = FakeSession(lambda url, kwargs: FakeResponse(ollama_lines("Hello.")))
    translate_with(
        session,
        "مرحبا بالعالم.",
        source=language("ar"),
        target=language("en"),
        source_explicit=False,
    )

    prompt = _first_prompt(session)
    assert "The source language is" not in prompt
    assert prompt.startswith("Translate the following text into English.")
