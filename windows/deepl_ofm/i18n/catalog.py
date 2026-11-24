"""Generated interface catalogue ported from Sources/HyMT/Support/Localization.swift.

Do not edit by hand: run ``python -m deepl_ofm.i18n._parse`` to regenerate.

Layout
------
English is the identity mapping (an English key is its own translation) and is
therefore not stored.  The eight translated tables are module-level dicts named
``UKRAINIAN``, ``RUSSIAN``, ``GERMAN``, ``FRENCH``, ``SPANISH``, ``POLISH``,
``PORTUGUESE`` and ``ITALIAN``; every one maps an English source string to the
translation used for that language.

``BY_LANGUAGE`` (aliased as ``TRANSLATIONS``) maps an ISO-639-1 code to its
table so callers can select one at runtime.  There is deliberately no ``"en"``
entry: :func:`deepl_ofm.i18n.t` falls back to the key for English.

305 English keys; per language: uk=305, ru=305, de=305, fr=305, es=305, pl=305, pt=305, it=305.
"""

from __future__ import annotations

UKRAINIAN: dict[str, str] = {
    'Could not open DeepL-oFM.': 'Не вдалося відкрити DeepL-oFM.',
    'Quit DeepL-oFM if it is running, then try again.': (
        'Якщо DeepL-oFM уже працює, завершіть його й спробуйте ще раз.'
    ),
    'More actions': 'Інші дії',
    'Remove file': 'Прибрати файл',
    'Preparing file…': 'Готуємо файл…',
    'Saving…': 'Зберігаємо…',
    'Translation progress': 'Хід перекладу',
    'Could not read or save translation history.': (
        'Не вдалося прочитати або зберегти історію перекладів.'
    ),
    'Some paragraphs are still in the original language (%d).': (
        'Деякі абзаци залишилися мовою оригіналу (%d).'
    ),
    'The server interrupted the response. Try again.': (
        'Сервер перервав відповідь. Спробуйте ще раз.'
    ),
    'The provider rejected the request. Check the API key and model in Settings.': (
        'Провайдер відхилив запит. Перевірте ключ доступу й модель у налаштуваннях.'
    ),
    'The provider is temporarily unavailable. Try again.': (
        'Провайдер тимчасово недоступний. Спробуйте ще раз.'
    ),
    'Privacy policy': 'Політика конфіденційності',
    'Source language': 'Мова оригіналу',
    'Target language': 'Мова перекладу',
    'Fallback': 'Резерв',
    'Too many requests. Wait a moment and try again.': (
        'Забагато запитів. Зачекайте трохи й спробуйте ще раз.'
    ),
    'Improve clarity, grammar and style while keeping the meaning.': (
        'Виправте граматику й зробіть текст зрозумілішим, зберігши його зміст.'
    ),
    'Improve in': 'Покращити мовою',
    'Improve text': 'Покращити текст',
    'Improving…': 'Редагуємо текст…',
    'Improved text will appear here': 'Покращений текст з’явиться тут',
    'Type or paste text to improve': 'Введіть або вставте текст для покращення',
    'Files': 'Файли',
    'Translate a document and save the result in its original format.': (
        'Перекладіть документ і збережіть його в тому самому форматі.'
    ),
    'Drop a file here or choose one': 'Перетягніть файл сюди або виберіть на комп’ютері',
    'Supported formats: TXT, Markdown, PDF and DOCX.': (
        'Підтримувані формати: TXT, Markdown, PDF і DOCX.'
    ),
    'Choose a file…': 'Вибрати файл…',
    'Translate to': 'Перекласти на',
    'Translation complete': 'Переклад завершено',
    'Translate another file': 'Перекласти інший файл',
    'The file could not be translated.': 'Не вдалося перекласти файл.',
    'The file could not be saved.': 'Не вдалося зберегти файл.',
    'Voice': 'Голос',
    'Automatic': 'Автоматично',
    'Stop': 'Зупинити',
    (
        'The Dock icon appears while the window is open. Turn this on to keep it in the Dock all '
        'the time.'
    ): (
        'Іконка в Dock з’являється, поки вікно відкрите. Увімкніть, щоб вона була там постійно.'
    ),
    (
        'For better voices, download Enhanced or Premium voices in System Settings → '
        'Accessibility → Spoken Content.'
    ): (
        'Кращі голоси можна завантажити в Системних налаштуваннях → Доступність → Мовлення → '
        'Системний голос.'
    ),
    'Done': 'Готово',
    'Share': 'Поділитися',
    'Version': 'Версія',
    'Source': 'Оригінал',
    'Result': 'Результат',
    'Add your API key in Settings.': 'Додайте ключ API у Налаштуваннях.',
    'Cloud providers need an API key. For a server on your Wi-Fi network, choose Custom.': (
        'Для хмарного провайдера потрібен ключ доступу. Для сервера у вашій мережі Wi-Fi виберіть '
        '«Власний».'
    ),
    'Dock icon': 'Іконка в Dock',
    'Hide the Dock icon to keep DeepL-oFM in the menu bar only.': (
        'Вимкніть іконку в Dock, щоб DeepL-oFM залишався лише в меню-барі.'
    ),
    'Back to translation': 'Назад до перекладу',
    'File': 'Файл',
    'Translate file…': 'Перекласти файл…',
    'Save translation…': 'Зберегти переклад…',
    'Translated file': 'Перекладений файл',
    'Open a document': 'Відкрити документ',
    'This file type is not supported.': 'Цей тип файлу не підтримується.',
    'The file could not be read.': 'Не вдалося прочитати файл.',
    'No selectable text found. For a scanned PDF, run text recognition first.': (
        'Не знайдено тексту, який можна виділити. Спершу розпізнайте текст у сканованому PDF.'
    ),
    'The Word document could not be processed.': 'Не вдалося обробити документ Word.',
    'The translation could not be saved.': 'Не вдалося зберегти переклад.',
    'Drop a file to translate': 'Перетягніть файл для перекладу',
    'Preview': 'Перегляд',
    'Text only': 'Тільки текст',
    'Markdown': 'Markdown',
    'Show plain text': 'Показати лише текст',
    'Copy translation (formatted text)': 'Скопіювати переклад (форматований текст)',
    'Copy translation (plain text)': 'Скопіювати переклад (простий текст)',
    'Copy translation (Markdown)': 'Скопіювати переклад (Markdown)',
    'Show rendered Markdown': 'Показати відформатований Markdown',
    'Show Markdown source': 'Показати розмітку Markdown',
    'Translate text': 'Перекласти текст',
    'History': 'Історія',
    'Settings': 'Налаштування',
    'Translation': 'Переклад',
    'Translate now': 'Перекласти',
    'Translate clipboard': 'Перекласти буфер обміну',
    'Swap languages': 'Обміняти мови',
    'Copy translation': 'Скопіювати переклад',
    'Copy translation (Markdown + formatting)': 'Скопіювати переклад (Markdown + форматування)',
    'Copy': 'Копіювати',
    'Sample text': 'Зразок тексту',
    'Translation failed': 'Не вдалося перекласти',
    'Settings…': 'Налаштування…',
    'Connection status': 'Стан підключення',
    'Check connection': "Перевірити з'єднання",
    'Open DeepL-oFM': 'Відкрити DeepL-oFM',
    'Quit': 'Вийти',
    'Translate clipboard (%@)': 'Перекласти буфер обміну (%@)',
    'Auto-detect': 'Автовизначення',
    'Style': 'Стиль',
    'Tone': 'Тон',
    'Auto': 'Авто',
    'Literal': 'Дослівний',
    'Natural': 'Природний',
    'Default': 'За замовчуванням',
    'Formal': 'Офіційний',
    'Casual': 'Розмовний',
    'The model picks a natural style': 'Модель сама обирає природний стиль',
    'Word for word, without free paraphrase': 'Точно за словами, без вільного перефразування',
    'Conveys meaning rather than wording': 'Передає смисл, а не окремі слова',
    'No extra tone': 'Без додаткового тону',
    'Formal and professional': 'Формальний, професійний',
    'Casual and conversational': 'Невимушений, розмовний',
    'Enter or paste text…': 'Введіть або вставте текст…',
    'Translation will appear here': 'Тут з’явиться переклад',
    'Translating…': 'Перекладаю…',
    'Translating… %d of %d': 'Перекладаю… %d з %d',
    'Retry': 'Повторити',
    'Clear': 'Очистити',
    'Listen to the original': 'Прослухати оригінал',
    'Copy the original': 'Скопіювати оригінал',
    'Listen to the translation': 'Прослухати переклад',
    'Translate again': 'Перекласти ще раз',
    'Swap languages (⇧⌘S)': 'Обміняти мови (⇧⌘S)',
    'Checking connection…': "Перевіряю з'єднання…",
    'Server unavailable': 'Сервер недоступний',
    'Model “%@” not found': 'Модель «%@» не знайдена',
    'Not checked yet': 'Ще не перевірено',
    'Connection works. Model “%@” is available.': "З'єднання працює. Модель «%@» доступна.",
    'Server responds, but model “%@” is missing. Available: %@.': (
        'Сервер відповідає, але моделі «%@» немає. Доступні: %@.'
    ),
    'Connection works.': "З'єднання працює.",
    '%@ — translate clipboard': '%@ — перекласти буфер',
    '%@ — active': '%@ — активна',
    'Could not register %@. The shortcut may be taken.': (
        'Не вдалося зареєструвати %@. Можливо, комбінація вже зайнята.'
    ),
    'Press a combination…': 'Натисніть комбінацію…',
    'Reset': 'Скинути',
    'At least one modifier is required — ⌘, ⌥ or ⌃. Press Esc to cancel.': (
        'Потрібен щонайменше один модифікатор — ⌘, ⌥ або ⌃. Натисніть Esc, щоб скасувати.'
    ),
    'Hot key': 'Гаряча клавіша',
    'Copy text anywhere and press the shortcut — DeepL-oFM opens and translates the clipboard.': (
        'Скопіюйте текст у будь-якому застосунку та натисніть комбінацію — DeepL-oFM відкриється '
        'й одразу перекладе вміст буфера обміну.'
    ),
    'Select text in any app and press the shortcut — DeepL-oFM copies it and translates.': (
        'Виділіть текст у будь-якому застосунку та натисніть комбінацію — DeepL-oFM скопіює його '
        'й перекладе.'
    ),
    'Translate selection': 'Перекласти виділене',
    'Translate selection (%@)': 'Перекласти виділене (%@)',
    'Selected text': 'Виділений текст',
    'Accessibility access': 'Доступ до Accessibility',
    'Granted': 'Надано',
    'Not granted': 'Не надано',
    'Open System Settings': 'Відкрити системні налаштування',
    'Check access': 'Перевірити доступ',
    'Delete': 'Видалити',
    'Forward Delete': 'Видалити вперед',
    'Examples: ⌥⌘T or ⌥⌘C.': 'Наприклад: ⌥⌘T або ⌥⌘C.',
    (
        'If access is already granted, remove DeepL-oFM from the Accessibility list and add the '
        'current app again — a permission from an older build does not apply.'
    ): (
        'Якщо доступ уже надано, видаліть DeepL-oFM зі списку Accessibility і додайте поточний '
        'застосунок знову — дозвіл від старої збірки не діє.'
    ),
    'Accessibility access is required to copy the selected text.': (
        'Для копіювання виділеного тексту потрібен доступ до Accessibility.'
    ),
    'Could not copy the selected text. Check Accessibility access.': (
        'Не вдалося скопіювати виділений текст. Перевірте доступ до Accessibility.'
    ),
    'Space': 'Пробіл',
    'key %d': 'клавіша %d',
    'Can be empty for local servers. Stored in the macOS Keychain, never in the repository.': (
        'Може бути порожнім для локального сервера. Ключ зберігається в Keychain macOS і ніколи '
        'не потрапляє в репозиторій.'
    ),
    'DeepL-oFM — local translation': 'DeepL-oFM — локальний переклад',
    'Other': 'Інший',
    'Custom': 'Власний',
    'Ollama Cloud through a direct API key. No local server is needed.': (
        'Ollama Cloud через прямий API-ключ. Локальний сервер не потрібен.'
    ),
    'Connect': "Під'єднатися",
    'Models on the server': 'Моделі на сервері',
    'Filter by name': 'Фільтр за назвою',
    'Refresh': 'Оновити',
    'The server returned no models.': 'Сервер не повернув жодної моделі.',
    'Select a model from the list or type its ID.': (
        'Оберіть модель зі списку або введіть її ідентифікатор.'
    ),
    'Models: %d': 'Моделей: %d',
    'Cloud': 'Хмара',
    'Gemma 4 in Ollama Cloud. Fast and strong for general translation.': (
        'Gemma 4 в Ollama Cloud. Швидка й сильна для загального перекладу.'
    ),
    'A fast cloud model from DeepSeek with a large context.': (
        'Швидка хмарна модель DeepSeek із великим контекстом.'
    ),
    "Mistral's general-purpose model in Ollama Cloud.": (
        'Універсальна модель Mistral в Ollama Cloud.'
    ),
    "NVIDIA's high-throughput model for difficult texts.": (
        'Високопродуктивна модель NVIDIA для складних текстів.'
    ),
    'Model and provider': 'Модель і провайдер',
    'Local models run offline and for free. Cloud models answer faster but need a key.': (
        'Локальні моделі працюють офлайн і безкоштовно. Хмарні відповідають швидше, але '
        'потребують ключа.'
    ),
    'API key': 'Ключ API',
    'Get key ↗': 'Отримати ключ ↗',
    'Server address': 'Адреса сервера',
    'Model': 'Модель',
    'Model catalog…': 'Каталог моделей…',
    'For difficult texts, use Hy-MT2 30B or a cloud model.': (
        'Для складних текстів використовуйте Hy-MT2 30B або хмарну модель.'
    ),
    'Fallback provider': 'Резервний провайдер',
    'Used automatically when the primary provider fails.': (
        'Використовується автоматично, якщо основний провайдер не відповідає.'
    ),
    'Use a fallback provider': 'Використовувати резервний провайдер',
    'Provider': 'Провайдер',
    'Load models': 'Завантажити моделі',
    'Choose model': 'Оберіть модель',
    'Choose a model': 'Оберіть модель',
    'Uses the Keychain key for this provider.': 'Використовує ключ Keychain цього провайдера.',
    'If the primary provider fails, the same text is retried with these settings.': (
        'Якщо основний провайдер не відповідає, той самий текст повторюється з цими '
        'налаштуваннями.'
    ),
    'Load the translator at launch': 'Завантажувати перекладач під час запуску',
    'Connects to the provider, refreshes the model list and warms up a local model.': (
        'Підключається до провайдера, оновлює список моделей і завантажує локальну модель у '
        "пам'ять."
    ),
    'Fallback provider works.': 'Резервний провайдер працює.',
    'fallback': 'резерв',
    'Generation parameters': 'Параметри генерації',
    'Defaults match Tencent’s recommendations for Hy-MT2 7B.': (
        'Значення за замовчуванням відповідають рекомендаціям Tencent для Hy-MT2 7B.'
    ),
    'Temperature': 'Температура',
    'Repetition': 'Повторення',
    'Only this many most likely tokens are considered while decoding.': (
        'Під час декодування розглядається стільки найімовірніших токенів.'
    ),
    'Context': 'Контекст',
    'Behavior': 'Поведінка',
    'Translate automatically while typing': 'Перекладати автоматично під час введення',
    'Delay': 'Затримка',
    'Keep translation history': 'Зберігати історію перекладів',
    'Open at login': 'Запускати під час входу в macOS',
    'Allow DeepL-oFM to open at login in System Settings.': (
        'Дозвольте автозапуск DeepL-oFM у системних налаштуваннях.'
    ),
    'Could not change Open at login. %@': 'Не вдалося змінити налаштування автозапуску. %@',
    'Menu bar icon': 'Іконка в меню-барі',
    'Interface language': 'Мова інтерфейсу',
    'System': 'Системна',
    'System prompt': 'Системний промпт',
    (
        'Hy-MT2 has no system prompt: instruction and text go in one message. Wording follows the '
        'model card.'
    ): (
        'Hy-MT2 не має системного промпту: інструкція та текст ідуть одним повідомленням. '
        'Формулювання збігаються з карткою моделі.'
    ),
    'About': 'Про програму',
    'local translator for macOS': 'локальний перекладач для macOS',
    'Model: Hy-MT2 7B (Tencent Hy). License and model card on Hugging Face.': (
        'Модель: Hy-MT2 7B (Tencent Hy). Ліцензія та картка моделі — на Hugging Face.'
    ),
    'Check for Updates…': 'Перевірити оновлення…',
    'Checking for updates…': 'Перевіряю оновлення…',
    "You're up to date.": 'У вас остання версія.',
    'Update available: %@': 'Доступне оновлення: %@',
    'Update check failed: %@': 'Не вдалося перевірити оновлення: %@',
    'Automatically check for updates': 'Автоматично перевіряти оновлення',
    'Automatically download and install updates': (
        'Автоматично завантажувати й встановлювати оновлення'
    ),
    'Updates are signed and notarized.': 'Оновлення підписані та нотарізовані.',
    'Project repository': 'Репозиторій проєкту',
    'DeepL-oFM on GitHub': 'DeepL-oFM на GitHub',
    'Local Ollama server. The model must be pulled with ollama pull.': (
        'Локальний сервер Ollama. Модель має бути завантажена командою ollama pull.'
    ),
    'LM Studio with its local server enabled. The model ID is shown in LM Studio.': (
        'LM Studio з увімкненим локальним сервером. Ідентифікатор моделі видно в LM Studio.'
    ),
    'oMLX — an MLX server for Apple Silicon. Enable the OpenAI-compatible API.': (
        'oMLX — MLX-сервер для Apple Silicon. Увімкніть OpenAI-сумісний API.'
    ),
    'llama-server with --api. The default address is port 8080.': (
        'llama-server з прапорцем --api. Адреса за замовчуванням — порт 8080.'
    ),
    'Hundreds of models with one key. Free models are marked :free.': (
        'Сотні моделей через один ключ. Є безкоштовні моделі з позначкою :free.'
    ),
    'Very fast cloud. Has a free tier with request limits.': (
        'Дуже швидка хмара. Є безкоштовний тариф із лімітами на кількість запитів.'
    ),
    'Fastest inference for open models. Has a free tier with limits.': (
        'Найшвидший inference для відкритих моделей. Є безкоштовний тариф із лімітами.'
    ),
    'Any OpenAI-compatible server: your proxy, vLLM, LocalAI, Together, and so on.': (
        'Будь-який OpenAI-сумісний сервер: свій проксі, vLLM, LocalAI, Together тощо.'
    ),
    'Model catalog': 'Каталог моделей',
    'Ready translators for local use and cloud options with free tiers.': (
        'Готові перекладачі для локального запуску й хмарні варіанти з безкоштовними тарифами.'
    ),
    'Search model': 'Пошук моделі',
    'Free only': 'Лише безкоштовні',
    'Fetch from server': 'Отримати з сервера',
    'Nothing found': 'Нічого не знайдено',
    'Found on the server': 'Знайдені на сервері',
    'Recommended': 'Рекомендовані',
    'Models': 'Моделі',
    (
        'Need another model? Type its ID into the Model field — any model your server supports '
        'will work.'
    ): (
        'Інша модель? Введіть її ідентифікатор у полі «Модель» — підійде будь-яка модель, яку '
        'підтримує ваш сервер.'
    ),
    'Choose': 'Обрати',
    'Copy install command': 'Скопіювати команду встановлення',
    'Enter the API key for %@ in Settings first.': (
        'Спочатку введіть ключ API для %@ у налаштуваннях.'
    ),
    'Search in history': 'Пошук в історії',
    'Search language': 'Пошук мови',
    'Clear history?': 'Очистити історію?',
    'Cancel': 'Скасувати',
    'All saved translations will be deleted permanently.': (
        'Усі збережені переклади буде видалено без можливості відновлення.'
    ),
    'History is empty': 'Історія порожня',
    'Translations will be saved here automatically.': 'Переклади зберігатимуться тут автоматично.',
    'Try another query.': 'Спробуйте інший запит.',
    'Delete entry': 'Видалити запис',
    'Invalid server URL: %@': 'Некоректна адреса сервера: %@',
    'Choose a model in Settings.': 'Виберіть модель у налаштуваннях.',
    'Could not connect to %@. Check that the server is running.': (
        'Не вдалося підключитися до %@. Перевірте, чи запущений сервер.'
    ),
    'Server returned error %@.': 'Сервер повернув помилку %@.',
    'Server returned error %@: %@': 'Сервер повернув помилку %@: %@',
    'Model “%@” not found on the server.': 'Модель «%@» не знайдена на сервері.',
    'The model returned an empty translation. Try again.': (
        'Модель повернула порожній переклад. Спробуйте ще раз.'
    ),
    'The model could not translate this text. Try again or choose another model.': (
        'Модель не змогла перекласти цей текст. Спробуйте ще раз або виберіть іншу модель.'
    ),
    'Some lines could not be translated (%d); they are left in the source language.': (
        'Деякі рядки не вдалося перекласти (%d); їх залишено мовою оригіналу.'
    ),
    'Server returned an unexpected response.': 'Сервер повернув неочікувану відповідь.',
    "Tencent's specialised translation model. The default for this app.": (
        'Спеціалізована модель перекладу Tencent. Базова для застосунку.'
    ),
    'The same model in a lighter size: fast even on weaker Macs.': (
        'Легка версія тієї ж моделі: швидко працює навіть на слабких Mac.'
    ),
    'The highest-quality MoE version. Needs a lot of memory.': (
        "MoE-версія найвищої якості. Потребує багато пам'яті."
    ),
    "Google's translation model built on Gemma 3.": 'Перекладацька модель Google на базі Gemma 3.',
    'A larger TranslateGemma for stronger machines.': (
        'Якісніша версія TranslateGemma для сильніших машин.'
    ),
    'A compact model tuned only to translate — no explanations or reasoning.': (
        'Компактна модель, донавчена лише перекладати — без пояснень і міркувань.'
    ),
    "Cohere's multilingual model with a good speed-quality balance.": (
        'Багатомовна модель Cohere з добрим балансом швидкості та якості.'
    ),
    'A general model; translates well but may add explanations.': (
        'Універсальна модель; добре перекладає, але може додавати пояснення.'
    ),
    'The same translation model in the cloud. Very cheap, no download.': (
        'Та сама перекладацька модель у хмарі. Дуже дешева, без завантаження.'
    ),
    'The cheapest Hy-MT2 option on OpenRouter.': 'Найдешевший варіант Hy-MT2 через OpenRouter.',
    'The highest-quality Hy-MT2 version on OpenRouter.': (
        'Найякісніша версія Hy-MT2 через OpenRouter.'
    ),
    "Google's free model with a large context. Good general translation.": (
        'Безкоштовна модель Google з великим контекстом. Гарний загальний переклад.'
    ),
    'A free MoE version of Gemma 4: faster than 31B.': (
        'Безкоштовна MoE-версія Gemma 4: швидша за 31B.'
    ),
    'A large free NVIDIA model for difficult texts.': (
        'Велика безкоштовна модель NVIDIA для складних текстів.'
    ),
    'A free fast model with a 1M-token context.': (
        'Безкоштовна швидка модель із контекстом 1M токенів.'
    ),
    'Cheap and very fast general translation from Google.': (
        'Дешевий і дуже швидкий загальний переклад від Google.'
    ),
    'The cheapest fast Qwen model for bulk translation.': (
        'Найдешевша швидка модель Qwen для масових перекладів.'
    ),
    'Reliable general translation from OpenAI.': 'Надійний загальний переклад від OpenAI.',
    "OpenAI's flagship open model on Groq's fast inference.": (
        'Флагманська відкрита модель OpenAI на швидкому inference Groq.'
    ),
    'The fastest option for short texts.': 'Найшвидший варіант для коротких текстів.',
    "Meta's proven general-purpose model.": 'Перевірена універсальна модель Meta.',
    'A fresh Qwen with strong translation; preview status.': (
        'Свіжа Qwen із сильним перекладом; статус preview.'
    ),
    'Around 3000 tokens per second — the fastest option for long texts.': (
        'Близько 3000 токенів за секунду — найшвидший варіант для довгих текстів.'
    ),
    'A fast Qwen with good multilingual translation.': (
        'Швидка Qwen із добрим багатомовним перекладом.'
    ),
    '33 languages': '33 мови',
    '55 languages': '55 мов',
    '23 languages': '23 мови',
    'recommended': 'рекомендовано',
    'light': 'легка',
    'fast': 'швидка',
    'large': 'велика',
    'specialised': 'спеціалізована',
    'cheap': 'дешева',
    'cheapest': 'найдешевша',
    'universal': 'універсальна',
    'slower': 'повільніша',
    'Free': 'Безкоштовно',
    'Free tier': 'Free-тариф',
    'preview': 'preview',
    'MoE': 'MoE',
    'translation': 'переклад',
    'Local': 'Локально',
    '≈4.6 GB': '≈4,6 ГБ',
    '≈3 GB': '≈3 ГБ',
    '≈8 GB': '≈8 ГБ',
    '~500 t/s': '~500 т/с',
    '~1000 t/s': '~1000 т/с',
    '~280 t/s': '~280 т/с',
    '~450 t/s': '~450 т/с',
    '~3000 t/s': '~3000 т/с',
    '~1850 t/s': '~1850 т/с',
    'Paste from clipboard': 'Вставити з буфера',
}

