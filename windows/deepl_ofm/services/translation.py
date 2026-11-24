"""Network translation engine ported from ``Sources/HyMT/Services/TranslationService.swift``.

The module owns the two provider protocols (Ollama ``/api/chat`` NDJSON and the
OpenAI-compatible SSE ``/chat/completions`` endpoint), the streaming byte
limiter, the per-line translation pipeline with its retry ladder and the
writing-mode ``rewrite`` used by the Write tab.  It has no UI dependencies and
is designed to run inside a worker thread; cancellation goes through a
``threading.Event``.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, replace
from math import isfinite
from typing import Callable, Iterator, Literal
from urllib.parse import urlsplit

import requests

from deepl_ofm.core.chunker import TextChunker, _closes_fence, _fence_marker, _parse_prefix
from deepl_ofm.core.languages import AppLanguage, Language, LanguageTable
from deepl_ofm.core.prompts import PromptBuilder, TranslationStyle, TranslationTone
from deepl_ofm.core.providers import BackendConfig, BackendKind
from deepl_ofm.core.sanitizer import OutputSanitizer
from deepl_ofm.core.tokens import TokenRestorer
from deepl_ofm.i18n import t, tf

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 10.0
_DEFAULT_TIMEOUT = 180.0
_WARM_UP_TIMEOUT = 180.0
_REWRITE_MAX_BYTES = 128_000 * 4
_MAX_OUTPUT_TOKENS = 4096
_DOCUMENT_PREVIEW_INTERVAL = 0.120
_STOP_SEQUENCES = [
    "hy_end",
    "<｜hy_place▁holder▁no▁8｜>",
    "<｜hy_place▁holder▁no▁2｜>",
]
_STREAM_USAGE_HOSTS = frozenset({"ollama.com", "api.openai.com", "api.deepseek.com", "openrouter.ai"})
_SHORT_BLOCK_LIMIT = 80
#: A short block ending with one of these is a sentence, not a heading.
_TERMINAL_PUNCTUATION = frozenset(".!?\u2026\u3002\uFF01\uFF1F")
_TRAILING_CLOSERS = "\"'”’»)]"

_REWRITE_INSTRUCTION = (
    "You are an editor. Rewrite the following text in {language}. Improve clarity, "
    "grammar, tone and style. Preserve the meaning, Markdown syntax, lists and line "
    "breaks. Return only the rewritten text, without explanations or quotes."
)

_MARKDOWN_INLINE_FORMATTING = tuple(
    re.compile(pattern)
    for pattern in (
        r"\*\*[^*\n]+\*\*",              # bold
        r"__[^_\n]+__",                   # bold
        r"(?<![\w*])\*[^*\n]+\*(?![\w*])",  # italic
        r"(?<![\w_])_[^_\n]+_(?![\w_])",  # italic
    )
)
_INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`)(.*?)(?<!`)\1(?!`)")
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_TABLE_ESCAPE = re.compile(r"\\[\\|]")
_TABLE_DELIMITER = re.compile(r":?-+:?")
_MARKDOWN_PATTERNS = tuple(
    re.compile(pattern, re.MULTILINE)
    for pattern in (
        r"^\s{0,3}#{1,6}\s+\S",           # heading
        r"^\s{0,3}[-*+]\s+\S",            # unordered list
        r"^\s{0,3}\d+[.)]\s+\S",          # ordered list
        r"^\s{0,3}>\s+\S",                # block quote
    )
) + _MARKDOWN_INLINE_FORMATTING + (_INLINE_CODE, _MARKDOWN_LINK)

_CONTEXT_LIMIT = re.compile(
    r"context_length_exceeded|context window|context length|context limit|"
    r"(?:input|prompt) (?:is )?too long",
    re.IGNORECASE,
)


class TranslationError(Exception):
    """Provider/transport failure with a stable ``kind`` for the UI.

    ``kind`` is one of ``connection``, ``invalid_url``, ``http``, ``unauthorized``,
    ``rate_limit``, ``server``, ``model``, ``interrupted``, ``unexpected``,
    ``empty`` or ``cancelled``.
    """

    def __init__(self, kind: str, status: int | None = None, detail: str = "") -> None:
        self.kind = kind
        self.status = status
        self.detail = detail
        text = f"{kind}: {detail}" if detail else kind
        super().__init__(text)

    def message(self, language: AppLanguage | str | None = None) -> str:
        """Localised, user-facing text (English keys come from the Swift app)."""
        kind = self.kind
        if kind == "invalid_url":
            return tf("Invalid server URL: %@", self.detail, language=language)
        if kind == "model":
            if not self.detail:
                return t("Choose a model in Settings.", language)
            return tf("Model “%@” not found on the server.", self.detail, language=language)
        if kind == "connection":
            return tf(
                "Could not connect to %@. Check that the server is running.",
                self.detail,
                language=language,
            )
        if kind == "unauthorized":
            if self.detail == "api_key":
                return t("Add your API key in Settings.", language)
            return t(
                "The provider rejected the request. Check the API key and model in Settings.",
                language,
            )
        if kind == "rate_limit":
            return t("Too many requests. Wait a moment and try again.", language)
        if kind == "server":
            return t("The provider is temporarily unavailable. Try again.", language)
        if kind == "empty":
            return t("The model returned an empty translation. Try again.", language)
        if kind == "interrupted":
            return t("The server interrupted the response. Try again.", language)
        if kind == "unexpected":
            return t(
                "The model could not translate this text. Try again or choose another model.",
                language,
            )
        if kind == "cancelled":
            return "Translation cancelled."
        if kind == "http":
            if self.status is None:
                return t(
                    "The provider rejected the request. "
                    "Check the API key and model in Settings.",
                    language,
                )
            if self.status in (400, 401, 403, 422):
                return t(
                    "The provider rejected the request. "
                    "Check the API key and model in Settings.",
                    language,
                )
            if 500 <= self.status <= 599:
                return t("The provider is temporarily unavailable. Try again.", language)
            return tf("Server returned error %@.", self.status, language=language)
        return t("Translation failed", language)


class TranslationCancelled(Exception):
    """Raised when the caller set the cancellation event."""


@dataclass
class TranslationOutput:
    """Result of one translation or rewrite job."""

    text: str
    warnings: int = 0
    tokens_per_second: float | None = None
    duration_ms: int | None = None
    used_fallback: bool = False


@dataclass(frozen=True)
class _ChatResult:
    text: str
    tokens_per_second: float | None
    tokens: int
    seconds: float
    exceeded_limit: bool = False


@dataclass(frozen=True)
class _BlockResult:
    text: str
    warning: bool
    tokens: int = 0
    seconds: float = 0.0


@dataclass(frozen=True)
class _JobResult:
    text: str
    warnings: int
    tokens: int
    seconds: float
    degenerate: bool = False


def _is_char_boundary(data: bytes, index: int) -> bool:
    """True when `index` starts a character in `data`."""
    return index == 0 or index >= len(data) or (data[index] & 0xC0) != 0x80


class _OutputBudget:
    """Byte-capped UTF-8 accumulator with streaming marker detection.

    A straight port of ``TranslationOutput`` at the end of
    ``TranslationService.swift``.  ``append`` returns ``False`` as soon as a
    chat-template marker (``hy-assistant``, ``hy_end``, ``<|`` …) is found, so
    the caller can stop reading the response; ``exceeded_limit`` is set when
    the byte cap truncated live text.
    """

    _MARKERS = tuple(
        marker.encode("utf-8")
        for marker in ("hy-assistant", "hy-user", "hy_end", "<｜", "<|", "</|", "｜hy")
    )
    _OVERLAP = max(len(marker) for marker in _MARKERS) - 1

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max(0, int(max_bytes))
        self._bytes = bytearray()
        self.exceeded_limit = False

    @property
    def text(self) -> str:
        return self._bytes.decode("utf-8", errors="replace")

    def append(self, piece: str) -> bool:
        """Append streamed text; return False when generation must stop."""
        if not piece:
            return True
        overlap = min(self._OVERLAP, len(self._bytes))
        remaining = self.max_bytes - len(self._bytes)
        data = piece.encode("utf-8", errors="replace")
        fragment = data[: max(0, remaining + self._OVERLAP + 1)]
        window = bytes(self._bytes[-overlap:]) + fragment
        folded = bytes(byte + 32 if 65 <= byte <= 90 else byte for byte in window)
        offsets = [folded.find(marker) for marker in self._MARKERS]
        offsets = [offset for offset in offsets if offset >= 0]
        if offsets:
            offset = min(offsets)
            if offset < overlap:
                del self._bytes[len(self._bytes) - (overlap - offset):]
            elif offset - overlap <= remaining:
                self._bytes.extend(window[overlap:offset])
            else:
                # The marker starts behind the byte cap, so the cap — not the
                # model — ended the generation. That is an overflow: the Swift
                # limiter sets the flag here too, and without it a truncated
                # answer would be validated and shown as a complete translation.
                self.exceeded_limit = True
                keep = min(remaining, len(fragment))
                while keep > 0 and not _is_char_boundary(fragment, keep):
                    keep -= 1
                self._bytes.extend(fragment[:keep])
            return False
        if len(fragment) > remaining:
            self.exceeded_limit = True
            return False
        self._bytes.extend(fragment)
        return True


def _http_error(status: int, detail: str = "") -> TranslationError:
    """Map an HTTP status to the documented ``TranslationError`` kind."""
    if status in (401, 403):
        return TranslationError("unauthorized", status=status, detail=detail)
    if status == 429:
        return TranslationError("rate_limit", status=status, detail=detail)
    if 500 <= status <= 599:
        return TranslationError("server", status=status, detail=detail)
    return TranslationError("http", status=status, detail=detail)


def _ollama_endpoint(base: str) -> str:
    return base.rstrip("/") + "/api/chat"


def _openai_endpoint(base: str, path: str) -> str:
    """Append ``/v1`` exactly like ``TranslationService.openAIEndpoint``."""
    value = base.rstrip("/")
    if value.endswith("/v1"):
        return value + "/" + path
    return value + "/v1/" + path


def _generation_stats(
    count: object, duration: object, units_per_second: int = 1
) -> tuple[int, float] | None:
    """Validate the pair before using a provider's generation measurements."""
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        return None
    if not isinstance(duration, (int, float)) or isinstance(duration, bool):
        return None
    seconds = duration / units_per_second
    if seconds <= 0 or not isfinite(seconds):
        return None
    return count, seconds


