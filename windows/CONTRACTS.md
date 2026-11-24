# DeepL-oFM for Windows — module contracts

This document is the **single source of truth** for module boundaries while several
agents work in parallel. Every implementation must match the signatures below
exactly; if a signature is impossible or clearly wrong, keep the documented one
and report the deviation at the end of your task instead of changing it silently.

The macOS original lives in the repository root (`Sources/HyMT/`). Read it for
behavioural details — this port must feel identical. Python files live under
`windows/deepl_ofm/`.

## 0. Ground rules

- Python **3.10+**, `from __future__ import annotations` at the top of every module.
- Public API uses type hints. Internal helpers may be prefixed with `_`.
- Never modify the macOS Swift sources, the root `README.md`, or other agents'
  files. Only your own files + your own tests.
- No new third-party dependency without a note in your final report. Allowed
  libraries are listed in `requirements.txt`.
- No network at import time, no `QApplication` at import time, no side effects in
  module import. UI modules must be importable in a headless environment
  (`QT_QPA_PLATFORM=offscreen`).
- UI strings: always `from deepl_ofm.i18n import t` then `t("English source string")`.
  The English string **is** the translation key — copy it verbatim from the Swift
  source so the existing 9-language catalogue applies.
- Tests: `pytest`, placed in `windows/tests/`, run with
  `cd windows && .venv/bin/python -m pytest tests -q`.
- Style: 4 spaces, max line 100, no wildcard imports.

## 1. Layout and ownership

```
windows/
  deepl_ofm/
    core/languages.py      Language, AppLanguage, LanguageTable.detect
    core/prompts.py        TranslationStyle, TranslationTone, PromptBuilder
    core/providers.py      BackendKind, Provider, BackendConfig
    core/keycombo.py       KeyCombo (parse / format / JSON)
    core/chunker.py        TextChunk, TextChunker
    core/tokens.py         TokenRestorer
    core/sanitizer.py      OutputSanitizer + block validation helpers
    core/catalog.py        CatalogEntry, ModelCatalog
    core/settings.py       AppSettings
    services/translation.py TranslationError, TranslationCancelled,
                            TranslationOutput, Translator
    services/probe.py      probe_models(), model_listed()
    services/documents.py  DocumentKind, DocumentError, OpenedDocument,
                           DocumentTranslator
    services/history.py    HistoryEntry, HistoryStore
    services/secrets.py    SecretStore
    services/hotkeys.py    HotkeyManager, HotkeyError
    services/speech.py     Speaker
    i18n/__init__.py       L10n: t(), set_language(), current_language()
    i18n/catalog.py        generated dictionaries
    ui/theme.py            design tokens
    ui/icons.py            icons.icon()
    ui/components.py       shared widgets
    ui/markdown_view.py    Markdown rendering widget + md->html / md->rtf
    ui/translate_view.py   Translate tab
    ui/files_view.py       Files tab
    ui/write_view.py       Write tab
    ui/history_view.py     History tab
    ui/settings_view.py    Settings dialog
    ui/catalog_view.py     Model catalog dialog
    ui/main_window.py      window shell, tabs, menu
    ui/tray.py             system tray
    controller.py          AppController (QObject) — application state
    app.py                 entry point
    __main__.py            `python -m deepl_ofm`
```

## 2. `core/languages.py`

```python
class AppLanguage(str, Enum):
    SYSTEM = "system"; EN = "en"; UK = "uk"; RU = "ru"; DE = "de"
    FR = "fr"; ES = "es"; PL = "pl"; PT = "pt"; IT = "it"
    # .resolved -> AppLanguage (system -> detected OS language, default EN)
    # .picker_title -> str  ("System" localised / "English" / "Українська" ...)
    # .locale_identifier -> str ("uk_UA")
    @staticmethod
    def system_resolved() -> AppLanguage

@dataclass(frozen=True, slots=True)
class Language:
    code: str
    english_name: str
    local_name: str
    bcp47: str | None = None
    # .display_name(app_language: AppLanguage | str | None = None) -> str
    #    auto -> t("Auto-detect"); otherwise the language name in that locale
    @property
    def is_auto(self) -> bool

class LanguageTable:  # or module helpers; both listed below are required
    AUTO: Language
    ALL: list[Language]                 # 38 entries, order of the Swift file
    @staticmethod
    def get(code: str) -> Language | None
    @staticmethod
    def detect(text: str, preferred: AppLanguage | str = AppLanguage.SYSTEM) -> Language | None
```

