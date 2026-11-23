# DeepL-oFM — static frontend for the Tauri shell

This directory is the entire UI of DeepL-oFM. It is plain HTML, CSS and ES2020
JavaScript: **no build step, no bundler, no npm, no `package.json`**. The files
are loaded as they are, both by `ofm-desktop` (`tauri.conf.json` →
`"frontendDist": "../ui"`) and by a normal browser opening `index.html`.

```
index.html      shell: header, four panes, status bar, three dialogs, SVG sprite
styles.css      design tokens, light/dark themes, components, dialogs, Markdown
app.js          state, rendering, events, keyboard, prompt preview, Markdown
mock.js         standalone stubs for every Rust command + demo data
strings.js      English string table, language lists, localisation hook
screenshots.sh  regenerates every docs-*.png with headless Chrome
docs-*.png      verification screenshots (light, dark, 960, 1440, Ukrainian)
```

Open it directly:

```bash
xdg-open rust/ui/index.html          # Linux
open rust/ui/index.html              # macOS
start rust\ui\index.html             # Windows
```

`window.__TAURI__` is absent there, so `mock.js` installs `window.OFM_MOCK` and
every command resolves locally with deterministic data. Nothing is uploaded and
no server is required. If a browser refuses `file://` scripts (rare), serve the
folder with any static server, e.g.:

```bash
python3 -m http.server 8000 --directory rust/ui
# http://localhost:8000/index.html
```

## URL parameters and scenarios (standalone)

| Parameter | Effect |
|---|---|
| `?theme=dark` / `?theme=light` | Forces `data-theme` on `<html>` before the first paint. Without it the OS scheme decides. |
| `?lang=uk` (any UI code) | Mock-only: forces the interface language, e.g. `?lang=uk`, `?lang=de`. |
| `?still=1` | Disables entrance animations/transitions for deterministic screenshots. |
| `?startup=catalog` / `?startup=write` / `?startup=<tab>` | Mock-only: makes `get_startup` return a command-line action, exactly as the Rust shell would. |

A hash selects a demo state:

| Hash | Shows |
|---|---|
| *(none)*, `#translate` | filled translation |
| `#empty` | empty translate tab |
| `#progress` | translation in flight (3 of 7) |
| `#error` | failed connection + Retry |
| `#markdown` / `#text` / `#source-markdown` | the Markdown renderer in each result view |
| `#source-preview` | source card showing rendered Markdown |
| `#files`, `#files-empty`, `#files-progress`, `#files-error` | Files tab states |
| `#write`, `#write-busy`, `#write-warning` | finished improvement / running / result with a warning |
| `#history`, `#history-empty` | history list / empty state |
| `#settings`, `#settings-model`, `#settings-generation`, `#settings-behaviour`, `#settings-hotkeys`, `#settings-about` | settings dialog tabs |
| `#catalog` | model catalogue dialog |
| `#menu` | the header More menu, with the live shortcut labels |
| `#settings-missing` | Settings with the missing-model probe and install-command hint |

Combine query and hash: `index.html?theme=dark&lang=uk&still=1#settings-model`.

## Screenshots

```bash
./screenshots.sh
```

The script uses `google-chrome` (falling back to `google-chrome-stable`,
`chromium`, `chromium-browser`) in headless mode with a throw-away profile. It
renders every tab in light and dark at 1180×800, the dialogs, the transient
states, the minimum window (960×620, both schemes) and a wide window (1440×900).
Feature shots cover the source Markdown preview, the Write warning pill, the
missing-model install hint and the More menu; `?startup=…` covers the
command-line actions. Each image is inspected with an image viewer/`read_image`
as part of the UI checklist.

Manual single shot:

```bash
google-chrome --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
  --user-data-dir="$(mktemp -d)" --window-size=1180,800 \
  --screenshot=docs-translate.png \
  "file:///path/to/rust/ui/index.html?still=1#translate"
```

Screenshots and hashes are listed in the table above; `docs-uk-*.png` are the
Ukrainian pass (`?lang=uk`).

## What the Rust shell must provide

`tauri.conf.json` must enable the global API (`"app": { "withGlobalTauri": true }`)
and use `"build": { "frontendDist": "../ui" }`. The window is 1180×800 with a
minimum of 960×620. Events are emitted as `app://event` with a serialised
`ofm_app::AppEvent`; the UI subscribes with
`window.__TAURI__.event.listen("app://event", …)`.

`app.js` calls exactly the 50 commands below through
`window.__TAURI__.core.invoke(name, args)`. Tauri renames camelCase wire keys to
the snake_case Rust parameters, e.g. `{ modelId }` binds `model_id`. A command
that does not exist in `crates/desktop/src/commands.rs` is a bug in this file —
`scripts/check_shell_contract.py` enforces the list.