RUSSIAN: dict[str, str] = {
    'Could not open DeepL-oFM.': 'Не удалось открыть DeepL-oFM.',
    'Quit DeepL-oFM if it is running, then try again.': (
        'Если DeepL-oFM уже работает, завершите его и попробуйте ещё раз.'
    ),
    'More actions': 'Другие действия',
    'Remove file': 'Убрать файл',
    'Preparing file…': 'Подготовка файла…',
    'Saving…': 'Сохранение…',
    'Translation progress': 'Ход перевода',
    'Could not read or save translation history.': (
        'Не удалось прочитать или сохранить историю переводов.'
    ),
    'Some paragraphs are still in the original language (%d).': (
        'Некоторые абзацы остались на языке оригинала (%d).'
    ),
    'The server interrupted the response. Try again.': 'Сервер прервал ответ. Попробуйте ещё раз.',
    'The provider rejected the request. Check the API key and model in Settings.': (
        'Поставщик отклонил запрос. Проверьте ключ доступа и модель в настройках.'
    ),
    'The provider is temporarily unavailable. Try again.': (
        'Поставщик временно недоступен. Попробуйте ещё раз.'
    ),
    'Privacy policy': 'Политика конфиденциальности',
    'Source language': 'Язык оригинала',
    'Target language': 'Язык перевода',
    'Fallback': 'Резерв',
    'Too many requests. Wait a moment and try again.': (
        'Слишком много запросов. Подождите немного и попробуйте ещё раз.'
    ),
    'Improve clarity, grammar and style while keeping the meaning.': (
        'Улучшайте ясность, грамматику и стиль, сохраняя смысл.'
    ),
    'Improve in': 'Улучшить на языке',
    'Improve text': 'Улучшить текст',
    'Improving…': 'Улучшаю…',
    'Improved text will appear here': 'Улучшенный текст появится здесь',
    'Type or paste text to improve': 'Введите или вставьте текст для улучшения',
    'Files': 'Файлы',
    'Translate a document and save the result in its original format.': (
        'Переведите документ и сохраните результат в исходном формате.'
    ),
    'Drop a file here or choose one': 'Перетащите файл сюда или выберите его',
    'Supported formats: TXT, Markdown, PDF and DOCX.': (
        'Поддерживаемые форматы: TXT, Markdown, PDF и DOCX.'
    ),
    'Choose a file…': 'Выбрать файл…',
    'Translate to': 'Перевести на',
    'Translation complete': 'Перевод завершён',
    'Translate another file': 'Перевести другой файл',
    'The file could not be translated.': 'Не удалось перевести файл.',
    'The file could not be saved.': 'Не удалось сохранить файл.',
    'Voice': 'Голос',
    'Automatic': 'Автоматически',
    'Stop': 'Остановить',
    (
        'The Dock icon appears while the window is open. Turn this on to keep it in the Dock all '
        'the time.'
    ): (
        'Иконка в Dock появляется, пока окно открыто. Включите, чтобы она была там постоянно.'
    ),
    (
        'For better voices, download Enhanced or Premium voices in System Settings → '
        'Accessibility → Spoken Content.'
    ): (
        'Лучшие голоса можно загрузить в Системных настройках → Универсальный доступ → Устная '
        'речь → Системный голос.'
    ),
    'Done': 'Готово',
    'Share': 'Поделиться',
    'Version': 'Версия',
    'Source': 'Источник',
    'Result': 'Результат',
    'Add your API key in Settings.': 'Добавьте ключ API в Настройках.',
    'Cloud providers need an API key. For a server on your Wi-Fi network, choose Custom.': (
        'Для облачного поставщика нужен ключ доступа. Для сервера в вашей сети Wi-Fi выберите '
        '«Свой».'
    ),
    'Dock icon': 'Иконка в Dock',
    'Hide the Dock icon to keep DeepL-oFM in the menu bar only.': (
        'Отключите иконку в Dock, чтобы DeepL-oFM оставался только в меню-баре.'
    ),
    'Back to translation': 'Назад к переводу',
    'File': 'Файл',
    'Translate file…': 'Перевести файл…',
    'Save translation…': 'Сохранить перевод…',
    'Translated file': 'Переведённый файл',
    'Open a document': 'Открыть документ',
    'This file type is not supported.': 'Этот тип файла не поддерживается.',
    'The file could not be read.': 'Не удалось прочитать файл.',
    'No selectable text found. For a scanned PDF, run text recognition first.': (
        'Не найден текст, который можно выделить. Сначала распознайте текст в отсканированном PDF.'
    ),
    'The Word document could not be processed.': 'Не удалось обработать документ Word.',
    'The translation could not be saved.': 'Не удалось сохранить перевод.',
    'Drop a file to translate': 'Перетащите файл для перевода',
    'Preview': 'Просмотр',
    'Text only': 'Только текст',
    'Markdown': 'Markdown',
    'Show plain text': 'Показать только текст',
    'Copy translation (formatted text)': 'Скопировать перевод (форматированный текст)',
    'Copy translation (plain text)': 'Скопировать перевод (простой текст)',
    'Copy translation (Markdown)': 'Скопировать перевод (Markdown)',
    'Show rendered Markdown': 'Показать отформатированный Markdown',
    'Show Markdown source': 'Показать разметку Markdown',
    'Translate text': 'Перевести текст',
    'History': 'История',
    'Settings': 'Настройки',
    'Translation': 'Перевод',
    'Translate now': 'Перевести',
    'Translate clipboard': 'Перевести буфер обмена',
    'Swap languages': 'Поменять языки',
    'Copy translation': 'Скопировать перевод',
    'Copy translation (Markdown + formatting)': 'Скопировать перевод (Markdown + форматирование)',
    'Copy': 'Копировать',
    'Sample text': 'Образец текста',
    'Translation failed': 'Не удалось перевести',
    'Settings…': 'Настройки…',
    'Connection status': 'Состояние подключения',
    'Check connection': 'Проверить соединение',
    'Open DeepL-oFM': 'Открыть DeepL-oFM',
    'Quit': 'Выйти',
    'Translate clipboard (%@)': 'Перевести буфер обмена (%@)',
    'Auto-detect': 'Автоопределение',
    'Style': 'Стиль',
    'Tone': 'Тон',
    'Auto': 'Авто',
    'Literal': 'Дословный',
    'Natural': 'Естественный',
    'Default': 'По умолчанию',
    'Formal': 'Официальный',
    'Casual': 'Разговорный',
    'The model picks a natural style': 'Модель сама выбирает естественный стиль',
    'Word for word, without free paraphrase': 'Точно по словам, без свободного перефразирования',
    'Conveys meaning rather than wording': 'Передаёт смысл, а не отдельные слова',
    'No extra tone': 'Без дополнительного тона',
    'Formal and professional': 'Формальный, профессиональный',
    'Casual and conversational': 'Непринуждённый, разговорный',
    'Enter or paste text…': 'Введите или вставьте текст…',
    'Translation will appear here': 'Здесь появится перевод',
    'Translating…': 'Перевожу…',
    'Translating… %d of %d': 'Перевожу… %d из %d',
    'Retry': 'Повторить',
    'Clear': 'Очистить',
    'Listen to the original': 'Прослушать оригинал',
    'Copy the original': 'Скопировать оригинал',
    'Listen to the translation': 'Прослушать перевод',
    'Translate again': 'Перевести ещё раз',
    'Swap languages (⇧⌘S)': 'Поменять языки (⇧⌘S)',
    'Checking connection…': 'Проверяю соединение…',
    'Server unavailable': 'Сервер недоступен',
    'Model “%@” not found': 'Модель «%@» не найдена',
    'Not checked yet': 'Ещё не проверено',
    'Connection works. Model “%@” is available.': 'Соединение работает. Модель «%@» доступна.',
    'Server responds, but model “%@” is missing. Available: %@.': (
        'Сервер отвечает, но модели «%@» нет. Доступны: %@.'
    ),
    'Connection works.': 'Соединение работает.',
    '%@ — translate clipboard': '%@ — перевести буфер обмена',
    '%@ — active': '%@ — активна',
    'Could not register %@. The shortcut may be taken.': (
        'Не удалось зарегистрировать %@. Возможно, комбинация уже занята.'
    ),
    'Press a combination…': 'Нажмите комбинацию…',
    'Reset': 'Сбросить',
    'At least one modifier is required — ⌘, ⌥ or ⌃. Press Esc to cancel.': (
        'Нужен хотя бы один модификатор — ⌘, ⌥ или ⌃. Нажмите Esc, чтобы отменить.'
    ),
    'Hot key': 'Горячая клавиша',
    'Copy text anywhere and press the shortcut — DeepL-oFM opens and translates the clipboard.': (
        'Скопируйте текст в любом приложении и нажмите комбинацию — DeepL-oFM откроется и сразу '
        'переведёт содержимое буфера обмена.'
    ),
    'Select text in any app and press the shortcut — DeepL-oFM copies it and translates.': (
        'Выделите текст в любом приложении и нажмите комбинацию — DeepL-oFM скопирует его и '
        'переведёт.'
    ),
    'Translate selection': 'Перевести выделенное',
    'Translate selection (%@)': 'Перевести выделенное (%@)',
    'Selected text': 'Выделенный текст',
    'Accessibility access': 'Доступ к Accessibility',
    'Granted': 'Предоставлен',
    'Not granted': 'Не предоставлен',
    'Open System Settings': 'Открыть системные настройки',
    'Check access': 'Проверить доступ',
    'Delete': 'Удалить',
    'Forward Delete': 'Удалить вперёд',
    'Examples: ⌥⌘T or ⌥⌘C.': 'Например: ⌥⌘T или ⌥⌘C.',
    (
        'If access is already granted, remove DeepL-oFM from the Accessibility list and add the '
        'current app again — a permission from an older build does not apply.'
    ): (
        'Если доступ уже предоставлен, удалите DeepL-oFM из списка Accessibility и добавьте '
        'текущее приложение снова — разрешение от старой сборки не действует.'
    ),
    'Accessibility access is required to copy the selected text.': (
        'Для копирования выделенного текста нужен доступ к Accessibility.'
    ),
    'Could not copy the selected text. Check Accessibility access.': (
        'Не удалось скопировать выделенный текст. Проверьте доступ к Accessibility.'
    ),
    'Space': 'Пробел',
    'key %d': 'клавиша %d',
    'Can be empty for local servers. Stored in the macOS Keychain, never in the repository.': (
        'Может быть пустым для локального сервера. Ключ хранится в Keychain macOS и никогда не '
        'попадает в репозиторий.'
    ),
    'DeepL-oFM — local translation': 'DeepL-oFM — локальный перевод',
    'Other': 'Другой',
    'Custom': 'Свой',
    'Ollama Cloud through a direct API key. No local server is needed.': (
        'Ollama Cloud через прямой API-ключ. Локальный сервер не нужен.'
    ),
    'Connect': 'Подключиться',
    'Models on the server': 'Модели на сервере',
    'Filter by name': 'Фильтр по названию',
    'Refresh': 'Обновить',
    'The server returned no models.': 'Сервер не вернул ни одной модели.',
    'Select a model from the list or type its ID.': (
        'Выберите модель из списка или введите её идентификатор.'
    ),
    'Models: %d': 'Моделей: %d',
    'Cloud': 'Облако',
    'Gemma 4 in Ollama Cloud. Fast and strong for general translation.': (
        'Gemma 4 в Ollama Cloud. Быстрая и сильная для общего перевода.'
    ),
    'A fast cloud model from DeepSeek with a large context.': (
        'Быстрая облачная модель DeepSeek с большим контекстом.'
    ),
    "Mistral's general-purpose model in Ollama Cloud.": (
        'Универсальная модель Mistral в Ollama Cloud.'
    ),
    "NVIDIA's high-throughput model for difficult texts.": (
        'Высокопроизводительная модель NVIDIA для сложных текстов.'
    ),
    'Model and provider': 'Модель и провайдер',
    'Local models run offline and for free. Cloud models answer faster but need a key.': (
        'Локальные модели работают офлайн и бесплатно. Облачные отвечают быстрее, но требуют '
        'ключа.'
    ),
    'API key': 'Ключ API',
    'Get key ↗': 'Получить ключ ↗',
    'Server address': 'Адрес сервера',
    'Model': 'Модель',
    'Model catalog…': 'Каталог моделей…',
    'For difficult texts, use Hy-MT2 30B or a cloud model.': (
        'Для сложных текстов используйте Hy-MT2 30B или облачную модель.'
    ),
    'Fallback provider': 'Резервный провайдер',
    'Used automatically when the primary provider fails.': (
        'Используется автоматически, если основной провайдер не отвечает.'
    ),
    'Use a fallback provider': 'Использовать резервный провайдер',
    'Provider': 'Провайдер',
    'Load models': 'Загрузить модели',
    'Choose model': 'Выберите модель',
    'Choose a model': 'Выберите модель',
    'Uses the Keychain key for this provider.': 'Использует ключ Keychain этого провайдера.',
    'If the primary provider fails, the same text is retried with these settings.': (
        'Если основной провайдер не отвечает, тот же текст повторяется с этими настройками.'
    ),
    'Load the translator at launch': 'Загружать переводчик при запуске',
    'Connects to the provider, refreshes the model list and warms up a local model.': (
        'Подключается к провайдеру, обновляет список моделей и загружает локальную модель в '
        'память.'
    ),
    'Fallback provider works.': 'Резервный провайдер работает.',
    'fallback': 'резерв',
    'Generation parameters': 'Параметры генерации',
    'Defaults match Tencent’s recommendations for Hy-MT2 7B.': (
        'Значения по умолчанию соответствуют рекомендациям Tencent для Hy-MT2 7B.'
    ),
    'Temperature': 'Температура',
    'Repetition': 'Повторение',
    'Only this many most likely tokens are considered while decoding.': (
        'При декодировании рассматривается столько самых вероятных токенов.'
    ),
    'Context': 'Контекст',
    'Behavior': 'Поведение',
    'Translate automatically while typing': 'Переводить автоматически во время ввода',
    'Delay': 'Задержка',
    'Keep translation history': 'Сохранять историю переводов',
    'Open at login': 'Запускать при входе в macOS',
    'Allow DeepL-oFM to open at login in System Settings.': (
        'Разрешите автозапуск DeepL-oFM в системных настройках.'
    ),
    'Could not change Open at login. %@': 'Не удалось изменить настройку автозапуска. %@',
    'Menu bar icon': 'Иконка в меню-баре',
    'Interface language': 'Язык интерфейса',
    'System': 'Системная',
    'System prompt': 'Системный промпт',
    (
        'Hy-MT2 has no system prompt: instruction and text go in one message. Wording follows the '
        'model card.'
    ): (
        'У Hy-MT2 нет системного промпта: инструкция и текст идут одним сообщением. Формулировки '
        'совпадают с карточкой модели.'
    ),
    'About': 'О программе',
    'local translator for macOS': 'локальный переводчик для macOS',
    'Model: Hy-MT2 7B (Tencent Hy). License and model card on Hugging Face.': (
        'Модель: Hy-MT2 7B (Tencent Hy). Лицензия и карточка модели — на Hugging Face.'
    ),
    'Check for Updates…': 'Проверить обновления…',
    'Checking for updates…': 'Проверяю обновления…',
    "You're up to date.": 'У вас последняя версия.',
    'Update available: %@': 'Доступно обновление: %@',
    'Update check failed: %@': 'Не удалось проверить обновления: %@',
    'Automatically check for updates': 'Автоматически проверять обновления',
    'Automatically download and install updates': (
        'Автоматически загружать и устанавливать обновления'
    ),
    'Updates are signed and notarized.': 'Обновления подписаны и нотаризованы.',
    'Project repository': 'Репозиторий проекта',
    'DeepL-oFM on GitHub': 'DeepL-oFM на GitHub',
    'Local Ollama server. The model must be pulled with ollama pull.': (
        'Локальный сервер Ollama. Модель должна быть загружена командой ollama pull.'
    ),
    'LM Studio with its local server enabled. The model ID is shown in LM Studio.': (
        'LM Studio с включённым локальным сервером. Идентификатор модели виден в LM Studio.'
    ),
    'oMLX — an MLX server for Apple Silicon. Enable the OpenAI-compatible API.': (
        'oMLX — MLX-сервер для Apple Silicon. Включите OpenAI-совместимый API.'
    ),
    'llama-server with --api. The default address is port 8080.': (
        'llama-server с флагом --api. Адрес по умолчанию — порт 8080.'
    ),
    'Hundreds of models with one key. Free models are marked :free.': (
        'Сотни моделей через один ключ. Есть бесплатные модели с пометкой :free.'
    ),
    'Very fast cloud. Has a free tier with request limits.': (
        'Очень быстрое облако. Есть бесплатный тариф с лимитами на количество запросов.'
    ),
    'Fastest inference for open models. Has a free tier with limits.': (
        'Самый быстрый inference для открытых моделей. Есть бесплатный тариф с лимитами.'
    ),
    'Any OpenAI-compatible server: your proxy, vLLM, LocalAI, Together, and so on.': (
        'Любой OpenAI-совместимый сервер: свой прокси, vLLM, LocalAI, Together и т. п.'
    ),
    'Model catalog': 'Каталог моделей',
    'Ready translators for local use and cloud options with free tiers.': (
        'Готовые переводчики для локального запуска и облачные варианты с бесплатными тарифами.'
    ),
    'Search model': 'Поиск модели',
    'Free only': 'Только бесплатные',
    'Fetch from server': 'Получить с сервера',
    'Nothing found': 'Ничего не найдено',
    'Found on the server': 'Найдены на сервере',
    'Recommended': 'Рекомендуемые',
    'Models': 'Модели',
    (
        'Need another model? Type its ID into the Model field — any model your server supports '
        'will work.'
    ): (
        'Нужна другая модель? Введите её идентификатор в поле «Модель» — подойдёт любая модель, '
        'которую поддерживает ваш сервер.'
    ),
    'Choose': 'Выбрать',
    'Copy install command': 'Скопировать команду установки',
    'Enter the API key for %@ in Settings first.': 'Сначала введите ключ API для %@ в настройках.',
    'Search in history': 'Поиск в истории',
    'Search language': 'Поиск языка',
    'Clear history?': 'Очистить историю?',
    'Cancel': 'Отмена',
    'All saved translations will be deleted permanently.': (
        'Все сохранённые переводы будут удалены без возможности восстановления.'
    ),
    'History is empty': 'История пуста',
    'Translations will be saved here automatically.': (
        'Переводы будут сохраняться здесь автоматически.'
    ),
    'Try another query.': 'Попробуйте другой запрос.',
    'Delete entry': 'Удалить запись',
    'Invalid server URL: %@': 'Некорректный адрес сервера: %@',
    'Choose a model in Settings.': 'Выберите модель в настройках.',
    'Could not connect to %@. Check that the server is running.': (
        'Не удалось подключиться к %@. Проверьте, запущен ли сервер.'
    ),
    'Server returned error %@.': 'Сервер вернул ошибку %@.',
    'Server returned error %@: %@': 'Сервер вернул ошибку %@: %@',
    'Model “%@” not found on the server.': 'Модель «%@» не найдена на сервере.',
    'The model returned an empty translation. Try again.': (
        'Модель вернула пустой перевод. Попробуйте ещё раз.'
    ),
    'The model could not translate this text. Try again or choose another model.': (
        'Модель не смогла перевести этот текст. Попробуйте ещё раз или выберите другую модель.'
    ),
    'Some lines could not be translated (%d); they are left in the source language.': (
        'Некоторые строки не удалось перевести (%d); они оставлены на языке оригинала.'
    ),
    'Server returned an unexpected response.': 'Сервер вернул неожиданный ответ.',
    "Tencent's specialised translation model. The default for this app.": (
        'Специализированная модель перевода Tencent. Базовая для приложения.'
    ),
    'The same model in a lighter size: fast even on weaker Macs.': (
        'Лёгкая версия той же модели: быстро работает даже на слабых Mac.'
    ),
    'The highest-quality MoE version. Needs a lot of memory.': (
        'MoE-версия наивысшего качества. Требует много памяти.'
    ),
    "Google's translation model built on Gemma 3.": 'Переводческая модель Google на базе Gemma 3.',
    'A larger TranslateGemma for stronger machines.': (
        'Более качественная версия TranslateGemma для сильных машин.'
    ),
    'A compact model tuned only to translate — no explanations or reasoning.': (
        'Компактная модель, дообученная только переводить — без пояснений и рассуждений.'
    ),
    "Cohere's multilingual model with a good speed-quality balance.": (
        'Многоязычная модель Cohere с хорошим балансом скорости и качества.'
    ),
    'A general model; translates well but may add explanations.': (
        'Универсальная модель; хорошо переводит, но может добавлять пояснения.'
    ),
    'The same translation model in the cloud. Very cheap, no download.': (
        'Та же переводческая модель в облаке. Очень дешёвая, без загрузки.'
    ),
    'The cheapest Hy-MT2 option on OpenRouter.': 'Самый дешёвый вариант Hy-MT2 через OpenRouter.',
    'The highest-quality Hy-MT2 version on OpenRouter.': (
        'Самая качественная версия Hy-MT2 через OpenRouter.'
    ),
    "Google's free model with a large context. Good general translation.": (
        'Бесплатная модель Google с большим контекстом. Хороший общий перевод.'
    ),
    'A free MoE version of Gemma 4: faster than 31B.': (
        'Бесплатная MoE-версия Gemma 4: быстрее, чем 31B.'
    ),
    'A large free NVIDIA model for difficult texts.': (
        'Большая бесплатная модель NVIDIA для сложных текстов.'
    ),
    'A free fast model with a 1M-token context.': (
        'Бесплатная быстрая модель с контекстом 1M токенов.'
    ),
    'Cheap and very fast general translation from Google.': (
        'Дешёвый и очень быстрый общий перевод от Google.'
    ),
    'The cheapest fast Qwen model for bulk translation.': (
        'Самая дешёвая быстрая модель Qwen для массовых переводов.'
    ),
    'Reliable general translation from OpenAI.': 'Надёжный общий перевод от OpenAI.',
    "OpenAI's flagship open model on Groq's fast inference.": (
        'Флагманская открытая модель OpenAI на быстром inference Groq.'
    ),
    'The fastest option for short texts.': 'Самый быстрый вариант для коротких текстов.',
    "Meta's proven general-purpose model.": 'Проверенная универсальная модель Meta.',
    'A fresh Qwen with strong translation; preview status.': (
        'Свежая Qwen с сильным переводом; статус preview.'
    ),
    'Around 3000 tokens per second — the fastest option for long texts.': (
        'Около 3000 токенов в секунду — самый быстрый вариант для длинных текстов.'
    ),
    'A fast Qwen with good multilingual translation.': (
        'Быстрая Qwen с хорошим многоязычным переводом.'
    ),
    '33 languages': '33 языка',
    '55 languages': '55 языков',
    '23 languages': '23 языка',
    'recommended': 'рекомендуется',
    'light': 'лёгкая',
    'fast': 'быстрая',
    'large': 'большая',
    'specialised': 'специализированная',
    'cheap': 'дешёвая',
    'cheapest': 'самая дешёвая',
    'universal': 'универсальная',
    'slower': 'медленнее',
    'Free': 'Бесплатно',
    'Free tier': 'Free-тариф',
    'preview': 'preview',
    'MoE': 'MoE',
    'translation': 'перевод',
    'Local': 'Локально',
    '≈4.6 GB': '≈4,6 ГБ',
    '≈3 GB': '≈3 ГБ',
    '≈8 GB': '≈8 ГБ',
    '~500 t/s': '~500 т/с',
    '~1000 t/s': '~1000 т/с',
    '~280 t/s': '~280 т/с',
    '~450 t/s': '~450 т/с',
    '~3000 t/s': '~3000 т/с',
    '~1850 t/s': '~1850 т/с',
    'Paste from clipboard': 'Вставить из буфера',
}