Module-level shortcuts are required too:
`AUTO = LanguageTable.AUTO`, `ALL = LanguageTable.ALL`, `get_language(code)`,
`detect_language(text, preferred)`.

`detect` mirrors `Language.detect` in Swift: script ranges first (ja, ko, th, he,
ar, hi, bn, ta, te, gu, zh, Cyrillic uk/ru scoring with the word lists, then
Latin → `en`). The macOS `NLLanguageRecognizer` part is not available: implement
a small heuristic (stop-word scoring for en/fr/de/es/pt/it/pl/nl/tr/vi/id/ms) and
fall back to `en` when Latin text is present.

## 3. `core/prompts.py`

```python
class TranslationStyle(str, Enum): AUTO = "auto"; LITERAL = "literal"; NATURAL = "natural"
class TranslationTone(str, Enum): STANDARD = "standard"; FORMAL = "formal"; CASUAL = "casual"
# both have .title and .detail (English text, localised by the UI via t())

class PromptBuilder:
    @staticmethod
    def instruction(style, tone, target_language: str, preserve_markdown: bool = False) -> str
    @staticmethod
    def prompt(text, style, tone, target_language, preserve_markdown: bool = False) -> str
    @staticmethod
    def heading_instruction(style, tone, target_language, preserve_markdown: bool = False) -> str
    @staticmethod
    def heading_prompt(text, style, tone, target_language, preserve_markdown: bool = False) -> str
    @staticmethod
    def plain_instruction(target_language: str) -> str
    @staticmethod
    def plain_prompt(text, target_language: str) -> str
    @staticmethod
    def preview(style, tone, target_language, sample: str = "Hello, world!") -> str
```

Text must be byte-identical to `Sources/HyMT/Models/Prompt.swift`, including the
`markdownClause`. Covered by `tests/test_prompts.py` (port the Swift tests).

## 4. `core/providers.py`

```python
class BackendKind(str, Enum): OLLAMA = "ollama"; OPENAI = "openAI"

class Provider(str, Enum):
    OLLAMA="ollama"; OLLAMA_CLOUD="ollamaCloud"; LM_STUDIO="lmStudio"; OMLX="omlx"
    LLAMA_CPP="llamaCpp"; OPEN_ROUTER="openRouter"; GROQ="groq"; CEREBRAS="cerebras"; CUSTOM="custom"
    # .title .base_url .kind -> BackendKind .is_local .requires_key .key_url
    # .key_account -> "provider:<value>"   .detail_key -> English sentence
    # .detail(app_language=None) -> str   (t(detail_key))
    @staticmethod
    def infer(backend: BackendKind, base_url: str) -> Provider
    @classmethod
    def from_stored(cls, value: str) -> Provider | None   # tolerant lookup

@dataclass
class BackendConfig:
    kind: BackendKind
    base_url: str
    model: str
    api_key: str = ""
    temperature: float = 0.7
    top_p: float = 0.6
    top_k: int = 20
    repetition_penalty: float = 1.05
    context_window: int = 8192
    requires_api_key: bool = False
    # .compatible_base() -> str  (strip trailing "/", empty -> kind default)
```

## 5. `core/keycombo.py`