def _openai_stats(frame: dict) -> tuple[int, float] | None:
    usage = frame.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    count = usage.get("completion_tokens")
    timings = frame.get("timings")
    if isinstance(timings, dict):
        stats = _generation_stats(
            timings.get("predicted_n") or count, timings.get("predicted_ms"), 1000
        )
        if stats is not None:
            return stats
    stats = _generation_stats(count, usage.get("completion_time"))
    if stats is not None:
        return stats
    time_info = frame.get("time_info")
    if isinstance(time_info, dict):
        stats = _generation_stats(count, time_info.get("completion_time"))
        if stats is not None:
            return stats
    groq = frame.get("x_groq")
    if isinstance(groq, dict) and isinstance(groq.get("usage"), dict):
        usage = groq["usage"]
        return _generation_stats(usage.get("completion_tokens"), usage.get("completion_time"))
    return None


def _contains_markdown(text: str) -> bool:
    """Port of ``Sources/HyMT/Support/MarkdownDetector.swift``."""
    return any(pattern.search(text) for pattern in _MARKDOWN_PATTERNS) or (
        "\n" in text and "|" in text and bool(_markdown_table_rows(text.split("\n")))
    )


def _table_cells(line: str) -> tuple[list[str], bool, bool] | None:
    """Split cells on pipes outside of backtick spans and backslash escapes."""
    row = _TABLE_ESCAPE.sub("x", _INLINE_CODE.sub("x", line.strip()))
    if "|" not in row:
        return None
    leading = row.startswith("|")
    trailing = row.endswith("|")
    cells = row.split("|")[int(leading) : -1 if trailing else None]
    return ([cell.strip() for cell in cells], leading, trailing) if cells else None


def _table_shape(line: str) -> tuple[tuple[bool, ...], bool, bool] | None:
    row = _table_cells(line)
    if row is None:
        return None
    cells, leading, trailing = row
    return tuple(bool(cell) for cell in cells), leading, trailing


def _markdown_table_rows(lines: list[str]) -> set[int]:
    """Identify headers, delimiters and pipe-bearing rows in GFM tables."""
    rows: set[int] = set()
    previous_columns = 0
    in_table = False
    fence = None
    for index, line in enumerate(lines):
        if fence is not None:
            if _closes_fence(line, fence):
                fence = None
            continue
        fence = _fence_marker(line)
        row = (
            _table_cells(line)
            if fence is None and not line.startswith(("    ", "\t")) and not _parse_prefix(line)[0]
            else None
        )
        if row is None:
            previous_columns = 0
            in_table = False
            continue
        cells, _, _ = row
        if previous_columns == len(cells) and all(
            _TABLE_DELIMITER.fullmatch(cell) for cell in cells
        ):
            rows.update((index - 1, index))
            in_table = True
        elif in_table:
            rows.add(index)
        previous_columns = len(cells)
    return rows