GERMAN: dict[str, str] = {
    'Could not open DeepL-oFM.': 'DeepL-oFM konnte nicht geöffnet werden.',
    'Quit DeepL-oFM if it is running, then try again.': (
        'Beende DeepL-oFM, falls es läuft, und versuche es erneut.'
    ),
    'More actions': 'Weitere Aktionen',
    'Remove file': 'Datei entfernen',
    'Preparing file…': 'Datei wird vorbereitet…',
    'Saving…': 'Wird gespeichert…',
    'Translation progress': 'Übersetzungsfortschritt',
    'Could not read or save translation history.': (
        'Der Übersetzungsverlauf konnte nicht gelesen oder gespeichert werden.'
    ),
    'Some paragraphs are still in the original language (%d).': (
        'Einige Absätze sind noch in der Originalsprache (%d).'
    ),
    'The server interrupted the response. Try again.': (
        'Der Server hat die Antwort abgebrochen. Versuche es erneut.'
    ),
    'The provider rejected the request. Check the API key and model in Settings.': (
        'Der Anbieter hat die Anfrage abgelehnt. Prüfe den API-Schlüssel und das Modell in den '
        'Einstellungen.'
    ),
    'The provider is temporarily unavailable. Try again.': (
        'Der Anbieter ist vorübergehend nicht erreichbar. Versuche es erneut.'
    ),
    'Privacy policy': 'Datenschutzerklärung',
    'Source language': 'Ausgangssprache',
    'Target language': 'Zielsprache',
    'Fallback': 'Ausweich',
    'Too many requests. Wait a moment and try again.': (
        'Zu viele Anfragen. Warte kurz und versuche es erneut.'
    ),
    'Improve clarity, grammar and style while keeping the meaning.': (
        'Verbessern Sie Klarheit, Grammatik und Stil, ohne den Sinn zu verändern.'
    ),
    'Improve in': 'Verbessern auf',
    'Improve text': 'Text verbessern',
    'Improving…': 'Verbessere…',
    'Improved text will appear here': 'Der verbesserte Text erscheint hier',
    'Type or paste text to improve': 'Text zum Verbessern eingeben oder einfügen',
    'Files': 'Dateien',
    'Translate a document and save the result in its original format.': (
        'Übersetzen Sie ein Dokument und speichern Sie das Ergebnis im Originalformat.'
    ),
    'Drop a file here or choose one': 'Datei hierher ziehen oder auswählen',
    'Supported formats: TXT, Markdown, PDF and DOCX.': (
        'Unterstützte Formate: TXT, Markdown, PDF und DOCX.'
    ),
    'Choose a file…': 'Datei auswählen…',
    'Translate to': 'Übersetzen nach',
    'Translation complete': 'Übersetzung abgeschlossen',
    'Translate another file': 'Weitere Datei übersetzen',
    'The file could not be translated.': 'Die Datei konnte nicht übersetzt werden.',
    'The file could not be saved.': 'Die Datei konnte nicht gespeichert werden.',
    'Voice': 'Stimme',
    'Automatic': 'Automatisch',
    'Stop': 'Stoppen',
    (
        'The Dock icon appears while the window is open. Turn this on to keep it in the Dock all '
        'the time.'
    ): (
        'Das Dock-Symbol erscheint, solange das Fenster geöffnet ist. Aktivieren, um es dauerhaft '
        'im Dock zu behalten.'
    ),
    (
        'For better voices, download Enhanced or Premium voices in System Settings → '
        'Accessibility → Spoken Content.'
    ): (
        'Bessere Stimmen lassen sich in den Systemeinstellungen → Bedienungshilfen → '
        'Sprachausgabe → Systemstimme laden.'
    ),
    'Done': 'Fertig',
    'Share': 'Teilen',
    'Version': 'Version',
    'Source': 'Quelle',
    'Result': 'Ergebnis',
    'Add your API key in Settings.': 'Fügen Sie Ihren API-Schlüssel in den Einstellungen hinzu.',
    'Cloud providers need an API key. For a server on your Wi-Fi network, choose Custom.': (
        'Cloud-Anbieter brauchen einen API-Schlüssel. Wähle für einen Server in deinem WLAN '
        '„Benutzerdefiniert“.'
    ),
    'Dock icon': 'Dock-Symbol',
    'Hide the Dock icon to keep DeepL-oFM in the menu bar only.': (
        'Dock-Symbol ausblenden, damit DeepL-oFM nur in der Menüleiste bleibt.'
    ),
    'Back to translation': 'Zurück zur Übersetzung',
    'File': 'Datei',
    'Translate file…': 'Datei übersetzen…',
    'Save translation…': 'Übersetzung sichern…',
    'Translated file': 'Übersetzte Datei',
    'Open a document': 'Dokument öffnen',
    'This file type is not supported.': 'Dieser Dateityp wird nicht unterstützt.',
    'The file could not be read.': 'Die Datei konnte nicht gelesen werden.',
    'No selectable text found. For a scanned PDF, run text recognition first.': (
        'Kein auswählbarer Text gefunden. Wende bei gescannten PDFs zuerst die Texterkennung an.'
    ),
    'The Word document could not be processed.': (
        'Das Word-Dokument konnte nicht verarbeitet werden.'
    ),
    'The translation could not be saved.': 'Die Übersetzung konnte nicht gesichert werden.',
    'Drop a file to translate': 'Datei zum Übersetzen ablegen',
    'Preview': 'Vorschau',
    'Text only': 'Nur Text',
    'Markdown': 'Markdown',
    'Show plain text': 'Nur Text anzeigen',
    'Copy translation (formatted text)': 'Übersetzung kopieren (formatierter Text)',
    'Copy translation (plain text)': 'Übersetzung kopieren (reiner Text)',
    'Copy translation (Markdown)': 'Übersetzung kopieren (Markdown)',
    'Show rendered Markdown': 'Gerendertes Markdown anzeigen',
    'Show Markdown source': 'Markdown-Quelltext anzeigen',
    'Translate text': 'Text übersetzen',
    'History': 'Verlauf',
    'Settings': 'Einstellungen',
    'Translation': 'Übersetzung',
    'Translate now': 'Übersetzen',
    'Translate clipboard': 'Zwischenablage übersetzen',
    'Swap languages': 'Sprachen tauschen',
    'Copy translation': 'Übersetzung kopieren',
    'Copy translation (Markdown + formatting)': 'Übersetzung kopieren (Markdown + Formatierung)',
    'Copy': 'Kopieren',
    'Sample text': 'Beispieltext',
    'Translation failed': 'Übersetzung fehlgeschlagen',
    'Settings…': 'Einstellungen…',
    'Connection status': 'Verbindungsstatus',
    'Check connection': 'Verbindung prüfen',
    'Open DeepL-oFM': 'DeepL-oFM öffnen',
    'Quit': 'Beenden',
    'Translate clipboard (%@)': 'Zwischenablage übersetzen (%@)',
    'Auto-detect': 'Automatisch erkennen',
    'Style': 'Stil',
    'Tone': 'Ton',
    'Auto': 'Auto',
    'Literal': 'Wörtlich',
    'Natural': 'Natürlich',
    'Default': 'Standard',
    'Formal': 'Formell',
    'Casual': 'Umgangssprachlich',
    'The model picks a natural style': 'Das Modell wählt einen natürlichen Stil',
    'Word for word, without free paraphrase': 'Wort für Wort, ohne freie Paraphrase',
    'Conveys meaning rather than wording': 'Vermittelt die Bedeutung statt der Formulierung',
    'No extra tone': 'Kein zusätzlicher Ton',
    'Formal and professional': 'Formell und professionell',
    'Casual and conversational': 'Informell und gesprächig',
    'Enter or paste text…': 'Text eingeben oder einfügen…',
    'Translation will appear here': 'Hier erscheint die Übersetzung',
    'Translating…': 'Übersetze…',
    'Translating… %d of %d': 'Übersetze… %d von %d',
    'Retry': 'Erneut versuchen',
    'Clear': 'Löschen',
    'Listen to the original': 'Original anhören',
    'Copy the original': 'Original kopieren',
    'Listen to the translation': 'Übersetzung anhören',
    'Translate again': 'Erneut übersetzen',
    'Swap languages (⇧⌘S)': 'Sprachen tauschen (⇧⌘S)',
    'Checking connection…': 'Verbindung prüfen…',
    'Server unavailable': 'Server nicht verfügbar',
    'Model “%@” not found': 'Modell “%@” nicht gefunden',
    'Not checked yet': 'Noch nicht geprüft',
    'Connection works. Model “%@” is available.': (
        'Verbindung funktioniert. Modell “%@” ist verfügbar.'
    ),
    'Server responds, but model “%@” is missing. Available: %@.': (
        'Server antwortet, aber Modell “%@” fehlt. Verfügbar: %@.'
    ),
    'Connection works.': 'Verbindung funktioniert.',
    '%@ — translate clipboard': '%@ — Zwischenablage übersetzen',
    '%@ — active': '%@ — aktiv',
    'Could not register %@. The shortcut may be taken.': (
        'Konnte %@ nicht registrieren. Der Shortcut könnte bereits belegt sein.'
    ),
    'Press a combination…': 'Kombination drücken…',
    'Reset': 'Zurücksetzen',
    'At least one modifier is required — ⌘, ⌥ or ⌃. Press Esc to cancel.': (
        'Mindestens ein Modifikator ist erforderlich — ⌘, ⌥ oder ⌃. Esc drücken zum Abbrechen.'
    ),
    'Hot key': 'Hotkey',
    'Copy text anywhere and press the shortcut — DeepL-oFM opens and translates the clipboard.': (
        'Text überall kopieren und Shortcut drücken — DeepL-oFM öffnet und übersetzt die '
        'Zwischenablage.'
    ),
    'Select text in any app and press the shortcut — DeepL-oFM copies it and translates.': (
        'Text in beliebiger App auswählen und Shortcut drücken — DeepL-oFM kopiert ihn und '
        'übersetzt.'
    ),
    'Translate selection': 'Auswahl übersetzen',
    'Translate selection (%@)': 'Auswahl übersetzen (%@)',
    'Selected text': 'Ausgewählter Text',
    'Accessibility access': 'Barrierefreiheit‑Zugriff',
    'Granted': 'Gewährt',
    'Not granted': 'Nicht gewährt',
    'Open System Settings': 'Systemeinstellungen öffnen',
    'Check access': 'Zugriff prüfen',
    'Delete': 'Löschen',
    'Forward Delete': 'Vorwärts löschen',
    'Examples: ⌥⌘T or ⌥⌘C.': 'Beispiele: ⌥⌘T oder ⌥⌘C.',
    (
        'If access is already granted, remove DeepL-oFM from the Accessibility list and add the '
        'current app again — a permission from an older build does not apply.'
    ): (
        'Ist der Zugriff bereits gewährt, entferne DeepL-oFM aus der Barrierefreiheits‑Liste und '
        'füge die aktuelle App erneut hinzu – eine Berechtigung aus einer älteren Version gilt '
        'nicht.'
    ),
    'Accessibility access is required to copy the selected text.': (
        'Barrierefreiheit‑Zugriff ist zum Kopieren des ausgewählten Textes erforderlich.'
    ),
    'Could not copy the selected text. Check Accessibility access.': (
        'Kopieren des ausgewählten Textes fehlgeschlagen. Barrierefreiheit‑Zugriff prüfen.'
    ),
    'Space': 'Leertaste',
    'key %d': 'Taste %d',
    'Can be empty for local servers. Stored in the macOS Keychain, never in the repository.': (
        'Kann für lokale Server leer bleiben. Wird im macOS‑Schlüsselbund gespeichert, nie im '
        'Repository.'
    ),
    'DeepL-oFM — local translation': 'DeepL-oFM — lokale Übersetzung',
    'Other': 'Andere',
    'Custom': 'Benutzerdefiniert',
    'Ollama Cloud through a direct API key. No local server is needed.': (
        'Ollama Cloud über einen direkten API‑Schlüssel. Kein lokaler Server nötig.'
    ),
    'Connect': 'Verbinden',
    'Models on the server': 'Modelle auf dem Server',
    'Filter by name': 'Nach Name filtern',
    'Refresh': 'Aktualisieren',
    'The server returned no models.': 'Der Server hat keine Modelle zurückgegeben.',
    'Select a model from the list or type its ID.': (
        'Wähle ein Modell aus der Liste oder gib seine ID ein.'
    ),
    'Models: %d': 'Modelle: %d',
    'Cloud': 'Cloud',
    'Gemma 4 in Ollama Cloud. Fast and strong for general translation.': (
        'Gemma\u202f4 in Ollama Cloud. Schnell und leistungsstark für allgemeine Übersetzungen.'
    ),
    'A fast cloud model from DeepSeek with a large context.': (
        'Ein schnelles Cloud‑Modell von DeepSeek mit großem Kontext.'
    ),
    "Mistral's general-purpose model in Ollama Cloud.": 'Mistrals Allzweckmodell in Ollama Cloud.',
    "NVIDIA's high-throughput model for difficult texts.": (
        'NVIDIAs Hochdurchsatz‑Modell für schwierige Texte.'
    ),
    'Model and provider': 'Modell und Anbieter',
    'Local models run offline and for free. Cloud models answer faster but need a key.': (
        'Lokale Modelle laufen offline und kostenlos. Cloud‑Modelle antworten schneller, '
        'benötigen jedoch einen Schlüssel.'
    ),
    'API key': 'API‑Schlüssel',
    'Get key ↗': 'Schlüssel erhalten ↗',
    'Server address': 'Serveradresse',
    'Model': 'Modell',
    'Model catalog…': 'Modellkatalog…',
    'For difficult texts, use Hy-MT2 30B or a cloud model.': (
        'Für schwierige Texte Hy‑MT2 30B oder ein Cloud‑Modell verwenden.'
    ),
    'Fallback provider': 'Ausweich‑Anbieter',
    'Used automatically when the primary provider fails.': (
        'Wird automatisch verwendet, wenn der primäre Anbieter ausfällt.'
    ),
    'Use a fallback provider': 'Ausweich‑Anbieter verwenden',
    'Provider': 'Anbieter',
    'Load models': 'Modelle laden',
    'Choose model': 'Modell wählen',
    'Choose a model': 'Ein Modell wählen',
    'Uses the Keychain key for this provider.': (
        'Verwendet den Schlüssel aus dem Schlüsselbund für diesen Anbieter.'
    ),
    'If the primary provider fails, the same text is retried with these settings.': (
        'Falls der primäre Anbieter ausfällt, wird derselbe Text mit diesen Einstellungen erneut '
        'versucht.'
    ),
    'Load the translator at launch': 'Übersetzer beim Start laden',
    'Connects to the provider, refreshes the model list and warms up a local model.': (
        'Verbindet sich mit dem Anbieter, aktualisiert die Modellliste und startet ein lokales '
        'Modell.'
    ),
    'Fallback provider works.': 'Ausweich‑Anbieter funktioniert.',
    'fallback': 'Ausweich',
    'Generation parameters': 'Generierungsparameter',
    'Defaults match Tencent’s recommendations for Hy-MT2 7B.': (
        'Standardwerte entsprechen den Empfehlungen von Tencent für Hy‑MT2 7B.'
    ),
    'Temperature': 'Temperatur',
    'Repetition': 'Wiederholung',
    'Only this many most likely tokens are considered while decoding.': (
        'Nur diese Anzahl wahrscheinlichster Tokens wird beim Dekodieren berücksichtigt.'
    ),
    'Context': 'Kontext',
    'Behavior': 'Verhalten',
    'Translate automatically while typing': 'Während des Tippens automatisch übersetzen',
    'Delay': 'Verzögerung',
    'Keep translation history': 'Übersetzungshistorie behalten',
    'Open at login': 'Bei der Anmeldung öffnen',
    'Allow DeepL-oFM to open at login in System Settings.': (
        'Erlaube DeepL-oFM in den Systemeinstellungen, bei der Anmeldung zu starten.'
    ),
    'Could not change Open at login. %@': (
        'Die Einstellung für den Start bei der Anmeldung konnte nicht geändert werden. %@'
    ),
    'Menu bar icon': 'Menüleistensymbol',
    'Interface language': 'Oberflächensprache',
    'System': 'System',
    'System prompt': 'Systemaufforderung',
    (
        'Hy-MT2 has no system prompt: instruction and text go in one message. Wording follows the '
        'model card.'
    ): (
        'Hy-MT2 hat keinen Systemprompt: Anweisung und Text gehen in einer Nachricht. Die '
        'Formulierung folgt dem Model-Card.'
    ),
    'About': 'Über',
    'local translator for macOS': 'lokaler Übersetzer für macOS',
    'Model: Hy-MT2 7B (Tencent Hy). License and model card on Hugging Face.': (
        'Modell: Hy-MT2 7B (Tencent Hy). Lizenz und Model-Card auf Hugging Face.'
    ),
    'Check for Updates…': 'Nach Updates suchen…',
    'Checking for updates…': 'Suche nach Updates…',
    "You're up to date.": 'Sie sind auf dem neuesten Stand.',
    'Update available: %@': 'Update verfügbar: %@',
    'Update check failed: %@': 'Update‑Prüfung fehlgeschlagen: %@',
    'Automatically check for updates': 'Automatisch nach Updates suchen',
    'Automatically download and install updates': (
        'Updates automatisch herunterladen und installieren'
    ),
    'Updates are signed and notarized.': 'Updates sind signiert und notariell beglaubigt.',
    'Project repository': 'Projekt-Repository',
    'DeepL-oFM on GitHub': 'DeepL-oFM auf GitHub',
    'Local Ollama server. The model must be pulled with ollama pull.': (
        'Lokaler Ollama‑Server. Das Modell muss mit ollama pull heruntergeladen werden.'
    ),
    'LM Studio with its local server enabled. The model ID is shown in LM Studio.': (
        'LM Studio mit aktiviertem lokalem Server. Die Modell‑ID wird in LM Studio angezeigt.'
    ),
    'oMLX — an MLX server for Apple Silicon. Enable the OpenAI-compatible API.': (
        'oMLX – ein MLX‑Server für Apple Silicon. OpenAI‑kompatible API aktivieren.'
    ),
    'llama-server with --api. The default address is port 8080.': (
        'llama-server mit --api. Die Standardadresse ist Port 8080.'
    ),
    'Hundreds of models with one key. Free models are marked :free.': (
        'Hunderte Modelle mit einem Schlüssel. Kostenlose Modelle sind mit :free gekennzeichnet.'
    ),
    'Very fast cloud. Has a free tier with request limits.': (
        'Sehr schnelle Cloud. Verfügt über eine kostenlose Stufe mit Anfragelimits.'
    ),
    'Fastest inference for open models. Has a free tier with limits.': (
        'Schnellste Inferenz für offene Modelle. Verfügt über eine kostenlose Stufe mit Limits.'
    ),
    'Any OpenAI-compatible server: your proxy, vLLM, LocalAI, Together, and so on.': (
        'Jeder OpenAI‑kompatible Server: Ihr Proxy, vLLM, LocalAI, Together usw.'
    ),
    'Model catalog': 'Modellkatalog',
    'Ready translators for local use and cloud options with free tiers.': (
        'Bereit für lokale Nutzung und Cloud-Optionen mit kostenlosen Stufen.'
    ),
    'Search model': 'Modell suchen',
    'Free only': 'Nur kostenlos',
    'Fetch from server': 'Vom Server abrufen',
    'Nothing found': 'Nichts gefunden',
    'Found on the server': 'Auf dem Server gefunden',
    'Recommended': 'Empfohlen',
    'Models': 'Modelle',
    (
        'Need another model? Type its ID into the Model field — any model your server supports '
        'will work.'
    ): (
        'Benötigen Sie ein anderes Modell? Geben Sie dessen ID in das Modell‑Feld ein – jedes '
        'Modell, das Ihr Server unterstützt, funktioniert.'
    ),
    'Choose': 'Auswählen',
    'Copy install command': 'Installationsbefehl kopieren',
    'Enter the API key for %@ in Settings first.': (
        'Geben Sie zuerst den API‑Schlüssel für %@ in den Einstellungen ein.'
    ),
    'Search in history': 'In Verlauf suchen',
    'Search language': 'Sprache suchen',
    'Clear history?': 'Verlauf löschen?',
    'Cancel': 'Abbrechen',
    'All saved translations will be deleted permanently.': (
        'Alle gespeicherten Übersetzungen werden dauerhaft gelöscht.'
    ),
    'History is empty': 'Verlauf ist leer',
    'Translations will be saved here automatically.': (
        'Übersetzungen werden hier automatisch gespeichert.'
    ),
    'Try another query.': 'Andere Anfrage versuchen.',
    'Delete entry': 'Eintrag löschen',
    'Invalid server URL: %@': 'Ungültige Server‑URL: %@',
    'Choose a model in Settings.': 'Wähle in den Einstellungen ein Modell aus.',
    'Could not connect to %@. Check that the server is running.': (
        'Verbindung zu %@ fehlgeschlagen. Prüfen Sie, ob der Server läuft.'
    ),
    'Server returned error %@.': 'Server gab Fehler %@ zurück.',
    'Server returned error %@: %@': 'Server gab Fehler %@ zurück: %@',
    'Model “%@” not found on the server.': 'Modell „%@“ wurde auf dem Server nicht gefunden.',
    'The model returned an empty translation. Try again.': (
        'Das Modell lieferte eine leere Übersetzung. Bitte erneut versuchen.'
    ),
    'The model could not translate this text. Try again or choose another model.': (
        'Das Modell konnte diesen Text nicht übersetzen. Versuche es erneut oder wähle ein '
        'anderes Modell.'
    ),
    'Some lines could not be translated (%d); they are left in the source language.': (
        'Einige Zeilen konnten nicht übersetzt werden (%d); sie bleiben in der Ausgangssprache.'
    ),
    'Server returned an unexpected response.': 'Server hat eine unerwartete Antwort zurückgegeben.',
    "Tencent's specialised translation model. The default for this app.": (
        'Tencents spezialisiertes Übersetzungsmodell. Standard für diese App.'
    ),
    'The same model in a lighter size: fast even on weaker Macs.': (
        'Dasselbe Modell in leichterer Größe: schnell selbst auf schwächeren Macs.'
    ),
    'The highest-quality MoE version. Needs a lot of memory.': (
        'Die hochwertigste MoE-Version. Benötigt viel Speicher.'
    ),
    "Google's translation model built on Gemma 3.": (
        'Googles Übersetzungsmodell, basierend auf Gemma\u202f3.'
    ),
    'A larger TranslateGemma for stronger machines.': (
        'Ein größeres TranslateGemma für leistungsstärkere Geräte.'
    ),
    'A compact model tuned only to translate — no explanations or reasoning.': (
        'Ein kompaktes Modell, ausschließlich zum Übersetzen optimiert – ohne Erklärungen oder '
        'Argumentation.'
    ),
    "Cohere's multilingual model with a good speed-quality balance.": (
        'Cohere‑s mehrsprachiges Modell mit gutem Geschwindigkeits‑Qualitäts‑Verhältnis.'
    ),
    'A general model; translates well but may add explanations.': (
        'Ein allgemeines Modell; übersetzt gut, kann aber Erklärungen hinzufügen.'
    ),
    'The same translation model in the cloud. Very cheap, no download.': (
        'Dasselbe Übersetzungsmodell in der Cloud. Sehr günstig, kein Download.'
    ),
    'The cheapest Hy-MT2 option on OpenRouter.': 'Die günstigste Hy‑MT2‑Option bei OpenRouter.',
    'The highest-quality Hy-MT2 version on OpenRouter.': (
        'Die hochwertigste Hy‑MT2‑Version bei OpenRouter.'
    ),
    "Google's free model with a large context. Good general translation.": (
        'Googles kostenloses Modell mit großem Kontext. Gute allgemeine Übersetzung.'
    ),
    'A free MoE version of Gemma 4: faster than 31B.': (
        'Eine kostenlose MoE-Version von Gemma\u202f4: schneller als 31\u202fB.'
    ),
    'A large free NVIDIA model for difficult texts.': (
        'Ein großes kostenloses NVIDIA‑Modell für schwierige Texte.'
    ),
    'A free fast model with a 1M-token context.': (
        'Ein kostenloses, schnelles Modell mit 1\u202fM‑Token‑Kontext.'
    ),
    'Cheap and very fast general translation from Google.': (
        'Günstige und sehr schnelle allgemeine Übersetzung von Google.'
    ),
    'The cheapest fast Qwen model for bulk translation.': (
        'Das günstigste schnelle Qwen‑Modell für Massenübersetzung.'
    ),
    'Reliable general translation from OpenAI.': 'Zuverlässige allgemeine Übersetzung von OpenAI.',
    "OpenAI's flagship open model on Groq's fast inference.": (
        'OpenAIs Flaggschiff‑Open‑Modell mit schneller Inferenz von Groq.'
    ),
    'The fastest option for short texts.': 'Die schnellste Option für kurze Texte.',
    "Meta's proven general-purpose model.": 'Metas bewährtes Allzweck‑Modell.',
    'A fresh Qwen with strong translation; preview status.': (
        'Ein neuer Qwen mit starker Übersetzung; Vorschau‑Status.'
    ),
    'Around 3000 tokens per second — the fastest option for long texts.': (
        'Etwa 3000 Token pro Sekunde – die schnellste Option für lange Texte.'
    ),
    'A fast Qwen with good multilingual translation.': (
        'Ein schneller Qwen mit guter mehrsprachiger Übersetzung.'
    ),
    '33 languages': '33 Sprachen',
    '55 languages': '55 Sprachen',
    '23 languages': '23 Sprachen',
    'recommended': 'empfohlen',
    'light': 'leicht',
    'fast': 'schnell',
    'large': 'groß',
    'specialised': 'spezialisiert',
    'cheap': 'günstig',
    'cheapest': 'am günstigsten',
    'universal': 'universell',
    'slower': 'langsamer',
    'Free': 'Kostenlos',
    'Free tier': 'Kostenloser Tarif',
    'preview': 'Vorschau',
    'MoE': 'MoE',
    'translation': 'Übersetzung',
    'Local': 'Lokal',
    '≈4.6 GB': '≈4.6 GB',
    '≈3 GB': '≈3 GB',
    '≈8 GB': '≈8 GB',
    '~500 t/s': '~500 t/s',
    '~1000 t/s': '~1000 t/s',
    '~280 t/s': '~280 t/s',
    '~450 t/s': '~450 t/s',
    '~3000 t/s': '~3000 t/s',
    '~1850 t/s': '~1850 t/s',
    'Paste from clipboard': 'Aus Zwischenablage einfügen',
}