```python
@dataclass(frozen=True)
class KeyCombo:
    key: str                 # lower-case character or named key: "t", "f5", "space"
    command: bool = False    # Ctrl on Windows (kept as `command` for parity)
    option: bool = False     # Alt
    control: bool = False
    shift: bool = False
    @property
    def display(self) -> str          # "Ctrl+Alt+T" on Windows
    @property
    def qt_sequence(self) -> str      # "Ctrl+Alt+T" accepted by QKeySequence
    @property
    def is_valid(self) -> bool        # at least one of ctrl/alt/shift... see Swift
    def matches(self, event) -> bool  # QKeyEvent -> bool (optional helper)
    @staticmethod
    def standard() -> KeyCombo        # Ctrl+Alt+T
    @staticmethod
    def selection() -> KeyCombo       # Ctrl+Alt+C
    def to_dict(self) -> dict; @classmethod from_dict(cls, data) -> KeyCombo
```

Swift requires at least one of ⌘/⌥/⌃; on Windows map ⌘→Ctrl, ⌥→Alt: require at
least one of Ctrl/Alt/Shift? Keep the original rule: **at least one of ctrl or
alt** must be set, otherwise `is_valid` is False.

## 6. `core/chunker.py`

```python
@dataclass
class TextChunk:
    prefix: str          # markdown marker ("## ", "- ", "1. ", "> ", "- [ ] ")
    text: str            # text to translate (without the prefix)
    is_heading: bool
    index: int           # position in the returned list

class TextChunker:
    @staticmethod
    def normalize(text: str) -> str                       # CRLF/CR -> LF
    @staticmethod
    def split(text: str) -> list[TextChunk]               # one chunk per non-empty line
    @staticmethod
    def compose(chunks: list[TextChunk], translated: list[str], leading_blank_line: bool = False) -> str
    @staticmethod
    def split_sentences(text: str) -> list[str]           # long-block fallback
```

Port `Sources/HyMT/Services/TranslationService.swift` lines ~63–167 plus
`TextChunkerTests.swift`. The output of `compose` must reproduce the source
layout exactly (blank lines preserved, prefixes re-attached, trailing newline
semantics).

## 7. `core/tokens.py`

```python
class TokenRestorer:
    @staticmethod
    def restore(source: str, translated: str) -> str | None   # None => token count lost
    @staticmethod
    def preserve_trailing_punctuation(source: str, translated: str) -> str
```

Port `Sources/HyMT/Support/TokenRestorer.swift` including the regex (Python `re`
supports the same constructs; `(?<![A-Za-z0-9._-])` works, no variable-width
lookbehind is used), hyphen normalisation and the trailing-punctuation loop.

## 8. `core/sanitizer.py`

```python
class OutputSanitizer:
    @staticmethod
    def strip_wrappers(text: str) -> str
    @staticmethod
    def has_role_tokens(text: str) -> bool
    @staticmethod
    def is_degenerate(source: str, translated: str, target: Language) -> tuple[bool, str]
        # returns (failed, reason) — reason: "empty" | "repetition" | "script" |
        # "role_tokens" | "echo" | "length"
    @staticmethod
    def script_ok(text: str, target: Language) -> bool
```

Port `Sources/HyMT/Support/OutputSanitizer.swift` and the validation helpers from
`TranslationService.swift` (`translateBlock`) — read both files.

## 9. `core/catalog.py`

```python
@dataclass(frozen=True)
class CatalogEntry:
    name: str; model_id: str; provider: Provider; size: str; languages: str
    note: str; install_command: str

class ModelCatalog:
    ENTRIES: list[CatalogEntry]
    @staticmethod
    def install_command(for_model: str) -> str | None
```

Port `Sources/HyMT/Models/ModelCatalog.swift`.

## 10. `core/settings.py`