def _split_mixed_line(text: str) -> tuple[str, str] | None:
    """Split ``"id, id — description"`` so ids stay byte-for-byte."""
    marker = " — "
    index = text.find(marker)
    if index < 0:
        return None
    left = text[:index]
    right = text[index + len(marker):].strip()
    if not right:
        return None

    latin = sum(
        1 for char in left if 0x41 <= ord(char) <= 0x7A or 0x30 <= ord(char) <= 0x39
    )
    cyrillic = sum(1 for char in left if 0x400 <= ord(char) <= 0x4FF)
    if latin < 8 or latin <= cyrillic * 2:
        return None

    pieces = [piece.strip() for piece in left.split(",")]
    if not pieces:
        return None
    looks_like_ids = all(
        piece
        and not any(char.isspace() for char in piece)
        and any(char in piece for char in "/:.-")
        and any(char.isdigit() for char in piece)
        for piece in pieces
    )
    if not looks_like_ids:
        return None
    return left + marker, right


def _markdown_structure(text: str) -> list[str]:
    """Port of ``TranslationService.markdownStructure`` (headings/lists)."""
    structure: list[str] = []
    for line in text.splitlines():
        body = line.lstrip(" \t")
        if not body:
            continue
        first = body[0]
        prefix_length = 0
        while prefix_length < len(body) and body[prefix_length] == first:
            prefix_length += 1
        rest = body[prefix_length:]
        if first in "#>":
            if rest and rest[0].isspace():
                structure.append(body[:prefix_length])
            continue
        if first in "-+*" and prefix_length == 1 and rest and rest[0].isspace():
            structure.append("bullet")
            continue
        digits = 0
        while digits < len(body) and body[digits].isdigit():
            digits += 1
        if digits and digits < len(body) and body[digits] in ".)":
            if digits + 1 < len(body) and body[digits + 1].isspace():
                structure.append("number")
    return structure


def _with_source_language(prompt: str, source: Language | None) -> str:
    """Prefix an ordinary prompt with the source language the user picked."""
    if source is None or source.is_auto:
        return prompt
    return f"The source language is {source.english_name}. " + prompt


def _gemma_source(
    text: str, model: str, explicit_source: Language | None = None
) -> Language | None:
    """Resolve the source required by TranslateGemma's published prompt."""
    name = model.strip().rsplit("/", 1)[-1].lower()
    if not name.startswith("translategemma"):
        return None
    if explicit_source is not None and not explicit_source.is_auto:
        return explicit_source
    return LanguageTable.detect(text, for_prompt=True)


def _is_structural_heading(text: str, is_heading: bool) -> bool:
    """Recognise Markdown headings and short, title-case labels."""
    if is_heading:
        return True
    body = text.strip()
    if len(body) > _SHORT_BLOCK_LIMIT:
        return False
    tail = body.rstrip().rstrip(_TRAILING_CLOSERS).rstrip()
    if not tail or tail[-1] in _TERMINAL_PUNCTUATION:
        return False
    initials = [next((char for char in word if char.isalpha()), "") for word in tail.split()]
    return any(char.isupper() for char in initials) and not any(
        char.islower() for char in initials
    )


def _watch_cancel(cancel: threading.Event, response: object, done: threading.Event) -> None:
    """Close a blocked response promptly when the caller cancels."""
    while not done.wait(0.05):
        if cancel.is_set():
            try:
                response.close()  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - defensive
                pass
            return