FRENCH: dict[str, str] = {
    'Could not open DeepL-oFM.': 'Impossible d’ouvrir DeepL-oFM.',
    'Quit DeepL-oFM if it is running, then try again.': (
        'Quittez DeepL-oFM s’il est ouvert, puis réessayez.'
    ),
    'More actions': 'Autres actions',
    'Remove file': 'Retirer le fichier',
    'Preparing file…': 'Préparation du fichier…',
    'Saving…': 'Enregistrement…',
    'Translation progress': 'Progression de la traduction',
    'Could not read or save translation history.': (
        'Impossible de lire ou d’enregistrer l’historique des traductions.'
    ),
    'Some paragraphs are still in the original language (%d).': (
        'Certains paragraphes sont encore dans la langue d’origine (%d).'
    ),
    'The server interrupted the response. Try again.': (
        'Le serveur a interrompu la réponse. Réessayez.'
    ),
    'The provider rejected the request. Check the API key and model in Settings.': (
        'Le fournisseur a refusé la demande. Vérifiez la clé API et le modèle dans les réglages.'
    ),
    'The provider is temporarily unavailable. Try again.': (
        'Le fournisseur est temporairement indisponible. Réessayez.'
    ),
    'Privacy policy': 'Politique de confidentialité',
    'Source language': 'Langue source',
    'Target language': 'Langue cible',
    'Fallback': 'Secours',
    'Too many requests. Wait a moment and try again.': (
        'Trop de demandes. Patientez un instant, puis réessayez.'
    ),
    'Improve clarity, grammar and style while keeping the meaning.': (
        'Améliorez la clarté, la grammaire et le style tout en gardant le sens.'
    ),
    'Improve in': 'Améliorer en',
    'Improve text': 'Améliorer le texte',
    'Improving…': 'Amélioration…',
    'Improved text will appear here': 'Le texte amélioré apparaîtra ici',
    'Type or paste text to improve': 'Saisissez ou collez le texte à améliorer',
    'Files': 'Fichiers',
    'Translate a document and save the result in its original format.': (
        'Traduisez un document et enregistrez le résultat dans son format d’origine.'
    ),
    'Drop a file here or choose one': 'Déposez un fichier ici ou choisissez-en un',
    'Supported formats: TXT, Markdown, PDF and DOCX.': (
        'Formats pris en charge : TXT, Markdown, PDF et DOCX.'
    ),
    'Choose a file…': 'Choisir un fichier…',
    'Translate to': 'Traduire vers',
    'Translation complete': 'Traduction terminée',
    'Translate another file': 'Traduire un autre fichier',
    'The file could not be translated.': 'Impossible de traduire le fichier.',
    'The file could not be saved.': 'Impossible d’enregistrer le fichier.',
    'Voice': 'Voix',
    'Automatic': 'Automatique',
    'Stop': 'Arrêter',
    (
        'The Dock icon appears while the window is open. Turn this on to keep it in the Dock all '
        'the time.'
    ): (
        'L’icône du Dock apparaît tant que la fenêtre est ouverte. Activez pour la garder en '
        'permanence.'
    ),
    (
        'For better voices, download Enhanced or Premium voices in System Settings → '
        'Accessibility → Spoken Content.'
    ): (
        'De meilleures voix se téléchargent dans Réglages Système → Accessibilité → Contenu '
        'énoncé → Voix du système.'
    ),
    'Done': 'Terminé',
    'Share': 'Partager',
    'Version': 'Version',
    'Source': 'Source',
    'Result': 'Résultat',
    'Add your API key in Settings.': 'Ajoutez votre clé API dans les Réglages.',
    'Cloud providers need an API key. For a server on your Wi-Fi network, choose Custom.': (
        'Les fournisseurs cloud demandent une clé API. Pour un serveur sur votre réseau Wi-Fi, '
        'choisissez « Personnalisé ».'
    ),
    'Dock icon': 'Icône du Dock',
    'Hide the Dock icon to keep DeepL-oFM in the menu bar only.': (
        'Masquez l’icône du Dock pour garder DeepL-oFM uniquement dans la barre des menus.'
    ),
    'Back to translation': 'Retour à la traduction',
    'File': 'Fichier',
    'Translate file…': 'Traduire un fichier…',
    'Save translation…': 'Enregistrer la traduction…',
    'Translated file': 'Fichier traduit',
    'Open a document': 'Ouvrir un document',
    'This file type is not supported.': "Ce type de fichier n'est pas pris en charge.",
    'The file could not be read.': 'Impossible de lire le fichier.',
    'No selectable text found. For a scanned PDF, run text recognition first.': (
        'Aucun texte sélectionnable. Pour un PDF scanné, commencez par reconnaître le texte.'
    ),
    'The Word document could not be processed.': 'Impossible de traiter le document Word.',
    'The translation could not be saved.': "Impossible d'enregistrer la traduction.",
    'Drop a file to translate': 'Déposez un fichier à traduire',
    'Preview': 'Aperçu',
    'Text only': 'Texte seul',
    'Markdown': 'Markdown',
    'Show plain text': 'Afficher le texte seul',
    'Copy translation (formatted text)': 'Copier la traduction (texte mis en forme)',
    'Copy translation (plain text)': 'Copier la traduction (texte brut)',
    'Copy translation (Markdown)': 'Copier la traduction (Markdown)',
    'Show rendered Markdown': 'Afficher le Markdown rendu',
    'Show Markdown source': 'Afficher la source Markdown',
    'Translate text': 'Traduire le texte',
    'History': 'Historique',
    'Settings': 'Paramètres',
    'Translation': 'Traduction',
    'Translate now': 'Traduire',
    'Translate clipboard': 'Traduire le presse-papiers',
    'Swap languages': 'Échanger les langues',
    'Copy translation': 'Copier la traduction',
    'Copy translation (Markdown + formatting)': 'Copier la traduction (Markdown + mise en forme)',
    'Copy': 'Copier',
    'Sample text': "Texte d'exemple",
    'Translation failed': 'Échec de la traduction',
    'Settings…': 'Paramètres…',
    'Connection status': 'État de la connexion',
    'Check connection': 'Vérifier la connexion',
    'Open DeepL-oFM': 'Ouvrir DeepL-oFM',
    'Quit': 'Quitter',
    'Translate clipboard (%@)': 'Traduire le presse-papiers (%@)',
    'Auto-detect': 'Détection automatique',
    'Style': 'Style',
    'Tone': 'Ton',
    'Auto': 'Auto',
    'Literal': 'Littéral',
    'Natural': 'Naturel',
    'Default': 'Par défaut',
    'Formal': 'Formel',
    'Casual': 'Décontracté',
    'The model picks a natural style': 'Le modèle choisit un style naturel',
    'Word for word, without free paraphrase': 'Mot à mot, sans paraphrase libre',
    'Conveys meaning rather than wording': 'Transmet le sens plutôt que les mots',
    'No extra tone': 'Pas de ton supplémentaire',
    'Formal and professional': 'Formel et professionnel',
    'Casual and conversational': 'Décontracté et conversationnel',
    'Enter or paste text…': 'Saisissez ou collez du texte…',
    'Translation will appear here': 'La traduction s’affichera ici',
    'Translating…': 'Traduction en cours…',
    'Translating… %d of %d': 'Traduction en cours… %d sur %d',
    'Retry': 'Réessayer',
    'Clear': 'Effacer',
    'Listen to the original': "Écouter l'original",
    'Copy the original': "Copier l'original",
    'Listen to the translation': 'Écouter la traduction',
    'Translate again': 'Traduire à nouveau',
    'Swap languages (⇧⌘S)': 'Échanger les langues (⇧⌘S)',
    'Checking connection…': 'Vérification de la connexion…',
    'Server unavailable': 'Serveur indisponible',
    'Model “%@” not found': 'Modèle «\u202f%@\u202f» introuvable',
    'Not checked yet': 'Pas encore vérifié',
    'Connection works. Model “%@” is available.': (
        'Connexion fonctionnelle. Modèle «\u202f%@\u202f» disponible.'
    ),
    'Server responds, but model “%@” is missing. Available: %@.': (
        'Le serveur répond, mais le modèle «\u202f%@\u202f» est absent. Disponibles\u202f: %@.'
    ),
    'Connection works.': 'Connexion fonctionnelle.',
    '%@ — translate clipboard': '%@ — traduire le presse‑papiers',
    '%@ — active': '%@ — actif',
    'Could not register %@. The shortcut may be taken.': (
        'Impossible d’enregistrer %@. Le raccourci est peut‑être déjà utilisé.'
    ),
    'Press a combination…': 'Appuyez sur une combinaison…',
    'Reset': 'Réinitialiser',
    'At least one modifier is required — ⌘, ⌥ or ⌃. Press Esc to cancel.': (
        'Au moins un modificateur est requis — ⌘, ⌥ ou ⌃. Appuyez sur Échap pour annuler.'
    ),
    'Hot key': 'Raccourci',
    'Copy text anywhere and press the shortcut — DeepL-oFM opens and translates the clipboard.': (
        'Copiez du texte n’importe où et appuyez sur le raccourci — DeepL-oFM s’ouvre et traduit '
        'le presse‑papiers.'
    ),
    'Select text in any app and press the shortcut — DeepL-oFM copies it and translates.': (
        'Sélectionnez du texte dans n’importe quelle application et appuyez sur le raccourci — '
        'DeepL-oFM le copie et le traduit.'
    ),
    'Translate selection': 'Traduire la sélection',
    'Translate selection (%@)': 'Traduire la sélection (%@)',
    'Selected text': 'Texte sélectionné',
    'Accessibility access': 'Accès à l’accessibilité',
    'Granted': 'Accordé',
    'Not granted': 'Non accordé',
    'Open System Settings': 'Ouvrir les paramètres système',
    'Check access': 'Vérifier l’accès',
    'Delete': 'Supprimer',
    'Forward Delete': 'Supprimer avant',
    'Examples: ⌥⌘T or ⌥⌘C.': 'Exemples\xa0: ⌥⌘T ou ⌥⌘C.',
    (
        'If access is already granted, remove DeepL-oFM from the Accessibility list and add the '
        'current app again — a permission from an older build does not apply.'
    ): (
        'Si l’accès est déjà accordé, retirez DeepL-oFM de la liste Accessibilité et ajoutez à '
        'nouveau l’application actuelle — une autorisation d’une version antérieure ne s’applique '
        'pas.'
    ),
    'Accessibility access is required to copy the selected text.': (
        'L’accès à l’accessibilité est requis pour copier le texte sélectionné.'
    ),
    'Could not copy the selected text. Check Accessibility access.': (
        'Impossible de copier le texte sélectionné. Vérifiez l’accès à l’accessibilité.'
    ),
    'Space': 'Espace',
    'key %d': 'touche %d',
    'Can be empty for local servers. Stored in the macOS Keychain, never in the repository.': (
        'Peut être vide pour les serveurs locaux. Stocké dans le Trousseau macOS, jamais dans le '
        'dépôt.'
    ),
    'DeepL-oFM — local translation': 'DeepL-oFM — traduction locale',
    'Other': 'Autre',
    'Custom': 'Personnalisé',
    'Ollama Cloud through a direct API key. No local server is needed.': (
        'Ollama Cloud via une clé API directe. Aucun serveur local n’est nécessaire.'
    ),
    'Connect': 'Connecter',
    'Models on the server': 'Modèles sur le serveur',
    'Filter by name': 'Filtrer par nom',
    'Refresh': 'Actualiser',
    'The server returned no models.': 'Le serveur n’a renvoyé aucun modèle.',
    'Select a model from the list or type its ID.': (
        'Sélectionnez un modèle dans la liste ou saisissez son ID.'
    ),
    'Models: %d': 'Modèles\xa0: %d',
    'Cloud': 'Cloud',
    'Gemma 4 in Ollama Cloud. Fast and strong for general translation.': (
        'Gemma 4 dans Ollama Cloud. Rapide et puissant pour la traduction générale.'
    ),
    'A fast cloud model from DeepSeek with a large context.': (
        'Un modèle cloud rapide de DeepSeek avec un grand contexte.'
    ),
    "Mistral's general-purpose model in Ollama Cloud.": (
        'Modèle polyvalent de Mistral dans Ollama Cloud.'
    ),
    "NVIDIA's high-throughput model for difficult texts.": (
        'Modèle à haut débit de NVIDIA pour les textes difficiles.'
    ),
    'Model and provider': 'Modèle et fournisseur',
    'Local models run offline and for free. Cloud models answer faster but need a key.': (
        'Les modèles locaux fonctionnent hors ligne et gratuitement. Les modèles cloud répondent '
        'plus rapidement mais nécessitent une clé.'
    ),
    'API key': 'Clé API',
    'Get key ↗': 'Obtenir la clé ↗',
    'Server address': 'Adresse du serveur',
    'Model': 'Modèle',
    'Model catalog…': 'Catalogue de modèles…',
    'For difficult texts, use Hy-MT2 30B or a cloud model.': (
        'Pour les textes difficiles, utilisez Hy-MT2 30B ou un modèle cloud.'
    ),
    'Fallback provider': 'Fournisseur de secours',
    'Used automatically when the primary provider fails.': (
        'Utilisé automatiquement lorsque le fournisseur principal échoue.'
    ),
    'Use a fallback provider': 'Utiliser un fournisseur de secours',
    'Provider': 'Fournisseur',
    'Load models': 'Charger les modèles',
    'Choose model': 'Choisir le modèle',
    'Choose a model': 'Choisir un modèle',
    'Uses the Keychain key for this provider.': 'Utilise la clé du trousseau pour ce fournisseur.',
    'If the primary provider fails, the same text is retried with these settings.': (
        'Si le fournisseur principal échoue, le même texte est retenté avec ces paramètres.'
    ),
    'Load the translator at launch': 'Charger le traducteur au lancement',
    'Connects to the provider, refreshes the model list and warms up a local model.': (
        'Se connecte au fournisseur, rafraîchit la liste des modèles et préchauffe un modèle '
        'local.'
    ),
    'Fallback provider works.': 'Le fournisseur de secours fonctionne.',
    'fallback': 'secours',
    'Generation parameters': 'Paramètres de génération',
    'Defaults match Tencent’s recommendations for Hy-MT2 7B.': (
        'Les valeurs par défaut correspondent aux recommandations de Tencent pour Hy-MT2 7B.'
    ),
    'Temperature': 'Température',
    'Repetition': 'Répétition',
    'Only this many most likely tokens are considered while decoding.': (
        'Seuls ce nombre de tokens les plus probables sont pris en compte lors du décodage.'
    ),
    'Context': 'Contexte',
    'Behavior': 'Comportement',
    'Translate automatically while typing': 'Traduire automatiquement pendant la saisie',
    'Delay': 'Délai',
    'Keep translation history': "Conserver l'historique des traductions",
    'Open at login': 'Ouvrir à l’ouverture de session',
    'Allow DeepL-oFM to open at login in System Settings.': (
        'Autorisez DeepL-oFM à s’ouvrir à l’ouverture de session dans les réglages système.'
    ),
    'Could not change Open at login. %@': (
        'Impossible de modifier le réglage d’ouverture à l’ouverture de session. %@'
    ),
    'Menu bar icon': 'Icône de la barre de menus',
    'Interface language': "Langue de l'interface",
    'System': 'Système',
    'System prompt': 'Invite système',
    (
        'Hy-MT2 has no system prompt: instruction and text go in one message. Wording follows the '
        'model card.'
    ): (
        "Hy-MT2 n'a pas d'invite système : l'instruction et le texte sont dans un seul message. "
        'Le libellé suit la fiche modèle.'
    ),
    'About': 'À propos',
    'local translator for macOS': 'traducteur local pour macOS',
    'Model: Hy-MT2 7B (Tencent Hy). License and model card on Hugging Face.': (
        'Modèle : Hy-MT2 7B (Tencent Hy). Licence et fiche modèle sur Hugging Face.'
    ),
    'Check for Updates…': 'Vérifier les mises à jour…',
    'Checking for updates…': 'Vérification des mises à jour…',
    "You're up to date.": 'Vous êtes à jour.',
    'Update available: %@': 'Mise à jour disponible : %@',
    'Update check failed: %@': 'Échec de la vérification des mises à jour : %@',
    'Automatically check for updates': 'Vérifier automatiquement les mises à jour',
    'Automatically download and install updates': (
        'Télécharger et installer automatiquement les mises à jour'
    ),
    'Updates are signed and notarized.': 'Les mises à jour sont signées et notariées.',
    'Project repository': 'Dépôt du projet',
    'DeepL-oFM on GitHub': 'DeepL-oFM sur GitHub',
    'Local Ollama server. The model must be pulled with ollama pull.': (
        'Serveur Ollama local. Le modèle doit être récupéré avec ollama pull.'
    ),
    'LM Studio with its local server enabled. The model ID is shown in LM Studio.': (
        "LM Studio avec son serveur local activé. L'ID du modèle est affiché dans LM Studio."
    ),
    'oMLX — an MLX server for Apple Silicon. Enable the OpenAI-compatible API.': (
        "oMLX — un serveur MLX pour Apple Silicon. Activez l'API compatible OpenAI."
    ),
    'llama-server with --api. The default address is port 8080.': (
        "llama-server avec --api. L'adresse par défaut est le port 8080."
    ),
    'Hundreds of models with one key. Free models are marked :free.': (
        'Des centaines de modèles avec une seule clé. Les modèles gratuits sont indiqués :free.'
    ),
    'Very fast cloud. Has a free tier with request limits.': (
        'Cloud très rapide. Propose un niveau gratuit avec des limites de requêtes.'
    ),
    'Fastest inference for open models. Has a free tier with limits.': (
        'Inférence la plus rapide pour les modèles ouverts. Niveau gratuit avec limites.'
    ),
    'Any OpenAI-compatible server: your proxy, vLLM, LocalAI, Together, and so on.': (
        'Tout serveur compatible OpenAI\u202f: votre proxy, vLLM, LocalAI, Together, etc.'
    ),
    'Model catalog': 'Catalogue de modèles',
    'Ready translators for local use and cloud options with free tiers.': (
        "Traducteurs prêts à l'emploi en local et options cloud avec niveaux gratuits."
    ),
    'Search model': 'Rechercher un modèle',
    'Free only': 'Gratuit uniquement',
    'Fetch from server': 'Récupérer depuis le serveur',
    'Nothing found': 'Aucun résultat',
    'Found on the server': 'Trouvé sur le serveur',
    'Recommended': 'Recommandé',
    'Models': 'Modèles',
    (
        'Need another model? Type its ID into the Model field — any model your server supports '
        'will work.'
    ): (
        "Besoin d'un autre modèle\u202f? Saisissez son ID dans le champ Modèle — tout modèle "
        'supporté par votre serveur fonctionnera.'
    ),
    'Choose': 'Choisir',
    'Copy install command': "Copier la commande d'installation",
    'Enter the API key for %@ in Settings first.': (
        "Entrez d'abord la clé API pour %@ dans les Réglages."
    ),
    'Search in history': "Rechercher dans l'historique",
    'Search language': 'Rechercher la langue',
    'Clear history?': "Effacer l'historique\xa0?",
    'Cancel': 'Annuler',
    'All saved translations will be deleted permanently.': (
        'Toutes les traductions enregistrées seront supprimées définitivement.'
    ),
    'History is empty': "L'historique est vide",
    'Translations will be saved here automatically.': (
        'Les traductions seront enregistrées ici automatiquement.'
    ),
    'Try another query.': 'Essayez une autre requête.',
    'Delete entry': "Supprimer l'entrée",
    'Invalid server URL: %@': 'URL du serveur invalide\xa0: %@',
    'Choose a model in Settings.': 'Choisissez un modèle dans les réglages.',
    'Could not connect to %@. Check that the server is running.': (
        'Impossible de se connecter à %@. Vérifiez que le serveur fonctionne.'
    ),
    'Server returned error %@.': "Le serveur a renvoyé l'erreur %@.",
    'Server returned error %@: %@': "Le serveur a renvoyé l'erreur %@\xa0: %@",
    'Model “%@” not found on the server.': 'Modèle «\xa0%@\xa0» introuvable sur le serveur.',
    'The model returned an empty translation. Try again.': (
        'Le modèle a renvoyé une traduction vide. Réessayez.'
    ),
    'The model could not translate this text. Try again or choose another model.': (
        'Le modèle n’a pas pu traduire ce texte. Réessayez ou choisissez un autre modèle.'
    ),
    'Some lines could not be translated (%d); they are left in the source language.': (
        "Certaines lignes n'ont pas pu être traduites (%d)\u202f; elles restent dans la langue "
        'source.'
    ),
    'Server returned an unexpected response.': 'Le serveur a renvoyé une réponse inattendue.',
    "Tencent's specialised translation model. The default for this app.": (
        "Modèle de traduction spécialisé de Tencent. Le modèle par défaut de l'application."
    ),
    'The same model in a lighter size: fast even on weaker Macs.': (
        'Le même modèle en version allégée\u202f: rapide même sur les Macs les plus faibles.'
    ),
    'The highest-quality MoE version. Needs a lot of memory.': (
        'Version MoE de la plus haute qualité. Nécessite beaucoup de mémoire.'
    ),
    "Google's translation model built on Gemma 3.": (
        'Modèle de traduction de Google basé sur Gemma\u202f3.'
    ),
    'A larger TranslateGemma for stronger machines.': (
        'Un TranslateGemma plus grand pour les machines puissantes.'
    ),
    'A compact model tuned only to translate — no explanations or reasoning.': (
        'Modèle compact réglé uniquement pour traduire — sans explications ni raisonnement.'
    ),
    "Cohere's multilingual model with a good speed-quality balance.": (
        'Modèle multilingue de Cohere avec un bon équilibre vitesse‑qualité.'
    ),
    'A general model; translates well but may add explanations.': (
        'Modèle général\u202f; traduit bien mais peut ajouter des explications.'
    ),
    'The same translation model in the cloud. Very cheap, no download.': (
        'Le même modèle de traduction dans le cloud. Très économique, aucun téléchargement.'
    ),
    'The cheapest Hy-MT2 option on OpenRouter.': "L'option Hy-MT2 la moins chère sur OpenRouter.",
    'The highest-quality Hy-MT2 version on OpenRouter.': (
        'La version Hy-MT2 de la plus haute qualité sur OpenRouter.'
    ),
    "Google's free model with a large context. Good general translation.": (
        'Modèle gratuit de Google avec un grand contexte. Bonne traduction générale.'
    ),
    'A free MoE version of Gemma 4: faster than 31B.': (
        'Version MoE gratuite de Gemma\u202f4\u202f: plus rapide que le 31B.'
    ),
    'A large free NVIDIA model for difficult texts.': (
        'Grand modèle NVIDIA gratuit pour les textes difficiles.'
    ),
    'A free fast model with a 1M-token context.': (
        'Modèle gratuit et rapide avec un contexte de 1\u202fM de tokens.'
    ),
    'Cheap and very fast general translation from Google.': (
        'Traduction générale bon marché et très rapide de Google.'
    ),
    'The cheapest fast Qwen model for bulk translation.': (
        'Le modèle Qwen rapide le moins cher pour la traduction en masse.'
    ),
    'Reliable general translation from OpenAI.': "Traduction générale fiable d'OpenAI.",
    "OpenAI's flagship open model on Groq's fast inference.": (
        "Le modèle open phare d'OpenAI sur l'inférence rapide de Groq."
    ),
    'The fastest option for short texts.': "L'option la plus rapide pour les courts textes.",
    "Meta's proven general-purpose model.": 'Le modèle polyvalent éprouvé de Meta.',
    'A fresh Qwen with strong translation; preview status.': (
        'Un Qwen récent avec une traduction puissante\u202f; statut aperçu.'
    ),
    'Around 3000 tokens per second — the fastest option for long texts.': (
        "Environ 3000 jetons par seconde — l'option la plus rapide pour les longs textes."
    ),
    'A fast Qwen with good multilingual translation.': (
        'Un Qwen rapide avec une bonne traduction multilingue.'
    ),
    '33 languages': '33 langues',
    '55 languages': '55 langues',
    '23 languages': '23 langues',
    'recommended': 'recommandé',
    'light': 'léger',
    'fast': 'rapide',
    'large': 'grand',
    'specialised': 'spécialisé',
    'cheap': 'pas cher',
    'cheapest': 'le moins cher',
    'universal': 'universel',
    'slower': 'plus lent',
    'Free': 'Gratuit',
    'Free tier': 'Niveau gratuit',
    'preview': 'aperçu',
    'MoE': 'MoE',
    'translation': 'traduction',
    'Local': 'Local',
    '≈4.6 GB': '≈4.6 GB',
    '≈3 GB': '≈3 GB',
    '≈8 GB': '≈8 GB',
    '~500 t/s': '~500 t/s',
    '~1000 t/s': '~1000 t/s',
    '~280 t/s': '~280 t/s',
    '~450 t/s': '~450 t/s',
    '~3000 t/s': '~3000 t/s',
    '~1850 t/s': '~1850 t/s',
    'Paste from clipboard': 'Coller depuis le presse-papiers',
}

