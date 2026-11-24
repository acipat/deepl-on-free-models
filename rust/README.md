# DeepL-oFM на Rust

Порт приложения на Rust: одно ядро, две системы (Windows и macOS), один
маленький бинарник без Python и без рантайма.

```
rust/
  crates/i18n      ofm-i18n      38 языков, определение языка, каталог интерфейса
  crates/text      ofm-text      промпты, нарезка, защита токенов, валидатор
  crates/config    ofm-config    провайдеры, каталог моделей, KeyCombo, настройки
  crates/net       ofm-net       стриминг Ollama/OpenAI, ретраи, резерв, пробник
  crates/docs      ofm-docs      txt, Markdown, DOCX, PDF
  crates/store     ofm-store     история, ключи (Credential Manager / Keychain / DPAPI)
  crates/platform  ofm-platform  буфер обмена, выделение, хоткеи, озвучка
  crates/app       ofm-app       контроллер: состояние и события, без UI
  crates/cli       ofm-cli       headless-бинарник `ofm`
  crates/desktop   ofm-desktop   оболочка Tauri v2 (Windows/macOS)
  ui/                            фронтенд: статические HTML/CSS/JS, без npm
```

Зависимости направлены в одну сторону: `i18n ← text, config, docs, store,
platform ← net, app ← cli, desktop`. Компилятор — интегратор: контракт API
зафиксирован в [`CONTRACTS.md`](CONTRACTS.md).

## Что это

Полный порт приложения на Rust: то же ядро перевода, тот же каталог моделей,
та же история и те же 9 языков интерфейса, но один бинарник и две системы —
Windows и macOS. Ядро не зависит от UI: им пользуются и графическая оболочка
(Tauri v2), и консольная утилита `ofm`.

```
$ ofm translate --text "Hello, world!" --target uk
Привіт, світе!

$ ofm check
ok · http://127.0.0.1:11434 · hy-mt2:7b · 3 models
```

Утиліта `ofm` у релізі важить **7.4 МБ** одним файлом — без Python, без venv і
без Qt. Для порівняння: збірка Python-порта через PyInstaller — близько 280 МБ.

## Сборка

Нужен Rust 1.82+ (проверено на 1.96). Дальше:

```bash
cd rust

# ядро + CLI (работает на любой ОС, без системных библиотек)
cargo build --release -p ofm-cli
./target/release/ofm --help

# тесты всех крейтов, кроме оболочки
cargo test

# оболочка: нужны WebView-библиотеки платформы
cargo build --release -p ofm-desktop
```

В этом окружении `~/.cargo` только для чтения, поэтому в репозитории есть
обёртка `rust/cargo.sh`: она выставляет `CARGO_HOME` внутрь рабочей копии.
Используйте `./cargo.sh test` вместо `cargo test`, если сборка падает на
записи в реестр.

### Windows