```python
class AppSettings:
    """JSON-backed settings (QSettings-independent, usable from tests)."""

    def __init__(self, path: Path | None = None, secrets: SecretStore | None = None)
    # every Swift @Published property becomes a plain attribute, same snake_case:
    # provider: Provider, base_url: str, model: str, api_key: str,
    # fallback_enabled: bool, fallback_provider: Provider, fallback_api_key: str,
    # fallback_base_url: str, fallback_model: str,
    # temperature: float, top_p: float, top_k: int, repetition_penalty: float,
    # context_window: int, auto_translate: bool, debounce: float,
    # hot_key: KeyCombo, selection_hot_key: KeyCombo,
    # show_in_menu_bar: bool, show_in_dock: bool, speech_voice_id: str,
    # keep_history: bool, warm_up_on_launch: bool,
    # interface_language: AppLanguage, result_view: str ("preview"|"text"|"markdown"),
    # last_style: TranslationStyle, last_tone: TranslationTone,
    # last_target_code: str, last_source_code: str
    def save(self) -> None
    def snapshot(self) -> BackendConfig
    def fallback_config(self) -> BackendConfig | None
    def fallback_probe_config(self) -> BackendConfig
    def apply_provider(self, provider: Provider, model: str | None = None) -> None
    def apply_catalog_entry(self, entry: CatalogEntry) -> None
    def clear_key(self) -> None
    def install_command(self) -> str | None
    @staticmethod
    def default_path() -> Path
```

Behaviour to copy from `Sources/HyMT/Models/AppSettings.swift`: per-provider
remembered `base_url`/`model`, API keys read/written through `SecretStore`,
defaults (0.7 / 0.6 / 20 / 1.05 / 8192, auto_translate True, debounce 0.45,
keep_history True, warm_up False, last_target "en", last_source "auto",
result_view "preview"), and the "never lose the only entry point" rule for
`show_in_menu_bar` / `show_in_dock` (tray / window).

Persistence: JSON in `%APPDATA%\DeepL-oFM\settings.json`
(`Path(os.environ.get("APPDATA", Path.home()/".config")) / "DeepL-oFM"`), atomic
write (temp file + `os.replace`), tolerant loading (unknown keys ignored, bad
values fall back to defaults).

## 11. `i18n/__init__.py`

```python
def t(key: str, language: AppLanguage | str | None = None) -> str
def set_language(language: AppLanguage | str) -> None
def current_language() -> AppLanguage
def available_languages() -> list[AppLanguage]
def install_translator(app_language: AppLanguage | str) -> None  # alias of set_language
```

`%d`/`%s`/`%@` placeholders from the Swift catalogue must be converted to
`{}`-style and exposed through a helper:

```python
def tf(key: str, *args, language=None) -> str   # t(key).format(*args)
```

`i18n/catalog.py` holds nine dictionaries (`en` is implicit: key == value).
Generate them **mechanically** from `Sources/HyMT/Support/Localization.swift`
(Ukraine/Russian/German/French/Spanish/Polish/Portuguese/Italian dictionaries).
Add `tests/test_i18n.py` asserting: every non-English dict has ≥ 90 % of the
English keys, no key is empty, and a few spot checks
(`t("Settings","uk") == "Налаштування"` — verify against the Swift file).

## 12. `services/translation.py`

```python
class TranslationError(Exception):
    kind: str          # "connection" | "invalid_url" | "http" | "unauthorized" |
                       # "rate_limit" | "server" | "model" | "interrupted" |
                       # "unexpected" | "empty" | "cancelled"
    status: int | None
    detail: str
    def message(self, language: AppLanguage | str | None = None) -> str

class TranslationCancelled(Exception): ...

@dataclass
class TranslationOutput:
    text: str
    warnings: int = 0            # lines left untranslated
    tokens_per_second: float | None = None
    duration_ms: int | None = None
    used_fallback: bool = False

class Translator:
    def __init__(self, session: requests.Session | None = None, timeout: float = 180.0)
    def translate(self, text: str, *, source: Language, target: Language,
                  style: TranslationStyle, tone: TranslationTone,
                  config: BackendConfig, fallback: BackendConfig | None = None,
                  on_progress: Callable[[int, int], None] | None = None,
                  on_partial: Callable[[str], None] | None = None,
                  cancel: threading.Event | None = None) -> TranslationOutput
    def rewrite(self, text: str, *, target: Language, config: BackendConfig,
                fallback: BackendConfig | None = None,
                on_progress=None, on_partial=None, cancel=None) -> TranslationOutput
    def stream_chat(self, messages: list[dict], config: BackendConfig, *, cancel=None,
                    on_token: Callable[[str], None] | None = None,
                    max_bytes: int = 1_000_000) -> tuple[str, float | None]
    def list_models(self, config: BackendConfig) -> list[str]
    def warm_up(self, config: BackendConfig) -> bool
```