SPANISH: dict[str, str] = {
    'Could not open DeepL-oFM.': 'No se pudo abrir DeepL-oFM.',
    'Quit DeepL-oFM if it is running, then try again.': (
        'Cierra DeepL-oFM si está abierto y vuelve a intentarlo.'
    ),
    'More actions': 'Más acciones',
    'Remove file': 'Quitar archivo',
    'Preparing file…': 'Preparando el archivo…',
    'Saving…': 'Guardando…',
    'Translation progress': 'Progreso de la traducción',
    'Could not read or save translation history.': (
        'No se pudo leer o guardar el historial de traducciones.'
    ),
    'Some paragraphs are still in the original language (%d).': (
        'Algunos párrafos siguen en el idioma original (%d).'
    ),
    'The server interrupted the response. Try again.': (
        'El servidor interrumpió la respuesta. Vuelve a intentarlo.'
    ),
    'The provider rejected the request. Check the API key and model in Settings.': (
        'El proveedor rechazó la solicitud. Revisa la clave API y el modelo en los ajustes.'
    ),
    'The provider is temporarily unavailable. Try again.': (
        'El proveedor no está disponible. Vuelve a intentarlo.'
    ),
    'Privacy policy': 'Política de privacidad',
    'Source language': 'Idioma de origen',
    'Target language': 'Idioma de destino',
    'Fallback': 'Respaldo',
    'Too many requests. Wait a moment and try again.': (
        'Demasiadas solicitudes. Espera un momento y vuelve a intentarlo.'
    ),
    'Improve clarity, grammar and style while keeping the meaning.': (
        'Mejora la claridad, la gramática y el estilo sin cambiar el significado.'
    ),
    'Improve in': 'Mejorar en',
    'Improve text': 'Mejorar texto',
    'Improving…': 'Mejorando…',
    'Improved text will appear here': 'El texto mejorado aparecerá aquí',
    'Type or paste text to improve': 'Escribe o pega el texto que quieres mejorar',
    'Files': 'Archivos',
    'Translate a document and save the result in its original format.': (
        'Traduce un documento y guarda el resultado en su formato original.'
    ),
    'Drop a file here or choose one': 'Suelta un archivo aquí o elige uno',
    'Supported formats: TXT, Markdown, PDF and DOCX.': (
        'Formatos compatibles: TXT, Markdown, PDF y DOCX.'
    ),
    'Choose a file…': 'Elegir un archivo…',
    'Translate to': 'Traducir a',
    'Translation complete': 'Traducción completada',
    'Translate another file': 'Traducir otro archivo',
    'The file could not be translated.': 'No se pudo traducir el archivo.',
    'The file could not be saved.': 'No se pudo guardar el archivo.',
    'Voice': 'Voz',
    'Automatic': 'Automático',
    'Stop': 'Detener',
    (
        'The Dock icon appears while the window is open. Turn this on to keep it in the Dock all '
        'the time.'
    ): (
        'El icono del Dock aparece mientras la ventana está abierta. Actívalo para mantenerlo '
        'siempre.'
    ),
    (
        'For better voices, download Enhanced or Premium voices in System Settings → '
        'Accessibility → Spoken Content.'
    ): (
        'Puedes descargar mejores voces en Ajustes del Sistema → Accesibilidad → Contenido '
        'hablado → Voz del sistema.'
    ),
    'Done': 'Listo',
    'Share': 'Compartir',
    'Version': 'Versión',
    'Source': 'Origen',
    'Result': 'Resultado',
    'Add your API key in Settings.': 'Añade tu clave API en Ajustes.',
    'Cloud providers need an API key. For a server on your Wi-Fi network, choose Custom.': (
        'Los proveedores en la nube requieren una clave API. Para un servidor en tu red Wi-Fi, '
        'elige «Personalizado».'
    ),
    'Dock icon': 'Icono del Dock',
    'Hide the Dock icon to keep DeepL-oFM in the menu bar only.': (
        'Oculta el icono del Dock para mantener DeepL-oFM solo en la barra de menús.'
    ),
    'Back to translation': 'Volver a la traducción',
    'File': 'Archivo',
    'Translate file…': 'Traducir archivo…',
    'Save translation…': 'Guardar traducción…',
    'Translated file': 'Archivo traducido',
    'Open a document': 'Abrir un documento',
    'This file type is not supported.': 'Este tipo de archivo no es compatible.',
    'The file could not be read.': 'No se pudo leer el archivo.',
    'No selectable text found. For a scanned PDF, run text recognition first.': (
        'No hay texto seleccionable. Si el PDF es un escaneo, usa primero el reconocimiento de '
        'texto.'
    ),
    'The Word document could not be processed.': 'No se pudo procesar el documento de Word.',
    'The translation could not be saved.': 'No se pudo guardar la traducción.',
    'Drop a file to translate': 'Suelta un archivo para traducir',
    'Preview': 'Vista previa',
    'Text only': 'Solo texto',
    'Markdown': 'Markdown',
    'Show plain text': 'Mostrar solo texto',
    'Copy translation (formatted text)': 'Copiar traducción (texto con formato)',
    'Copy translation (plain text)': 'Copiar traducción (texto sin formato)',
    'Copy translation (Markdown)': 'Copiar traducción (Markdown)',
    'Show rendered Markdown': 'Mostrar Markdown renderizado',
    'Show Markdown source': 'Mostrar código Markdown',
    'Translate text': 'Traducir texto',
    'History': 'Historial',
    'Settings': 'Configuración',
    'Translation': 'Traducción',
    'Translate now': 'Traducir',
    'Translate clipboard': 'Traducir portapapeles',
    'Swap languages': 'Intercambiar idiomas',
    'Copy translation': 'Copiar traducción',
    'Copy translation (Markdown + formatting)': 'Copiar traducción (Markdown + formato)',
    'Copy': 'Copiar',
    'Sample text': 'Texto de ejemplo',
    'Translation failed': 'Error en la traducción',
    'Settings…': 'Configuración…',
    'Connection status': 'Estado de la conexión',
    'Check connection': 'Comprobar conexión',
    'Open DeepL-oFM': 'Abrir DeepL-oFM',
    'Quit': 'Salir',
    'Translate clipboard (%@)': 'Traducir portapapeles (%@)',
    'Auto-detect': 'Detección automática',
    'Style': 'Estilo',
    'Tone': 'Tono',
    'Auto': 'Automático',
    'Literal': 'Literal',
    'Natural': 'Natural',
    'Default': 'Predeterminado',
    'Formal': 'Formal',
    'Casual': 'Informal',
    'The model picks a natural style': 'El modelo elige un estilo natural',
    'Word for word, without free paraphrase': 'Palabra por palabra, sin paráfrasis libre',
    'Conveys meaning rather than wording': 'Transmite el significado más que la redacción',
    'No extra tone': 'Sin tono adicional',
    'Formal and professional': 'Formal y profesional',
    'Casual and conversational': 'Informal y conversacional',
    'Enter or paste text…': 'Introduce o pega texto…',
    'Translation will appear here': 'Aquí aparecerá la traducción',
    'Translating…': 'Traduciendo…',
    'Translating… %d of %d': 'Traduciendo… %d de %d',
    'Retry': 'Reintentar',
    'Clear': 'Borrar',
    'Listen to the original': 'Escuchar el original',
    'Copy the original': 'Copiar el original',
    'Listen to the translation': 'Escuchar la traducción',
    'Translate again': 'Traducir de nuevo',
    'Swap languages (⇧⌘S)': 'Cambiar idiomas (⇧⌘S)',
    'Checking connection…': 'Comprobando conexión…',
    'Server unavailable': 'Servidor no disponible',
    'Model “%@” not found': 'Modelo “%@” no encontrado',
    'Not checked yet': 'Aún no verificado',
    'Connection works. Model “%@” is available.': (
        'La conexión funciona. Modelo “%@” está disponible.'
    ),
    'Server responds, but model “%@” is missing. Available: %@.': (
        'El servidor responde, pero el modelo “%@” falta. Disponibles: %@.'
    ),
    'Connection works.': 'La conexión funciona.',
    '%@ — translate clipboard': '%@ — traducir portapapeles',
    '%@ — active': '%@ — activo',
    'Could not register %@. The shortcut may be taken.': (
        'No se pudo registrar %@. Es posible que el atajo ya esté en uso.'
    ),
    'Press a combination…': 'Presiona una combinación…',
    'Reset': 'Restablecer',
    'At least one modifier is required — ⌘, ⌥ or ⌃. Press Esc to cancel.': (
        'Se requiere al menos un modificador — ⌘, ⌥ o ⌃. Presiona Esc para cancelar.'
    ),
    'Hot key': 'Tecla rápida',
    'Copy text anywhere and press the shortcut — DeepL-oFM opens and translates the clipboard.': (
        'Copia texto en cualquier lugar y pulsa el atajo — DeepL-oFM se abre y traduce el '
        'portapapeles.'
    ),
    'Select text in any app and press the shortcut — DeepL-oFM copies it and translates.': (
        'Selecciona texto en cualquier aplicación y pulsa el atajo — DeepL-oFM lo copia y lo '
        'traduce.'
    ),
    'Translate selection': 'Traducir selección',
    'Translate selection (%@)': 'Traducir selección (%@)',
    'Selected text': 'Texto seleccionado',
    'Accessibility access': 'Acceso de accesibilidad',
    'Granted': 'Concedido',
    'Not granted': 'No concedido',
    'Open System Settings': 'Abrir Configuración del Sistema',
    'Check access': 'Verificar acceso',
    'Delete': 'Eliminar',
    'Forward Delete': 'Eliminar hacia adelante',
    'Examples: ⌥⌘T or ⌥⌘C.': 'Ejemplos: ⌥⌘T o ⌥⌘C.',
    (
        'If access is already granted, remove DeepL-oFM from the Accessibility list and add the '
        'current app again — a permission from an older build does not apply.'
    ): (
        'Si el acceso ya está concedido, elimine DeepL-oFM de la lista de Accesibilidad y añada '
        'la aplicación actual nuevamente — un permiso de una versión anterior no se aplica.'
    ),
    'Accessibility access is required to copy the selected text.': (
        'Se requiere acceso de accesibilidad para copiar el texto seleccionado.'
    ),
    'Could not copy the selected text. Check Accessibility access.': (
        'No se pudo copiar el texto seleccionado. Verifique el acceso de accesibilidad.'
    ),
    'Space': 'Espacio',
    'key %d': 'tecla %d',
    'Can be empty for local servers. Stored in the macOS Keychain, never in the repository.': (
        'Puede estar vacío para servidores locales. Almacenado en el llavero de macOS, nunca en '
        'el repositorio.'
    ),
    'DeepL-oFM — local translation': 'DeepL-oFM — traducción local',
    'Other': 'Otro',
    'Custom': 'Personalizado',
    'Ollama Cloud through a direct API key. No local server is needed.': (
        'Ollama Cloud mediante una clave API directa. No se necesita servidor local.'
    ),
    'Connect': 'Conectar',
    'Models on the server': 'Modelos en el servidor',
    'Filter by name': 'Filtrar por nombre',
    'Refresh': 'Actualizar',
    'The server returned no models.': 'El servidor no devolvió modelos.',
    'Select a model from the list or type its ID.': (
        'Seleccione un modelo de la lista o escriba su ID.'
    ),
    'Models: %d': 'Modelos: %d',
    'Cloud': 'Nube',
    'Gemma 4 in Ollama Cloud. Fast and strong for general translation.': (
        'Gemma 4 en Ollama Cloud. Rápido y potente para traducción general.'
    ),
    'A fast cloud model from DeepSeek with a large context.': (
        'Un modelo en la nube rápido de DeepSeek con un gran contexto.'
    ),
    "Mistral's general-purpose model in Ollama Cloud.": (
        'Modelo de propósito general de Mistral en Ollama Cloud.'
    ),
    "NVIDIA's high-throughput model for difficult texts.": (
        'Modelo de alto rendimiento de NVIDIA para textos difíciles.'
    ),
    'Model and provider': 'Modelo y proveedor',
    'Local models run offline and for free. Cloud models answer faster but need a key.': (
        'Los modelos locales funcionan sin conexión y gratis. Los modelos en la nube responden '
        'más rápido pero requieren una clave.'
    ),
    'API key': 'Clave API',
    'Get key ↗': 'Obtener clave ↗',
    'Server address': 'Dirección del servidor',
    'Model': 'Modelo',
    'Model catalog…': 'Catálogo de modelos…',
    'For difficult texts, use Hy-MT2 30B or a cloud model.': (
        'Para textos difíciles, usa Hy-MT2 30B o un modelo en la nube.'
    ),
    'Fallback provider': 'Proveedor de respaldo',
    'Used automatically when the primary provider fails.': (
        'Se usa automáticamente cuando falla el proveedor principal.'
    ),
    'Use a fallback provider': 'Usar un proveedor de respaldo',
    'Provider': 'Proveedor',
    'Load models': 'Cargar modelos',
    'Choose model': 'Elegir modelo',
    'Choose a model': 'Elige un modelo',
    'Uses the Keychain key for this provider.': 'Usa la clave del Keychain para este proveedor.',
    'If the primary provider fails, the same text is retried with these settings.': (
        'Si falla el proveedor principal, el mismo texto se reintenta con esta configuración.'
    ),
    'Load the translator at launch': 'Cargar el traductor al iniciar',
    'Connects to the provider, refreshes the model list and warms up a local model.': (
        'Conecta al proveedor, actualiza la lista de modelos y inicia un modelo local.'
    ),
    'Fallback provider works.': 'El proveedor de respaldo funciona.',
    'fallback': 'respaldo',
    'Generation parameters': 'Parámetros de generación',
    'Defaults match Tencent’s recommendations for Hy-MT2 7B.': (
        'Los valores predeterminados coinciden con las recomendaciones de Tencent para Hy-MT2 7B.'
    ),
    'Temperature': 'Temperatura',
    'Repetition': 'Repetición',
    'Only this many most likely tokens are considered while decoding.': (
        'Solo se consideran este número de tokens más probables durante la decodificación.'
    ),
    'Context': 'Contexto',
    'Behavior': 'Comportamiento',
    'Translate automatically while typing': 'Traducir automáticamente mientras se escribe',
    'Delay': 'Retardo',
    'Keep translation history': 'Mantener historial de traducciones',
    'Open at login': 'Abrir al iniciar sesión',
    'Allow DeepL-oFM to open at login in System Settings.': (
        'Permite que DeepL-oFM se abra al iniciar sesión en Configuración del Sistema.'
    ),
    'Could not change Open at login. %@': (
        'No se pudo cambiar el ajuste de apertura al iniciar sesión. %@'
    ),
    'Menu bar icon': 'Icono de la barra de menús',
    'Interface language': 'Idioma de la interfaz',
    'System': 'Sistema',
    'System prompt': 'Prompt del sistema',
    (
        'Hy-MT2 has no system prompt: instruction and text go in one message. Wording follows the '
        'model card.'
    ): (
        'Hy-MT2 no tiene prompt del sistema: la instrucción y el texto van en un solo mensaje. La '
        'redacción sigue la tarjeta del modelo.'
    ),
    'About': 'Acerca de',
    'local translator for macOS': 'traductor local para macOS',
    'Model: Hy-MT2 7B (Tencent Hy). License and model card on Hugging Face.': (
        'Modelo: Hy-MT2 7B (Tencent Hy). Licencia y ficha del modelo en Hugging Face.'
    ),
    'Check for Updates…': 'Buscar actualizaciones…',
    'Checking for updates…': 'Comprobando actualizaciones…',
    "You're up to date.": 'Estás al día.',
    'Update available: %@': 'Actualización disponible: %@',
    'Update check failed: %@': 'Error al comprobar actualizaciones: %@',
    'Automatically check for updates': 'Comprobar actualizaciones automáticamente',
    'Automatically download and install updates': (
        'Descargar e instalar actualizaciones automáticamente'
    ),
    'Updates are signed and notarized.': 'Las actualizaciones están firmadas y notariadas.',
    'Project repository': 'Repositorio del proyecto',
    'DeepL-oFM on GitHub': 'DeepL-oFM en GitHub',
    'Local Ollama server. The model must be pulled with ollama pull.': (
        'Servidor local de Ollama. El modelo debe descargarse con ollama pull.'
    ),
    'LM Studio with its local server enabled. The model ID is shown in LM Studio.': (
        'LM Studio con su servidor local habilitado. El ID del modelo se muestra en LM Studio.'
    ),
    'oMLX — an MLX server for Apple Silicon. Enable the OpenAI-compatible API.': (
        'oMLX — un servidor MLX para Apple Silicon. Habilita la API compatible con OpenAI.'
    ),
    'llama-server with --api. The default address is port 8080.': (
        'llama-server con --api. La dirección predeterminada es el puerto 8080.'
    ),
    'Hundreds of models with one key. Free models are marked :free.': (
        'Cientos de modelos con una sola clave. Los modelos gratuitos están marcados como :free.'
    ),
    'Very fast cloud. Has a free tier with request limits.': (
        'Nube muy rápida. Tiene un nivel gratuito con límites de solicitudes.'
    ),
    'Fastest inference for open models. Has a free tier with limits.': (
        'La inferencia más rápida para modelos abiertos. Tiene un nivel gratuito con límites.'
    ),
    'Any OpenAI-compatible server: your proxy, vLLM, LocalAI, Together, and so on.': (
        'Cualquier servidor compatible con OpenAI: tu proxy, vLLM, LocalAI, Together, etc.'
    ),
    'Model catalog': 'Catálogo de modelos',
    'Ready translators for local use and cloud options with free tiers.': (
        'Traductores listos para uso local y opciones en la nube con niveles gratuitos.'
    ),
    'Search model': 'Buscar modelo',
    'Free only': 'Solo gratuitos',
    'Fetch from server': 'Obtener del servidor',
    'Nothing found': 'No se encontró nada',
    'Found on the server': 'Encontrado en el servidor',
    'Recommended': 'Recomendado',
    'Models': 'Modelos',
    (
        'Need another model? Type its ID into the Model field — any model your server supports '
        'will work.'
    ): (
        '¿Necesitas otro modelo? Escribe su ID en el campo Modelo — cualquier modelo que soporte '
        'tu servidor funcionará.'
    ),
    'Choose': 'Seleccionar',
    'Copy install command': 'Copiar comando de instalación',
    'Enter the API key for %@ in Settings first.': (
        'Introduce primero la clave API para %@ en Configuración.'
    ),
    'Search in history': 'Buscar en el historial',
    'Search language': 'Buscar idioma',
    'Clear history?': '¿Borrar historial?',
    'Cancel': 'Cancelar',
    'All saved translations will be deleted permanently.': (
        'Todas las traducciones guardadas se eliminarán permanentemente.'
    ),
    'History is empty': 'El historial está vacío',
    'Translations will be saved here automatically.': (
        'Las traducciones se guardarán aquí automáticamente.'
    ),
    'Try another query.': 'Intenta otra consulta.',
    'Delete entry': 'Eliminar entrada',
    'Invalid server URL: %@': 'URL del servidor no válida: %@',
    'Choose a model in Settings.': 'Elige un modelo en los ajustes.',
    'Could not connect to %@. Check that the server is running.': (
        'No se pudo conectar a %@. Verifica que el servidor esté en funcionamiento.'
    ),
    'Server returned error %@.': 'El servidor devolvió el error %@.',
    'Server returned error %@: %@': 'El servidor devolvió el error %@: %@',
    'Model “%@” not found on the server.': 'Modelo “%@” no encontrado en el servidor.',
    'The model returned an empty translation. Try again.': (
        'El modelo devolvió una traducción vacía. Inténtalo de nuevo.'
    ),
    'The model could not translate this text. Try again or choose another model.': (
        'El modelo no pudo traducir este texto. Vuelve a intentarlo o elige otro modelo.'
    ),
    'Some lines could not be translated (%d); they are left in the source language.': (
        'Algunas líneas no se pudieron traducir (%d); se dejan en el idioma original.'
    ),
    'Server returned an unexpected response.': 'El servidor devolvió una respuesta inesperada.',
    "Tencent's specialised translation model. The default for this app.": (
        'Modelo de traducción especializado de Tencent. El predeterminado para esta aplicación.'
    ),
    'The same model in a lighter size: fast even on weaker Macs.': (
        'El mismo modelo en una versión más ligera: rápido incluso en Macs más débiles.'
    ),
    'The highest-quality MoE version. Needs a lot of memory.': (
        'La versión MoE de mayor calidad. Requiere mucha memoria.'
    ),
    "Google's translation model built on Gemma 3.": (
        'Modelo de traducción de Google basado en Gemma 3.'
    ),
    'A larger TranslateGemma for stronger machines.': (
        'Un TranslateGemma más grande para máquinas más potentes.'
    ),
    'A compact model tuned only to translate — no explanations or reasoning.': (
        'Un modelo compacto ajustado solo para traducir — sin explicaciones ni razonamiento.'
    ),
    "Cohere's multilingual model with a good speed-quality balance.": (
        'Modelo multilingüe de Cohere con buen equilibrio entre velocidad y calidad.'
    ),
    'A general model; translates well but may add explanations.': (
        'Un modelo general; traduce bien pero puede añadir explicaciones.'
    ),
    'The same translation model in the cloud. Very cheap, no download.': (
        'El mismo modelo de traducción en la nube. Muy barato, sin descarga.'
    ),
    'The cheapest Hy-MT2 option on OpenRouter.': 'La opción Hy-MT2 más barata en OpenRouter.',
    'The highest-quality Hy-MT2 version on OpenRouter.': (
        'La versión Hy-MT2 de mayor calidad en OpenRouter.'
    ),
    "Google's free model with a large context. Good general translation.": (
        'Modelo gratuito de Google con gran contexto. Buena traducción general.'
    ),
    'A free MoE version of Gemma 4: faster than 31B.': (
        'Versión MoE gratuita de Gemma 4: más rápida que 31B.'
    ),
    'A large free NVIDIA model for difficult texts.': (
        'Modelo grande y gratuito de NVIDIA para textos difíciles.'
    ),
    'A free fast model with a 1M-token context.': (
        'Modelo gratuito y rápido con contexto de 1\u202fM de tokens.'
    ),
    'Cheap and very fast general translation from Google.': (
        'Traducción general barata y muy rápida de Google.'
    ),
    'The cheapest fast Qwen model for bulk translation.': (
        'El modelo Qwen rápido más barato para traducción masiva.'
    ),
    'Reliable general translation from OpenAI.': 'Traducción general fiable de OpenAI.',
    "OpenAI's flagship open model on Groq's fast inference.": (
        'Modelo insignia abierto de OpenAI en la inferencia rápida de Groq.'
    ),
    'The fastest option for short texts.': 'La opción más rápida para textos cortos.',
    "Meta's proven general-purpose model.": 'Modelo de propósito general probado de Meta.',
    'A fresh Qwen with strong translation; preview status.': (
        'Un Qwen nuevo con traducción potente; estado de vista previa.'
    ),
    'Around 3000 tokens per second — the fastest option for long texts.': (
        'Alrededor de 3000 tokens por segundo — la opción más rápida para textos largos.'
    ),
    'A fast Qwen with good multilingual translation.': (
        'Un Qwen rápido con buena traducción multilingüe.'
    ),
    '33 languages': '33 idiomas',
    '55 languages': '55 idiomas',
    '23 languages': '23 idiomas',
    'recommended': 'recomendado',
    'light': 'ligero',
    'fast': 'rápido',
    'large': 'grande',
    'specialised': 'especializado',
    'cheap': 'barato',
    'cheapest': 'más barato',
    'universal': 'universal',
    'slower': 'más lento',
    'Free': 'Gratis',
    'Free tier': 'Nivel gratuito',
    'preview': 'Vista previa',
    'MoE': 'MoE',
    'translation': 'traducción',
    'Local': 'Local',
    '≈4.6 GB': '≈4.6 GB',
    '≈3 GB': '≈3 GB',
    '≈8 GB': '≈8 GB',
    '~500 t/s': '~500 t/s',
    '~1000 t/s': '~1000 t/s',
    '~280 t/s': '~280 t/s',
    '~450 t/s': '~450 t/s',
    '~3000 t/s': '~3000 t/s',
    '~1850 t/s': '~1850 t/s',
    'Paste from clipboard': 'Pegar desde el portapapeles',
}