class Translator:
    """Streaming translation engine for Ollama and OpenAI-compatible backends."""

    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ):
        self._session = session if session is not None else requests.Session()
        self._timeout = float(timeout)

    # ------------------------------------------------------------------ public

    def translate(
        self,
        text: str,
        *,
        source: Language,
        target: Language,
        style: TranslationStyle,
        tone: TranslationTone,
        config: BackendConfig,
        fallback: BackendConfig | None = None,
        source_explicit: bool = True,
        one_request: bool = False,
        on_progress: Callable[[int, int], None] | None = None,
        on_partial: Callable[[str], None] | None = None,
        cancel: threading.Event | None = None,
    ) -> TranslationOutput:
        """Translate text, optionally trying one request before splitting it."""
        started = time.monotonic()
        self._raise_if_cancelled(cancel)
        if not text.strip():
            return TranslationOutput(text=text, duration_ms=0)

        try:
            job = self._run_job(
                text,
                source=source,
                target=target,
                style=style,
                tone=tone,
                config=config,
                source_explicit=source_explicit,
                one_request=one_request,
                on_progress=on_progress,
                on_partial=on_partial,
                cancel=cancel,
            )
            if job.degenerate and fallback is not None and fallback is not config:
                # Swift retries the whole job when no block was translated.
                raise TranslationError("empty", detail="no block could be translated")
            used_fallback = False
        except TranslationCancelled:
            raise
        except Exception as exc:
            if cancel is not None and cancel.is_set():
                raise TranslationCancelled() from None
            if fallback is None or fallback is config:
                raise
            logger.info("primary translation failed (%s); retrying with fallback", exc)
            self._emit_partial(on_partial, "")
            job = self._run_job(
                text,
                source=source,
                target=target,
                style=style,
                tone=tone,
                config=fallback,
                source_explicit=source_explicit,
                one_request=one_request,
                on_progress=on_progress,
                on_partial=on_partial,
                cancel=cancel,
            )
            used_fallback = True

        duration_ms = int((time.monotonic() - started) * 1000)
        return TranslationOutput(
            text=job.text,
            warnings=job.warnings,
            tokens_per_second=self._rate(job.tokens, job.seconds),
            duration_ms=duration_ms,
            used_fallback=used_fallback,
        )

    def rewrite(
        self,
        text: str,
        *,
        target: Language,
        config: BackendConfig,
        fallback: BackendConfig | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        on_partial: Callable[[str], None] | None = None,
        cancel: threading.Event | None = None,
    ) -> TranslationOutput:
        """Improve ``text`` (DeepL Write) using the editor instruction."""
        started = time.monotonic()
        self._raise_if_cancelled(cancel)
        prompt = _REWRITE_INSTRUCTION.format(language=target.english_name) + "\n\n" + text

        def run(backend: BackendConfig) -> _ChatResult:
            self._report(on_progress, 0, 1)
            result = self._stream_chat(
                [{"role": "user", "content": prompt}],
                backend,
                cancel=cancel,
                on_token=None,
                max_bytes=_REWRITE_MAX_BYTES,
            )
            if result.exceeded_limit:
                raise TranslationError("empty", detail="rewrite output too long")
            cleaned = self._clean_output(result.text)
            if not cleaned:
                raise TranslationError("empty", detail="rewrite returned nothing")
            self._report(on_progress, 1, 1)
            return _ChatResult(
                cleaned, result.tokens_per_second, result.tokens, result.seconds
            )

        try:
            result = run(config)
            used_fallback = False
        except TranslationCancelled:
            raise
        except Exception as exc:
            if cancel is not None and cancel.is_set():
                raise TranslationCancelled() from None
            if fallback is None or fallback is config:
                raise
            logger.info("primary rewrite failed (%s); retrying with fallback", exc)
            self._emit_partial(on_partial, "")
            result = run(fallback)
            used_fallback = True

        self._emit_partial(on_partial, result.text)
        return TranslationOutput(
            text=result.text,
            tokens_per_second=self._rate(result.tokens, result.seconds),
            duration_ms=int((time.monotonic() - started) * 1000),
            used_fallback=used_fallback,
        )

    def stream_chat(
        self,
        messages: list[dict],
        config: BackendConfig,
        *,
        cancel: threading.Event | None = None,
        on_token: Callable[[str], None] | None = None,
        max_bytes: int = 1_000_000,
    ) -> tuple[str, float | None]:
        """Stream one chat completion; return ``(text, tokens_per_second)``."""
        result = self._stream_chat(
            messages,
            config,
            cancel=cancel,
            on_token=on_token,
            max_bytes=max_bytes,
        )
        return result.text, result.tokens_per_second

    def translate_block(
        self,
        text: str,
        *,
        style: TranslationStyle,
        tone: TranslationTone,
        target: Language,
        config: BackendConfig,
        cancel: threading.Event | None = None,
    ) -> tuple[str, bool]:
        """Buffered single-block translation (port of ``translateBlock``)."""
        preserve = _contains_markdown(text)
        gemma_source = _gemma_source(text, config.model)
        if gemma_source is not None:
            prompts = [PromptBuilder.translate_gemma_prompt(text, gemma_source, target)]
        else:
            standard_prompt = PromptBuilder.prompt(
                text,
                style,
                tone,
                target.english_name,
                preserve_markdown=preserve,
            )
            concise_prompt = (
                f"Translate into {target.english_name}."
                + (" Preserve Markdown syntax and keep line breaks." if preserve else "")
                + "\n\n"
                + text
            )
            auto = style == TranslationStyle.AUTO and tone == TranslationTone.STANDARD
            prompts = [
                concise_prompt if auto else standard_prompt,
                standard_prompt if auto else concise_prompt,
                PromptBuilder.plain_prompt(text, target.english_name),
            ]
        result = self._buffered_translation(
            prompts,
            text,
            target,
            config,
            cancel,
            gemma_source=gemma_source,
            preserve_line_breaks=True,
            requires_markdown_structure=preserve,
        )
        restored = TokenRestorer.restore(text, result.text)
        if restored is None:
            raise TranslationError("empty", detail="protected tokens changed")
        return restored, result.warning

    def list_models(self, config: BackendConfig) -> list[str]:
        """Return the model ids advertised by the configured backend."""
        from deepl_ofm.services.probe import probe_models

        return probe_models(config, timeout=8.0, session=self._session)

    def warm_up(self, config: BackendConfig) -> bool:
        """Load a local model into memory; a 200 response means it is warm."""
        if not config.model:
            return False
        base = config.compatible_base()
        if config.kind == BackendKind.OLLAMA:
            url = _ollama_endpoint(base)
            body: dict = {
                "model": config.model,
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
                "keep_alive": "5m",
                "options": {
                    "temperature": 0.0,
                    "num_predict": 1,
                    "num_ctx": config.context_window,
                },
            }
        else:
            url = _openai_endpoint(base, "chat/completions")
            body = {
                "model": config.model,
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
                "temperature": 0.0,
                "max_tokens": 1,
            }
        try:
            self._validate_url(url, base)
            response = self._session.post(
                url,
                json=body,
                headers=self._headers(config),
                timeout=(_CONNECT_TIMEOUT, _WARM_UP_TIMEOUT),
            )
        except requests.exceptions.RequestException:
            return False
        except TranslationError:
            return False
        try:
            return int(getattr(response, "status_code", 0)) == 200
        finally:
            self._close(response)

    # --------------------------------------------------------------- pipeline

    def _run_job(
        self,
        text: str,
        *,
        source: Language,
        target: Language,
        style: TranslationStyle,
        tone: TranslationTone,
        config: BackendConfig,
        source_explicit: bool,
        one_request: bool,
        on_progress: Callable[[int, int], None] | None,
        on_partial: Callable[[str], None] | None,
        cancel: threading.Event | None,
    ) -> _JobResult:
        normalized = TextChunker.normalize(text)
        lines = normalized.split("\n") if "|" in normalized else []
        table_rows = _markdown_table_rows(lines)
        chunks = TextChunker.split(normalized, keep_whole_lines=table_rows)
        if not chunks:
            return _JobResult(text=text, warnings=0, tokens=0, seconds=0.0)

        explicit_source = source if source_explicit else None
        gemma_source = _gemma_source(text, config.model, explicit_source)
        body = normalized.strip("\n")
        rejected_prompt = None
        if one_request and any(
            not chunk.is_code and any(char.isalpha() for char in chunk.text)
            for chunk in chunks
        ):
            # Keep the dedicated wording and protected prefix for standalone
            # headings and model-ID descriptions.
            if len(chunks) != 1 or not (
                _is_structural_heading(chunks[0].text, chunks[0].is_heading)
                or _split_mixed_line(chunks[0].text) is not None
            ):
                whole, rejected_prompt = self._translate_document(
                    body,
                    target=target,
                    style=style,
                    tone=tone,
                    config=config,
                    source_language=explicit_source,
                    gemma_source=gemma_source,
                    preserve_table=bool(table_rows),
                    on_progress=on_progress,
                    on_partial=on_partial,
                    cancel=cancel,
                )
                if whole is not None:
                    return whole
        total = len(chunks)
        self._report(on_progress, 0, total)
        translated: list[str] = []
        warnings = 0
        translated_count = 0
        tokens = 0
        seconds = 0.0
        stats_complete = True
        line_number = next((index for index, line in enumerate(lines) if line.strip()), 0)

        for index, chunk in enumerate(chunks):
            self._raise_if_cancelled(cancel)
            line_number += chunk.separator_before.count("\n")
            preserve_table = line_number in table_rows
            body = chunk.text
            line = chunk.prefix + body
            has_words = any(char.isalpha() for char in body)
            long_table_row = preserve_table and has_words and len(body) > TextChunker.limit
            if chunk.is_code or long_table_row or not has_words:
                if chunk.is_code:
                    line_number += body.count("\n")
                if long_table_row:
                    warnings += 1
                translated.append(body)
                self._emit_partial(on_partial, TextChunker.compose(chunks[: index + 1], translated))
                self._report(on_progress, index + 1, total)
                continue

            keep = ""
            translatable = body
            mixed = None if preserve_table else _split_mixed_line(body)
            if mixed is not None:
                keep, translatable = mixed

            try:
                block = self._translate_chunk(
                    translatable,
                    target=target,
                    style=style,
                    tone=tone,
                    config=config,
                    source_language=explicit_source if gemma_source is None else None,
                    gemma_source=gemma_source,
                    cancel=cancel,
                    preserve_markdown=preserve_table or _contains_markdown(line),
                    is_heading=chunk.is_heading,
                    preserve_table=preserve_table,
                    rejected_prompt=rejected_prompt,
                )
            except TranslationError as exc:
                if exc.kind != "empty":
                    raise
                # Swift keeps the source line for this block and counts a warning.
                logger.debug("block left untranslated: %s", exc.detail)
                translated.append(keep + translatable)
                warnings += 1
                self._emit_partial(
                    on_partial, TextChunker.compose(chunks[: index + 1], translated)
                )
                self._report(on_progress, index + 1, total)
                continue

            restored = TokenRestorer.restore(translatable, block.text)
            if restored is not None and preserve_table:
                translated_row = chunk.prefix + restored
                if (
                    _table_shape(line) != _table_shape(translated_row)
                    or _INLINE_CODE.findall(line) != _INLINE_CODE.findall(translated_row)
                ):
                    restored = None
            if restored is None:
                logger.debug("protected tokens or table cells changed in model output")
                translated_text = translatable
                warning = True
            else:
                translated_text = TokenRestorer.preserve_trailing_punctuation(
                    translatable, restored
                )
                warning = block.warning
                tokens += block.tokens
                seconds += block.seconds
                stats_complete = stats_complete and block.tokens > 0
            translated.append(keep + translated_text)
            if warning:
                warnings += 1
            else:
                translated_count += 1
            self._emit_partial(on_partial, TextChunker.compose(chunks[: index + 1], translated))
            self._report(on_progress, index + 1, total)

        return _JobResult(
            text=TextChunker.compose(chunks, translated),
            warnings=warnings,
            tokens=tokens if stats_complete else 0,
            seconds=seconds,
            degenerate=warnings > 0 and translated_count == 0,
        )

    def _translate_document(
        self,
        text: str,
        *,
        target: Language,
        style: TranslationStyle,
        tone: TranslationTone,
        config: BackendConfig,
        source_language: Language | None,
        gemma_source: Language | None,
        preserve_table: bool,
        on_progress: Callable[[int, int], None] | None,
        on_partial: Callable[[str], None] | None,
        cancel: threading.Event | None,
    ) -> tuple[_JobResult | None, str | None]:
        """Try the whole text once; the caller can retry in smaller pieces."""
        if gemma_source is not None:
            prompt = PromptBuilder.translate_gemma_prompt(text, gemma_source, target)
        else:
            preserve_markdown = preserve_table or _contains_markdown(text) or any(
                _fence_marker(line) is not None for line in text.split("\n")
            )
            instruction = PromptBuilder.instruction(style, tone, target.english_name, preserve_markdown)
            constraints = ""
            if "\n" in text:
                constraints += " Preserve line breaks and blank lines."
            if preserve_table:
                constraints += " Keep table structure, URLs and code unchanged."
            elif preserve_markdown or "http://" in text or "https://" in text or "](" in text:
                constraints += " Keep URLs and code unchanged."
            if constraints:
                instruction = instruction.removesuffix(":") + "." + constraints
            prompt = _with_source_language(instruction + "\n\n" + text, source_language)

        # Leave space for chat framing and an output that grows in translation.
        estimated_input = (len(prompt.encode("utf-8")) + 3) // 4 + 128
        estimated_output = 2 * ((len(text.encode("utf-8")) + 3) // 4) + 64
        available_output = config.context_window - estimated_input
        if estimated_output > available_output:
            return None, None

        pieces: list[str] = []
        last_preview = 0.0
        preview_sent = False

        def preview(piece: str) -> None:
            nonlocal last_preview, preview_sent
            pieces.append(piece)
            now = time.monotonic()
            if preview_sent and now - last_preview < _DOCUMENT_PREVIEW_INTERVAL:
                return
            visible = self._clean_output(OutputSanitizer.strip_preamble("".join(pieces), text))
            if visible:
                self._emit_partial(on_partial, visible)
                last_preview = now
                preview_sent = True

        self._report(on_progress, 0, 1)
        accepted = False
        try:
            result = self._stream_chat(
                [{"role": "user", "content": prompt}],
                config,
                cancel=cancel,
                on_token=preview if on_partial is not None else None,
                max_bytes=max(200, len(text) * 4 + 100) * 4,
                max_tokens=min(available_output, max(_MAX_OUTPUT_TOKENS, estimated_output)),
                detect_context_limit=True,
            )
            if result.exceeded_limit:
                return None, prompt
            cleaned = self._validate_document(text, result.text, target)
            if cleaned is None:
                return None, prompt
            self._raise_if_cancelled(cancel)
            accepted = True
        except TranslationError as exc:
            if exc.kind == "empty" or exc.status == 413 or (
                exc.kind == "http" and _CONTEXT_LIMIT.search(exc.detail)
            ):
                return None, prompt
            raise
        finally:
            if preview_sent and not accepted:
                self._emit_partial(on_partial, "")
        self._emit_partial(on_partial, cleaned)
        self._report(on_progress, 1, 1)
        return _JobResult(cleaned, 0, result.tokens, result.seconds), None

    def _validate_document(self, source: str, translated: str, target: Language) -> str | None:
        result = TextChunker.normalize(translated).strip("\n")
        source_lines = source.split("\n")
        result_lines = result.split("\n")
        if len(source_lines) != len(result_lines):
            return None

        table_rows = _markdown_table_rows(source_lines) if "|" in source else set()
        fence = None
        restored_lines: list[str] = []
        for index, (before, after) in enumerate(zip(source_lines, result_lines)):
            if fence is not None:
                if before != after:
                    return None
                if _closes_fence(before, fence):
                    fence = None
                restored_lines.append(before)
                continue
            fence = _fence_marker(before)
            if fence is not None or _fence_marker(after) is not None:
                if before != after:
                    return None
                restored_lines.append(before)
                continue

            if _INLINE_CODE.findall(before) != _INLINE_CODE.findall(after):
                return None
            before_prose = _INLINE_CODE.sub("", before)
            if not any(char.isalpha() for char in before_prose):
                if before != after:
                    return None
                restored_lines.append(before)
                continue
            restored = TokenRestorer.restore(before, after)
            if restored is None or _INLINE_CODE.findall(before) != _INLINE_CODE.findall(restored):
                return None
            if index in table_rows and _table_shape(before) != _table_shape(restored):
                return None
            after_prose = _INLINE_CODE.sub("", restored)
            if (
                _markdown_structure(before) != _markdown_structure(restored)
                or _parse_prefix(before)[0] != _parse_prefix(restored)[0]
                or [destination for _, destination in _MARKDOWN_LINK.findall(before_prose)]
                != [destination for _, destination in _MARKDOWN_LINK.findall(after_prose)]
                or any(
                    len(pattern.findall(before_prose)) != len(pattern.findall(after_prose))
                    for pattern in _MARKDOWN_INLINE_FORMATTING
                )
            ):
                return None
            before_prose = _MARKDOWN_LINK.sub(r"\1", before_prose)
            after_prose = _MARKDOWN_LINK.sub(r"\1", after_prose)
            clean = self._validated(after_prose, before_prose, target)
            if clean is None or clean != after_prose.strip():
                return None
            restored_lines.append(restored)
        return "\n".join(restored_lines)

    def _translate_chunk(
        self,
        text: str,
        *,
        target: Language,
        style: TranslationStyle,
        tone: TranslationTone,
        config: BackendConfig,
        source_language: Language | None,
        gemma_source: Language | None,
        cancel: threading.Event | None,
        preserve_markdown: bool,
        is_heading: bool = False,
        preserve_table: bool = False,
        rejected_prompt: str | None = None,
    ) -> _BlockResult:
        """Choose the prompt ladder for one line and translate it."""
        body = text.strip()
        if gemma_source is not None:
            prompts = [PromptBuilder.translate_gemma_prompt(body, gemma_source, target)]
        elif not preserve_table and _is_structural_heading(body, is_heading):
            heading = PromptBuilder.heading_prompt(
                body,
                style,
                tone,
                target.english_name,
                preserve_markdown=False,
            )
            prompts = [heading, PromptBuilder.plain_prompt(body, target.english_name)]
        else:
            plain_fallback = PromptBuilder.plain_prompt(body, target.english_name)
            styled = PromptBuilder.prompt(
                body, style, tone, target.english_name, preserve_markdown
            )
            natural = PromptBuilder.prompt(
                body,
                TranslationStyle.NATURAL,
                tone,
                target.english_name,
                preserve_markdown,
            )
            literal = PromptBuilder.prompt(
                body,
                TranslationStyle.LITERAL,
                TranslationTone.STANDARD,
                target.english_name,
                preserve_markdown,
            )
            if style == TranslationStyle.AUTO:
                prompts = [styled, natural, plain_fallback]
            elif style == TranslationStyle.NATURAL:
                prompts = [styled, plain_fallback, literal]
            else:
                prompts = [styled, natural, plain_fallback]
        if preserve_table and gemma_source is None:
            prompts = [
                prompt.replace(":\n\n", ". Keep table structure unchanged.\n\n", 1)
                for prompt in prompts
            ]
        if rejected_prompt is not None:
            prompts = [
                prompt for prompt in prompts
                if _with_source_language(prompt, source_language) != rejected_prompt
            ]
        return self._buffered_translation(
            prompts,
            body,
            target,
            config,
            cancel,
            source_language=source_language,
            gemma_source=gemma_source,
            preserve_line_breaks=False,
            requires_markdown_structure=False,
        )

    def _buffered_translation(
        self,
        prompts: list[str],
        source: str,
        target: Language,
        config: BackendConfig,
        cancel: threading.Event | None,
        *,
        source_language: Language | None = None,
        gemma_source: Language | None = None,
        preserve_line_breaks: bool = False,
        requires_markdown_structure: bool = False,
    ) -> _BlockResult:
        """Try every prompt (and lowered-temperature retries) until one validates."""
        source_count = len(source)
        max_bytes = max(200, source_count * 4 + 100) * 4
        for prompt_index, prompt in enumerate(prompts):
            attempts = 3 if prompt_index == 0 else 2
            for attempt in range(attempts):
                if attempt > 0:
                    self._sleep(0.120, cancel)
                retry_config = config
                if attempt > 0:
                    retry_config = replace(
                        config, temperature=min(config.temperature, 0.3)
                    )
                raw = self._collect_candidate(
                    _with_source_language(prompt, source_language),
                    retry_config,
                    max_bytes,
                    cancel,
                )
                clean = self._validated(
                    raw.text,
                    source,
                    target,
                    preserve_line_breaks=preserve_line_breaks,
                )
                if clean is None:
                    logger.debug(
                        "rejected model output (prompt %s, attempt %s)",
                        prompt_index,
                        attempt,
                    )
                    continue
                if requires_markdown_structure and (
                    _markdown_structure(clean) != _markdown_structure(source)
                ):
                    logger.debug(
                        "markdown structure changed (prompt %s, attempt %s)",
                        prompt_index,
                        attempt,
                    )
                    continue
                return _BlockResult(clean, False, raw.tokens, raw.seconds)

        if not requires_markdown_structure and not (
            preserve_line_breaks and "\n" in source
        ):
            segmented = self._sentence_fallback(
                source,
                target,
                config,
                cancel,
                source_language=source_language,
                gemma_source=gemma_source,
            )
            if segmented is not None:
                return segmented
        raise TranslationError("empty", detail="model output rejected")

    def _sentence_fallback(
        self,
        source: str,
        target: Language,
        config: BackendConfig,
        cancel: threading.Event | None,
        *,
        source_language: Language | None,
        gemma_source: Language | None,
    ) -> _BlockResult | None:
        """Translate sentence by sentence when the whole block keeps failing."""
        if "http" in source or "](" in source or "`" in source:
            return None
        pieces = TextChunker.split_sentences(source)
        if len(pieces) <= 1:
            return None

        translated: list[str] = []
        failures = 0
        tokens = 0
        seconds = 0.0
        stats_complete = True
        for piece in pieces:
            self._raise_if_cancelled(cancel)
            if gemma_source is not None:
                prompts = [PromptBuilder.translate_gemma_prompt(piece, gemma_source, target)]
            else:
                prompts = [
                    PromptBuilder.plain_prompt(piece, target.english_name),
                    PromptBuilder.prompt(
                        piece,
                        TranslationStyle.NATURAL,
                        TranslationTone.STANDARD,
                        target.english_name,
                    ),
                    PromptBuilder.prompt(
                        piece,
                        TranslationStyle.LITERAL,
                        TranslationTone.STANDARD,
                        target.english_name,
                    ),
                ]
            success: str | None = None
            for prompt in prompts:
                retry_config = replace(
                    config, temperature=min(config.temperature, 0.3)
                )
                max_bytes = max(200, len(piece) * 4 + 100) * 4
                raw = self._collect_candidate(
                    _with_source_language(prompt, source_language),
                    retry_config,
                    max_bytes,
                    cancel,
                )
                clean = self._validated(raw.text, piece, target)
                if clean is not None:
                    success = clean
                    tokens += raw.tokens
                    seconds += raw.seconds
                    stats_complete = stats_complete and raw.tokens > 0
                    break
            if success is None:
                translated.append(piece)
                failures += 1
            else:
                translated.append(success)

        if failures >= len(pieces):
            return None
        return _BlockResult(
            " ".join(translated), failures > 0, tokens if stats_complete else 0, seconds
        )

    # -------------------------------------------------------------- streaming

    def _collect_candidate(
        self,
        prompt: str,
        config: BackendConfig,
        max_bytes: int,
        cancel: threading.Event | None,
    ) -> _ChatResult:
        """One streamed candidate; a length-cut response becomes empty text."""
        try:
            return self._collect_with_retry(prompt, config, max_bytes, cancel)
        except TranslationError as exc:
            if exc.kind == "empty":
                logger.debug("candidate rejected by the provider: %s", exc.detail)
                return _ChatResult("", None, 0, 0.0)
            raise

    def _collect_with_retry(
        self,
        prompt: str,
        config: BackendConfig,
        max_bytes: int,
        cancel: threading.Event | None,
    ) -> _ChatResult:
        result = self._stream_chat(
            [{"role": "user", "content": prompt}],
            config,
            cancel=cancel,
            on_token=None,
            max_bytes=max_bytes,
        )
        if result.exceeded_limit:
            raise TranslationError("empty", detail="output limit")
        return result

    def _stream_chat(
        self,
        messages: list[dict],
        config: BackendConfig,
        *,
        cancel: threading.Event | None,
        on_token: Callable[[str], None] | None,
        max_bytes: int,
        max_tokens: int = _MAX_OUTPUT_TOKENS,
        detect_context_limit: bool = False,
    ) -> _ChatResult:
        if not config.model:
            raise TranslationError("model", detail="")
        if config.requires_api_key and not config.api_key:
            raise TranslationError("unauthorized", detail="api_key")
        self._raise_if_cancelled(cancel)

        base = config.compatible_base()
        if config.kind == BackendKind.OLLAMA:
            url = _ollama_endpoint(base)
            body = self._ollama_body(messages, config, max_tokens)
            protocol = "ollama"
        else:
            url = _openai_endpoint(base, "chat/completions")
            body = self._openai_body(messages, config, max_tokens)
            protocol = "openai"
        self._validate_url(url, base)
        stream_options = body.get("stream_options")
        wait_for_usage = (
            isinstance(stream_options, dict) and stream_options.get("include_usage") is True
        )

        response = self._post(url, body, config, base)
        done = threading.Event()
        budget = _OutputBudget(max_bytes)
        finished = False
        server_stats: tuple[int, float] | None = None

        def emit(piece: str) -> bool:
            if finished:
                return True
            keep_going = budget.append(piece)
            if keep_going and on_token is not None:
                on_token(piece)
            return keep_going

        try:
            if cancel is not None:
                threading.Thread(
                    target=_watch_cancel,
                    args=(cancel, response, done),
                    daemon=True,
                ).start()
            self._check_status(response, config, detect_context_limit=detect_context_limit)

            for line in self._decoded_lines(response, cancel):
                if cancel is not None and cancel.is_set():
                    raise TranslationCancelled()
                if not line.strip():
                    continue
                if protocol == "ollama":
                    terminal, stats = self._consume_ollama(line, emit)
                else:
                    phase, stats = self._consume_openai(line, emit)
                    # Only servers asked for usage are expected to send a trailer.
                    finished = finished or phase == "stop"
                    terminal = phase == "done" or (
                        finished
                        and (
                            not wait_for_usage
                            or phase == "usage"
                            or stats is not None
                            or server_stats is not None
                        )
                    )
                if stats is not None:
                    server_stats = stats
                if terminal:
                    finished = True
                    break

            if cancel is not None and cancel.is_set():
                raise TranslationCancelled()
            if not finished:
                raise TranslationError(
                    "interrupted", detail="stream ended without a terminal event"
                )
        finally:
            done.set()
            self._close(response)

        total_tokens, generation_seconds = server_stats or (0, 0.0)
        return _ChatResult(
            text=budget.text,
            tokens_per_second=self._rate(total_tokens, generation_seconds),
            tokens=total_tokens,
            seconds=generation_seconds,
            exceeded_limit=budget.exceeded_limit,
        )

    def _consume_ollama(
        self, line: str, emit: Callable[[str], bool]
    ) -> tuple[bool, tuple[int, float] | None]:
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            return False, None
        if not isinstance(obj, dict):
            return False, None
        error = obj.get("error")
        if isinstance(error, str) and error:
            raise TranslationError("http", detail=error)
        message = obj.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content and not emit(content):
                return True, None
        if obj.get("done") is True:
            if obj.get("done_reason") == "length":
                raise TranslationError("empty", detail="length")
            return True, _generation_stats(
                obj.get("eval_count"), obj.get("eval_duration"), 1_000_000_000
            )
        return False, None

    def _consume_openai(
        self, line: str, emit: Callable[[str], bool]
    ) -> tuple[Literal["more", "stop", "usage", "done"], tuple[int, float] | None]:
        stripped = line.strip()
        if not stripped.startswith("data:"):
            return "more", None
        payload = stripped[5:].strip()
        if payload == "[DONE]":
            return "done", None
        if not payload:
            return "more", None
        try:
            obj = json.loads(payload)
        except (ValueError, TypeError):
            return "more", None
        if not isinstance(obj, dict):
            return "more", None

        error = obj.get("error")
        if isinstance(error, dict):
            message = error.get("message") or json.dumps(error)
            raise TranslationError("http", detail=str(message))
        if isinstance(error, str) and error:
            raise TranslationError("http", detail=error)

        stats = _openai_stats(obj)
        usage = obj.get("usage")
        has_usage = isinstance(usage, dict) and bool(usage)
        choices = obj.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                delta = first.get("delta")
                if not isinstance(delta, dict):
                    delta = first.get("message")
                if isinstance(delta, dict):
                    content = delta.get("content")
                    if isinstance(content, str) and content and not emit(content):
                        return "done", stats
                reason = first.get("finish_reason")
                if isinstance(reason, str) and reason:
                    if reason == "length":
                        raise TranslationError("empty", detail="length")
                    if reason in ("stop", "end_turn"):
                        return ("done" if has_usage else "stop"), stats
                    raise TranslationError("interrupted", detail=reason)
        if has_usage and not choices:
            return "usage", stats
        return "more", stats

    # ---------------------------------------------------------------- helpers

    def _ollama_body(self, messages: list[dict], config: BackendConfig, max_tokens: int) -> dict:
        return {
            "model": config.model,
            "messages": messages,
            "stream": True,
            "keep_alive": "5m",
            "options": {
                "temperature": config.temperature,
                "top_p": config.top_p,
                "top_k": config.top_k,
                "repeat_penalty": config.repetition_penalty,
                "num_ctx": config.context_window,
                "num_predict": max_tokens,
                "stop": list(_STOP_SEQUENCES),
            },
        }

    def _openai_body(self, messages: list[dict], config: BackendConfig, max_tokens: int) -> dict:
        body: dict[str, object] = {
            "model": config.model,
            "messages": messages,
            "stream": True,
            "temperature": config.temperature,
            "top_p": config.top_p,
            "max_tokens": max_tokens,
            "stop": list(_STOP_SEQUENCES),
        }
        endpoint = urlsplit(config.compatible_base())
        if endpoint.scheme == "https" and endpoint.hostname in _STREAM_USAGE_HOSTS:
            body["stream_options"] = {"include_usage": True}
        return body

    def _headers(self, config: BackendConfig) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        return headers

    def _post(
        self,
        url: str,
        body: dict,
        config: BackendConfig,
        base: str,
    ) -> requests.Response:
        try:
            return self._session.post(
                url,
                json=body,
                headers=self._headers(config),
                stream=True,
                timeout=(_CONNECT_TIMEOUT, self._timeout),
            )
        except (
            requests.exceptions.InvalidURL,
            requests.exceptions.MissingSchema,
            requests.exceptions.InvalidSchema,
        ) as exc:
            raise TranslationError("invalid_url", detail=base) from exc
        except requests.exceptions.RequestException as exc:
            raise TranslationError("connection", detail=base) from exc

    def _decoded_lines(
        self, response: object, cancel: threading.Event | None
    ) -> Iterator[str]:
        try:
            for raw in response.iter_lines():  # type: ignore[attr-defined]
                if cancel is not None and cancel.is_set():
                    raise TranslationCancelled()
                if isinstance(raw, bytes):
                    yield raw.decode("utf-8", errors="replace")
                else:
                    yield str(raw)
        except TranslationCancelled:
            raise
        except Exception as exc:
            if cancel is not None and cancel.is_set():
                raise TranslationCancelled() from None
            raise TranslationError("interrupted", detail=str(exc) or type(exc).__name__) from exc

    def _check_status(
        self,
        response: requests.Response,
        config: BackendConfig,
        *,
        detect_context_limit: bool = False,
    ) -> None:
        status = int(getattr(response, "status_code", 0))
        if 200 <= status < 300:
            return
        detail = ""
        headers = getattr(response, "headers", None)
        if status == 429 and isinstance(headers, dict):
            detail = str(headers.get("Retry-After", "") or "")
        elif status == 404:
            detail = config.model
        elif detect_context_limit and status in (400, 422):
            try:
                payload = next(response.iter_content(chunk_size=4096), b"")
            except requests.exceptions.RequestException:
                pass  # Keep the original HTTP error if its body cannot be read.
            else:
                if _CONTEXT_LIMIT.search(payload.decode("utf-8", errors="replace")):
                    detail = "context limit"
        raise _http_error(status, detail)

    def _validate_url(self, url: str, base: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise TranslationError("invalid_url", detail=base)

    def _clean_output(self, raw: str) -> str:
        cleaner = getattr(OutputSanitizer, "clean", None)
        if callable(cleaner):
            return cleaner(raw)
        return OutputSanitizer.strip_wrappers(raw)

    def _validated(
        self,
        raw: str,
        source: str,
        target: Language,
        *,
        preserve_line_breaks: bool = False,
    ) -> str | None:
        # Swift validates the collected text before OutputSanitizer.clean:
        # the U+FFFD guard must see the raw stream (strip_wrappers would remove
        # the replacement character together with the token around it).
        if "\ufffd" in raw:
            return None
        candidate = OutputSanitizer.strip_preamble(raw, source)
        cleaned = self._clean_output(candidate)
        if not preserve_line_breaks:
            cleaned = re.sub(r"\s*\n\s*", " ", cleaned)
        cleaned = cleaned.strip()
        if not cleaned:
            return None
        failed, reason = OutputSanitizer.is_degenerate(source, cleaned, target)
        if failed:
            logger.debug("sanitizer rejected output: %s", reason)
            return None
        return cleaned

    def _report(
        self,
        callback: Callable[[int, int], None] | None,
        completed: int,
        total: int,
    ) -> None:
        if callback is not None:
            try:
                callback(completed, total)
            except Exception:  # pragma: no cover - UI callbacks must not kill a job
                logger.exception("progress callback failed")

    def _emit_partial(
        self,
        callback: Callable[[str], None] | None,
        text: str,
    ) -> None:
        if callback is not None:
            try:
                callback(text)
            except Exception:  # pragma: no cover - UI callbacks must not kill a job
                logger.exception("partial callback failed")

    def _raise_if_cancelled(self, cancel: threading.Event | None) -> None:
        if cancel is not None and cancel.is_set():
            raise TranslationCancelled()

    def _sleep(self, seconds: float, cancel: threading.Event | None) -> None:
        if cancel is None:
            time.sleep(seconds)
            return
        if cancel.wait(seconds):
            raise TranslationCancelled()

    @staticmethod
    def _rate(tokens: int, seconds: float) -> float | None:
        if tokens > 0 and seconds > 0:
            return tokens / seconds
        return None

    @staticmethod
    def _close(response: object) -> None:
        try:
            response.close()  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - defensive
            pass