Wire protocol, exactly like the Swift implementation:

- `BackendKind.OLLAMA` → `POST {base}/api/chat`, body
  `{"model", "messages", "stream": true, "options": {"temperature","top_p","top_k","repeat_penalty","num_ctx","num_predict"?}}`,
  response is NDJSON: `{"message": {"content": ...}, "done": bool}`.
- `BackendKind.OPENAI` → `POST {base}/chat/completions` (append `/v1` only when the
  base has no path part — reuse the Swift rule: if base ends with "/v1" use as is,
  else `{base}/v1/chat/completions`), body
  `{"model", "messages", "stream": true, "temperature", "top_p"}`,
  SSE lines `data: {...}` with `choices[0].delta.content`, terminated by
  `data: [DONE]`.
- `Authorization: Bearer <key>` when the key is non-empty.
- Timeouts: connect 10 s, read `timeout`. HTTP 401/403 → `unauthorized`,
  429 → `rate_limit`, ≥500 → `server`, other non-2xx → `http` with status.
- Streaming accumulates through the `TranslationOutput` byte limiter (port the
  struct at the end of `TranslationService.swift`: marker scan for
  `hy-assistant`, `hy-user`, `hy_end`, `<｜`, `<|`, `</|`, `｜hy` with the
  overlap window and the byte cap) — implement it as a private `_OutputBudget`
  class inside `translation.py`.
- Per-block pipeline: `TextChunker.split` → translate each block (short blocks
  get a different instruction) → validate with `OutputSanitizer` → retry with a
  lower temperature and the plain prompt → sentence-by-sentence fallback for a
  long failing block → count warnings. Progress callback after each block.
- `cancel` (`threading.Event`) aborts within ~100 ms: close the response and
  raise `TranslationCancelled`.
- Fallback config is used when the primary request fails with a non-cancellation
  error; the output then has `used_fallback=True`.

Tests: `tests/test_translation.py` with a fake `requests.Session` (no sockets)
covering streaming assembly, marker truncation, retry on empty output, fallback,
cancellation, and error mapping.

## 13. `services/probe.py`

```python
def probe_models(config: BackendConfig, *, timeout: float = 8.0,
                 session=None) -> list[str]
def model_listed(name: str, models: list[str]) -> bool
```

Port `Sources/HyMT/Services/Probe.swift` (`/api/tags` for Ollama, `/v1/models`
otherwise) and raise `TranslationError` on failure.

## 14. `services/documents.py`

```python
class DocumentKind(str, Enum):
    TEXT="txt"; MARKDOWN="md"; PDF="pdf"; DOCX="docx"
    @staticmethod
    def from_path(path: Path) -> DocumentKind | None
    @property
    def pattern(self) -> str   # "*.txt" etc. used by the file dialog

class DocumentError(Exception):
    kind: str   # "unsupported" | "no_text" | "unreadable" | "write_failed" | "encrypted"
    def message(self, language=None) -> str

@dataclass
class OpenedDocument:
    path: Path
    kind: DocumentKind
    source_text: str | None            # txt/md
    paragraphs: list[str]              # pdf/docx units
    payload: object | None             # parsed layout / zip / xml

class DocumentTranslator:
    @staticmethod
    def read(path: Path) -> OpenedDocument
    @staticmethod
    def suggested_path(path: Path, target: Language) -> Path      # report.pdf -> report_uk.pdf
    @staticmethod
    def write(doc: OpenedDocument, out_path: Path,
              translate: Callable[[str], str],
              on_progress: Callable[[int, int], None] | None = None,
              cancel: threading.Event | None = None) -> Path
```