POLISH: dict[str, str] = {
    'Could not open DeepL-oFM.': 'Nie udało się otworzyć DeepL-oFM.',
    'Quit DeepL-oFM if it is running, then try again.': (
        'Jeśli DeepL-oFM jest otwarty, zamknij go i spróbuj ponownie.'
    ),
    'More actions': 'Więcej działań',
    'Remove file': 'Usuń plik',
    'Preparing file…': 'Przygotowywanie pliku…',
    'Saving…': 'Zapisywanie…',
    'Translation progress': 'Postęp tłumaczenia',
    'Could not read or save translation history.': (
        'Nie udało się odczytać ani zapisać historii tłumaczeń.'
    ),
    'Some paragraphs are still in the original language (%d).': (
        'Niektóre akapity pozostały w języku oryginału (%d).'
    ),
    'The server interrupted the response. Try again.': (
        'Serwer przerwał odpowiedź. Spróbuj ponownie.'
    ),
    'The provider rejected the request. Check the API key and model in Settings.': (
        'Dostawca odrzucił żądanie. Sprawdź klucz API i model w ustawieniach.'
    ),
    'The provider is temporarily unavailable. Try again.': (
        'Dostawca jest chwilowo niedostępny. Spróbuj ponownie.'
    ),
    'Privacy policy': 'Polityka prywatności',
    'Source language': 'Język źródłowy',
    'Target language': 'Język docelowy',
    'Fallback': 'Zapas',
    'Too many requests. Wait a moment and try again.': (
        'Za dużo żądań. Poczekaj chwilę i spróbuj ponownie.'
    ),
    'Improve clarity, grammar and style while keeping the meaning.': (
        'Popraw klarowność, gramatykę i styl, zachowując sens.'
    ),
    'Improve in': 'Popraw w języku',
    'Improve text': 'Popraw tekst',
    'Improving…': 'Poprawianie…',
    'Improved text will appear here': 'Poprawiony tekst pojawi się tutaj',
    'Type or paste text to improve': 'Wpisz lub wklej tekst do poprawy',
    'Files': 'Pliki',
    'Translate a document and save the result in its original format.': (
        'Przetłumacz dokument i zapisz wynik w oryginalnym formacie.'
    ),
    'Drop a file here or choose one': 'Przeciągnij plik tutaj lub wybierz go',
    'Supported formats: TXT, Markdown, PDF and DOCX.': (
        'Obsługiwane formaty: TXT, Markdown, PDF i DOCX.'
    ),
    'Choose a file…': 'Wybierz plik…',
    'Translate to': 'Przetłumacz na',
    'Translation complete': 'Tłumaczenie gotowe',
    'Translate another file': 'Przetłumacz inny plik',
    'The file could not be translated.': 'Nie udało się przetłumaczyć pliku.',
    'The file could not be saved.': 'Nie udało się zapisać pliku.',
    'Voice': 'Głos',
    'Automatic': 'Automatycznie',
    'Stop': 'Zatrzymaj',
    (
        'The Dock icon appears while the window is open. Turn this on to keep it in the Dock all '
        'the time.'
    ): (
        'Ikona w Docku pojawia się, gdy okno jest otwarte. Włącz, aby pozostała tam na stałe.'
    ),
    (
        'For better voices, download Enhanced or Premium voices in System Settings → '
        'Accessibility → Spoken Content.'
    ): (
        'Lepsze głosy można pobrać w Ustawieniach systemowych → Dostępność → Treść mówiona → Głos '
        'systemowy.'
    ),
    'Done': 'Gotowe',
    'Share': 'Udostępnij',
    'Version': 'Wersja',
    'Source': 'Źródło',
    'Result': 'Wynik',
    'Add your API key in Settings.': 'Dodaj klucz API w Ustawieniach.',
    'Cloud providers need an API key. For a server on your Wi-Fi network, choose Custom.': (
        'Dostawcy chmurowi wymagają klucza API. Dla serwera w twojej sieci Wi-Fi wybierz „Własny”.'
    ),
    'Dock icon': 'Ikona w Docku',
    'Hide the Dock icon to keep DeepL-oFM in the menu bar only.': (
        'Ukryj ikonę w Docku, aby DeepL-oFM pozostał tylko w pasku menu.'
    ),
    'Back to translation': 'Powrót do tłumaczenia',
    'File': 'Plik',
    'Translate file…': 'Przetłumacz plik…',
    'Save translation…': 'Zapisz tłumaczenie…',
    'Translated file': 'Przetłumaczony plik',
    'Open a document': 'Otwórz dokument',
    'This file type is not supported.': 'Ten typ pliku nie jest obsługiwany.',
    'The file could not be read.': 'Nie udało się odczytać pliku.',
    'No selectable text found. For a scanned PDF, run text recognition first.': (
        'Brak tekstu do zaznaczenia. Jeśli PDF jest skanem, najpierw użyj rozpoznawania tekstu.'
    ),
    'The Word document could not be processed.': 'Nie udało się przetworzyć dokumentu Word.',
    'The translation could not be saved.': 'Nie udało się zapisać tłumaczenia.',
    'Drop a file to translate': 'Przeciągnij plik do tłumaczenia',
    'Preview': 'Podgląd',
    'Text only': 'Tylko tekst',
    'Markdown': 'Markdown',
    'Show plain text': 'Pokaż tylko tekst',
    'Copy translation (formatted text)': 'Skopiuj tłumaczenie (tekst sformatowany)',
    'Copy translation (plain text)': 'Skopiuj tłumaczenie (tekst jawny)',
    'Copy translation (Markdown)': 'Skopiuj tłumaczenie (Markdown)',
    'Show rendered Markdown': 'Pokaż wyrenderowany Markdown',
    'Show Markdown source': 'Pokaż źródło Markdown',
    'Translate text': 'Przetłumacz tekst',
    'History': 'Historia',
    'Settings': 'Ustawienia',
    'Translation': 'Tłumaczenie',
    'Translate now': 'Przetłumacz',
    'Translate clipboard': 'Przetłumacz schowek',
    'Swap languages': 'Zamień języki',
    'Copy translation': 'Skopiuj tłumaczenie',
    'Copy translation (Markdown + formatting)': 'Skopiuj tłumaczenie (Markdown + formatowanie)',
    'Copy': 'Kopiuj',
    'Sample text': 'Przykładowy tekst',
    'Translation failed': 'Tłumaczenie nie powiodło się',
    'Settings…': 'Ustawienia…',
    'Connection status': 'Status połączenia',
    'Check connection': 'Sprawdź połączenie',
    'Open DeepL-oFM': 'Otwórz DeepL-oFM',
    'Quit': 'Zakończ',
    'Translate clipboard (%@)': 'Przetłumacz schowek (%@)',
    'Auto-detect': 'Automatyczne wykrywanie',
    'Style': 'Styl',
    'Tone': 'Ton',
    'Auto': 'Automatyczny',
    'Literal': 'Dosłowny',
    'Natural': 'Naturalny',
    'Default': 'Domyślny',
    'Formal': 'Formalny',
    'Casual': 'Swobodny',
    'The model picks a natural style': 'Model wybiera styl naturalny',
    'Word for word, without free paraphrase': 'Słowo w słowo, bez swobodnej parafrazy',
    'Conveys meaning rather than wording': 'Przekazuje znaczenie, a nie dosłowne słowa',
    'No extra tone': 'Brak dodatkowego tonu',
    'Formal and professional': 'Formalny i profesjonalny',
    'Casual and conversational': 'Swobodny i konwersacyjny',
    'Enter or paste text…': 'Wpisz lub wklej tekst…',
    'Translation will appear here': 'Tutaj pojawi się tłumaczenie',
    'Translating…': 'Tłumaczenie…',
    'Translating… %d of %d': 'Tłumaczenie… %d z %d',
    'Retry': 'Ponów',
    'Clear': 'Wyczyść',
    'Listen to the original': 'Odsłuchaj oryginał',
    'Copy the original': 'Skopiuj oryginał',
    'Listen to the translation': 'Odsłuchaj tłumaczenie',
    'Translate again': 'Przetłumacz ponownie',
    'Swap languages (⇧⌘S)': 'Zamień języki (⇧⌘S)',
    'Checking connection…': 'Sprawdzanie połączenia…',
    'Server unavailable': 'Serwer niedostępny',
    'Model “%@” not found': 'Model “%@” nie znaleziono',
    'Not checked yet': 'Jeszcze nie sprawdzono',
    'Connection works. Model “%@” is available.': 'Połączenie działa. Model “%@” jest dostępny.',
    'Server responds, but model “%@” is missing. Available: %@.': (
        'Serwer odpowiada, ale model “%@” jest nieobecny. Dostępne: %@.'
    ),
    'Connection works.': 'Połączenie działa.',
    '%@ — translate clipboard': '%@ — tłumacz schowek',
    '%@ — active': '%@ — aktywny',
    'Could not register %@. The shortcut may be taken.': (
        'Nie udało się zarejestrować %@. Skrót może być już zajęty.'
    ),
    'Press a combination…': 'Naciśnij kombinację…',
    'Reset': 'Resetuj',
    'At least one modifier is required — ⌘, ⌥ or ⌃. Press Esc to cancel.': (
        'Wymagany jest przynajmniej jeden modyfikator — ⌘, ⌥ lub ⌃. Naciśnij Esc, aby anulować.'
    ),
    'Hot key': 'Skrót klawiszowy',
    'Copy text anywhere and press the shortcut — DeepL-oFM opens and translates the clipboard.': (
        'Skopiuj tekst w dowolnym miejscu i naciśnij skrót — DeepL-oFM otwiera się i tłumaczy '
        'schowek.'
    ),
    'Select text in any app and press the shortcut — DeepL-oFM copies it and translates.': (
        'Zaznacz tekst w dowolnej aplikacji i naciśnij skrót — DeepL-oFM kopiuje go i tłumaczy.'
    ),
    'Translate selection': 'Przetłumacz zaznaczenie',
    'Translate selection (%@)': 'Przetłumacz zaznaczenie (%@)',
    'Selected text': 'Zaznaczony tekst',
    'Accessibility access': 'Dostęp do funkcji dostępności',
    'Granted': 'Przyznano',
    'Not granted': 'Nie przyznano',
    'Open System Settings': 'Otwórz ustawienia systemowe',
    'Check access': 'Sprawdź dostęp',
    'Delete': 'Usuń',
    'Forward Delete': 'Usuń w przód',
    'Examples: ⌥⌘T or ⌥⌘C.': 'Przykłady: ⌥⌘T lub ⌥⌘C.',
    (
        'If access is already granted, remove DeepL-oFM from the Accessibility list and add the '
        'current app again — a permission from an older build does not apply.'
    ): (
        'Jeśli dostęp jest już przyznany, usuń DeepL-oFM z listy dostępności i ponownie dodaj '
        'bieżącą aplikację — uprawnienie z wcześniejszej wersji nie obowiązuje.'
    ),
    'Accessibility access is required to copy the selected text.': (
        'Dostęp do funkcji dostępności jest wymagany, aby skopiować zaznaczony tekst.'
    ),
    'Could not copy the selected text. Check Accessibility access.': (
        'Nie udało się skopiować zaznaczonego tekstu. Sprawdź dostęp do funkcji dostępności.'
    ),
    'Space': 'Spacja',
    'key %d': 'klawisz %d',
    'Can be empty for local servers. Stored in the macOS Keychain, never in the repository.': (
        'Może być puste dla serwerów lokalnych. Przechowywane w pęku kluczy macOS, nigdy w '
        'repozytorium.'
    ),
    'DeepL-oFM — local translation': 'DeepL-oFM — tłumaczenie lokalne',
    'Other': 'Inne',
    'Custom': 'Niestandardowe',
    'Ollama Cloud through a direct API key. No local server is needed.': (
        'Ollama Cloud przy użyciu bezpośredniego klucza API. Nie jest potrzebny lokalny serwer.'
    ),
    'Connect': 'Połącz',
    'Models on the server': 'Modele na serwerze',
    'Filter by name': 'Filtruj według nazwy',
    'Refresh': 'Odśwież',
    'The server returned no models.': 'Serwer nie zwrócił żadnych modeli.',
    'Select a model from the list or type its ID.': 'Wybierz model z listy lub wpisz jego ID.',
    'Models: %d': 'Modele: %d',
    'Cloud': 'Chmura',
    'Gemma 4 in Ollama Cloud. Fast and strong for general translation.': (
        'Gemma 4 w Ollama Cloud. Szybka i wydajna do ogólnego tłumaczenia.'
    ),
    'A fast cloud model from DeepSeek with a large context.': (
        'Szybki model w chmurze od DeepSeek z dużym kontekstem.'
    ),
    "Mistral's general-purpose model in Ollama Cloud.": (
        'Model ogólnego przeznaczenia Mistrala w Ollama Cloud.'
    ),
    "NVIDIA's high-throughput model for difficult texts.": (
        'Model NVIDIA o wysokiej przepustowości do trudnych tekstów.'
    ),
    'Model and provider': 'Model i dostawca',
    'Local models run offline and for free. Cloud models answer faster but need a key.': (
        'Modele lokalne działają offline i za darmo. Modele w chmurze odpowiadają szybciej, ale '
        'wymagają klucza.'
    ),
    'API key': 'Klucz API',
    'Get key ↗': 'Pobierz klucz ↗',
    'Server address': 'Adres serwera',
    'Model': 'Model',
    'Model catalog…': 'Katalog modeli…',
    'For difficult texts, use Hy-MT2 30B or a cloud model.': (
        'Do trudnych tekstów użyj Hy-MT2 30B lub modelu w chmurze.'
    ),
    'Fallback provider': 'Dostawca zapasowy',
    'Used automatically when the primary provider fails.': (
        'Używany automatycznie, gdy główny dostawca zawiedzie.'
    ),
    'Use a fallback provider': 'Użyj dostawcy zapasowego',
    'Provider': 'Dostawca',
    'Load models': 'Wczytaj modele',
    'Choose model': 'Wybierz model',
    'Choose a model': 'Wybierz model',
    'Uses the Keychain key for this provider.': 'Używa klucza Keychain dla tego dostawcy.',
    'If the primary provider fails, the same text is retried with these settings.': (
        'Jeśli główny dostawca zawiedzie, ten sam tekst zostanie ponownie przetworzony z tymi '
        'ustawieniami.'
    ),
    'Load the translator at launch': 'Wczytaj tłumacza przy uruchomieniu',
    'Connects to the provider, refreshes the model list and warms up a local model.': (
        'Łączy się z dostawcą, odświeża listę modeli i przygotowuje lokalny model.'
    ),
    'Fallback provider works.': 'Dostawca zapasowy działa.',
    'fallback': 'zapasowy',
    'Generation parameters': 'Parametry generacji',
    'Defaults match Tencent’s recommendations for Hy-MT2 7B.': (
        'Domyślne wartości odpowiadają zaleceniom Tencent dla Hy-MT2 7B.'
    ),
    'Temperature': 'Temperatura',
    'Repetition': 'Powtórzenia',
    'Only this many most likely tokens are considered while decoding.': (
        'Tylko tyle najbardziej prawdopodobnych tokenów jest brane pod uwagę podczas dekodowania.'
    ),
    'Context': 'Kontekst',
    'Behavior': 'Zachowanie',
    'Translate automatically while typing': 'Tłumacz automatycznie podczas pisania',
    'Delay': 'Opóźnienie',
    'Keep translation history': 'Zachowuj historię tłumaczeń',
    'Open at login': 'Otwieraj przy logowaniu',
    'Allow DeepL-oFM to open at login in System Settings.': (
        'Zezwól na otwieranie DeepL-oFM przy logowaniu w Ustawieniach systemowych.'
    ),
    'Could not change Open at login. %@': (
        'Nie udało się zmienić ustawienia otwierania przy logowaniu. %@'
    ),
    'Menu bar icon': 'Ikona paska menu',
    'Interface language': 'Język interfejsu',
    'System': 'System',
    'System prompt': 'Prompt systemowy',
    (
        'Hy-MT2 has no system prompt: instruction and text go in one message. Wording follows the '
        'model card.'
    ): (
        'Hy-MT2 nie ma promptu systemowego: instrukcja i tekst są w jednej wiadomości. '
        'Sformułowanie zgodne z kartą modelu.'
    ),
    'About': 'O programie',
    'local translator for macOS': 'lokalny tłumacz dla macOS',
    'Model: Hy-MT2 7B (Tencent Hy). License and model card on Hugging Face.': (
        'Model: Hy-MT2 7B (Tencent Hy). Licencja i karta modelu na Hugging Face.'
    ),
    'Check for Updates…': 'Sprawdź aktualizacje…',
    'Checking for updates…': 'Sprawdzanie aktualizacji…',
    "You're up to date.": 'Jesteś na bieżąco.',
    'Update available: %@': 'Dostępna aktualizacja: %@',
    'Update check failed: %@': 'Sprawdzenie aktualizacji nie powiodło się: %@',
    'Automatically check for updates': 'Automatycznie sprawdzaj aktualizacje',
    'Automatically download and install updates': 'Automatycznie pobieraj i instaluj aktualizacje',
    'Updates are signed and notarized.': 'Aktualizacje są podpisane i notaryzowane.',
    'Project repository': 'Repozytorium projektu',
    'DeepL-oFM on GitHub': 'DeepL-oFM na GitHub',
    'Local Ollama server. The model must be pulled with ollama pull.': (
        'Lokalny serwer Ollama. Model musi być pobrany poleceniem ollama pull.'
    ),
    'LM Studio with its local server enabled. The model ID is shown in LM Studio.': (
        'LM Studio z włączonym lokalnym serwerem. ID modelu jest wyświetlane w LM Studio.'
    ),
    'oMLX — an MLX server for Apple Silicon. Enable the OpenAI-compatible API.': (
        'oMLX — serwer MLX dla Apple Silicon. Włącz API zgodne z OpenAI.'
    ),
    'llama-server with --api. The default address is port 8080.': (
        'llama-server z opcją --api. Domyślny adres to port 8080.'
    ),
    'Hundreds of models with one key. Free models are marked :free.': (
        'Setki modeli przy jednym kluczu. Darmowe modele są oznaczone :free.'
    ),
    'Very fast cloud. Has a free tier with request limits.': (
        'Bardzo szybka chmura. Posiada darmowy poziom z limitami zapytań.'
    ),
    'Fastest inference for open models. Has a free tier with limits.': (
        'Najszybsze wnioskowanie dla otwartych modeli. Posiada darmowy poziom z limitami.'
    ),
    'Any OpenAI-compatible server: your proxy, vLLM, LocalAI, Together, and so on.': (
        'Dowolny serwer zgodny z OpenAI: Twój proxy, vLLM, LocalAI, Together i inne.'
    ),
    'Model catalog': 'Katalog modeli',
    'Ready translators for local use and cloud options with free tiers.': (
        'Gotowe tłumacze do użytku lokalnego i w chmurze z darmowymi planami.'
    ),
    'Search model': 'Wyszukaj model',
    'Free only': 'Tylko darmowe',
    'Fetch from server': 'Pobierz z serwera',
    'Nothing found': 'Nic nie znaleziono',
    'Found on the server': 'Znaleziono na serwerze',
    'Recommended': 'Polecane',
    'Models': 'Modele',
    (
        'Need another model? Type its ID into the Model field — any model your server supports '
        'will work.'
    ): (
        'Potrzebujesz innego modelu? Wpisz jego ID w polu Model — każdy model obsługiwany przez '
        'serwer będzie działał.'
    ),
    'Choose': 'Wybierz',
    'Copy install command': 'Skopiuj polecenie instalacji',
    'Enter the API key for %@ in Settings first.': (
        'Najpierw wprowadź klucz API dla %@ w Ustawieniach.'
    ),
    'Search in history': 'Szukaj w historii',
    'Search language': 'Język wyszukiwania',
    'Clear history?': 'Wyczyścić historię?',
    'Cancel': 'Anuluj',
    'All saved translations will be deleted permanently.': (
        'Wszystkie zapisane tłumaczenia zostaną trwale usunięte.'
    ),
    'History is empty': 'Historia jest pusta',
    'Translations will be saved here automatically.': (
        'Tłumaczenia będą tutaj zapisywane automatycznie.'
    ),
    'Try another query.': 'Spróbuj innego zapytania.',
    'Delete entry': 'Usuń wpis',
    'Invalid server URL: %@': 'Nieprawidłowy URL serwera: %@',
    'Choose a model in Settings.': 'Wybierz model w ustawieniach.',
    'Could not connect to %@. Check that the server is running.': (
        'Nie można połączyć się z %@. Sprawdź, czy serwer działa.'
    ),
    'Server returned error %@.': 'Serwer zwrócił błąd %@.',
    'Server returned error %@: %@': 'Serwer zwrócił błąd %@: %@',
    'Model “%@” not found on the server.': 'Model „%@” nie został znaleziony na serwerze.',
    'The model returned an empty translation. Try again.': (
        'Model zwrócił puste tłumaczenie. Spróbuj ponownie.'
    ),
    'The model could not translate this text. Try again or choose another model.': (
        'Model nie przetłumaczył tego tekstu. Spróbuj ponownie lub wybierz inny model.'
    ),
    'Some lines could not be translated (%d); they are left in the source language.': (
        'Nie udało się przetłumaczyć niektórych linii (%d); pozostają w języku źródłowym.'
    ),
    'Server returned an unexpected response.': 'Serwer zwrócił nieoczekiwaną odpowiedź.',
    "Tencent's specialised translation model. The default for this app.": (
        'Specjalistyczny model tłumaczeniowy Tencent. Domyślny w tej aplikacji.'
    ),
    'The same model in a lighter size: fast even on weaker Macs.': (
        'Ten sam model w lżejszej wersji: szybki nawet na słabszych Macach.'
    ),
    'The highest-quality MoE version. Needs a lot of memory.': (
        'Najwyższej jakości wersja MoE. Wymaga dużo pamięci.'
    ),
    "Google's translation model built on Gemma 3.": 'Model tłumaczeniowy Google oparty na Gemma 3.',
    'A larger TranslateGemma for stronger machines.': (
        'Większy TranslateGemma dla mocniejszych maszyn.'
    ),
    'A compact model tuned only to translate — no explanations or reasoning.': (
        'Kompaktowy model przeznaczony wyłącznie do tłumaczenia — bez wyjaśnień i rozumowania.'
    ),
    "Cohere's multilingual model with a good speed-quality balance.": (
        'Wielojęzyczny model Cohere o dobrym stosunku szybkości do jakości.'
    ),
    'A general model; translates well but may add explanations.': (
        'Model ogólny; dobrze tłumaczy, ale może dodawać wyjaśnienia.'
    ),
    'The same translation model in the cloud. Very cheap, no download.': (
        'Ten sam model tłumaczenia w chmurze. Bardzo tani, bez pobierania.'
    ),
    'The cheapest Hy-MT2 option on OpenRouter.': 'Najtańsza opcja Hy-MT2 na OpenRouter.',
    'The highest-quality Hy-MT2 version on OpenRouter.': (
        'Najwyższej jakości wersja Hy-MT2 na OpenRouter.'
    ),
    "Google's free model with a large context. Good general translation.": (
        'Darmowy model Google z dużym kontekstem. Dobre tłumaczenie ogólne.'
    ),
    'A free MoE version of Gemma 4: faster than 31B.': (
        'Darmowa wersja MoE Gemma 4: szybsza niż 31B.'
    ),
    'A large free NVIDIA model for difficult texts.': (
        'Duży, darmowy model NVIDIA do trudnych tekstów.'
    ),
    'A free fast model with a 1M-token context.': 'Darmowy, szybki model z kontekstem 1M tokenów.',
    'Cheap and very fast general translation from Google.': (
        'Tanie i bardzo szybkie tłumaczenie ogólne od Google.'
    ),
    'The cheapest fast Qwen model for bulk translation.': (
        'Najtańszy szybki model Qwen do tłumaczenia masowego.'
    ),
    'Reliable general translation from OpenAI.': 'Niezawodne tłumaczenie ogólne od OpenAI.',
    "OpenAI's flagship open model on Groq's fast inference.": (
        'Flagowy otwarty model OpenAI na szybkiej inferencji Groq.'
    ),
    'The fastest option for short texts.': 'Najszybsza opcja dla krótkich tekstów.',
    "Meta's proven general-purpose model.": 'Sprawdzony model ogólnego przeznaczenia Meta.',
    'A fresh Qwen with strong translation; preview status.': (
        'Nowy Qwen z silnym tłumaczeniem; status podglądu.'
    ),
    'Around 3000 tokens per second — the fastest option for long texts.': (
        'Około 3000 tokenów na sekundę — najszybsza opcja dla długich tekstów.'
    ),
    'A fast Qwen with good multilingual translation.': (
        'Szybki Qwen z dobrą wielojęzyczną translacją.'
    ),
    '33 languages': '33 języki',
    '55 languages': '55 języków',
    '23 languages': '23 języki',
    'recommended': 'zalecane',
    'light': 'lekki',
    'fast': 'szybki',
    'large': 'duży',
    'specialised': 'specjalistyczny',
    'cheap': 'tani',
    'cheapest': 'najtańszy',
    'universal': 'uniwersalny',
    'slower': 'wolniejszy',
    'Free': 'Darmowy',
    'Free tier': 'Darmowy poziom',
    'preview': 'podgląd',
    'MoE': 'MoE',
    'translation': 'tłumaczenie',
    'Local': 'Lokalny',
    '≈4.6 GB': '≈4.6 GB',
    '≈3 GB': '≈3 GB',
    '≈8 GB': '≈8 GB',
    '~500 t/s': '~500 t/s',
    '~1000 t/s': '~1000 t/s',
    '~280 t/s': '~280 t/s',
    '~450 t/s': '~450 t/s',
    '~3000 t/s': '~3000 t/s',
    '~1850 t/s': '~1850 t/s',
    'Paste from clipboard': 'Wklej ze schowka',
}