Нужен [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
(C++ workload) и WebView2 (в Windows 11 уже установлен, в Windows 10 —
[Evergreen Bootstrapper](https://developer.microsoft.com/microsoft-edge/webview2/)).

```powershell
cd rust
cargo build --release -p ofm-desktop
.\target\release\ofm-desktop.exe
```

### macOS

```bash
xcode-select --install
cd rust
cargo build --release -p ofm-desktop
open target/release/ofm-desktop.app   # после `cargo tauri bundle`
```

Подпись и нотаризация для распространения: `cargo tauri build` + Apple
Developer ID. Иконки генерируются один раз командой
`cargo tauri icon ../docs/app-icon.png`.

### Linux

`ofm-cli` собирается и работает. Оболочке нужны
`libwebkit2gtk-4.1-dev`, `libgtk-3-dev`, `libayatana-appindicator3-dev`.

## Командная строка

```bash
ofm translate --text "Hello world" --target uk
ofm translate --target de < report.txt
ofm translate-file report.pdf --target uk --out report-uk.pdf
ofm models --provider ollama
ofm check --provider groq --model llama-3.3-70b-versatile
ofm prompt --text "Hello" --target uk     # что именно уйдёт в модель
ofm info                                  # пути, провайдер, модель
```

Ключи провайдеров читаются из системного хранилища — того же, что использует
приложение.

## Что перенесено

| Возможность | Состояние |
|---|---|
| Hy-MT2 промпты байт-в-байт, стили Auto/Literal/Natural, тон | ✅ |
| Нарезка по строкам с сохранением Markdown, защита токенов, валидатор вывода | ✅ |
| Ollama (NDJSON) и OpenAI-совместимые (SSE), стриминг, ретраи, резервный провайдер | ✅ |
| 28 моделей в каталоге, фильтр «бесплатные», подсказки установки | ✅ |
| 9 провайдеров, ключи в Credential Manager / Keychain / DPAPI | ✅ |
| 38 языков, определение языка, 9 языков интерфейса (374 ключа) | ✅ |
| TXT/MD с определением кодировки (UTF-8/16/32, cp1251, cp1252) | ✅ |
| DOCX с сохранением форматирования и всех частей пакета | ✅ |
| PDF: чтение блоков с координатами, наложение перевода | ⚠️ приближённо |
| История с поиском, восстановлением, лимитом 400 | ✅ |
| Глобальные хоткеи (Ctrl+Alt+T — буфер, Ctrl+Alt+C — выделение), трей | ✅ Windows/macOS |
| Озвучка, захват выделения, rich-text из буфера | ✅ Windows/macOS |
| Интерфейс: 4 вкладки, настройки из 5 разделов, светлая и тёмная темы | ✅ |

## Тесты

```bash
./cargo.sh test        # 563 теста во всех крейтах, кроме оболочки
```

| Крейт | Тестов | Что покрывают |
|---|---|---|
| `ofm-i18n` | 61 | каталог 302+73 ключа × 8 языков, определение языка |
| `ofm-text` | 135 | промпты (185/185 строк совпали с Swift), нарезка, токены, валидатор |
| `ofm-config` | 76 | провайдеры, каталог 28 моделей, KeyCombo, настройки |
| `ofm-net` | 87 | стриминг NDJSON/SSE, лестница ретраев, бюджет, отмена, резерв |
| `ofm-docs` | 47 | TXT/MD с кодировками, DOCX, PDF-оверлей |
| `ofm-store` | 55 | история, хранилище ключей, атомарная запись |
| `ofm-platform` | 78 | HTML/RTF → Markdown, хоткеи, озвучка |
| `ofm-app` | 13 | состояние, ключи, память провайдеров, события |
| `ofm-cli` | 9 | сквозные прогоны бинарника против фейкового сервера |

Плюс два скрипта-стража: `scripts/check_shell_contract.py` (50 команд
оболочки ⇄ фронтенд) и `scripts/check_i18n_keys.py` (ни одного
непереведённого ключа).

## Использование диска (Disk usage)

Сборка с полной отладочной информацией занимала около 10 ГиБ в `rust/target`
(`target/debug` — 9.5 ГиБ) и однажды переполнила диск. Поэтому в `Cargo.toml`
профиль `dev` теперь собирается без отладочной информации (`debug = 0`); для
зависимостей то же значение задано явно в `[profile.dev.package."*"]`. На
поведение и тесты это не влияет: чистая сборка ядра и тесты держат `target/`
около 2 ГиБ (замер после `cargo clean`: 2.3 ГиБ вместо 9.5 ГиБ).

Скрипт `scripts/disk-report.sh` печатает `df` и размеры `target`,
`target/debug`, `.cargo-home` и `windows/.venv`, а также завершается с кодом
1, если свободного места меньше 10 ГиБ:

```bash
rust/scripts/disk-report.sh
```

Освободить место (сначала остановите сборки: `pgrep -a cargo; pgrep -a rustc`):

```bash
cd rust && ./cargo.sh clean
```

## Ограничения

Честно о том, что работает не так, как в macOS-версии:

- **PDF** — приближение. Читаются блоки с координатами, страницы и графика
  сохраняются, перевод рисуется поверх с подложкой цвета фона. Но: страницы
  с `/Rotate` получают горизонтальный текст; используется MediaBox (CropBox и
  ненулевое начало координат игнорируются); фон определяется по геометрии
  заливок, а не по растеризации; шрифт встраивается целиком (без субсетов),
  поэтому файл больше; CID-шрифты без `/ToUnicode` читаются только для
  Adobe `Uni*-UCS2-*`; блоки, для которых нет системного шрифта, остаются на
  исходном языке.
- **DOCX** — переписывается только `word/document.xml`; колонтитулы, сноски и
  комментарии не переводятся (как и в Python-версии). Формулы, поля, удалённый
  текст и `mc:Fallback` намеренно не трогаются.
- **Трей и глобальные хоткеи** — только Windows и macOS. На Linux `ofm-cli`
  работает, а оболочка собирается без трея и хоткеев.
- **Буфер обмена** получает `text/plain` + `text/html`; RTF не формируется.
- **Подпись и нотаризация** — настраиваются скриптами в `packaging/`, но здесь
  не выполнялись: нужны сертификаты и macOS/Windows-машина.

## Отличия от Python-порта

- Нет Qt: оболочка на Tauri, интерфейс — статические HTML/CSS/JS без npm.
- Нет Python-рантайма: один бинарник.
- Интерфейс переводится на 9 языков теми же 375 строками каталога.

## Разработка

```bash
./cargo.sh test -p ofm-net          # один крейт
./cargo.sh clippy --all-targets
./cargo.sh fmt --all

python3 scripts/gen_i18n.py         # пересобрать каталог из Swift
python3 scripts/gen_i18n.py --check # проверить, что каталог не устарел
```

Фронтенд открывается без Tauri:

```bash
google-chrome rust/ui/index.html    # mock.js подставит данные
```

Скриншоты для документации: `rust/ui/README.md`.