| Command | Arguments | Returns |
|---|---|---|
| `get_state` | — | `AppState` |
| `get_settings` | — | `AppSettings` |
| `save_settings` | `settings` (whole camelCase object) | new `AppState` |
| `get_catalog` | — | `CatalogEntry[]` (camelCase) |
| `set_source_text` | `text` | — |
| `set_source_language` | `code` | — |
| `set_target_language` | `code` | — |
| `swap_languages` | — | — |
| `set_style` | `style` | — |
| `set_tone` | `tone` | — |
| `set_result_view` | `mode` (`preview`/`text`/`markdown`) | — |
| `clear_source` | — | — |
| `translate_text` | `force` (bool, optional) | — |
| `cancel` | — | — |
| `copy_translation` | — | — |
| `copy_source` | — | — |
| `translate_clipboard` | — | — |
| `translate_selection` | — | — |
| `speak` | `target` (`source`/`translation`) | — |
| `stop_speaking` | — | — |
| `check_connection` | — | — |
| `connect_and_load_models` | — | — |
| `load_fallback_models` | — | — |
| `apply_catalog_entry` | `modelId` | — |
| `apply_model` | `modelId` (catalogue or server-discovered) | — |
| `set_interface_language` | `code` | — |
| `set_tab` | `tab` | — |
| `translate_file` | `path` (absolute), `target` (optional code) | — |
| `cancel_file_translation` | — | — |
| `save_translated_file` | `path` (absolute) | — |
| `clear_file_job` | — | — |
| `write_text` | `text`, `targetCode` (nullable) | — |
| `cancel_write` | — | — |
| `history_list` | — | `HistoryEntry[]` |
| `history_search` | `query` | `HistoryEntry[]` |
| `history_delete` | `id` | — |
| `history_clear` | — | — |
| `load_history_entry` | `id` | — |
| `list_models` | — | `string[]` |
| `list_voices` | — | `[{ id, label }]` |
| `pick_save_path` | `suggestedName` | absolute path or `null` |
| `preview_prompt` | `style`, `tone`, `targetCode` | `{ "prompt": string }` |
| `read_clipboard` | — | `string` or `null` |
| `copy_text` | `text` | — |
| `open_url` | `url` | — |
| `reveal_in_folder` | `path` | — |
| `pick_file` | — | absolute path or `null` |
| `get_translations` | — | `{ "English key": "translation" }` |
| `get_diagnostics` | — | `{ settingsPath, historyPath, secretBackend, version, interfaceLanguage, providerCount, catalogCount }` |
| `get_startup` | — | `{ catalog, writeText, tab }` |

`save_translated_file` and `translate_file` receive an **absolute path**, never
file contents. Files arrive through `pick_file` and Tauri's native
`tauri://drag-drop` event (`{ paths: [...] }`); the HTML5 drop handler is only a
highlight fallback because browsers hide paths.

## State shapes

The UI consumes `AppState` from `get_state` and renders everything from it:

- `AppState`, `FileJob` and `WriteState` are defined in
  `crates/app/src/state.rs` (camelCase on the wire).
- `HistoryEntry` is defined in `crates/store/src/history.rs`.
- `AppSettings` is defined in `crates/config/src/settings.rs` (camelCase, with
  `interfaceLanguage` as the code string `system`/`en`/`uk`/…).
- `CatalogEntry` comes from `get_catalog`: `name`, `modelId`, `provider`
  (`Provider::title()`, e.g. `"Ollama"`), `size`, `languages`, `note`,
  `installCommand`, `badges`, `isFree`.

`normalizeState` also tolerates snake_case spellings of every field, so a
renamed field never blanks the UI. `WriteState` has exactly `inProgress`,
`output`, `error`, `detectedCode`, `durationMs` and `warnings`; the draft text in
the Write tab lives only in the webview.

## Startup and command-line actions

After the first `get_state`, `app.js` calls `get_startup()` once. The Rust shell
has already applied `--prefill`, `--open-file`, `--translate-file`,
`--translate-clipboard`, `--connect` and `--load-fallback-models` before the
webview loads, so the snapshot reflects them. The remaining actions arrive from
`get_startup` and are applied once:

- `catalog: true` opens the model catalogue;
- `writeText` fills the Write editor and switches to the Write tab;
- `tab` selects that tab.

## Tab-specific behaviour

- **Write** sends `targetCode: null` until the user picks a language in
  "Improve in"; the select shows `write.detectedCode` as the automatic choice.
  Editing the draft calls `cancel_write()` and hides the previous result, so
  Copy can never return text for an older draft. `write.warnings` (and the
  localised sentence in `write.error`) render as a warning pill under the
  result, not as a fatal error.
- **Files** keeps its own target language and passes it as the `target`
  argument of `translate_file`; it never calls `set_target_language`. A failed
  job offers "Try again" (same path and target) next to "Choose a file…".
- **Translate** can swap the source editor for a rendered, read-only Markdown
  view (eye/code button). Rich clipboard pastes call `read_clipboard()` and
  insert the Markdown conversion; plain pastes keep the browser's default.
- The **More** menu rebuilds its shortcut labels from
  `settings.hotKey` / `selectionHotKey` every time it opens and includes Check
  connection and History.