PORTUGUESE: dict[str, str] = {
    'Could not open DeepL-oFM.': 'Não foi possível abrir o DeepL-oFM.',
    'Quit DeepL-oFM if it is running, then try again.': (
        'Se o DeepL-oFM estiver aberto, feche-o e tente novamente.'
    ),
    'More actions': 'Mais ações',
    'Remove file': 'Remover ficheiro',
    'Preparing file…': 'A preparar o ficheiro…',
    'Saving…': 'A guardar…',
    'Translation progress': 'Progresso da tradução',
    'Could not read or save translation history.': (
        'Não foi possível ler ou guardar o histórico de traduções.'
    ),
    'Some paragraphs are still in the original language (%d).': (
        'Alguns parágrafos continuam no idioma original (%d).'
    ),
    'The server interrupted the response. Try again.': (
        'O servidor interrompeu a resposta. Tente novamente.'
    ),
    'The provider rejected the request. Check the API key and model in Settings.': (
        'O fornecedor recusou o pedido. Verifique a chave API e o modelo nas definições.'
    ),
    'The provider is temporarily unavailable. Try again.': (
        'O fornecedor está temporariamente indisponível. Tente novamente.'
    ),
    'Privacy policy': 'Política de privacidade',
    'Source language': 'Idioma de origem',
    'Target language': 'Idioma de destino',
    'Fallback': 'Reserva',
    'Too many requests. Wait a moment and try again.': (
        'Demasiados pedidos. Aguarde um momento e tente novamente.'
    ),
    'Improve clarity, grammar and style while keeping the meaning.': (
        'Melhore a clareza, a gramática e o estilo mantendo o significado.'
    ),
    'Improve in': 'Melhorar em',
    'Improve text': 'Melhorar texto',
    'Improving…': 'A melhorar…',
    'Improved text will appear here': 'O texto melhorado aparecerá aqui',
    'Type or paste text to improve': 'Escreva ou cole o texto a melhorar',
    'Files': 'Ficheiros',
    'Translate a document and save the result in its original format.': (
        'Traduza um documento e guarde o resultado no formato original.'
    ),
    'Drop a file here or choose one': 'Arraste um ficheiro para aqui ou escolha um',
    'Supported formats: TXT, Markdown, PDF and DOCX.': (
        'Formatos suportados: TXT, Markdown, PDF e DOCX.'
    ),
    'Choose a file…': 'Escolher um ficheiro…',
    'Translate to': 'Traduzir para',
    'Translation complete': 'Tradução concluída',
    'Translate another file': 'Traduzir outro ficheiro',
    'The file could not be translated.': 'Não foi possível traduzir o ficheiro.',
    'The file could not be saved.': 'Não foi possível guardar o ficheiro.',
    'Voice': 'Voz',
    'Automatic': 'Automático',
    'Stop': 'Parar',
    (
        'The Dock icon appears while the window is open. Turn this on to keep it in the Dock all '
        'the time.'
    ): (
        'O ícone no Dock aparece enquanto a janela está aberta. Ative para o manter sempre.'
    ),
    (
        'For better voices, download Enhanced or Premium voices in System Settings → '
        'Accessibility → Spoken Content.'
    ): (
        'Pode transferir vozes melhores em Definições do Sistema → Acessibilidade → Conteúdo '
        'falado → Voz do sistema.'
    ),
    'Done': 'Concluído',
    'Share': 'Partilhar',
    'Version': 'Versão',
    'Source': 'Origem',
    'Result': 'Resultado',
    'Add your API key in Settings.': 'Adicione a sua chave API nas Definições.',
    'Cloud providers need an API key. For a server on your Wi-Fi network, choose Custom.': (
        'Os fornecedores na nuvem pedem uma chave API. Para um servidor na sua rede Wi-Fi, '
        'escolha «Personalizado».'
    ),
    'Dock icon': 'Ícone no Dock',
    'Hide the Dock icon to keep DeepL-oFM in the menu bar only.': (
        'Oculte o ícone no Dock para manter o DeepL-oFM apenas na barra de menus.'
    ),
    'Back to translation': 'Voltar à tradução',
    'File': 'Arquivo',
    'Translate file…': 'Traduzir arquivo…',
    'Save translation…': 'Salvar tradução…',
    'Translated file': 'Arquivo traduzido',
    'Open a document': 'Abrir documento',
    'This file type is not supported.': 'Este tipo de arquivo não é compatível.',
    'The file could not be read.': 'Não foi possível ler o arquivo.',
    'No selectable text found. For a scanned PDF, run text recognition first.': (
        'Não foi encontrado texto selecionável. Se o PDF for digitalizado, use primeiro o '
        'reconhecimento de texto.'
    ),
    'The Word document could not be processed.': 'Não foi possível processar o documento do Word.',
    'The translation could not be saved.': 'Não foi possível salvar a tradução.',
    'Drop a file to translate': 'Solte um arquivo para traduzir',
    'Preview': 'Pré-visualização',
    'Text only': 'Somente texto',
    'Markdown': 'Markdown',
    'Show plain text': 'Mostrar somente texto',
    'Copy translation (formatted text)': 'Copiar tradução (texto formatado)',
    'Copy translation (plain text)': 'Copiar tradução (texto simples)',
    'Copy translation (Markdown)': 'Copiar tradução (Markdown)',
    'Show rendered Markdown': 'Mostrar Markdown renderizado',
    'Show Markdown source': 'Mostrar código Markdown',
    'Translate text': 'Traduzir texto',
    'History': 'Histórico',
    'Settings': 'Configurações',
    'Translation': 'Tradução',
    'Translate now': 'Traduzir',
    'Translate clipboard': 'Traduzir área de transferência',
    'Swap languages': 'Trocar idiomas',
    'Copy translation': 'Copiar tradução',
    'Copy translation (Markdown + formatting)': 'Copiar tradução (Markdown + formatação)',
    'Copy': 'Copiar',
    'Sample text': 'Texto de exemplo',
    'Translation failed': 'Falha na tradução',
    'Settings…': 'Configurações…',
    'Connection status': 'Status da conexão',
    'Check connection': 'Verificar conexão',
    'Open DeepL-oFM': 'Abrir DeepL-oFM',
    'Quit': 'Sair',
    'Translate clipboard (%@)': 'Traduzir área de transferência (%@)',
    'Auto-detect': 'Detecção automática',
    'Style': 'Estilo',
    'Tone': 'Tom',
    'Auto': 'Automático',
    'Literal': 'Literal',
    'Natural': 'Natural',
    'Default': 'Padrão',
    'Formal': 'Formal',
    'Casual': 'Casual',
    'The model picks a natural style': 'O modelo escolhe um estilo natural',
    'Word for word, without free paraphrase': 'Palavra por palavra, sem paráfrase livre',
    'Conveys meaning rather than wording': 'Transmite o sentido em vez da formulação',
    'No extra tone': 'Sem tom adicional',
    'Formal and professional': 'Formal e profissional',
    'Casual and conversational': 'Casual e conversacional',
    'Enter or paste text…': 'Insira ou cole o texto…',
    'Translation will appear here': 'A tradução aparece aqui',
    'Translating…': 'Traduzindo…',
    'Translating… %d of %d': 'Traduzindo… %d de %d',
    'Retry': 'Repetir',
    'Clear': 'Limpar',
    'Listen to the original': 'Ouvir o original',
    'Copy the original': 'Copiar o original',
    'Listen to the translation': 'Ouvir a tradução',
    'Translate again': 'Traduzir novamente',
    'Swap languages (⇧⌘S)': 'Trocar idiomas (⇧⌘S)',
    'Checking connection…': 'Verificando conexão…',
    'Server unavailable': 'Servidor indisponível',
    'Model “%@” not found': 'Modelo “%@” não encontrado',
    'Not checked yet': 'Ainda não verificado',
    'Connection works. Model “%@” is available.': 'Conexão funciona. Modelo “%@” está disponível.',
    'Server responds, but model “%@” is missing. Available: %@.': (
        'Servidor responde, mas o modelo “%@” está ausente. Disponíveis: %@.'
    ),
    'Connection works.': 'Conexão funciona.',
    '%@ — translate clipboard': '%@ — traduzir área de transferência',
    '%@ — active': '%@ — ativo',
    'Could not register %@. The shortcut may be taken.': (
        'Não foi possível registrar %@. O atalho pode estar em uso.'
    ),
    'Press a combination…': 'Pressione uma combinação…',
    'Reset': 'Redefinir',
    'At least one modifier is required — ⌘, ⌥ or ⌃. Press Esc to cancel.': (
        'É necessário ao menos um modificador — ⌘, ⌥ ou ⌃. Pressione Esc para cancelar.'
    ),
    'Hot key': 'Tecla de atalho',
    'Copy text anywhere and press the shortcut — DeepL-oFM opens and translates the clipboard.': (
        'Copie texto em qualquer lugar e pressione o atalho — DeepL-oFM abre e traduz a área de '
        'transferência.'
    ),
    'Select text in any app and press the shortcut — DeepL-oFM copies it and translates.': (
        'Selecione texto em qualquer aplicativo e pressione o atalho — DeepL-oFM copia e traduz.'
    ),
    'Translate selection': 'Traduzir seleção',
    'Translate selection (%@)': 'Traduzir seleção (%@)',
    'Selected text': 'Texto selecionado',
    'Accessibility access': 'Acesso à Acessibilidade',
    'Granted': 'Concedido',
    'Not granted': 'Não concedido',
    'Open System Settings': 'Abrir Configurações do Sistema',
    'Check access': 'Verificar acesso',
    'Delete': 'Excluir',
    'Forward Delete': 'Excluir à frente',
    'Examples: ⌥⌘T or ⌥⌘C.': 'Exemplos: ⌥⌘T ou ⌥⌘C.',
    (
        'If access is already granted, remove DeepL-oFM from the Accessibility list and add the '
        'current app again — a permission from an older build does not apply.'
    ): (
        'Se o acesso já estiver concedido, remova o DeepL-oFM da lista de Acessibilidade e '
        'adicione o aplicativo atual novamente — uma permissão de uma versão anterior não se '
        'aplica.'
    ),
    'Accessibility access is required to copy the selected text.': (
        'É necessário acesso à Acessibilidade para copiar o texto selecionado.'
    ),
    'Could not copy the selected text. Check Accessibility access.': (
        'Não foi possível copiar o texto selecionado. Verifique o acesso à Acessibilidade.'
    ),
    'Space': 'Espaço',
    'key %d': 'tecla %d',
    'Can be empty for local servers. Stored in the macOS Keychain, never in the repository.': (
        'Pode ficar vazio para servidores locais. Armazenado no Keychain do macOS, nunca no '
        'repositório.'
    ),
    'DeepL-oFM — local translation': 'DeepL-oFM — tradução local',
    'Other': 'Outro',
    'Custom': 'Personalizado',
    'Ollama Cloud through a direct API key. No local server is needed.': (
        'Ollama Cloud via chave de API direta. Nenhum servidor local é necessário.'
    ),
    'Connect': 'Conectar',
    'Models on the server': 'Modelos no servidor',
    'Filter by name': 'Filtrar por nome',
    'Refresh': 'Atualizar',
    'The server returned no models.': 'O servidor não retornou modelos.',
    'Select a model from the list or type its ID.': (
        'Selecione um modelo da lista ou digite seu ID.'
    ),
    'Models: %d': 'Modelos: %d',
    'Cloud': 'Nuvem',
    'Gemma 4 in Ollama Cloud. Fast and strong for general translation.': (
        'Gemma 4 no Ollama Cloud. Rápido e potente para tradução geral.'
    ),
    'A fast cloud model from DeepSeek with a large context.': (
        'Um modelo de nuvem rápido da DeepSeek com um grande contexto.'
    ),
    "Mistral's general-purpose model in Ollama Cloud.": (
        'Modelo de uso geral da Mistral no Ollama Cloud.'
    ),
    "NVIDIA's high-throughput model for difficult texts.": (
        'Modelo de alta taxa de transferência da NVIDIA para textos difíceis.'
    ),
    'Model and provider': 'Modelo e provedor',
    'Local models run offline and for free. Cloud models answer faster but need a key.': (
        'Modelos locais funcionam offline e são gratuitos. Modelos de nuvem respondem mais '
        'rápido, mas precisam de uma chave.'
    ),
    'API key': 'Chave API',
    'Get key ↗': 'Obter chave ↗',
    'Server address': 'Endereço do servidor',
    'Model': 'Modelo',
    'Model catalog…': 'Catálogo de modelos…',
    'For difficult texts, use Hy-MT2 30B or a cloud model.': (
        'Para textos difíceis, use Hy-MT2 30B ou um modelo de nuvem.'
    ),
    'Fallback provider': 'Provedor de fallback',
    'Used automatically when the primary provider fails.': (
        'Usado automaticamente quando o provedor principal falha.'
    ),
    'Use a fallback provider': 'Usar um provedor de fallback',
    'Provider': 'Provedor',
    'Load models': 'Carregar modelos',
    'Choose model': 'Escolher modelo',
    'Choose a model': 'Escolher um modelo',
    'Uses the Keychain key for this provider.': 'Usa a chave do Keychain para este provedor.',
    'If the primary provider fails, the same text is retried with these settings.': (
        'Se o provedor principal falhar, o mesmo texto será reenviado com estas configurações.'
    ),
    'Load the translator at launch': 'Carregar o tradutor ao iniciar',
    'Connects to the provider, refreshes the model list and warms up a local model.': (
        'Conecta ao provedor, atualiza a lista de modelos e prepara um modelo local.'
    ),
    'Fallback provider works.': 'O provedor de fallback funciona.',
    'fallback': 'fallback',
    'Generation parameters': 'Parâmetros de geração',
    'Defaults match Tencent’s recommendations for Hy-MT2 7B.': (
        'Os padrões correspondem às recomendações da Tencent para Hy-MT2 7B.'
    ),
    'Temperature': 'Temperatura',
    'Repetition': 'Repetição',
    'Only this many most likely tokens are considered while decoding.': (
        'Apenas este número de tokens mais prováveis é considerado durante a decodificação.'
    ),
    'Context': 'Contexto',
    'Behavior': 'Comportamento',
    'Translate automatically while typing': 'Traduzir automaticamente enquanto digita',
    'Delay': 'Atraso',
    'Keep translation history': 'Manter histórico de traduções',
    'Open at login': 'Abrir ao iniciar sessão',
    'Allow DeepL-oFM to open at login in System Settings.': (
        'Permita que o DeepL-oFM abra ao iniciar sessão nas Definições do Sistema.'
    ),
    'Could not change Open at login. %@': (
        'Não foi possível alterar a opção de abrir ao iniciar sessão. %@'
    ),
    'Menu bar icon': 'Ícone da barra de menus',
    'Interface language': 'Idioma da interface',
    'System': 'Sistema',
    'System prompt': 'Prompt do sistema',
    (
        'Hy-MT2 has no system prompt: instruction and text go in one message. Wording follows the '
        'model card.'
    ): (
        'Hy-MT2 não tem prompt de sistema: instrução e texto vão em uma única mensagem. A redação '
        'segue o cartão do modelo.'
    ),
    'About': 'Sobre',
    'local translator for macOS': 'tradutor local para macOS',
    'Model: Hy-MT2 7B (Tencent Hy). License and model card on Hugging Face.': (
        'Modelo: Hy-MT2 7B (Tencent Hy). Licença e ficha do modelo no Hugging Face.'
    ),
    'Check for Updates…': 'Verificar atualizações…',
    'Checking for updates…': 'Verificando atualizações…',
    "You're up to date.": 'Você está atualizado.',
    'Update available: %@': 'Atualização disponível: %@',
    'Update check failed: %@': 'Falha ao verificar atualização: %@',
    'Automatically check for updates': 'Verificar atualizações automaticamente',
    'Automatically download and install updates': 'Baixar e instalar atualizações automaticamente',
    'Updates are signed and notarized.': 'As atualizações são assinadas e notarizadas.',
    'Project repository': 'Repositório do projeto',
    'DeepL-oFM on GitHub': 'DeepL-oFM no GitHub',
    'Local Ollama server. The model must be pulled with ollama pull.': (
        'Servidor local Ollama. O modelo deve ser obtido com ollama pull.'
    ),
    'LM Studio with its local server enabled. The model ID is shown in LM Studio.': (
        'LM Studio com seu servidor local ativado. O ID do modelo é exibido no LM Studio.'
    ),
    'oMLX — an MLX server for Apple Silicon. Enable the OpenAI-compatible API.': (
        'oMLX — um servidor MLX para Apple Silicon. Ative a API compatível com OpenAI.'
    ),
    'llama-server with --api. The default address is port 8080.': (
        'llama-server com --api. O endereço padrão é a porta 8080.'
    ),
    'Hundreds of models with one key. Free models are marked :free.': (
        'Centenas de modelos com uma única chave. Modelos gratuitos são marcados :free.'
    ),
    'Very fast cloud. Has a free tier with request limits.': (
        'Nuvem muito rápida. Possui camada gratuita com limites de requisições.'
    ),
    'Fastest inference for open models. Has a free tier with limits.': (
        'Inferência mais rápida para modelos abertos. Possui camada gratuita com limites.'
    ),
    'Any OpenAI-compatible server: your proxy, vLLM, LocalAI, Together, and so on.': (
        'Qualquer servidor compatível com OpenAI: seu proxy, vLLM, LocalAI, Together, etc.'
    ),
    'Model catalog': 'Catálogo de modelos',
    'Ready translators for local use and cloud options with free tiers.': (
        'Tradutores prontos para uso local e opções de nuvem com planos gratuitos.'
    ),
    'Search model': 'Buscar modelo',
    'Free only': 'Apenas gratuitos',
    'Fetch from server': 'Buscar do servidor',
    'Nothing found': 'Nada encontrado',
    'Found on the server': 'Encontrado no servidor',
    'Recommended': 'Recomendado',
    'Models': 'Modelos',
    (
        'Need another model? Type its ID into the Model field — any model your server supports '
        'will work.'
    ): (
        'Precisa de outro modelo? Digite seu ID no campo Modelo — qualquer modelo suportado pelo '
        'seu servidor funcionará.'
    ),
    'Choose': 'Escolher',
    'Copy install command': 'Copiar comando de instalação',
    'Enter the API key for %@ in Settings first.': (
        'Insira a chave de API para %@ nas Configurações primeiro.'
    ),
    'Search in history': 'Buscar no histórico',
    'Search language': 'Buscar idioma',
    'Clear history?': 'Limpar histórico?',
    'Cancel': 'Cancelar',
    'All saved translations will be deleted permanently.': (
        'Todas as traduções salvas serão excluídas permanentemente.'
    ),
    'History is empty': 'Histórico está vazio',
    'Translations will be saved here automatically.': (
        'As traduções serão salvas aqui automaticamente.'
    ),
    'Try another query.': 'Tente outra consulta.',
    'Delete entry': 'Excluir entrada',
    'Invalid server URL: %@': 'URL do servidor inválida: %@',
    'Choose a model in Settings.': 'Escolha um modelo nas definições.',
    'Could not connect to %@. Check that the server is running.': (
        'Não foi possível conectar a %@. Verifique se o servidor está em execução.'
    ),
    'Server returned error %@.': 'Servidor retornou erro %@.',
    'Server returned error %@: %@': 'Servidor retornou erro %@: %@',
    'Model “%@” not found on the server.': 'Modelo “%@” não encontrado no servidor.',
    'The model returned an empty translation. Try again.': (
        'O modelo retornou uma tradução vazia. Tente novamente.'
    ),
    'The model could not translate this text. Try again or choose another model.': (
        'O modelo não conseguiu traduzir este texto. Tente novamente ou escolha outro modelo.'
    ),
    'Some lines could not be translated (%d); they are left in the source language.': (
        'Algumas linhas não puderam ser traduzidas (%d); permanecem no idioma original.'
    ),
    'Server returned an unexpected response.': 'O servidor retornou uma resposta inesperada.',
    "Tencent's specialised translation model. The default for this app.": (
        'Modelo de tradução especializado da Tencent. O padrão deste aplicativo.'
    ),
    'The same model in a lighter size: fast even on weaker Macs.': (
        'O mesmo modelo em tamanho reduzido: rápido mesmo em Macs mais fracos.'
    ),
    'The highest-quality MoE version. Needs a lot of memory.': (
        'A versão MoE de mais alta qualidade. Requer muita memória.'
    ),
    "Google's translation model built on Gemma 3.": (
        'Modelo de tradução da Google baseado no Gemma 3.'
    ),
    'A larger TranslateGemma for stronger machines.': (
        'Um TranslateGemma maior para máquinas mais potentes.'
    ),
    'A compact model tuned only to translate — no explanations or reasoning.': (
        'Um modelo compacto ajustado apenas para traduzir — sem explicações ou raciocínio.'
    ),
    "Cohere's multilingual model with a good speed-quality balance.": (
        'Modelo multilíngue da Cohere com bom equilíbrio entre velocidade e qualidade.'
    ),
    'A general model; translates well but may add explanations.': (
        'Um modelo geral; traduz bem, mas pode acrescentar explicações.'
    ),
    'The same translation model in the cloud. Very cheap, no download.': (
        'O mesmo modelo de tradução na nuvem. Muito barato, sem download.'
    ),
    'The cheapest Hy-MT2 option on OpenRouter.': 'A opção Hy-MT2 mais barata no OpenRouter.',
    'The highest-quality Hy-MT2 version on OpenRouter.': (
        'A versão Hy-MT2 de mais alta qualidade no OpenRouter.'
    ),
    "Google's free model with a large context. Good general translation.": (
        'Modelo gratuito da Google com grande contexto. Boa tradução geral.'
    ),
    'A free MoE version of Gemma 4: faster than 31B.': (
        'Versão MoE gratuita do Gemma 4: mais rápida que a 31B.'
    ),
    'A large free NVIDIA model for difficult texts.': (
        'Modelo NVIDIA gratuito e grande para textos difíceis.'
    ),
    'A free fast model with a 1M-token context.': (
        'Modelo gratuito e rápido com contexto de 1\u202fmilhão de tokens.'
    ),
    'Cheap and very fast general translation from Google.': (
        'Tradução geral barata e muito rápida da Google.'
    ),
    'The cheapest fast Qwen model for bulk translation.': (
        'O modelo Qwen rápido mais barato para tradução em massa.'
    ),
    'Reliable general translation from OpenAI.': 'Tradução geral confiável da OpenAI.',
    "OpenAI's flagship open model on Groq's fast inference.": (
        'Modelo aberto principal da OpenAI na inferência rápida da Groq.'
    ),
    'The fastest option for short texts.': 'A opção mais rápida para textos curtos.',
    "Meta's proven general-purpose model.": 'Modelo de uso geral comprovado da Meta.',
    'A fresh Qwen with strong translation; preview status.': (
        'Um Qwen novo com tradução forte; status de pré‑visualização.'
    ),
    'Around 3000 tokens per second — the fastest option for long texts.': (
        'Cerca de 3000 tokens por segundo — a opção mais rápida para textos longos.'
    ),
    'A fast Qwen with good multilingual translation.': (
        'Um Qwen rápido com boa tradução multilíngue.'
    ),
    '33 languages': '33 idiomas',
    '55 languages': '55 idiomas',
    '23 languages': '23 idiomas',
    'recommended': 'recomendado',
    'light': 'leve',
    'fast': 'rápido',
    'large': 'grande',
    'specialised': 'especializado',
    'cheap': 'barato',
    'cheapest': 'mais barato',
    'universal': 'universal',
    'slower': 'mais lento',
    'Free': 'Gratuito',
    'Free tier': 'Camada gratuita',
    'preview': 'visualização',
    'MoE': 'MoE',
    'translation': 'tradução',
    'Local': 'Local',
    '≈4.6 GB': '≈4.6 GB',
    '≈3 GB': '≈3 GB',
    '≈8 GB': '≈8 GB',
    '~500 t/s': '~500 t/s',
    '~1000 t/s': '~1000 t/s',
    '~280 t/s': '~280 t/s',
    '~450 t/s': '~450 t/s',
    '~3000 t/s': '~3000 t/s',
    '~1850 t/s': '~1850 t/s',
    'Paste from clipboard': 'Colar da área de transferência',
}