Port `Sources/HyMT/Services/DocumentTranslator.swift`:

- TXT/MD: translate paragraph by paragraph, keep blank lines; Markdown fenced
  code blocks pass through untouched.
- DOCX: keep the original package, rewrite only `word/document.xml` text nodes
  (`<w:t>` runs) paragraph by paragraph through `translate`; preserve styles,
  tables, images. Use `zipfile` + `xml.etree.ElementTree` with the `w:` namespace.
- PDF: read text blocks with `pdfplumber` (`page.extract_words(extra_attrs=...)`
  then group by line/block), translate block by block, then draw the translated
  text over the original blocks with `reportlab` (a transparent overlay PDF) and
  merge with `pypdf`. Keep the original text layer (do **not** redact). Choose a
  font that covers the target script (`STSong-Light` for zh, `HeiseiMin-W3` for
  ja, `HYSMyeongJo-Medium` for ko via `reportlab.pdfbase.cidfonts`, Helvetica
  otherwise). Shrink the font until the text fits the block height, wrap by
  width, clip with the block bbox.

Tests: build a tiny DOCX/TXT/MD/PDF fixture in `tests/` (create them on the fly
with `zipfile`/`reportlab`) and assert that the output keeps the structure and
that no exception leaks.

## 15. `services/history.py`

```python
@dataclass
class HistoryEntry:
    id: str; date: str (ISO-8601); source_text: str; translated_text: str
    source_code: str; target_code: str; style: str; tone: str
    engine: str; duration_ms: int
    def to_dict/from_dict

class HistoryStore:            # thread-safe, JSON at %APPDATA%\DeepL-oFM\history.json
    ENTRIES = 400
    def __init__(self, path: Path | None = None)
    entries: list[HistoryEntry]  # newest first
    def load(self) -> None
    def add(self, entry: HistoryEntry) -> None     # skips empty / identical head
    def remove(self, entry_id: str) -> None
    def clear(self) -> None
    has_storage_error: bool
    def search(self, query: str) -> list[HistoryEntry]
```

Atomic writes, tolerant parsing, never raise on corrupt JSON (set
`has_storage_error`).

## 16. `services/secrets.py`

```python
class SecretStore:
    """API keys: Windows Credential Manager via `keyring`, else DPAPI-encrypted file."""
    SERVICE = "ua.admin.hymt"
    def __init__(self, path: Path | None = None)
    def read(self, account: str) -> str
    def write(self, account: str, value: str) -> None
    def delete(self, account: str) -> None
    def backend_name(self) -> str   # "keyring" | "dpapi" | "plain"
```

On Windows without `keyring`, use `ctypes` + `CryptProtectData`/`CryptUnprotectData`
(user scope) writing `%APPDATA%\DeepL-oFM\secrets.dat`. On other platforms fall
back to a `0600` JSON file and `backend_name() == "plain"`. Never raise from
`read`/`write`; degrade to empty string.

## 17. `services/hotkeys.py`

```python
class HotkeyError(Exception):
    def message(self, language=None) -> str

class HotkeyManager(QObject):
    triggered = Signal(str)              # "translate" | "selection"
    error = Signal(str)
    def __init__(self, parent=None)
    def register(self, action: str, combo: KeyCombo) -> bool
    def unregister(self, action: str) -> None
    def unregister_all(self) -> None
    def is_supported(self) -> bool
```

Windows: `RegisterHotKey` through `ctypes` + a dedicated `QThread` running
`GetMessageW`, emitting through Qt signals (queued). Non-Windows: `is_supported()`
returns False, `register` returns False and emits `error("...")`. Use
`MOD_NOREPEAT`, map `MOD_CONTROL/MOD_ALT/MOD_SHIFT/MOD_WIN`.

## 18. `services/speech.py`