- **Settings → Cancel** restores the snapshot taken when the dialog opened,
  including provider, model list, key field and any side effects from Connect,
  Load models or a catalogue pick. **Save** sends one `save_settings`.
- **Settings → About** shows read-only `get_diagnostics()` rows for the
  settings file, history file and key storage, plus the reported version.

## Events

`app.js` subscribes to `app://event`. Every event is a hint, never the only
source of truth: `stateChanged` or an unrecognised event triggers a debounced
`get_state`, and while a job is running the UI polls `get_state` until it
finishes. Struct payload variants follow serde's internally-tagged
representation (`{"type":"progress","completed":2,"total":5}`), while scalar
payloads are accepted either as `{"type":"translatedText","value":"…"}` or under
a variant-named field.

> **Rust-side caveat (cannot be fixed from `ui/`).** `AppEvent` uses
> `#[serde(tag = "type")]` together with newtype variants such as
> `TranslatedText(String)` and `Translating(bool)`. Serde cannot serialise a
> tagged newtype of a primitive, so `main.rs` currently drops those events. The
> UI compensates with snapshot polling, but the Rust enum should wrap such
> payloads in a struct (`{ value: String }`) to make live events arrive at all.

## Interface localisation

`strings.js` is the English table and the offline fallback. The active
translation catalogue comes from `get_translations()`, which returns every
English key mapped to the language chosen in **Settings → Behavior → Interface
language**. `app.js` loads it on boot, after `save_settings`, and whenever an
`interfaceLanguage` event or a state change alters the language.

Lookup order in `tr(key)`:

1. `get_translations()` catalogue for the active language,
2. the English value in `strings.js` (`window.OFM_TRANSLATE`),
3. the key itself.

Dates, durations, sizes and decimals use `Intl.DateTimeFormat` /
`Intl.NumberFormat` with that language (`system` follows `navigator.language`).
Static labels are marked with `data-i18n`, `data-i18n-aria`,
`data-i18n-title` and `data-i18n-placeholder` and are re-applied on every
language change; dynamically created rows, toasts and dialogs call `tr()` at
render time.

## Keyboard

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` / `⌘↵` | translate (Translate tab) or improve (Write tab) |
| `Ctrl+N` / `⌘N` | clear the source and focus the editor (not while a text field has focus) |
| `Ctrl+O` / `⌘O` | pick a document and translate it in the Files tab (not while a text field has focus) |
| `Ctrl+S` / `⌘S` | save the finished Files job (works from any field) |
| `Ctrl+,` / `⌘,` | open Settings (works from any field) |
| `Ctrl+Shift+C` / `⌘⇧C` | copy the translation |
| `Ctrl+Shift+S` / `⌘⇧S` | swap source and target languages |
| `Esc` | close the topmost dialog (the last opened one wins), close the overflow menu, or cancel hot-key capture |

Settings is reachable and closable without a mouse: the header button opens it,
the dialog tabs support arrow keys/Home/End, `Tab` cycles inside the native
`<dialog>`, and both `Esc` and the Cancel button revert to the snapshot. When the
catalogue is open on top of Settings, `Esc` closes the catalogue first. Global
shortcuts never fire while a modal dialog is open.

Hot-key capture fields swallow the next combination, require at least one
modifier, and `Esc` cancels capture.

## Accessibility

- Every input, select and textarea has a `<label>` or an `aria-label`; icon-only
  buttons have `aria-label` + `title`.
- Tabs use `role="tablist"`/`role="tab"` with `aria-selected`, roving `tabindex`
  and arrow-key navigation; settings tabs do the same.
- `:focus-visible` draws a 2 px accent ring on every interactive element.
- Native `<dialog>` provides focus trapping and `Esc`; the dialog shell receives
  initial focus so no control is focused before the user acts.
- Progress bars expose `role="progressbar"` + `aria-valuenow`; results and toasts
  are `aria-live`.
- No `div` acts as a button: all actions are native `<button>` elements.
- `prefers-reduced-motion` and `?still=1` disable animation.

## Design notes

Tokens live in `:root` (light) and in two dark blocks (`prefers-color-scheme`
plus `[data-theme="dark"]`), matching `windows/deepl_ofm/ui/theme.py`. Palette:
accent `#2F6BFF`, canvas `#F6F7F9`, cards `#FFFFFF`, borders `#E3E6EB`, text
`#14161A`, muted `#6B7280`; dark canvas `#15171C`, cards `#1D2027`, borders
`#2A2E37`, text `#F2F4F8`. Radius 10 px, Segoe UI Variable / SF Pro, 14 px body.

Markdown is rendered by ~150 lines in `app.js`: HTML is escaped first, then
headings, emphasis, inline code, links, lists, quotes, fences and rules are
added. Link schemes are allow-listed to `http`, `https`, `mailto` and relative
targets; links open through `open_url` in the native shell.

The prompt preview calls `preview_prompt`; when that is unavailable the UI
composes the identical instruction locally (mirroring
`ofm_text::PromptBuilder::preview`) so Settings is still useful offline.