ITALIAN: dict[str, str] = {
    'Could not open DeepL-oFM.': 'Impossibile aprire DeepL-oFM.',
    'Quit DeepL-oFM if it is running, then try again.': (
        'Se DeepL-oFM è aperto, chiudilo e riprova.'
    ),
    'More actions': 'Altre azioni',
    'Remove file': 'Rimuovi file',
    'Preparing file…': 'Preparazione del file…',
    'Saving…': 'Salvataggio…',
    'Translation progress': 'Avanzamento della traduzione',
    'Could not read or save translation history.': (
        'Impossibile leggere o salvare la cronologia delle traduzioni.'
    ),
    'Some paragraphs are still in the original language (%d).': (
        'Alcuni paragrafi sono ancora nella lingua originale (%d).'
    ),
    'The server interrupted the response. Try again.': (
        'Il server ha interrotto la risposta. Riprova.'
    ),
    'The provider rejected the request. Check the API key and model in Settings.': (
        'Il fornitore ha rifiutato la richiesta. Controlla la chiave API e il modello nelle '
        'impostazioni.'
    ),
    'The provider is temporarily unavailable. Try again.': (
        'Il fornitore è temporaneamente indisponibile. Riprova.'
    ),
    'Privacy policy': 'Informativa sulla privacy',
    'Source language': 'Lingua di partenza',
    'Target language': 'Lingua di destinazione',
    'Fallback': 'Riserva',
    'Too many requests. Wait a moment and try again.': (
        'Troppe richieste. Attendi un momento e riprova.'
    ),
    'Improve clarity, grammar and style while keeping the meaning.': (
        'Migliora chiarezza, grammatica e stile mantenendo il significato.'
    ),
    'Improve in': 'Migliora in',
    'Improve text': 'Migliora testo',
    'Improving…': 'Miglioramento…',
    'Improved text will appear here': 'Il testo migliorato apparirà qui',
    'Type or paste text to improve': 'Scrivi o incolla il testo da migliorare',
    'Files': 'File',
    'Translate a document and save the result in its original format.': (
        'Traduci un documento e salva il risultato nel formato originale.'
    ),
    'Drop a file here or choose one': 'Trascina un file qui o scegline uno',
    'Supported formats: TXT, Markdown, PDF and DOCX.': (
        'Formati supportati: TXT, Markdown, PDF e DOCX.'
    ),
    'Choose a file…': 'Scegli un file…',
    'Translate to': 'Traduci in',
    'Translation complete': 'Traduzione completata',
    'Translate another file': 'Traduci un altro file',
    'The file could not be translated.': 'Impossibile tradurre il file.',
    'The file could not be saved.': 'Impossibile salvare il file.',
    'Voice': 'Voce',
    'Automatic': 'Automatico',
    'Stop': 'Ferma',
    (
        'The Dock icon appears while the window is open. Turn this on to keep it in the Dock all '
        'the time.'
    ): (
        'L’icona nel Dock appare mentre la finestra è aperta. Attivala per tenerla sempre.'
    ),
    (
        'For better voices, download Enhanced or Premium voices in System Settings → '
        'Accessibility → Spoken Content.'
    ): (
        'Voci migliori si scaricano in Impostazioni di Sistema → Accessibilità → Contenuto '
        'pronunciato → Voce di sistema.'
    ),
    'Done': 'Fatto',
    'Share': 'Condividi',
    'Version': 'Versione',
    'Source': 'Origine',
    'Result': 'Risultato',
    'Add your API key in Settings.': 'Aggiungi la tua chiave API nelle Impostazioni.',
    'Cloud providers need an API key. For a server on your Wi-Fi network, choose Custom.': (
        'I fornitori cloud richiedono una chiave API. Per un server sulla rete Wi-Fi, scegli '
        '«Personalizzato».'
    ),
    'Dock icon': 'Icona nel Dock',
    'Hide the Dock icon to keep DeepL-oFM in the menu bar only.': (
        'Nascondi l’icona nel Dock per tenere DeepL-oFM solo nella barra dei menu.'
    ),
    'Back to translation': 'Torna alla traduzione',
    'File': 'File',
    'Translate file…': 'Traduci file…',
    'Save translation…': 'Salva traduzione…',
    'Translated file': 'File tradotto',
    'Open a document': 'Apri documento',
    'This file type is not supported.': 'Questo tipo di file non è supportato.',
    'The file could not be read.': 'Impossibile leggere il file.',
    'No selectable text found. For a scanned PDF, run text recognition first.': (
        'Nessun testo selezionabile. Se il PDF è una scansione, esegui prima il riconoscimento '
        'del testo.'
    ),
    'The Word document could not be processed.': 'Impossibile elaborare il documento Word.',
    'The translation could not be saved.': 'Impossibile salvare la traduzione.',
    'Drop a file to translate': 'Trascina un file da tradurre',
    'Preview': 'Anteprima',
    'Text only': 'Solo testo',
    'Markdown': 'Markdown',
    'Show plain text': 'Mostra solo testo',
    'Copy translation (formatted text)': 'Copia traduzione (testo formattato)',
    'Copy translation (plain text)': 'Copia traduzione (testo semplice)',
    'Copy translation (Markdown)': 'Copia traduzione (Markdown)',
    'Show rendered Markdown': 'Mostra Markdown renderizzato',
    'Show Markdown source': 'Mostra sorgente Markdown',
    'Translate text': 'Traduci testo',
    'History': 'Cronologia',
    'Settings': 'Impostazioni',
    'Translation': 'Traduzione',
    'Translate now': 'Traduci',
    'Translate clipboard': 'Traduci appunti',
    'Swap languages': 'Scambia lingue',
    'Copy translation': 'Copia traduzione',
    'Copy translation (Markdown + formatting)': 'Copia traduzione (Markdown + formattazione)',
    'Copy': 'Copia',
    'Sample text': 'Testo di esempio',
    'Translation failed': 'Traduzione fallita',
    'Settings…': 'Impostazioni…',
    'Connection status': 'Stato connessione',
    'Check connection': 'Verifica connessione',
    'Open DeepL-oFM': 'Apri DeepL-oFM',
    'Quit': 'Esci',
    'Translate clipboard (%@)': 'Traduci appunti (%@)',
    'Auto-detect': 'Rilevamento automatico',
    'Style': 'Stile',
    'Tone': 'Tono',
    'Auto': 'Automatico',
    'Literal': 'Letterale',
    'Natural': 'Naturale',
    'Default': 'Predefinito',
    'Formal': 'Formale',
    'Casual': 'Informale',
    'The model picks a natural style': 'Il modello sceglie uno stile naturale',
    'Word for word, without free paraphrase': 'Parola per parola, senza parafrasi libera',
    'Conveys meaning rather than wording': 'Trasmette il significato più che le parole',
    'No extra tone': 'Nessun tono aggiuntivo',
    'Formal and professional': 'Formale e professionale',
    'Casual and conversational': 'Informale e conversazionale',
    'Enter or paste text…': 'Inserisci o incolla il testo…',
    'Translation will appear here': 'Qui comparirà la traduzione',
    'Translating…': 'Traduzione in corso…',
    'Translating… %d of %d': 'Traduzione in corso… %d di %d',
    'Retry': 'Riprova',
    'Clear': 'Cancella',
    'Listen to the original': "Ascolta l'originale",
    'Copy the original': "Copia l'originale",
    'Listen to the translation': 'Ascolta la traduzione',
    'Translate again': 'Traduci di nuovo',
    'Swap languages (⇧⌘S)': 'Scambia le lingue (⇧⌘S)',
    'Checking connection…': 'Verifica connessione…',
    'Server unavailable': 'Server non disponibile',
    'Model “%@” not found': 'Modello “%@” non trovato',
    'Not checked yet': 'Non ancora verificato',
    'Connection works. Model “%@” is available.': (
        'Connessione funzionante. Modello “%@” disponibile.'
    ),
    'Server responds, but model “%@” is missing. Available: %@.': (
        'Il server risponde, ma il modello “%@” è mancante. Disponibili: %@.'
    ),
    'Connection works.': 'Connessione funzionante.',
    '%@ — translate clipboard': '%@ — traduci appunti',
    '%@ — active': '%@ — attivo',
    'Could not register %@. The shortcut may be taken.': (
        'Impossibile registrare %@. La scorciatoia potrebbe essere già in uso.'
    ),
    'Press a combination…': 'Premi una combinazione…',
    'Reset': 'Reimposta',
    'At least one modifier is required — ⌘, ⌥ or ⌃. Press Esc to cancel.': (
        'È richiesto almeno un modificatore — ⌘, ⌥ o ⌃. Premi Esc per annullare.'
    ),
    'Hot key': 'Tasto rapido',
    'Copy text anywhere and press the shortcut — DeepL-oFM opens and translates the clipboard.': (
        'Copia il testo ovunque e premi la scorciatoia — DeepL-oFM si apre e traduce gli appunti.'
    ),
    'Select text in any app and press the shortcut — DeepL-oFM copies it and translates.': (
        'Seleziona il testo in qualsiasi app e premi la scorciatoia — DeepL-oFM lo copia e lo '
        'traduce.'
    ),
    'Translate selection': 'Traduci selezione',
    'Translate selection (%@)': 'Traduci selezione (%@)',
    'Selected text': 'Testo selezionato',
    'Accessibility access': 'Accesso all’Accessibilità',
    'Granted': 'Concesso',
    'Not granted': 'Non concesso',
    'Open System Settings': 'Apri Impostazioni di Sistema',
    'Check access': 'Verifica accesso',
    'Delete': 'Elimina',
    'Forward Delete': 'Cancella in avanti',
    'Examples: ⌥⌘T or ⌥⌘C.': 'Esempi: ⌥⌘T o ⌥⌘C.',
    (
        'If access is already granted, remove DeepL-oFM from the Accessibility list and add the '
        'current app again — a permission from an older build does not apply.'
    ): (
        "Se l'accesso è già concesso, rimuovi DeepL-oFM dall'elenco Accessibilità e aggiungi "
        "nuovamente l'app corrente — un permesso di una versione precedente non è valido."
    ),
    'Accessibility access is required to copy the selected text.': (
        "È necessario l'accesso all’Accessibilità per copiare il testo selezionato."
    ),
    'Could not copy the selected text. Check Accessibility access.': (
        "Impossibile copiare il testo selezionato. Verifica l'accesso all’Accessibilità."
    ),
    'Space': 'Spazio',
    'key %d': 'tasto %d',
    'Can be empty for local servers. Stored in the macOS Keychain, never in the repository.': (
        'Può essere vuoto per server locali. Conservato nel macOS Keychain, mai nel repository.'
    ),
    'DeepL-oFM — local translation': 'DeepL-oFM — traduzione locale',
    'Other': 'Altro',
    'Custom': 'Personalizzato',
    'Ollama Cloud through a direct API key. No local server is needed.': (
        'Ollama Cloud tramite una chiave API diretta. Non è necessario alcun server locale.'
    ),
    'Connect': 'Connetti',
    'Models on the server': 'Modelli sul server',
    'Filter by name': 'Filtra per nome',
    'Refresh': 'Aggiorna',
    'The server returned no models.': 'Il server non ha restituito modelli.',
    'Select a model from the list or type its ID.': (
        "Seleziona un modello dall'elenco o digita il suo ID."
    ),
    'Models: %d': 'Modelli: %d',
    'Cloud': 'Cloud',
    'Gemma 4 in Ollama Cloud. Fast and strong for general translation.': (
        'Gemma 4 in Ollama Cloud. Veloce e potente per la traduzione generale.'
    ),
    'A fast cloud model from DeepSeek with a large context.': (
        'Un modello cloud veloce di DeepSeek con un ampio contesto.'
    ),
    "Mistral's general-purpose model in Ollama Cloud.": (
        'Modello generico di Mistral in Ollama Cloud.'
    ),
    "NVIDIA's high-throughput model for difficult texts.": (
        'Modello ad alta velocità di NVIDIA per testi difficili.'
    ),
    'Model and provider': 'Modello e provider',
    'Local models run offline and for free. Cloud models answer faster but need a key.': (
        'I modelli locali funzionano offline e gratuitamente. I modelli cloud rispondono più '
        'velocemente ma richiedono una chiave.'
    ),
    'API key': 'Chiave API',
    'Get key ↗': 'Ottieni chiave ↗',
    'Server address': 'Indirizzo server',
    'Model': 'Modello',
    'Model catalog…': 'Catalogo modelli…',
    'For difficult texts, use Hy-MT2 30B or a cloud model.': (
        'Per testi difficili, usa Hy-MT2 30B o un modello cloud.'
    ),
    'Fallback provider': 'Provider di fallback',
    'Used automatically when the primary provider fails.': (
        'Usato automaticamente quando il provider principale fallisce.'
    ),
    'Use a fallback provider': 'Usa un provider di fallback',
    'Provider': 'Provider',
    'Load models': 'Carica modelli',
    'Choose model': 'Scegli modello',
    'Choose a model': 'Scegli un modello',
    'Uses the Keychain key for this provider.': 'Utilizza la chiave Keychain per questo provider.',
    'If the primary provider fails, the same text is retried with these settings.': (
        'Se il provider principale fallisce, lo stesso testo viene ritentato con queste '
        'impostazioni.'
    ),
    'Load the translator at launch': "Carica il traduttore all'avvio",
    'Connects to the provider, refreshes the model list and warms up a local model.': (
        "Si connette al provider, aggiorna l'elenco dei modelli e avvia un modello locale."
    ),
    'Fallback provider works.': 'Il provider di fallback funziona.',
    'fallback': 'fallback',
    'Generation parameters': 'Parametri di generazione',
    'Defaults match Tencent’s recommendations for Hy-MT2 7B.': (
        'Le impostazioni predefinite corrispondono alle raccomandazioni di Tencent per Hy-MT2 7B.'
    ),
    'Temperature': 'Temperatura',
    'Repetition': 'Ripetizione',
    'Only this many most likely tokens are considered while decoding.': (
        'Solo questo numero di token più probabili viene considerato durante la decodifica.'
    ),
    'Context': 'Contesto',
    'Behavior': 'Comportamento',
    'Translate automatically while typing': 'Traduci automaticamente durante la digitazione',
    'Delay': 'Ritardo',
    'Keep translation history': 'Mantieni cronologia traduzioni',
    'Open at login': 'Apri al login',
    'Allow DeepL-oFM to open at login in System Settings.': (
        'Consenti a DeepL-oFM di aprirsi al login nelle Impostazioni di Sistema.'
    ),
    'Could not change Open at login. %@': (
        'Impossibile modificare l’impostazione di apertura al login. %@'
    ),
    'Menu bar icon': 'Icona barra dei menu',
    'Interface language': "Lingua dell'interfaccia",
    'System': 'Sistema',
    'System prompt': 'Prompt di sistema',
    (
        'Hy-MT2 has no system prompt: instruction and text go in one message. Wording follows the '
        'model card.'
    ): (
        'Hy-MT2 non ha un prompt di sistema: istruzione e testo vanno in un unico messaggio. La '
        'formulazione segue la scheda del modello.'
    ),
    'About': 'Informazioni',
    'local translator for macOS': 'traduttore locale per macOS',
    'Model: Hy-MT2 7B (Tencent Hy). License and model card on Hugging Face.': (
        'Modello: Hy-MT2 7B (Tencent Hy). Licenza e scheda del modello su Hugging Face.'
    ),
    'Check for Updates…': 'Verifica aggiornamenti…',
    'Checking for updates…': 'Verifica aggiornamenti in corso…',
    "You're up to date.": 'Sei aggiornato.',
    'Update available: %@': 'Aggiornamento disponibile: %@',
    'Update check failed: %@': 'Verifica aggiornamento fallita: %@',
    'Automatically check for updates': 'Verifica automaticamente gli aggiornamenti',
    'Automatically download and install updates': (
        'Scarica e installa automaticamente gli aggiornamenti'
    ),
    'Updates are signed and notarized.': 'Gli aggiornamenti sono firmati e notarizzati.',
    'Project repository': 'Repository del progetto',
    'DeepL-oFM on GitHub': 'DeepL-oFM su GitHub',
    'Local Ollama server. The model must be pulled with ollama pull.': (
        'Server Ollama locale. Il modello deve essere scaricato con ollama pull.'
    ),
    'LM Studio with its local server enabled. The model ID is shown in LM Studio.': (
        "LM Studio con server locale abilitato. L'ID del modello è mostrato in LM Studio."
    ),
    'oMLX — an MLX server for Apple Silicon. Enable the OpenAI-compatible API.': (
        "oMLX — un server MLX per Apple Silicon. Abilita l'API compatibile con OpenAI."
    ),
    'llama-server with --api. The default address is port 8080.': (
        "llama-server con --api. L'indirizzo predefinito è la porta 8080."
    ),
    'Hundreds of models with one key. Free models are marked :free.': (
        'Centinaia di modelli con una sola chiave. I modelli gratuiti sono contrassegnati :free.'
    ),
    'Very fast cloud. Has a free tier with request limits.': (
        'Cloud molto veloce. Offre un livello gratuito con limiti di richieste.'
    ),
    'Fastest inference for open models. Has a free tier with limits.': (
        'Inferenza più veloce per modelli open. Offre un livello gratuito con limiti.'
    ),
    'Any OpenAI-compatible server: your proxy, vLLM, LocalAI, Together, and so on.': (
        'Qualsiasi server compatibile con OpenAI: il tuo proxy, vLLM, LocalAI, Together, ecc.'
    ),
    'Model catalog': 'Catalogo modelli',
    'Ready translators for local use and cloud options with free tiers.': (
        'Traduttori pronti per uso locale e opzioni cloud con piani gratuiti.'
    ),
    'Search model': 'Cerca modello',
    'Free only': 'Solo gratuiti',
    'Fetch from server': 'Recupera dal server',
    'Nothing found': 'Nessun risultato',
    'Found on the server': 'Trovato sul server',
    'Recommended': 'Consigliato',
    'Models': 'Modelli',
    (
        'Need another model? Type its ID into the Model field — any model your server supports '
        'will work.'
    ): (
        'Hai bisogno di un altro modello? Inserisci il suo ID nel campo Modello — qualsiasi '
        'modello supportato dal tuo server funzionerà.'
    ),
    'Choose': 'Scegli',
    'Copy install command': 'Copia comando di installazione',
    'Enter the API key for %@ in Settings first.': (
        'Inserisci prima la chiave API per %@ nelle Impostazioni.'
    ),
    'Search in history': 'Cerca nella cronologia',
    'Search language': 'Cerca lingua',
    'Clear history?': 'Cancellare la cronologia?',
    'Cancel': 'Annulla',
    'All saved translations will be deleted permanently.': (
        'Tutte le traduzioni salvate saranno eliminate definitivamente.'
    ),
    'History is empty': 'La cronologia è vuota',
    'Translations will be saved here automatically.': (
        'Le traduzioni verranno salvate qui automaticamente.'
    ),
    'Try another query.': "Prova un'altra ricerca.",
    'Delete entry': 'Elimina voce',
    'Invalid server URL: %@': 'URL del server non valido: %@',
    'Choose a model in Settings.': 'Scegli un modello nelle impostazioni.',
    'Could not connect to %@. Check that the server is running.': (
        'Impossibile connettersi a %@. Verifica che il server sia in esecuzione.'
    ),
    'Server returned error %@.': "Il server ha restituito l'errore %@.",
    'Server returned error %@: %@': "Il server ha restituito l'errore %@: %@",
    'Model “%@” not found on the server.': 'Modello “%@” non trovato sul server.',
    'The model returned an empty translation. Try again.': (
        'Il modello ha restituito una traduzione vuota. Riprova.'
    ),
    'The model could not translate this text. Try again or choose another model.': (
        'Il modello non è riuscito a tradurre questo testo. Riprova o scegli un altro modello.'
    ),
    'Some lines could not be translated (%d); they are left in the source language.': (
        'Alcune righe non hanno potuto essere tradotte (%d); sono lasciate nella lingua originale.'
    ),
    'Server returned an unexpected response.': 'Il server ha restituito una risposta inattesa.',
    "Tencent's specialised translation model. The default for this app.": (
        'Modello di traduzione specializzato di Tencent. Predefinito per questa app.'
    ),
    'The same model in a lighter size: fast even on weaker Macs.': (
        'Lo stesso modello in versione più leggera: veloce anche su Mac meno potenti.'
    ),
    'The highest-quality MoE version. Needs a lot of memory.': (
        'La versione MoE di massima qualità. Richiede molta memoria.'
    ),
    "Google's translation model built on Gemma 3.": (
        'Modello di traduzione di Google basato su Gemma 3.'
    ),
    'A larger TranslateGemma for stronger machines.': (
        'Un TranslateGemma più grande per macchine più potenti.'
    ),
    'A compact model tuned only to translate — no explanations or reasoning.': (
        'Un modello compatto ottimizzato solo per tradurre — senza spiegazioni né ragionamenti.'
    ),
    "Cohere's multilingual model with a good speed-quality balance.": (
        'Modello multilingue di Cohere con un buon equilibrio velocità‑qualità.'
    ),
    'A general model; translates well but may add explanations.': (
        'Un modello generico; traduce bene ma può aggiungere spiegazioni.'
    ),
    'The same translation model in the cloud. Very cheap, no download.': (
        'Lo stesso modello di traduzione nel cloud. Molto economico, nessun download.'
    ),
    'The cheapest Hy-MT2 option on OpenRouter.': "L'opzione Hy-MT2 più economica su OpenRouter.",
    'The highest-quality Hy-MT2 version on OpenRouter.': (
        'La versione Hy-MT2 di massima qualità su OpenRouter.'
    ),
    "Google's free model with a large context. Good general translation.": (
        'Modello gratuito di Google con ampio contesto. Buona traduzione generale.'
    ),
    'A free MoE version of Gemma 4: faster than 31B.': (
        'Versione MoE gratuita di Gemma 4: più veloce della 31B.'
    ),
    'A large free NVIDIA model for difficult texts.': (
        'Grande modello gratuito NVIDIA per testi complessi.'
    ),
    'A free fast model with a 1M-token context.': (
        'Modello gratuito e veloce con contesto da 1\u202fM di token.'
    ),
    'Cheap and very fast general translation from Google.': (
        'Traduzione generale economica e molto veloce da Google.'
    ),
    'The cheapest fast Qwen model for bulk translation.': (
        'Il modello Qwen veloce più economico per traduzioni di massa.'
    ),
    'Reliable general translation from OpenAI.': 'Traduzione generale affidabile da OpenAI.',
    "OpenAI's flagship open model on Groq's fast inference.": (
        'Modello di punta open di OpenAI su inferenza veloce di Groq.'
    ),
    'The fastest option for short texts.': "L'opzione più veloce per testi brevi.",
    "Meta's proven general-purpose model.": 'Modello generico comprovato di Meta.',
    'A fresh Qwen with strong translation; preview status.': (
        'Nuovo Qwen con traduzione potente; stato di anteprima.'
    ),
    'Around 3000 tokens per second — the fastest option for long texts.': (
        "Circa 3000 token al secondo — l'opzione più veloce per testi lunghi."
    ),
    'A fast Qwen with good multilingual translation.': (
        'Qwen veloce con buona traduzione multilingue.'
    ),
    '33 languages': '33 lingue',
    '55 languages': '55 lingue',
    '23 languages': '23 lingue',
    'recommended': 'consigliato',
    'light': 'leggero',
    'fast': 'veloce',
    'large': 'grande',
    'specialised': 'specializzato',
    'cheap': 'economico',
    'cheapest': 'più economico',
    'universal': 'universale',
    'slower': 'più lento',
    'Free': 'Gratis',
    'Free tier': 'Livello gratuito',
    'preview': 'anteprima',
    'MoE': 'MoE',
    'translation': 'traduzione',
    'Local': 'Locale',
    '≈4.6 GB': '≈4.6 GB',
    '≈3 GB': '≈3 GB',
    '≈8 GB': '≈8 GB',
    '~500 t/s': '~500 t/s',
    '~1000 t/s': '~1000 t/s',
    '~280 t/s': '~280 t/s',
    '~450 t/s': '~450 t/s',
    '~3000 t/s': '~3000 t/s',
    '~1850 t/s': '~1850 t/s',
    'Paste from clipboard': 'Incolla dagli appunti',
}

BY_LANGUAGE: dict[str, dict[str, str]] = {
    "uk": UKRAINIAN,
    "ru": RUSSIAN,
    "de": GERMAN,
    "fr": FRENCH,
    "es": SPANISH,
    "pl": POLISH,
    "pt": PORTUGUESE,
    "it": ITALIAN,
}

#: Alias kept for callers that think of the catalogue as one mapping.
TRANSLATIONS = BY_LANGUAGE