```python
class Speaker(QObject):
    started = Signal(str)     # target: "source" | "translation"
    finished = Signal(str)
    def __init__(self, parent=None)
    def voices(self) -> list[tuple[str, str]]   # (id, label)
    def speak(self, text: str, voice_id: str = "", target: str = "translation") -> None
    def stop(self) -> None
    def is_speaking(self) -> bool
    def is_available(self) -> bool
```

Use `PySide6.QtTextToSpeech.QTextToSpeech` when available; otherwise a no-op with
`is_available() == False`. Must not crash when no engine is installed.

## 19. UI contract

### `ui/theme.py`

```python
@dataclass(frozen=True)
class Palette:
    bg, panel, card, card_hover, border, text, muted, faint, accent, accent_hover,
    accent_soft, danger, success, warning, selection: str      # hex strings

class Theme:
    @staticmethod
    def palette(dark: bool | None = None) -> Palette      # None -> follow system
    @staticmethod
    def apply(app: QApplication, dark: bool | None = None) -> None   # global stylesheet
    @staticmethod
    def is_dark() -> bool
    @staticmethod
    def set_dark(dark: bool | None) -> None
    radius: int = 10; radius_small: int = 8; spacing: int = 12
    font_family() -> str      # "Segoe UI Variable", "Segoe UI", fallback
    mono_family() -> str      # "Cascadia Mono", "Consolas"
```

Visual language: DeepL-like calm surfaces, one blue accent (`#2F6BFF`), 10 px
radius, generous spacing, subtle borders (no heavy shadows), system font at
9.5 pt equivalent. Dark and light palettes both required. No hard-coded colours
outside `theme.py`.

### `ui/icons.py`

```python
def icon(name: str, color: str | None = None, size: int = 16) -> QIcon
def pixmap(name: str, color: str | None = None, size: int = 16) -> QPixmap
```
Inline SVG (lucide-style, 24-grid, 1.8 stroke). Required names:
`translate, files, write, history, settings, copy, check, x, swap, play, stop,
speaker, search, download, plus, trash, chevron-down, chevron-up, sparkles,
globe, arrow-right, folder, file, warning, info, refresh, external, folder-open`.

### `ui/components.py`

```python
class Card(QFrame)                    # rounded panel with optional title
class ProgressBar(QWidget)            # value 0..100, set_value(int), indeterminate(bool)
class Pill(QLabel)                    # status chip: variant "accent"|"muted"|"success"|"danger"|"warning"
class SearchField(QLineEdit)
class LanguageCombo(QWidget)          # searchable list of 38 languages, signal code_changed(str)
    def set_code(code: str); def code() -> str; def set_languages(list[Language])
class StyleChips(QWidget)             # Auto/Literal/Natural, signal changed(str)
class ToneChips(QWidget)              # Default/Formal/Casual, signal changed(str)
class SegmentedControl(QWidget)       # labels: list[str], signal changed(int), set_index(int)
class FormRow(QWidget)                # label + control (+ hint) for settings
class ToggleRow(QWidget)              # label + check box, signal toggled(bool)
class LinkButton(QPushButton)         # flat accent text button
class PrimaryButton(QPushButton); class SecondaryButton(QPushButton)
class EmptyState(QWidget)             # icon + title + subtitle
class SearchBar(QLineEdit)            # alias-friendly search input
```

All widgets must accept `parent=None`, expose `retranslate_ui()` where they hold
text, and use `theme.Theme.palette()` values at paint time (so a theme switch
repaints).

### Views

Every tab is a `QWidget` with this exact protocol:

```python
class TranslateView(QWidget):
    def __init__(self, controller: "AppController", parent: QWidget | None = None)
    def retranslate_ui(self) -> None      # re-read all strings from i18n
    def focus_source(self) -> None
```

The controller is imported lazily under `TYPE_CHECKING` only — no circular
imports (`ui` ↔ `controller`).

## 20. `controller.py`

`AppController(QObject)` owns state and background work. Attributes below are
public and may be read by views; mutate only through methods.

State (all plain Python attributes, mirrored to `settings`):

