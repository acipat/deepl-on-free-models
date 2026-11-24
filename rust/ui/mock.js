/* ==========================================================================
   DeepL-oFM — standalone mock
   Loaded in every page, active only when window.__TAURI__ is missing. It
   implements every command app.js uses with realistic, deterministic data so
   index.html can be opened over file:// and screenshotted headlessly.

   Scenario routing (location.hash):
     #translate (default)   filled translation
     #empty                 empty translate tab
     #progress              translation in flight
     #error                 failed translation with retry banner
     #files                 finished PDF job
     #files-progress        running file job
     #files-error           failed file job
     #write                 finished improvement
     #write-busy            improvement in flight
     #history               history list
     #settings[-tab]        app opens the settings dialog
     #catalog               app opens the model catalogue
   Force a scheme with ?theme=dark or ?theme=light.
   ========================================================================== */
(function () {
  "use strict";

  if (window.__TAURI__ && window.__TAURI__.core) return;

  const tr = typeof window.t === "function" ? window.t : (key) => key;
  const clone = (value) => (value === undefined ? undefined : JSON.parse(JSON.stringify(value)));

  const DEMO_SOURCE =
    "DeepL-oFM is a native translator for Windows that runs on local and cloud models.\nIt keeps paragraphs, lists and Markdown intact.";
  const DEMO_TRANSLATION =
    "DeepL-oFM — це нативний перекладач для Windows, який працює на локальних і хмарних моделях. Він зберігає абзаци, списки й Markdown без змін.";
  const WRITE_SOURCE =
    "The app is very good. It help me translate text fast and the formatting stays. I think it is a useful tool for every day work.";
  const MARKDOWN_SAMPLE =
    "# Release notes\n\nThis release adds **offline models**, *faster* startup and an inline `--wait` flag. Read the [full notes](https://example.com/releases/1.4) for details.\n\n> Translations stay on this computer. Nothing is uploaded.\n\n- Paragraphs, lists and block quotes are preserved\n- Links keep their target URL\n- Fenced code is left untouched\n\n```ts\nconst translator = await connect({ model: \"hy-mt2:7b\" });\n```\n\n---\n\n1. Connect to a model\n2. Paste text\n3. Press **Ctrl + Enter**\n";
  const WRITE_OUTPUT =
    "The app works very well. It helps me translate text quickly while preserving the original formatting, and I think it is a useful tool for everyday work.\n\n- **Fast** translations with the original formatting intact\n- A calm workspace that stays out of the way\n- One shortcut for the clipboard, one for the whole document";
  const WRITE_OUTPUT_UK =
    "Застосунок працює дуже добре. Він допомагає швидко перекладати текст, зберігаючи початкове форматування, і я вважаю його корисним інструментом для щоденної роботи.\n\n- **Швидкий** переклад із збереженням форматування\n- Спокійний робочий простір, що не відволікає\n- Одна комбінація для буфера, інша — для всього документа";

  // `get_translations()` returns the active interface catalogue. This is a
  // representative sample (the Rust i18n crate ships all 375 keys); keys are
  // the English strings used by strings.js and app.js.
  const TRANSLATIONS = {
    uk: {
      "Translate": "Перекласти",
      "Files": "Файли",
      "Write": "Текст",
      "History": "Історія",
      "Settings": "Налаштування",
      "Sections": "Розділи",
      "Connection status": "Стан з'єднання",
      "More actions": "Інші дії",
      "Translate clipboard": "Перекласти буфер",
      "Translate selection": "Перекласти виділене",
      "New translation": "Новий переклад",
      "Settings…": "Налаштування…",
      "Auto-detect": "Визначити мову",
      "Source": "Джерело",
      "Translation": "Переклад",
      "Copy": "Копіювати",
      "Copied": "Скопійовано",
      "Style": "Стиль",
      "Tone": "Тон",
      "Auto": "Авто",
      "Literal": "Дослівно",
      "Natural": "Природно",
      "Default": "Типово",
      "Formal": "Формально",
      "Casual": "Невимушено",
      "Preview": "Попередній перегляд",
      "Text only": "Лише текст",
      "Markdown": "Markdown",
      "Detected: %@": "Визначено: %@",
      "Translation will appear here": "Переклад з'явиться тут",
      "Press Ctrl + Enter to translate.": "Натисніть Ctrl + Enter, щоб перекласти.",
      "Translate now": "Перекласти зараз",
      "Listen to the original": "Прослухати оригінал",
      "Paste from clipboard": "Вставити з буфера",
      "Copy the original": "Копіювати оригінал",
      "Clear": "Очистити",
      "Translate again": "Перекласти ще раз",
      "Listen to the translation": "Прослухати переклад",
      "Copy translation": "Копіювати переклад",
      "%d characters": "%d символів",
      "%d character": "%d символ",
      "t/s": "т/с",
      "Enter or paste text…": "Введіть або вставте текст…",
      "Translate a document and save the result in its original format.": "Перекладіть документ і збережіть результат у початковому форматі.",
      "Drop a file here or choose one": "Перетягніть файл сюди або виберіть його",
      "Supported formats: TXT, Markdown, PDF and DOCX.": "Підтримувані формати: TXT, Markdown, PDF і DOCX.",
      "Choose a file…": "Вибрати файл…",
      "Translate to": "Перекласти на",
      "Translation complete": "Переклад завершено",
      "Some paragraphs are still in the original language (%d).": "Деякі абзаци залишилися мовою оригіналу (%d).",
      "Save file…": "Зберегти файл…",
      "Show in folder": "Показати в теці",
      "Translate another file": "Перекласти інший файл",
      "Translating…": "Переклад…",
      "Cancel": "Скасувати",
      "Improve text": "Покращити текст",
      "Improve clarity, grammar and style while keeping the meaning.": "Покращуйте ясність, граматику й стиль, зберігаючи зміст.",
      "Improve in": "Покращити мовою",
      "Result": "Результат",
      "Search in history": "Пошук в історії",
      "History is empty": "Історія порожня",
      "Translations will be saved here automatically.": "Переклади зберігатимуться тут автоматично.",
      "Nothing found": "Нічого не знайдено",
      "Try another query.": "Спробуйте інший запит.",
      "Model & provider": "Модель і постачальник",
      "Generation": "Генерація",
      "Behavior": "Поведінка",
      "Translate text in one request": "Перекладати текст одним запитом",
      "Hot keys": "Гарячі клавіші",
      "About": "Про програму",
      "Model and provider": "Модель і постачальник",
      "Provider": "Постачальник",
      "Server address": "Адреса сервера",
      "API key": "Ключ API",
      "Model": "Модель",
      "Connect": "Підключити",
      "Connected": "Підключено",
      "Models on the server": "Моделі на сервері",
      "Filter by name": "Фільтр за назвою",
      "Save": "Зберегти",
      "Changes apply when you save.": "Зміни застосовуються після збереження.",
      "Model catalog…": "Каталог моделей…",
      "Local Ollama server. The model must be pulled with ollama pull.": "Локальний сервер Ollama. Модель потрібно завантажити командою ollama pull.",
      "Can be empty for local servers. Stored securely on this computer.": "Може бути порожнім для локальних серверів. Зберігається безпечно на цьому комп'ютері.",
      "Models: %d": "Моделі: %d",
      "Select a model from the list or type its ID.": "Виберіть модель зі списку або введіть її ID.",
      "Generation parameters": "Параметри генерації",
      "System prompt": "Системна підказка",
      "Voice": "Голос",
      "Automatic": "Автоматично",
      "Interface language": "Мова інтерфейсу",
      "Not checked yet": "Ще не перевірено",
      "Server unavailable": "Сервер недоступний",
      "Loading the translator…": "Завантаження перекладача…",
      "Checking connection…": "Перевірка з'єднання…",
      "Connection works. Model “%@” is available.": "З'єднання працює. Модель “%@” доступна.",
      "Model catalog": "Каталог моделей",
      "Ready translators for local use and cloud options with free tiers.": "Готові перекладачі для локального використання та хмарні варіанти з безкоштовними тарифами.",
      "All providers": "Усі постачальники",
      "Free only": "Лише безкоштовні",
      "Search model": "Пошук моделі",
      "Fetch from server": "Отримати з сервера",
      "Recommended": "Рекомендовані",
      "Models": "Моделі",
      "Use this model": "Використати цю модель",
      "Close": "Закрити",
      "Found on the server": "Знайдено на сервері",
      "Copy install command": "Копіювати команду встановлення",
      "Install command": "Команда встановлення",
      "Free": "Безкоштовно",
      "Saved": "Збережено",
      "Something went wrong.": "Щось пішло не так.",
      "The clipboard is empty.": "Буфер обміну порожній.",
      "No file was chosen.": "Файл не вибрано.",
      "Cancelled": "Скасовано",
      "Show rendered Markdown": "Показати відформатований Markdown",
      "Show Markdown source": "Показати джерело Markdown",
      "Settings file": "Файл налаштувань",
      "History file": "Файл історії",
      "Key storage": "Сховище ключів",
      "Check connection": "Перевірити з'єднання",
      "Try again": "Спробувати ще раз",
      "Server responds, but model “%@” is missing. Available: %@.": "Сервер відповідає, але модель “%@” відсутня. Доступні: %@.",
      "Yesterday": "Учора",
      "Just now": "Щойно",
      "%d min ago": "%d хв тому",
      "%d h ago": "%d год тому",
      "%d days ago": "%d днів тому",
      "Version %@": "Версія %@",
      "Show": "Показати",
      "Hide": "Приховати",
      "Local models run offline and for free. Cloud models answer faster but need a key.": "Локальні моделі працюють офлайн і безкоштовно. Хмарні моделі відповідають швидше, але потребують ключа.",
      "Any OpenAI-compatible server: your proxy, vLLM, LocalAI, Together, and so on.": "Будь-який сервер, сумісний з OpenAI: ваш проксі, vLLM, LocalAI, Together тощо.",
      "Fallback provider": "Резервний постачальник",
      "Used automatically when the primary provider fails.": "Використовується автоматично, коли основний постачальник недоступний.",
      "Use a fallback provider": "Використовувати резервного постачальника",
      "Defaults match Tencent's recommendations for Hy-MT2 7B.": "Типові значення відповідають рекомендаціям Tencent для Hy-MT2 7B.",
      "Temperature": "Температура",
      "Top-p": "Top-p",
      "Top-k": "Top-k",
      "Repetition": "Повторення",
      "Context": "Контекст",
      "Delay": "Затримка",
      "Hy-MT2 has no system prompt: instruction and text go in one message. Wording follows the model card.": "Hy-MT2 не має системної підказки: інструкція й текст передаються одним повідомленням. Формулювання відповідає картці моделі.",
      "Work from any application — DeepL-oFM stays out of the way.": "Працюйте з будь-якої програми — DeepL-oFM не заважає.",
      "Examples: Ctrl+Alt+T or Ctrl+Alt+C.": "Приклади: Ctrl+Alt+T або Ctrl+Alt+C.",
      "Copy text anywhere and press the shortcut — DeepL-oFM opens and translates the clipboard.": "Скопіюйте текст будь-де й натисніть комбінацію — DeepL-oFM відкриється та перекладе буфер.",
      "Select text in any app and press the shortcut — DeepL-oFM copies it and translates.": "Виділіть текст у будь-якій програмі й натисніть комбінацію — DeepL-oFM скопіює його та перекладе.",
      "Selected text": "Виділений текст",
      "Hot key": "Гаряча клавіша",
      "Reset": "Скинути",
      "A native translator for local and cloud models.": "Нативний перекладач для локальних і хмарних моделей.",
      "MIT license · free and open source.": "Ліцензія MIT · безкоштовно з відкритим кодом.",
      "Model: Hy-MT2 7B (Tencent Hy). License and model card on Hugging Face.": "Модель: Hy-MT2 7B (Tencent Hy). Ліцензія та картка моделі на Hugging Face.",
      "DeepL-oFM on GitHub": "DeepL-oFM на GitHub",
      "Model on Hugging Face": "Модель на Hugging Face",
      "Need another model? Type its ID into the Model field — any model your server supports will work.": "Потрібна інша модель? Введіть її ID у поле «Модель» — підійде будь-яка модель, яку підтримує ваш сервер.",
      "More voices can be added in Windows Settings → Time & language → Speech.": "Більше голосів можна додати в Налаштуваннях Windows → Час і мова → Мовлення.",
      "%.1f s": "%.1f с",
      "%d ms": "%d мс",
      "%d of %d": "%d з %d",
      "%d warnings": "%d попереджень",
      "%d warning": "%d попередження",
      "English": "Англійська",
      "Ukrainian": "Українська",
      "Russian": "Російська",
      "German": "Німецька",
      "French": "Французька",
      "Spanish": "Іспанська",
      "Polish": "Польська",
      "Portuguese": "Португальська",
      "Italian": "Італійська",
      "Chinese": "Китайська",
      "Japanese": "Японська",
      "Turkish": "Турецька",
      "Arabic": "Арабська",
      "Korean": "Корейська",
      "Thai": "Тайська",
      "Vietnamese": "В'єтнамська",
      "Malay": "Малайська",
      "Indonesian": "Індонезійська",
      "Hindi": "Гінді",
      "Traditional Chinese": "Китайська (традиційна)",
    },
  };

  const VOICES = [
    { id: "system::Samantha", label: "Samantha" },
    { id: "system::Daniel", label: "Daniel" },
    { id: "system::Kyrylo", label: "Kyrylo" },
  ];

  const CATALOG = [
    {
      name: "Hy-MT2 7B",
      modelId: "hy-mt2:7b",
      provider: "Ollama",
      size: "≈4.6 GB",
      languages: "33 languages",
      note: "Tencent's specialised translation model. The default for this app.",
      installCommand:
        "ollama pull maternion/hy-mt2:7b && ollama cp maternion/hy-mt2:7b hy-mt2:7b",
      badges: ["33 languages", "≈4.6 GB", "recommended"],
      isFree: true,
    },
    {
      name: "Hy-MT2 1.8B",
      modelId: "hy-mt2:1.8b",
      provider: "Ollama",
      size: "1.8B",
      languages: "33 languages",
      note: "The same model in a lighter size: fast even on weaker Macs.",
      installCommand:
        "ollama pull maternion/hy-mt2:1.8b && ollama cp maternion/hy-mt2:1.8b hy-mt2:1.8b",
      badges: ["33 languages", "light", "fast"],
      isFree: true,
    },
    {
      name: "Hy-MT2 30B-A3B",
      modelId: "hy-mt2:30b",
      provider: "Ollama",
      size: "30B-A3B",
      languages: "33 languages",
      note: "The highest-quality MoE version. Needs a lot of memory.",
      installCommand:
        "ollama pull maternion/hy-mt2:30b-a3b && ollama cp maternion/hy-mt2:30b-a3b hy-mt2:30b",
      badges: ["33 languages", "MoE", "large"],
      isFree: true,
    },
    {
      name: "TranslateGemma 4B",
      modelId: "translategemma:4b",
      provider: "Ollama",
      size: "≈3 GB",
      languages: "55 languages",
      note: "Google's translation model built on Gemma 3.",
      installCommand: "ollama pull translategemma:4b",
      badges: ["55 languages", "≈3 GB"],
      isFree: true,
    },
    {
      name: "TranslateGemma 12B",
      modelId: "translategemma:12b",
      provider: "Ollama",
      size: "≈8 GB",
      languages: "55 languages",
      note: "A larger TranslateGemma for stronger machines.",
      installCommand: "ollama pull translategemma:12b",
      badges: ["55 languages", "≈8 GB"],
      isFree: true,
    },
    {
      name: "Qwen3.5-MT 2B",
      modelId: "qwen3.5-mt:2b",
      provider: "Ollama",
      size: "2B",
      languages: "",
      note: "A compact model tuned only to translate — no explanations or reasoning.",
      installCommand: "ollama pull kaelri/qwen3.5-mt:2b",
      badges: ["translation", "2B"],
      isFree: true,
    },
    {
      name: "Aya Expanse 8B",
      modelId: "aya-expanse:8b",
      provider: "Ollama",
      size: "8B",
      languages: "23 languages",
      note: "Cohere's multilingual model with a good speed-quality balance.",
      installCommand: "ollama pull aya-expanse:8b",
      badges: ["23 languages", "8B"],
      isFree: true,
    },
    {
      name: "Qwen3 8B",
      modelId: "qwen3:8b",
      provider: "Ollama",
      size: "8B",
      languages: "",
      note: "A general model; translates well but may add explanations.",
      installCommand: "ollama pull qwen3:8b",
      badges: ["universal", "8B"],
      isFree: true,
    },
    {
      name: "Gemma 4 31B",
      modelId: "gemma4:31b",
      provider: "Ollama Cloud",
      size: "31B",
      languages: "",
      note: "Gemma 4 in Ollama Cloud. Fast and strong for general translation.",
      installCommand: "",
      badges: ["Cloud", "31B", "fast"],
      isFree: false,
    },
    {
      name: "DeepSeek V4.1 Flash",
      modelId: "deepseek-v4.1-flash",
      provider: "Ollama Cloud",
      size: "1M",
      languages: "",
      note: "A fast cloud model from DeepSeek with a large context.",
      installCommand: "",
      badges: ["Cloud", "1M", "fast"],
      isFree: false,
    },
    {
      name: "Mistral Large 4",
      modelId: "mistral-large-4",
      provider: "Ollama Cloud",
      size: "large",
      languages: "",
      note: "Mistral's general-purpose model in Ollama Cloud.",
      installCommand: "",
      badges: ["Cloud", "large"],
      isFree: false,
    },
    {
      name: "Nemotron 3 Ultra",
      modelId: "nemotron-3-ultra",
      provider: "Ollama Cloud",
      size: "large",
      languages: "",
      note: "NVIDIA's high-throughput model for difficult texts.",
      installCommand: "",
      badges: ["Cloud", "large", "slower"],
      isFree: false,
    },
    {
      name: "Hy-MT2 7B",
      modelId: "tencent/hy-mt2-7b",
      provider: "OpenRouter",
      size: "7B",
      languages: "33 languages",
      note: "The same translation model in the cloud. Very cheap, no download.",
      installCommand: "",
      badges: ["33 languages", "specialised", "cheap"],
      isFree: false,
    },
    {
      name: "Hy-MT2 1.8B",
      modelId: "tencent/hy-mt2-1.8b",
      provider: "OpenRouter",
      size: "1.8B",
      languages: "33 languages",
      note: "The cheapest Hy-MT2 option on OpenRouter.",
      installCommand: "",
      badges: ["33 languages", "cheapest"],
      isFree: false,
    },
    {
      name: "Hy-MT2 30B-A3B",
      modelId: "tencent/hy-mt2-30b-a3b",
      provider: "OpenRouter",
      size: "30B-A3B",
      languages: "33 languages",
      note: "The highest-quality Hy-MT2 version on OpenRouter.",
      installCommand: "",
      badges: ["33 languages", "MoE"],
      isFree: false,
    },
    {
      name: "Gemma 4 31B",
      modelId: "google/gemma-4-31b-it:free",
      provider: "OpenRouter",
      size: "31B",
      languages: "",
      note: "Google's free model with a large context. Good general translation.",
      installCommand: "",
      badges: ["Free", "262K", "31B"],
      isFree: true,
    },
    {
      name: "Gemma 4 26B A4B",
      modelId: "google/gemma-4-26b-a4b-it:free",
      provider: "OpenRouter",
      size: "26B A4B",
      languages: "",
      note: "A free MoE version of Gemma 4: faster than 31B.",
      installCommand: "",
      badges: ["Free", "MoE", "fast"],
      isFree: true,
    },
    {
      name: "Nemotron 3 Ultra",
      modelId: "nvidia/nemotron-3-ultra-550b-a55b:free",
      provider: "OpenRouter",
      size: "550B",
      languages: "",
      note: "A large free NVIDIA model for difficult texts.",
      installCommand: "",
      badges: ["Free", "550B", "slower"],
      isFree: true,
    },
    {
      name: "Ling 3.2 Flash",
      modelId: "inclusionai/ling-3.2-flash:free",
      provider: "OpenRouter",
      size: "1M",
      languages: "",
      note: "A free fast model with a 1M-token context.",
      installCommand: "",
      badges: ["Free", "1M", "fast"],
      isFree: true,
    },
    {
      name: "Gemini 3.1 Flash Lite",
      modelId: "google/gemini-3.1-flash-lite",
      provider: "OpenRouter",
      size: "1M",
      languages: "",
      note: "Cheap and very fast general translation from Google.",
      installCommand: "",
      badges: ["1M", "fast", "cheap"],
      isFree: false,
    },
    {
      name: "Qwen3.7 Flash",
      modelId: "qwen/qwen3.7-flash",
      provider: "OpenRouter",
      size: "1M",
      languages: "",
      note: "The cheapest fast Qwen model for bulk translation.",
      installCommand: "",
      badges: ["1M", "cheapest"],
      isFree: false,
    },
    {
      name: "GPT-5 Mini",
      modelId: "openai/gpt-5-mini",
      provider: "OpenRouter",
      size: "400K",
      languages: "",
      note: "Reliable general translation from OpenAI.",
      installCommand: "",
      badges: ["400K", "universal"],
      isFree: false,
    },
  ];

  const now = Date.now();
  const historySeed = [
    {
      id: "mock-history-1",
      date: new Date(now - 2 * 3600 * 1000).toISOString(),
      sourceText: "Release notes for version 1.4 are now available.",
      translatedText: "Нотатки до випуску версії 1.4 вже доступні.",
      sourceCode: "en",
      targetCode: "uk",
      style: "auto",
      tone: "standard",
      engine: "Ollama · hy-mt2:7b",
      durationMs: 960,
    },
    {
      id: "mock-history-2",
      date: new Date(now - 26 * 3600 * 1000).toISOString(),
      sourceText: "Customers asked for offline models and a smaller download.",
      translatedText: "Клієнти просили офлайн-моделі та менший обсяг завантаження.",
      sourceCode: "en",
      targetCode: "uk",
      style: "natural",
      tone: "standard",
      engine: "Ollama · hy-mt2:7b",
      durationMs: 1900,
    },
    {
      id: "mock-history-3",
      date: new Date(now - 50 * 3600 * 1000).toISOString(),
      sourceText: "The quarterly report is ready for review.",
      translatedText: "Квартальний звіт готовий до перегляду.",
      sourceCode: "en",
      targetCode: "uk",
      style: "auto",
      tone: "formal",
      engine: "Ollama · hy-mt2:7b",
      durationMs: 2400,
    },
  ];

  // `get_catalog` reports Provider::title(); the settings use Provider::value().
  const PROVIDER_VALUES = {
    Ollama: "ollama",
    "Ollama Cloud": "ollamaCloud",
    "LM Studio": "lmStudio",
    oMLX: "omlx",
    "llama.cpp": "llamaCpp",
    OpenRouter: "openRouter",
    Groq: "groq",
    Cerebras: "cerebras",
    Custom: "custom",
  };

  function providerValueFor(title) {
    return PROVIDER_VALUES[String(title || "").trim()] || "";
  }

  function settings() {
    return {
      // AppSettings carries Provider::value(); only get_catalog sends titles.
      provider: "ollama",
      baseUrl: "http://127.0.0.1:11434",
      model: "hy-mt2:7b",
      apiKey: "",
      fallbackEnabled: false,
      fallbackProvider: "ollama",
      fallbackBaseUrl: "http://127.0.0.1:11434",
      fallbackModel: "",
      fallbackApiKey: "",
      temperature: 0.7,
      topP: 0.6,
      topK: 20,
      repetitionPenalty: 1.05,
      contextWindow: 8192,
      autoTranslate: true,
      translateInOneRequest: true,
      debounce: 0.45,
      hotKey: { key: "t", ctrl: true, alt: true, shift: false, meta: false },
      selectionHotKey: { key: "c", ctrl: true, alt: true, shift: false, meta: false },
      showInMenuBar: true,
      speechVoiceId: "",
      keepHistory: true,
      warmUpOnLaunch: false,
      interfaceLanguage: "system",
      resultView: "preview",
      lastStyle: "auto",
      lastTone: "standard",
      lastTargetCode: "uk",
      lastSourceCode: "auto",
    };
  }

  /** `?login=requiresApproval` lets the standalone UI show the approval hint. */
  function loginItemScenario() {
    const params = new URLSearchParams(location.search);
    const value = params.get("login") || "disabled";
    return ["enabled", "disabled", "requiresApproval", "unsupported"].includes(value)
      ? value
      : "disabled";
  }

  function baseState() {
    return {
      tab: "translate",
      sourceText: DEMO_SOURCE,
      translatedText: DEMO_TRANSLATION,
      isTranslating: false,
      completed: 0,
      total: 0,
      warningCount: 0,
      errorMessage: null,
      sourceLanguage: "auto",
      targetLanguage: "uk",
      detectedLanguage: "en",
      style: "auto",
      tone: "standard",
      resultView: "preview",
      backendStatus: "connected",
      probeMessage: "Connection works. Model “hy-mt2:7b” is available.",
      providerModels: ["hy-mt2:7b", "hy-mt2:1.8b", "translategemma:4b", "qwen3:8b"],
      modelsLoading: false,
      modelsError: null,
      fallbackModels: [],
      fallbackModelsLoading: false,
      fallbackModelsError: null,
      usingFallback: false,
      tokensPerSecond: 41.2,
      lastDurationMs: 1840,
      speaking: "",
      hotkeyMessage: "",
      selectionHotkeyMessage: "",
      loginItemStatus: loginItemScenario(),
      loginItemError: null,
      fileJob: null,
      write: {
        inProgress: false,
        output: "",
        error: null,
        detectedCode: null,
        durationMs: null,
        warnings: 0,
      },
      history: clone(historySeed),
      historyError: false,
      settings: settings(),
      version: "2.0.1",
    };
  }

  function scenarioState() {
    const state = baseState();
    const hash = String(location.hash || "").replace(/^#/, "").split("?")[0];
    // ?lang=uk forces an interface language for standalone screenshots.
    const params = new URLSearchParams(location.search);
    const forcedLanguage = params.get("lang");
    if (forcedLanguage) state.settings.interfaceLanguage = forcedLanguage;
    const fileJobDone = {
      path: "~/Documents/quarterly-report.pdf",
      name: "quarterly-report.pdf",
      kind: "pdf",
      size: 1284000,
      state: "done",
      completed: 11,
      total: 11,
      percent: 100,
      output: "~/Documents/quarterly-report_uk.pdf",
      savedPath: null,
      resultName: "quarterly-report_uk.pdf",
      message: null,
      warnings: 2,
      fallback: false,
      fallbackLabel: "",
      saveError: null,
    };

    if (hash === "empty" || hash === "translate-empty") {
      state.sourceText = "";
      state.translatedText = "";
      state.detectedLanguage = null;
      state.tokensPerSecond = null;
      state.lastDurationMs = null;
    } else if (hash === "progress" || hash === "translate-progress") {
      state.translatedText = "";
      state.isTranslating = true;
      state.completed = 3;
      state.total = 7;
      state.tokensPerSecond = null;
      state.lastDurationMs = null;
    } else if (hash === "streaming") {
      // A translation that is still running but already shows its partial text.
      const output = demoTranslation(state.sourceText);
      state.translatedText = output.slice(0, Math.ceil(output.length / 2));
      state.isTranslating = true;
      state.completed = 3;
      state.total = 7;
      state.tokensPerSecond = null;
      state.lastDurationMs = null;
    } else if (hash === "error" || hash === "translate-error") {
      state.translatedText = "";
      state.backendStatus = "failed";
      state.probeMessage = "Could not connect to http://127.0.0.1:11434. Check that the server is running.";
      state.errorMessage =
        "Could not connect to http://127.0.0.1:11434. Check that the server is running.";
      state.tokensPerSecond = null;
      state.lastDurationMs = null;
    } else if (hash === "files-empty") {
      state.tab = "files";
      state.fileJob = null;
    } else if (hash === "files" || hash === "files-done") {
      state.tab = "files";
      state.fileJob = fileJobDone;
    } else if (hash === "files-progress") {
      state.tab = "files";
      state.fileJob = {
        path: "~/Documents/quarterly-report.pdf",
        name: "quarterly-report.pdf",
        kind: "pdf",
        size: 1284000,
        state: "translating",
        completed: 4,
        total: 11,
        percent: 36,
        output: null,
        savedPath: null,
        resultName: null,
        message: null,
        warnings: 0,
        fallback: false,
        fallbackLabel: "",
        saveError: null,
      };
    } else if (hash === "files-error") {
      state.tab = "files";
      state.fileJob = {
        path: "~/Documents/scan.pdf",
        name: "scan.pdf",
        kind: "pdf",
        size: 4820000,
        state: "failed",
        completed: 0,
        total: 0,
        percent: 0,
        output: null,
        savedPath: null,
        resultName: null,
        message: "No selectable text found. For a scanned PDF, run text recognition first.",
        warnings: 0,
        fallback: false,
        fallbackLabel: "",
        saveError: null,
      };
    } else if (hash === "write" || hash === "write-busy") {
      state.tab = "write";
      state.write = {
        inProgress: hash === "write-busy",
        output: hash === "write-busy" ? "" : WRITE_OUTPUT,
        error: null,
        detectedCode: "en",
        durationMs: hash === "write-busy" ? null : 1240,
        warnings: 0,
      };
    } else if (hash === "write-warning") {
      state.tab = "write";
      state.write = {
        inProgress: false,
        output: WRITE_OUTPUT,
        error: "Some paragraphs are still in the original language (2).",
        detectedCode: "en",
        durationMs: 1240,
        warnings: 2,
      };
    } else if (hash === "markdown") {
      state.translatedText = MARKDOWN_SAMPLE;
      state.resultView = "preview";
    } else if (hash === "source-preview" || hash === "source-markdown-preview") {
      state.sourceText = MARKDOWN_SAMPLE;
      state.translatedText = DEMO_TRANSLATION;
      state.resultView = "preview";
    } else if (hash === "text") {
      state.translatedText = MARKDOWN_SAMPLE;
      state.resultView = "text";
    } else if (hash === "source-markdown") {
      state.translatedText = MARKDOWN_SAMPLE;
      state.resultView = "markdown";
    } else if (hash === "history") {
      state.tab = "history";
    } else if (hash === "history-empty") {
      state.tab = "history";
      state.history = [];
    } else if (hash === "settings-missing") {
      state.backendStatus = "failed";
      state.probeMessage =
        "Server responds, but model “hy-mt2:7b” is missing. Available: hy-mt2:1.8b, translategemma:4b.";
      state.modelsError = state.probeMessage;
      state.providerModels = ["hy-mt2:1.8b", "translategemma:4b", "qwen3:8b"];
    }
    return state;
  }

  let state = scenarioState();
  const listeners = new Set();
  let translateTimer = 0;
  let fileTimer = 0;
  let writeTimer = 0;
  let speakTimer = 0;

  function emit(payload) {
    const copy = clone(payload);
    listeners.forEach((handler) => {
      try {
        handler(copy);
      } catch (error) {
        /* keep the mock alive for the other listeners */
      }
    });
  }

  function later(callback, delay) {
    return setTimeout(callback, delay === undefined ? 0 : delay);
  }

  function numberedId() {
    return "mock-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 7);
  }

  function demoTranslation(text) {
    const value = String(text || "").trim();
    if (!value) return "";
    if (value === DEMO_SOURCE.trim()) return DEMO_TRANSLATION;
    if (value.indexOf("quarterly report") >= 0) return "Квартальний звіт готовий до перегляду.";
    if (value.indexOf("Release notes") >= 0) return "Нотатки до випуску версії 1.4 вже доступні.";
    if (value.indexOf("Customers asked") >= 0)
      return "Клієнти просили офлайн-моделі та менший обсяг завантаження.";
    return "Переклад: " + value;
  }

  function addHistory(source, translation) {
    if (!state.settings.keepHistory) return;
    const provider = state.settings.provider === "ollama" ? "Ollama" : state.settings.provider;
    state.history.unshift({
      id: numberedId(),
      date: new Date().toISOString(),
      sourceText: source,
      translatedText: translation,
      sourceCode: state.sourceLanguage === "auto" ? state.detectedLanguage || "en" : state.sourceLanguage,
      targetCode: state.targetLanguage,
      style: state.style,
      tone: state.tone,
      engine: provider + " · " + state.settings.model,
      durationMs: state.lastDurationMs || 1800,
    });
    state.history = state.history.slice(0, 400);
  }

  function stopTranslate() {
    clearInterval(translateTimer);
    translateTimer = 0;
  }

  function finishTranslate() {
    const output = demoTranslation(state.sourceText);
    state.translatedText = output;
    state.isTranslating = false;
    state.completed = state.total || 1;
    state.tokensPerSecond = 41.2;
    state.lastDurationMs = 1800 + Math.round(Math.random() * 700);
    addHistory(state.sourceText, output);
    emit({ type: "translatedText", value: output });
    emit({ type: "metrics", value: { tokensPerSecond: state.tokensPerSecond, lastDurationMs: state.lastDurationMs } });
    emit({ type: "translating", value: false });
    emit({ type: "history" });
  }

  function startTranslate() {
    stopTranslate();
    if (!String(state.sourceText || "").trim()) return;
    state.errorMessage = null;
    state.isTranslating = true;
    state.completed = 0;
    state.total = 7;
    state.translatedText = "";
    state.tokensPerSecond = null;
    state.lastDurationMs = null;
    emit({ type: "translating", value: true });
    emit({ type: "progress", completed: 0, total: state.total });
    translateTimer = setInterval(() => {
      state.completed = Math.min(state.total, state.completed + 1);
      emit({ type: "progress", completed: state.completed, total: state.total });
      if (state.completed === 3) {
        // Show the streaming preview the real controller now emits.
        const output = demoTranslation(state.sourceText);
        state.translatedText = output.slice(0, Math.ceil(output.length / 2));
        emit({ type: "translationPartial", value: state.translatedText });
      }
      if (state.completed >= state.total) {
        stopTranslate();
        finishTranslate();
      }
    }, 190);
  }

  function stopFileJob() {
    clearInterval(fileTimer);
    fileTimer = 0;
  }

  function fileTick() {
    const job = state.fileJob;
    if (!job) return;
    if (job.state === "reading") {
      job.state = "translating";
      job.total = 11;
      job.completed = 0;
      job.percent = 0;
    } else if (job.state === "translating") {
      job.completed += 1;
      job.percent = Math.round((job.completed / job.total) * 100);
      if (job.completed >= job.total) {
        job.state = "writing";
        job.percent = 100;
      }
    } else if (job.state === "writing") {
      stopFileJob();
      completeFileJob(job);
      return;
    }
    emitFileJob();
  }

  function completeFileJob(job) {
    job.state = "done";
    job.completed = job.total;
    job.percent = 100;
    const suffix = job.kind ? "." + job.kind : ".txt";
    const base = job.path.replace(/\.[^.\\/]+$/, "");
    const targetSuffix = job.kind || "pdf";
    const target = job.target || state.targetLanguage;
    let output = base + "_" + target + "." + targetSuffix;
    if (job.kind === "markdown") output = base + "_" + target + ".md";
    if (job.kind === "text") output = base + "_" + target + ".txt";
    job.output = output;
    job.resultName = output.split(/[\\/]/).pop();
    job.warnings = 2;
    job.state = "done";
    emitFileJob();
    emit({ type: "stateChanged" });
  }

  function startFile(path, target) {
    stopFileJob();
    const name = String(path).split(/[\\/]/).pop() || String(path);
    const extension = (name.split(".").pop() || "").toLowerCase();
    const kinds = { pdf: "pdf", docx: "docx", md: "markdown", markdown: "markdown", mdown: "markdown", txt: "text", text: "text" };
    state.tab = "files";
    state.fileJob = {
      path: path,
      name: name,
      kind: kinds[extension] || "text",
      size: 0,
      target: target || state.targetLanguage,
      state: "reading",
      completed: 0,
      total: 0,
      percent: 0,
      output: null,
      savedPath: null,
      resultName: null,
      message: null,
      warnings: 0,
      fallback: false,
      fallbackLabel: "",
      saveError: null,
    };
    emitFileJob();
    later(() => {
      if (!state.fileJob) return;
      state.fileJob.state = "translating";
      state.fileJob.total = 11;
      state.fileJob.completed = 1;
      state.fileJob.percent = 9;
      emitFileJob();
      fileTimer = setInterval(fileTick, 230);
    }, 620);
  }

  function detectDemoLanguage(text) {
    const value = String(text || "");
    if (/[іїєґ]/i.test(value)) return "uk";
    if (/[а-я]/i.test(value)) return "uk";
    if (/[äöüß]/i.test(value)) return "de";
    if (/[ñ¿¡]/i.test(value)) return "es";
    if (/[àâçéèêëîïôûùüÿœ]/i.test(value)) return "fr";
    return "en";
  }

  function startWrite(text, targetCode) {
    clearTimeout(writeTimer);
    const auto = !targetCode || targetCode === "auto";
    const detected = auto ? detectDemoLanguage(text) : targetCode;
    state.write = {
      inProgress: true,
      output: "",
      error: null,
      detectedCode: detected,
      durationMs: null,
      warnings: 0,
    };
    emitWrite();
    writeTimer = setTimeout(() => {
      state.write.inProgress = false;
      state.write.output = detected === "uk" ? WRITE_OUTPUT_UK : WRITE_OUTPUT;
      state.write.durationMs = 1240;
      state.write.detectedCode = detected;
      emit({ type: "stateChanged" });
      emitWrite();
    }, 950);
  }

  // AppEvent::Write is a newtype of WriteState, which serde merges next to
  // `type` (there is no `value` key for struct newtypes).
  function emitWrite() {
    emit(Object.assign({ type: "write" }, clone(state.write)));
  }

  function emitFileJob() {
    if (!state.fileJob) emit({ type: "fileJob", fileJob: null });
    else emit(Object.assign({ type: "fileJob" }, clone(state.fileJob)));
  }

  function promptPreview(style, tone, targetCode) {
    const language = (window.OFM_LANGUAGES || []).find((item) => item.code === targetCode);
    const target = language ? language.name : "Ukrainian";
    const lines = [];
    let instruction = "Translate the following text into " + target + ".";
    if (style === "literal") instruction += " Translate it literally, keeping the sentence structure.";
    else if (style === "natural") instruction += " Convey the meaning naturally rather than word for word.";
    if (tone === "formal") instruction += " Use a formal, professional tone.";
    else if (tone === "casual") instruction += " Use a casual, conversational tone.";
    instruction += " Note that you should only output the translated result without any additional explanation:";
    lines.push(instruction);
    lines.push("");
    lines.push(tr("Sample text"));
    return lines.join("\n");
  }

  const commands = {
    get_state() {
      return clone(state);
    },
    get_settings() {
      return clone(state.settings);
    },
    get_translations() {
      const language =
        state.settings.interfaceLanguage === "system"
          ? String(navigator.language || "en").slice(0, 2)
          : state.settings.interfaceLanguage;
      return clone(TRANSLATIONS[language] || {});
    },
    get_catalog() {
      return clone(CATALOG);
    },
    set_tab(args) {
      if (args && args.tab) state.tab = String(args.tab);
      emit({ type: "tab", value: state.tab });
      return clone(state);
    },
    set_source_text(args) {
      state.sourceText = String((args && args.text) || "");
      if (state.sourceText.trim()) state.detectedLanguage = "en";
      else state.detectedLanguage = null;
      return clone(state);
    },
    set_source_language(args) {
      state.sourceLanguage = String((args && args.code) || "auto");
      state.detectedLanguage = state.sourceLanguage === "auto" ? "en" : null;
      return clone(state);
    },
    set_target_language(args) {
      state.targetLanguage = String((args && args.code) || "uk");
      return clone(state);
    },
    swap_languages() {
      const previousSource = state.sourceLanguage;
      const previousTarget = state.targetLanguage;
      state.targetLanguage = previousSource === "auto" ? state.detectedLanguage || "en" : previousSource;
      state.sourceLanguage = previousTarget;
      state.detectedLanguage = state.sourceLanguage === "auto" ? state.detectedLanguage : null;
      state.translatedText = "";
      state.tokensPerSecond = null;
      state.lastDurationMs = null;
      emit({ type: "languages", value: { source: state.sourceLanguage, target: state.targetLanguage } });
      emit({ type: "stateChanged" });
      return clone(state);
    },
    set_style(args) {
      state.style = String((args && args.style) || "auto");
      emit({ type: "style", value: state.style });
      return clone(state);
    },
    set_tone(args) {
      state.tone = String((args && args.tone) || "standard");
      emit({ type: "tone", value: state.tone });
      return clone(state);
    },
    set_result_view(args) {
      state.resultView = String((args && args.mode) || "preview");
      emit({ type: "resultView", value: state.resultView });
      return clone(state);
    },
    clear_source() {
      stopTranslate();
      state.sourceText = "";
      state.translatedText = "";
      state.detectedLanguage = null;
      state.warningCount = 0;
      state.errorMessage = null;
      state.tokensPerSecond = null;
      state.lastDurationMs = null;
      state.isTranslating = false;
      emit({ type: "stateChanged" });
      return clone(state);
    },
    translate_text(args) {
      if (args && args.force === false && state.translatedText) return clone(state);
      startTranslate();
      return clone(state);
    },
    cancel() {
      stopTranslate();
      state.isTranslating = false;
      emit({ type: "translating", value: false });
      emit({ type: "stateChanged" });
      return clone(state);
    },
    translate_clipboard() {
      state.sourceText = "The quarterly report is ready for review.";
      state.detectedLanguage = "en";
      state.tab = "translate";
      emit({ type: "sourceText", value: state.sourceText });
      startTranslate();
      return clone(state);
    },
    translate_selection() {
      state.sourceText = "Selected text from another application.";
      state.detectedLanguage = "en";
      state.tab = "translate";
      emit({ type: "sourceText", value: state.sourceText });
      startTranslate();
      return clone(state);
    },
    copy_translation() {
      const text = state.translatedText;
      if (navigator.clipboard && navigator.clipboard.writeText && text) {
        navigator.clipboard.writeText(text).catch(() => {});
      }
      emit({ type: "copyFeedback", value: tr("Translation copied") });
      return true;
    },
    copy_source() {
      const text = state.sourceText;
      if (navigator.clipboard && navigator.clipboard.writeText && text) {
        navigator.clipboard.writeText(text).catch(() => {});
      }
      emit({ type: "copyFeedback", value: tr("Source text copied") });
      return true;
    },
    copy_text(args) {
      const text = (args && args.text) || "";
      if (navigator.clipboard && navigator.clipboard.writeText && text) {
        navigator.clipboard.writeText(text).catch(() => {});
      }
      emit({ type: "copyFeedback", value: tr("Copied") });
      return true;
    },
    read_clipboard() {
      return DEMO_SOURCE;
    },
    speak(args) {
      clearTimeout(speakTimer);
      state.speaking = String((args && args.target) || "translation");
      emit({ type: "speaking", value: state.speaking });
      speakTimer = setTimeout(() => {
        state.speaking = "";
        emit({ type: "speaking", value: "" });
      }, 3200);
      return true;
    },
    stop_speaking() {
      clearTimeout(speakTimer);
      state.speaking = "";
      emit({ type: "speaking", value: "" });
      return true;
    },
    check_connection() {
      state.backendStatus = "checking";
      emit({ type: "backendStatus", value: "checking" });
      later(() => {
        state.backendStatus = "connected";
        state.probeMessage = "Connection works. Model “" + state.settings.model + "” is available.";
        emit({ type: "probeMessage", value: state.probeMessage });
        emit({ type: "backendStatus", value: "connected" });
      }, 650);
      return true;
    },
    connect_and_load_models() {
      state.backendStatus = "checking";
      state.modelsLoading = true;
      state.modelsError = null;
      emit({ type: "backendStatus", value: "checking" });
      emit({ type: "modelsLoading", value: true });
      later(() => {
        state.backendStatus = "connected";
        state.probeMessage = "Connection works. Model “" + state.settings.model + "” is available.";
        state.providerModels = ["hy-mt2:7b", "hy-mt2:1.8b", "hy-mt2:30b", "translategemma:4b", "qwen3:8b"];
        state.modelsLoading = false;
        emit({ type: "probeMessage", value: state.probeMessage });
        emit({ type: "backendStatus", value: "connected" });
        emit({ type: "models", value: state.providerModels });
        emit({ type: "modelsLoading", value: false });
      }, 750);
      return true;
    },
    load_fallback_models() {
      state.fallbackModelsLoading = true;
      state.fallbackModelsError = null;
      emit({ type: "fallbackModelsLoading", value: true });
      later(() => {
        state.fallbackModelsLoading = false;
        state.fallbackModels = ["gemma4:31b", "mistral-large-4"];
        emit({ type: "fallbackModels", value: state.fallbackModels });
        emit({ type: "fallbackModelsLoading", value: false });
      }, 600);
      return true;
    },
    list_models() {
      return clone(state.providerModels);
    },
    list_voices() {
      return clone(VOICES);
    },
    preview_prompt(args) {
      return {
        prompt: promptPreview(
          (args && args.style) || "auto",
          (args && args.tone) || "standard",
          (args && args.targetCode) || "uk"
        ),
      };
    },
    apply_catalog_entry(args) {
      const modelId = (args && args.modelId) || "";
      const entry = CATALOG.find((item) => item.modelId === modelId);
      if (!entry) throw new Error("Model “" + modelId + "” not found.");
      state.settings.model = entry.modelId;
      const providerValue = providerValueFor(entry.provider);
      if (providerValue) {
        // Mirrors AppSettings::apply_provider: a session key belongs to the
        // provider it was issued for, never to the newly selected one.
        if (providerValue !== state.settings.provider) state.settings.apiKey = "";
        state.settings.provider = providerValue;
        if (providerValue === "ollama") state.settings.baseUrl = "http://127.0.0.1:11434";
        else if (providerValue === "ollamaCloud") state.settings.baseUrl = "https://ollama.com/v1";
        else if (providerValue === "openRouter") state.settings.baseUrl = "https://openrouter.ai/api/v1";
      }
      emit({ type: "settings", value: state.settings });
      return true;
    },
    apply_model(args) {
      const modelId = String((args && args.modelId) || "").trim();
      if (!modelId) return false;
      const entry = CATALOG.find((item) => item.modelId === modelId);
      if (entry) {
        const providerValue = providerValueFor(entry.provider);
        if (providerValue) state.settings.provider = providerValue;
        if (providerValue === "ollama") state.settings.baseUrl = "http://127.0.0.1:11434";
        else if (providerValue === "ollamaCloud") state.settings.baseUrl = "https://ollama.com/v1";
        else if (providerValue === "openRouter") state.settings.baseUrl = "https://openrouter.ai/api/v1";
      }
      state.settings.model = modelId;
      state.probeMessage = "Connection works. Model “" + modelId + "” is available.";
      emit({ type: "settings", value: state.settings });
      emit({ type: "probeMessage", value: state.probeMessage });
      return true;
    },
    get_diagnostics() {
      return {
        settingsPath: "~/.config/deepl-ofm/settings.json",
        historyPath: "~/.local/share/deepl-ofm/history.json",
        secretBackend: "Windows Credential Manager",
        version: "2.0.1",
        interfaceLanguage: state.settings.interfaceLanguage,
        providerCount: 9,
        catalogCount: CATALOG.length,
      };
    },
    get_startup() {
      const params = new URLSearchParams(location.search);
      const startup = params.get("startup") || "";
      if (startup === "catalog") return { catalog: true, writeText: null, tab: null };
      if (startup === "write") {
        return { catalog: false, writeText: WRITE_SOURCE, tab: "write" };
      }
      if (startup === "write-text") {
        // Mirrors `--write-text`: the text is in the payload, no tab requested.
        return { catalog: false, writeText: WRITE_SOURCE, tab: null };
      }
      if (["translate", "files", "write", "history"].includes(startup)) {
        return { catalog: false, writeText: null, tab: startup };
      }
      return { catalog: false, writeText: null, tab: null };
    },
    get_login_item() {
      return { status: state.loginItemStatus, error: state.loginItemError };
    },
    set_login_item(args) {
      const enabled = !!(args && args.enabled);
      if (state.loginItemStatus === "requiresApproval") return true;
      state.loginItemStatus = enabled ? "enabled" : "disabled";
      state.loginItemError = null;
      emit({ type: "loginItem", value: state.loginItemStatus });
      return true;
    },
    open_login_item_settings() {
      return true;
    },
    save_settings(args) {
      const incoming = args && args.settings ? args.settings : {};
      state.settings = Object.assign({}, state.settings, incoming);
      if (!state.settings.model) state.settings.model = "hy-mt2:7b";
      state.hotkeyMessage = "";
      state.selectionHotkeyMessage = "";
      emit({ type: "settings", value: state.settings });
      emit({ type: "stateChanged" });
      return clone(state.settings);
    },
    set_interface_language(args) {
      state.settings.interfaceLanguage = String((args && args.code) || "system");
      emit({ type: "interfaceLanguage", value: state.settings.interfaceLanguage });
      return true;
    },
    pick_file() {
      return "~/Documents/quarterly-report.pdf";
    },
    pick_save_path(args) {
      const suggested = (args && args.suggestedName) || "translation.pdf";
      return "~/Documents/" + suggested;
    },
    translate_file(args) {
      startFile(
        (args && args.path) || "~/Documents/quarterly-report.pdf",
        args && args.target
      );
      return true;
    },
    cancel_file_translation() {
      stopFileJob();
      if (state.fileJob) {
        state.fileJob.state = "cancelled";
        state.fileJob.message = tr("Cancelled");
        emitFileJob();
      }
      return true;
    },
    save_translated_file(args) {
      if (!state.fileJob) return false;
      const destination = (args && args.path) || "";
      if (!destination) return false;
      // The staged output stays the source for every later save.
      state.fileJob.savedPath = destination;
      state.fileJob.resultName = destination.split(/[\\/]/).pop();
      state.fileJob.saveError = null;
      emitFileJob();
      return true;
    },
    clear_file_job() {
      stopFileJob();
      state.fileJob = null;
      emitFileJob();
      return true;
    },
    reveal_in_folder() {
      return true;
    },
    write_text(args) {
      startWrite(String((args && args.text) || ""), args && args.targetCode);
      return true;
    },
    cancel_write() {
      clearTimeout(writeTimer);
      state.write.inProgress = false;
      state.write.error = null;
      emit({ type: "stateChanged" });
      return true;
    },
    history_list() {
      return clone(state.history);
    },
    history_search(args) {
      const query = String((args && args.query) || "").trim().toLowerCase();
      if (!query) return clone(state.history);
      return clone(
        state.history.filter((entry) =>
          (entry.sourceText + " " + entry.translatedText + " " + entry.engine)
            .toLowerCase()
            .includes(query)
        )
      );
    },
    history_delete(args) {
      const id = (args && args.id) || "";
      state.history = state.history.filter((entry) => entry.id !== id);
      emit({ type: "history" });
      return true;
    },
    history_clear() {
      state.history = [];
      emit({ type: "history" });
      return true;
    },
    load_history_entry(args) {
      const id = (args && args.id) || "";
      const entry = state.history.find((item) => item.id === id);
      if (!entry) return false;
      state.sourceText = entry.sourceText;
      state.translatedText = entry.translatedText;
      state.sourceLanguage = "auto";
      state.targetLanguage = entry.targetCode;
      state.detectedLanguage = entry.sourceCode;
      state.style = entry.style;
      state.tone = entry.tone;
      state.tab = "translate";
      state.tokensPerSecond = null;
      state.lastDurationMs = entry.durationMs;
      state.errorMessage = null;
      emit({ type: "stateChanged" });
      return true;
    },
    open_url(args) {
      try {
        if (args && args.url) window.open(args.url, "_blank", "noopener,noreferrer");
      } catch (error) {
        /* headless */
      }
      return true;
    },
  };

  window.OFM_MOCK = {
    invoke(name, args) {
      const command = commands[name];
      if (!command) {
        return Promise.reject(new Error("Unknown mock command: " + name));
      }
      return new Promise((resolve, reject) => {
        try {
          resolve(clone(command(args || {})));
        } catch (error) {
          reject(error);
        }
      });
    },
    listen(handler) {
      listeners.add(handler);
      return () => listeners.delete(handler);
    },
    getState() {
      return clone(state);
    },
    emit,
    catalog: CATALOG,
    writeDraft: WRITE_SOURCE,
  };
})();