```
tab: str                       # "translate" | "files" | "write" | "history"
source_text, translated_text: str
is_translating: bool
progress: tuple[int, int]      # (completed, total)
warning_count: int
error_message: str | None
detected_language: Language | None
source_language, target_language: Language
style: TranslationStyle; tone: TranslationTone
backend_status: str            # "unknown"|"checking"|"connected"|"failed"|"warming"
probe_message: str
provider_models: list[str]; models_loading: bool; models_error: str | None
fallback_models: list[str]; fallback_models_loading: bool; fallback_models_error: str | None
using_fallback: bool
hotkey_message: str; selection_hotkey_message: str
tokens_per_second: float | None; last_duration_ms: int | None
file_job: dict | None           # see files API below
history: HistoryStore
settings: AppSettings
```

Signals (exact names):

```
sourceTextChanged(str) translatedTextChanged(str) progressChanged(int,int)
translatingChanged(bool) warningCountChanged(int) errorRaised(str)
detectedLanguageChanged(str)   # code, "" when unknown
languagesChanged(str, str)
styleChanged(str) toneChanged(str) resultViewChanged(str)
backendStatusChanged(str) probeMessageChanged(str)
modelsChanged(list) fallbackModelsChanged(list)
modelsLoadingChanged(bool) fallbackModelsLoadingChanged(bool)
modelsErrorChanged(str) fallbackModelsErrorChanged(str)
settingsChanged() interfaceLanguageChanged(str) tabChanged(str)
historyChanged() fileJobChanged(dict) speakingChanged(str)
copyFeedback(str)              # "Translation copied" | "Source copied"
```

Commands:

```python
def bootstrap(self) -> None                     # probe, warm-up, tray/hotkeys
def set_source_text(self, text: str, *, from_user: bool = True) -> None
def set_source_language(self, code: str) -> None
def set_target_language(self, code: str) -> None
def set_style(self, style) ; def set_tone(self, tone)
def set_result_view(self, mode: str)
def swap_languages(self) -> None
def clear_source(self) -> None
def translate(self, force: bool = False) -> None
def cancel(self) -> None
def translate_clipboard(self) -> None
def translate_selection(self) -> None           # global hotkey path
def copy_translation(self) -> None
def copy_source(self) -> None
def speak(self, target: str) -> None            # "source" | "translation"
def stop_speaking(self) -> None
def connect_and_load_models(self) -> None
def load_fallback_models(self) -> None
def check_connection(self) -> None
def apply_catalog_entry(self, entry) -> None
def set_interface_language(self, language) -> None
def set_tab(self, tab: str) -> None
def load_history_entry(self, entry_id: str) -> None
def save_settings(self) -> None
# Files tab
def start_file_translation(self, path: Path, target_code: str | None = None) -> None
def cancel_file_translation(self) -> None
def save_translated_file(self, destination: Path) -> None
def clear_file_job(self) -> None
# Write tab
def write_text(self, text: str, target_code: str) -> None   # async rewrite
def cancel_write(self) -> None
```

`file_job` dict shape:
`{"path": str, "name": str, "kind": str, "state": "reading"|"translating"|"done"|"failed"|"cancelled",
  "completed": int, "total": int, "percent": int, "output": str|None, "message": str|None,
  "result_name": str|None, "warnings": int}`

## 21. Packaging

- `run.bat` — creates/uses `.venv`, installs requirements on first run, starts the app.
- `build_exe.bat` + `DeepL-oFM.spec` — PyInstaller one-folder build into `dist\DeepL-oFM`.
- `README.md` (Russian) — install, run, hotkeys, providers, files, troubleshooting.
- `app.py` must support `--prefill "text"`, `--tab files`, `--version`, `--debug`.

## 22. Definition of done for every module

1. Imports cleanly: `python -c "import deepl_ofm.<module>"`.
2. Own tests pass.
3. No `print()` debugging left; use `logging.getLogger(__name__)`.
4. Docstring at module top in English, one paragraph, explaining the ported
   counterpart (`Sources/HyMT/...`).
