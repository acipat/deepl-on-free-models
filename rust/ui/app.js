/* ==========================================================================
   DeepL-oFM — frontend controller
   Talks to Rust through window.__TAURI__ when present, otherwise through the
   standalone mock in mock.js. All state comes from the AppState snapshot;
   events are hints that patch or invalidate it.
   ========================================================================== */
(function () {
  "use strict";

  /* The language bar is sized from constants, never from measured text: the
     two pickers are a fixed 164 px, so a long language name cannot move the
     cluster.  The full style/tone chips are modelled as 1100 px plus five
     pixels per translated label character; the same numbers decide the Qt
     bar's breakpoint. */
  const FULL_CHIPS_BASE_WIDTH = 1100;
  const FULL_CHIPS_PER_CHARACTER = 5;
  const CHIP_LABELS = [
    "Style",
    "Auto",
    "Literal",
    "Natural",
    "Tone",
    "Default",
    "Formal",
    "Casual",
  ];

  /* ------------------------------------------------------------------ data */

  const PROVIDERS = [
    {
      value: "ollama",
      title: "Ollama",
      baseUrl: "http://127.0.0.1:11434",
      local: true,
      requiresKey: false,
      keyUrl: null,
      detail: "Local Ollama server. The model must be pulled with ollama pull.",
    },
    {
      value: "ollamaCloud",
      title: "Ollama Cloud",
      baseUrl: "https://ollama.com/v1",
      local: false,
      requiresKey: true,
      keyUrl: "https://ollama.com/settings/keys",
      detail: "Ollama Cloud through a direct API key. No local server is needed.",
    },
    {
      value: "lmStudio",
      title: "LM Studio",
      baseUrl: "http://127.0.0.1:1234/v1",
      local: true,
      requiresKey: false,
      keyUrl: null,
      detail:
        "LM Studio with its local server enabled. The model ID is shown in LM Studio.",
    },
    {
      value: "omlx",
      title: "oMLX",
      baseUrl: "http://127.0.0.1:50220/v1",
      local: true,
      requiresKey: false,
      keyUrl: null,
      detail:
        "oMLX — an MLX server for Apple Silicon. Enable the OpenAI-compatible API.",
    },
    {
      value: "llamaCpp",
      title: "llama.cpp",
      baseUrl: "http://127.0.0.1:8080/v1",
      local: true,
      requiresKey: false,
      keyUrl: null,
      detail: "llama-server with --api. The default address is port 8080.",
    },
    {
      value: "openRouter",
      title: "OpenRouter",
      baseUrl: "https://openrouter.ai/api/v1",
      local: false,
      requiresKey: true,
      keyUrl: "https://openrouter.ai/keys",
      detail: "Hundreds of models with one key. Free models are marked :free.",
    },
    {
      value: "groq",
      title: "Groq",
      baseUrl: "https://api.groq.com/openai/v1",
      local: false,
      requiresKey: true,
      keyUrl: "https://console.groq.com/keys",
      detail: "Very fast cloud. Has a free tier with request limits.",
    },
    {
      value: "cerebras",
      title: "Cerebras",
      baseUrl: "https://api.cerebras.ai/v1",
      local: false,
      requiresKey: true,
      keyUrl: "https://cloud.cerebras.ai",
      detail: "Fastest inference for open models. Has a free tier with limits.",
    },
    {
      value: "custom",
      title: "Custom",
      baseUrl: "http://127.0.0.1:1234/v1",
      local: false,
      requiresKey: false,
      keyUrl: null,
      detail:
        "Any OpenAI-compatible server: your proxy, vLLM, LocalAI, Together, and so on.",
    },
  ];

  const SETTINGS_TABS = ["model", "generation", "behaviour", "hotkeys", "about"];
  const TABS = ["translate", "files", "write", "history"];
  const RUNNING_FILE_STATES = ["reading", "translating", "writing"];

  const nativeCore = window.__TAURI__ && window.__TAURI__.core;
  const NATIVE = !!(nativeCore && typeof nativeCore.invoke === "function");
  const MOCK = window.OFM_MOCK || null;

  const t = typeof window.t === "function" ? window.t : (key) => key;
  const LANGS = Array.isArray(window.OFM_LANGUAGES) ? window.OFM_LANGUAGES : [];
  const UI_LANGS = Array.isArray(window.OFM_INTERFACE_LANGUAGES)
    ? window.OFM_INTERFACE_LANGUAGES
    : [];

  /* --------------------------------------------------------------- helpers */

  const SVG_NS = "http://www.w3.org/2000/svg";

  function $(id) {
    return document.getElementById(id);
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function icon(id, className) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", className || "icon");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS(SVG_NS, "use");
    use.setAttribute("href", "#i-" + id);
    svg.append(use);
    return svg;
  }

  function closest(target, selector) {
    return target && target.closest ? target.closest(selector) : null;
  }

  function debounce(fn, wait) {
    let timer = 0;
    return function debounced() {
      const args = arguments;
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(null, args), wait);
    };
  }

  function formatTemplate(template, args) {
    let index = 0;
    return String(template).replace(/%(?:\.(\d+))?([@dsf])|%%/g, (match, precision, kind) => {
      if (match === "%%") return "%";
      const value = args[index];
      index += 1;
      if (kind === "f") {
        return formatDecimal(Number(value), precision ? Number(precision) : 1);
      }
      if (kind === "d") {
        return String(Math.trunc(Number(value)));
      }
      return value === undefined || value === null ? "" : String(value);
    });
  }

  /** Translate with optional positional args; unknown keys fall back to key. */
  function tr(key) {
    const args = Array.prototype.slice.call(arguments, 1);
    let value = key;
    // `get_translations` (active interface language) wins; strings.js is the
    // English/offline fallback; the key itself is the last resort.
    if (
      local &&
      local.catalogue &&
      Object.prototype.hasOwnProperty.call(local.catalogue, key) &&
      local.catalogue[key]
    ) {
      value = String(local.catalogue[key]);
    } else if (typeof window.OFM_TRANSLATE === "function") {
      value = window.OFM_TRANSLATE(key);
    }
    return args.length ? formatTemplate(value, args) : value;
  }

  function characters(count) {
    return tr(count === 1 ? "%d character" : "%d characters", count);
  }

  /** Active interface language: `system` follows the browser. */
  function uiLanguageCode() {
    const code = state && state.settings ? state.settings.interfaceLanguage : "en";
    if (!code || code === "system") {
      const browser = (navigator.language || "en").split("-")[0];
      return browser || "en";
    }
    return String(code);
  }

  function numberFormat(options) {
    try {
      return new Intl.NumberFormat(uiLanguageCode(), options);
    } catch (error) {
      return new Intl.NumberFormat("en", options);
    }
  }

  function formatNumber(value) {
    return numberFormat().format(Math.trunc(Number(value)));
  }

  function formatDecimal(value, digits) {
    const places = digits === undefined ? 1 : digits;
    return numberFormat({
      minimumFractionDigits: places,
      maximumFractionDigits: places,
    }).format(Number(value));
  }

  function formatSeconds(milliseconds) {
    if (milliseconds === null || milliseconds === undefined) return "";
    return tr("%.1f s", Number(milliseconds) / 1000);
  }

  function formatDuration(milliseconds) {
    if (milliseconds === null || milliseconds === undefined) return "";
    const ms = Number(milliseconds);
    if (!Number.isFinite(ms)) return "";
    if (ms < 1000) return tr("%d ms", Math.round(ms));
    return tr("%.1f s", ms / 1000);
  }

  function basename(path) {
    if (!path) return "";
    const parts = String(path).split(/[\\/]/);
    return parts[parts.length - 1] || String(path);
  }

  function fileSize(bytes) {
    const size = Number(bytes) || 0;
    if (size <= 0) return "";
    const units = ["B", "KB", "MB", "GB"];
    let value = size;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024;
      unit += 1;
    }
    const digits = value >= 10 || unit === 0 ? 0 : 1;
    return formatDecimal(value, digits) + " " + units[unit];
  }

  function providerInfo(value) {
    const found = PROVIDERS.find((item) => item.value === value);
    if (found) return found;
    const spaced = String(value || "")
      .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
      .trim();
    const title = spaced ? spaced.charAt(0).toUpperCase() + spaced.slice(1) : "Custom";
    return {
      value: value || "custom",
      title: title,
      baseUrl: "",
      local: false,
      requiresKey: false,
      keyUrl: null,
      detail: "Any OpenAI-compatible server: your proxy, vLLM, LocalAI, Together, and so on.",
    };
  }

  function providerTitle(value) {
    return providerInfo(value).title;
  }

  function languageName(code) {
    if (!code || code === "auto") return tr("Auto-detect");
    const found = LANGS.find((item) => item.code === code);
    return found ? tr(found.name) : String(code).toUpperCase();
  }

  function relativeDate(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return String(iso);
    const diff = Date.now() - date.getTime();
    if (diff < 0) return absoluteDate(date);
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return tr("Just now");
    if (minutes < 60) return tr("%d min ago", minutes);
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return tr("%d h ago", hours);
    const days = Math.floor(hours / 24);
    if (days === 1) return tr("Yesterday");
    if (days < 7) return tr("%d days ago", days);
    return absoluteDate(date);
  }

  function absoluteDate(date) {
    try {
      return date.toLocaleDateString(uiLanguageCode(), {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch (error) {
      return date.toISOString().slice(0, 10);
    }
  }

  function comboFromObject(raw) {
    if (!raw) return { key: "", ctrl: false, alt: false, shift: false, meta: false };
    if (typeof raw === "string") return parseCombo(raw);
    const key = String(raw.key || raw.code || "").toLowerCase();
    let modifiers = raw.modifiers;
    if (typeof modifiers === "string") modifiers = [modifiers];
    const has = (name) =>
      (typeof modifiers !== "undefined" && Array.isArray(modifiers)
        ? modifiers.includes(name)
        : false) || raw[name] === true;
    return {
      key: key,
      ctrl: has("ctrl") || raw.control === true,
      alt: has("alt") || raw.option === true,
      shift: has("shift") === true,
      meta: has("meta") || has("cmd") || has("command") || has("super"),
    };
  }

  function parseCombo(text) {
    const parts = String(text)
      .split("+")
      .map((part) => part.trim())
      .filter(Boolean);
    const combo = { key: "", ctrl: false, alt: false, shift: false, meta: false };
    parts.forEach((part) => {
      const lower = part.toLowerCase();
      if (["ctrl", "control"].includes(lower)) combo.ctrl = true;
      else if (["alt", "option", "opt"].includes(lower)) combo.alt = true;
      else if (lower === "shift") combo.shift = true;
      else if (["meta", "cmd", "command", "super", "win"].includes(lower)) combo.meta = true;
      else combo.key = lower;
    });
    return combo;
  }

  function comboDisplay(combo) {
    if (!combo || !combo.key) return tr("Press a combination…");
    const parts = [];
    if (combo.ctrl) parts.push("Ctrl");
    if (combo.alt) parts.push("Alt");
    if (combo.shift) parts.push("Shift");
    if (combo.meta) parts.push("Meta");
    const key = combo.key;
    const labels = {
      space: "Space",
      escape: "Esc",
      enter: "Enter",
      tab: "Tab",
      backspace: "Backspace",
      delete: "Delete",
      arrowup: "↑",
      arrowdown: "↓",
      arrowleft: "←",
      arrowright: "→",
    };
    parts.push(labels[key] || (key.length === 1 ? key.toUpperCase() : key.toUpperCase()));
    return parts.join("+");
  }

  function comboIsValid(combo) {
    return !!(combo && combo.key && (combo.ctrl || combo.alt || combo.meta));
  }

  /* ------------------------------------------------------------ normalising */

  function pick(object, names, fallback) {
    if (!object || typeof object !== "object") return fallback;
    for (const name of names) {
      if (object[name] !== undefined) return object[name];
    }
    return fallback;
  }

  function asString(value, fallback) {
    return typeof value === "string" ? value : value === null || value === undefined ? fallback : String(value);
  }

  function asBool(value, fallback) {
    if (typeof value === "boolean") return value;
    if (value === "true" || value === 1) return true;
    if (value === "false" || value === 0) return false;
    return fallback;
  }

  function asNumber(value, fallback) {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function normalizeKeyCombo(value, fallback) {
    const combo = comboFromObject(value);
    return combo.key ? combo : comboFromObject(fallback);
  }

  function defaultSettings() {
    return {
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
      lastTargetCode: "en",
      lastSourceCode: "auto",
    };
  }

  function normalizeSettings(raw) {
    const base = defaultSettings();
    if (!raw || typeof raw !== "object") return base;
    return {
      provider: asString(pick(raw, ["provider"], base.provider), base.provider),
      baseUrl: asString(pick(raw, ["baseUrl", "base_url"], base.baseUrl), base.baseUrl),
      model: asString(pick(raw, ["model"], base.model), base.model),
      apiKey: asString(pick(raw, ["apiKey", "api_key"], base.apiKey), base.apiKey),
      fallbackEnabled: asBool(
        pick(raw, ["fallbackEnabled", "fallback_enabled"], base.fallbackEnabled),
        base.fallbackEnabled
      ),
      fallbackProvider: asString(
        pick(raw, ["fallbackProvider", "fallback_provider"], base.fallbackProvider),
        base.fallbackProvider
      ),
      fallbackBaseUrl: asString(
        pick(raw, ["fallbackBaseUrl", "fallback_base_url"], base.fallbackBaseUrl),
        base.fallbackBaseUrl
      ),
      fallbackModel: asString(
        pick(raw, ["fallbackModel", "fallback_model"], base.fallbackModel),
        base.fallbackModel
      ),
      fallbackApiKey: asString(
        pick(raw, ["fallbackApiKey", "fallback_api_key"], base.fallbackApiKey),
        base.fallbackApiKey
      ),
      temperature: asNumber(pick(raw, ["temperature"], base.temperature), base.temperature),
      topP: asNumber(pick(raw, ["topP", "top_p"], base.topP), base.topP),
      topK: Math.round(asNumber(pick(raw, ["topK", "top_k"], base.topK), base.topK)),
      repetitionPenalty: asNumber(
        pick(raw, ["repetitionPenalty", "repetition_penalty"], base.repetitionPenalty),
        base.repetitionPenalty
      ),
      contextWindow: Math.round(
        asNumber(pick(raw, ["contextWindow", "context_window"], base.contextWindow), base.contextWindow)
      ),
      autoTranslate: asBool(
        pick(raw, ["autoTranslate", "auto_translate"], base.autoTranslate),
        base.autoTranslate
      ),
      debounce: asNumber(pick(raw, ["debounce"], base.debounce), base.debounce),
      hotKey: normalizeKeyCombo(pick(raw, ["hotKey", "hot_key"], base.hotKey), base.hotKey),
      selectionHotKey: normalizeKeyCombo(
        pick(raw, ["selectionHotKey", "selection_hot_key"], base.selectionHotKey),
        base.selectionHotKey
      ),
      showInMenuBar: asBool(
        pick(raw, ["showInMenuBar", "show_in_menu_bar"], base.showInMenuBar),
        base.showInMenuBar
      ),
      speechVoiceId: asString(
        pick(raw, ["speechVoiceId", "speech_voice_id"], base.speechVoiceId),
        base.speechVoiceId
      ),
      keepHistory: asBool(
        pick(raw, ["keepHistory", "keep_history"], base.keepHistory),
        base.keepHistory
      ),
      warmUpOnLaunch: asBool(
        pick(raw, ["warmUpOnLaunch", "warm_up_on_launch"], base.warmUpOnLaunch),
        base.warmUpOnLaunch
      ),
      interfaceLanguage: asString(
        pick(raw, ["interfaceLanguage", "interface_language"], base.interfaceLanguage),
        base.interfaceLanguage
      ),
      resultView: asString(pick(raw, ["resultView", "result_view"], base.resultView), base.resultView),
      lastStyle: asString(pick(raw, ["lastStyle", "last_style"], base.lastStyle), base.lastStyle),
      lastTone: asString(pick(raw, ["lastTone", "last_tone"], base.lastTone), base.lastTone),
      lastTargetCode: asString(
        pick(raw, ["lastTargetCode", "last_target_code"], base.lastTargetCode),
        base.lastTargetCode
      ),
      lastSourceCode: asString(
        pick(raw, ["lastSourceCode", "last_source_code"], base.lastSourceCode),
        base.lastSourceCode
      ),
    };
  }

  function normalizeHistoryEntry(raw) {
    if (!raw || typeof raw !== "object") return null;
    const id = asString(pick(raw, ["id"], ""), "");
    if (!id) return null;
    return {
      id: id,
      date: asString(pick(raw, ["date"], ""), ""),
      sourceText: asString(pick(raw, ["sourceText", "source_text"], ""), ""),
      translatedText: asString(pick(raw, ["translatedText", "translated_text"], ""), ""),
      sourceCode: asString(pick(raw, ["sourceCode", "source_code"], "auto"), "auto"),
      targetCode: asString(pick(raw, ["targetCode", "target_code"], "en"), "en"),
      style: asString(pick(raw, ["style"], "auto"), "auto"),
      tone: asString(pick(raw, ["tone"], "standard"), "standard"),
      engine: asString(pick(raw, ["engine"], ""), ""),
      durationMs: asNumber(pick(raw, ["durationMs", "duration_ms"], 0), 0),
    };
  }

  function normalizeHistory(list) {
    if (!Array.isArray(list)) return [];
    return list.map(normalizeHistoryEntry).filter(Boolean);
  }

  function normalizeFileJob(raw) {
    if (!raw || typeof raw !== "object") return null;
    const path = asString(pick(raw, ["path"], ""), "");
    return {
      path: path,
      name: asString(pick(raw, ["name"], basename(path)), basename(path)),
      kind: asString(pick(raw, ["kind"], ""), ""),
      size: asNumber(pick(raw, ["size"], 0), 0),
      state: asString(pick(raw, ["state"], "reading"), "reading"),
      completed: Math.max(0, Math.round(asNumber(pick(raw, ["completed"], 0), 0))),
      total: Math.max(0, Math.round(asNumber(pick(raw, ["total"], 0), 0))),
      percent: Math.max(0, Math.min(100, Math.round(asNumber(pick(raw, ["percent"], 0), 0)))),
      output: pick(raw, ["output"], null) || null,
      savedPath: pick(raw, ["savedPath", "saved_path"], null) || null,
      resultName: pick(raw, ["resultName", "result_name"], null) || null,
      message: asString(pick(raw, ["message"], ""), ""),
      warnings: Math.max(0, Math.round(asNumber(pick(raw, ["warnings"], 0), 0))),
      fallback: asBool(pick(raw, ["fallback"], false), false),
      fallbackLabel: asString(pick(raw, ["fallbackLabel", "fallback_label"], ""), ""),
      saveError: pick(raw, ["saveError", "save_error"], null) || null,
    };
  }

  function normalizeWrite(raw) {
    // Mirrors ofm_app::WriteState (crates/app/src/state.rs): inProgress, output,
    // error, detectedCode, durationMs and warnings. There is no `text` or
    // `targetCode` field on the Rust side.
    const base = {
      output: "",
      running: false,
      error: null,
      durationMs: null,
      detectedCode: null,
      warnings: 0,
    };
    if (!raw || typeof raw !== "object") return base;
    return {
      output: asString(pick(raw, ["output", "result", "translatedText", "translated_text"], ""), ""),
      running: asBool(
        pick(raw, ["inProgress", "in_progress", "running", "isRunning", "is_running"], false),
        false
      ),
      error: pick(raw, ["error", "errorMessage", "error_message"], null) || null,
      durationMs: pick(raw, ["durationMs", "duration_ms"], null),
      detectedCode: pick(raw, ["detectedCode", "detected_code"], null) || null,
      warnings: Math.max(0, Math.round(asNumber(pick(raw, ["warnings"], 0), 0))),
    };
  }

  function defaultState() {
    return {
      tab: "translate",
      sourceText: "",
      translatedText: "",
      isTranslating: false,
      completed: 0,
      total: 0,
      warningCount: 0,
      errorMessage: null,
      sourceLanguage: "auto",
      targetLanguage: "en",
      detectedLanguage: null,
      style: "auto",
      tone: "standard",
      resultView: "preview",
      backendStatus: "unknown",
      probeMessage: "",
      providerModels: [],
      modelsLoading: false,
      modelsError: null,
      fallbackModels: [],
      fallbackModelsLoading: false,
      fallbackModelsError: null,
      usingFallback: false,
      tokensPerSecond: null,
      lastDurationMs: null,
      speaking: "",
      hotkeyMessage: "",
      selectionHotkeyMessage: "",
      loginItemStatus: "disabled",
      loginItemError: null,
      fileJob: null,
      write: normalizeWrite(null),
      history: [],
      historyError: false,
      settings: defaultSettings(),
      version: "",
    };
  }

  function normalizeState(raw) {
    if (raw && typeof raw === "object" && raw.state && typeof raw.state === "object") {
      raw = raw.state;
    }
    const state = defaultState();
    if (!raw || typeof raw !== "object") return state;
    state.tab = asString(pick(raw, ["tab"], state.tab), state.tab);
    state.sourceText = asString(pick(raw, ["sourceText", "source_text"], ""), "");
    state.translatedText = asString(pick(raw, ["translatedText", "translated_text"], ""), "");
    state.isTranslating = asBool(
      pick(raw, ["isTranslating", "is_translating"], false),
      false
    );
    state.completed = Math.max(0, Math.round(asNumber(pick(raw, ["completed"], 0), 0)));
    state.total = Math.max(0, Math.round(asNumber(pick(raw, ["total"], 0), 0)));
    state.warningCount = Math.max(0, Math.round(asNumber(pick(raw, ["warningCount", "warning_count"], 0), 0)));
    state.errorMessage = pick(raw, ["errorMessage", "error_message"], null) || null;
    state.sourceLanguage = asString(pick(raw, ["sourceLanguage", "source_language"], "auto"), "auto");
    state.targetLanguage = asString(pick(raw, ["targetLanguage", "target_language"], "en"), "en");
    state.detectedLanguage =
      pick(raw, ["detectedLanguage", "detected_language"], null) || null;
    state.style = asString(pick(raw, ["style"], "auto"), "auto").toLowerCase();
    state.tone = asString(pick(raw, ["tone"], "standard"), "standard").toLowerCase();
    state.resultView = asString(pick(raw, ["resultView", "result_view"], "preview"), "preview").toLowerCase();
    state.backendStatus = asString(
      pick(raw, ["backendStatus", "backend_status"], "unknown"),
      "unknown"
    ).toLowerCase();
    state.probeMessage = asString(pick(raw, ["probeMessage", "probe_message"], ""), "");
    state.providerModels = Array.isArray(pick(raw, ["providerModels", "provider_models"], []))
      ? pick(raw, ["providerModels", "provider_models"], []).map(String)
      : [];
    state.modelsLoading = asBool(
      pick(raw, ["modelsLoading", "models_loading"], false),
      false
    );
    state.modelsError = pick(raw, ["modelsError", "models_error"], null) || null;
    state.fallbackModels = Array.isArray(
      pick(raw, ["fallbackModels", "fallback_models"], [])
    )
      ? pick(raw, ["fallbackModels", "fallback_models"], []).map(String)
      : [];
    state.fallbackModelsLoading = asBool(
      pick(raw, ["fallbackModelsLoading", "fallback_models_loading"], false),
      false
    );
    state.fallbackModelsError =
      pick(raw, ["fallbackModelsError", "fallback_models_error"], null) || null;
    state.usingFallback = asBool(
      pick(raw, ["usingFallback", "using_fallback"], false),
      false
    );
    state.tokensPerSecond = pick(raw, ["tokensPerSecond", "tokens_per_second"], null);
    if (state.tokensPerSecond !== null) state.tokensPerSecond = Number(state.tokensPerSecond);
    state.lastDurationMs = pick(raw, ["lastDurationMs", "last_duration_ms"], null);
    if (state.lastDurationMs !== null) state.lastDurationMs = Number(state.lastDurationMs);
    state.speaking = asString(pick(raw, ["speaking"], ""), "");
    state.hotkeyMessage = asString(pick(raw, ["hotkeyMessage", "hotkey_message"], ""), "");
    state.selectionHotkeyMessage = asString(
      pick(raw, ["selectionHotkeyMessage", "selection_hotkey_message"], ""),
      ""
    );
    // "Open at login" comes from the platform, not from the settings file.
    state.loginItemStatus = asString(
      pick(raw, ["loginItemStatus", "login_item_status"], "disabled"),
      "disabled"
    );
    state.loginItemError = pick(raw, ["loginItemError", "login_item_error"], null) || null;
    state.fileJob = normalizeFileJob(pick(raw, ["fileJob", "file_job"], null));
    state.write = normalizeWrite(pick(raw, ["write"], null));
    state.history = normalizeHistory(pick(raw, ["history"], []));
    state.historyError = asBool(pick(raw, ["historyError", "history_error"], false), false);
    state.settings = normalizeSettings(pick(raw, ["settings"], null));
    state.version = asString(pick(raw, ["version"], ""), "");
    return state;
  }

  function providerValueFromTitle(title) {
    const needle = String(title || "").trim().toLowerCase();
    if (!needle) return "";
    const match = PROVIDERS.find((item) => item.title.toLowerCase() === needle);
    return match ? match.value : "";
  }

  function normalizeCatalogEntry(raw) {
    if (!raw || typeof raw !== "object") return null;
    const modelId = asString(pick(raw, ["modelId", "model_id"], ""), "");
    if (!modelId) return null;
    const badgesRaw = pick(raw, ["badges"], []);
    // `get_catalog` sends Provider::title() ("Ollama"), while the picker and
    // settings use Provider::value() ("ollama"). Keep both, derived once.
    const providerTitleValue = asString(pick(raw, ["provider"], ""), "");
    const providerValue =
      asString(pick(raw, ["providerValue", "provider_value"], ""), "") ||
      providerValueFromTitle(providerTitleValue);
    return {
      name: asString(pick(raw, ["name"], modelId), modelId),
      modelId: modelId,
      provider: providerTitleValue,
      providerValue: providerValue,
      size: asString(pick(raw, ["size"], ""), ""),
      languages: asString(pick(raw, ["languages"], ""), ""),
      note: asString(pick(raw, ["note"], ""), ""),
      installCommand: asString(pick(raw, ["installCommand", "install_command"], ""), ""),
      badges: Array.isArray(badgesRaw) ? badgesRaw.map(String) : [],
      isFree: asBool(pick(raw, ["isFree", "is_free"], false), false),
    };
  }

  function normalizeCatalog(list) {
    if (!Array.isArray(list)) return [];
    return list.map(normalizeCatalogEntry).filter(Boolean);
  }

  /* --------------------------------------------------------------- state/UI */

  const els = {};
  let state = defaultState();
  let refreshTimer = 0;
  let refreshSequence = 0;
  let toastSequence = 0;

  const local = {
    settingsDraft: null,
    settingsSnapshot: null,
    settingsModelsSnapshot: null,
    settingsFallbackModelsSnapshot: null,
    // The provider whose key each API-key field currently holds. Switching the
    // provider moves the field to that provider's own key, so the text of the
    // previous provider can never be saved under the new one.
    settingsKeyProvider: null,
    settingsFallbackKeyProvider: null,
    settingsKeyDirty: false,
    settingsFallbackKeyDirty: false,
    // Provider whose stored key the shell still has to report after a switch.
    settingsKeyAwaiting: null,
    settingsFallbackKeyAwaiting: null,
    primaryKeys: {},
    fallbackKeys: {},
    diagnostics: null,
    settingsTab: "model",
    modelFilter: "",
    historyQuery: "",
    historyResults: null,
    historySearchTimer: 0,
    copyFeedback: "",
    copyFeedbackTimer: 0,
    toastTimer: 0,
    sourcePreview: false,
    writeText: "",
    writeTarget: "",
    writeTargetChosen: false,
    writeStale: false,
    writePending: false,
    writeSubmittedAt: 0,
    writeSawRunning: false,
    writeCancelSent: false,
    writeView: "preview",
    writeBusy: false,
    writeBusyAt: 0,
    writeBusyTimer: 0,
    promptStyle: "auto",
    promptTone: "standard",
    promptTarget: "en",
    promptTimer: 0,
    promptPreviewCache: "",
    catalogEntries: [],
    catalogServerModels: [],
    catalogLoading: false,
    catalogFetching: false,
    catalogFilter: "",
    catalogProvider: "",
    catalogFree: false,
    catalogRequest: 0,
    capture: null,
    menuOpen: false,
    fileTarget: "",
    fileJobTarget: "",
    firstStateLoaded: false,
    translateBarWidth: 0,
    startupApplied: false,
    dialogStack: [],
    resultKeys: {},
    voices: [],
    catalogue: null,
    catalogueLang: "",
    catalogueRequest: 0,
  };

  /* -------------------------------------------------------------- transport */

  function invoke(name, args) {
    const payload = args === undefined ? {} : args;
    if (NATIVE) return nativeCore.invoke(name, payload);
    if (MOCK && typeof MOCK.invoke === "function") return Promise.resolve(MOCK.invoke(name, payload));
    return Promise.reject(new Error("The Tauri bridge is not available."));
  }

  function subscribe(handler) {
    if (NATIVE && window.__TAURI__.event && typeof window.__TAURI__.event.listen === "function") {
      return window.__TAURI__.event.listen("app://event", (event) => {
        let payload = event && "payload" in event ? event.payload : event;
        if (typeof payload === "string") {
          try {
            payload = JSON.parse(payload);
          } catch (error) {
            payload = { type: payload };
          }
        }
        handler(payload);
      });
    }
    if (MOCK && typeof MOCK.listen === "function") {
      return Promise.resolve(MOCK.listen(handler));
    }
    return Promise.resolve(null);
  }

  function send(name, args) {
    return invoke(name, args).catch((error) => {
      showToast(errorText(error));
      return null;
    });
  }

  function errorText(error) {
    if (!error) return "";
    if (typeof error === "string") return error;
    const message = error.message || error.toString();
    return message === "[object Object]" ? tr("Something went wrong.") : message;
  }

  /* -------------------------------------------------------------- platform */

  // `pick_file`, `pick_save_path` and `read_clipboard` return a JSON string or
  // null; unwrap both a bare string and a `{ path }` object defensively.
  function unwrapPath(value) {
    if (typeof value === "string") return value;
    if (value && typeof value === "object" && typeof value.path === "string") return value.path;
    return null;
  }

  function unwrapText(value) {
    if (typeof value === "string") return value;
    if (value && typeof value === "object" && typeof value.text === "string") return value.text;
    return "";
  }

  /* ------------------------------------------------------------------ boot */

  function cacheElements() {
    [
      "tabs",
      "connCapsule",
      "connDot",
      "connCapsuleLabel",
      "settingsBtn",
      "moreBtn",
      "moreMenu",
      "statusDot",
      "statusText",
      "statusError",
      "stopSpeaking",
      "statusMetrics",
      "toastRegion",
      "translateTop",
      "sourceLang",
      "targetLang",
      "swapBtn",
      "chipsBar",
      "chipsFull",
      "chipsCompact",
      "styleChips",
      "toneChips",
      "styleCompact",
      "toneCompact",
      "sourceInput",
      "sourceCounter",
      "speakSourceBtn",
      "sourcePreviewBtn",
      "sourcePreview",
      "pasteBtn",
      "copySourceBtn",
      "clearSourceBtn",
      "warningPill",
      "againBtn",
      "speakResultBtn",
      "copyBtn",
      "copyBtnLabel",
      "viewSwitch",
      "resultCounter",
      "resultScroll",
      "resultView",
      "resultEmpty",
      "translateNowBtn",
      "resultProgress",
      "progressTitle",
      "progressTrack",
      "progressFill",
      "progressStatus",
      "progressPercent",
      "stopBtn",
      "resultError",
      "errorText",
      "retryBtn",
      "errorBanner",
      "bannerText",
      "bannerRetry",
      "detectedWrap",
      "detectedLabel",
      "copyFeedback",
      "fallbackPill",
      "modelLabel",
      "metricsLabel",
      "metricSep",
      "dropZone",
      "chooseFileBtn",
      "fileSelected",
      "fileSelectedName",
      "fileSelectedMeta",
      "removeFileBtn",
      "fileActions",
      "fileTarget",
      "translateFileBtn",
      "fileProgress",
      "fileProgressName",
      "fileProgressPercent",
      "fileProgressTrack",
      "fileProgressFill",
      "fileProgressState",
      "cancelFileBtn",
      "fileResult",
      "fileResultName",
      "fileWarnings",
      "fileFallback",
      "fileSaveError",
      "saveFileBtn",
      "showFolderBtn",
      "anotherFileBtn",
      "fileError",
      "fileErrorText",
      "fileRetryBtn",
      "fileTryAgainBtn",
      "writeTarget",
      "improveBtn",
      "improveLabel",
      "cancelWriteBtn",
      "copyWriteBtn",
      "writeInput",
      "writeCounter",
      "clearWriteBtn",
      "writeViewSwitch",
      "writeResultView",
      "writeEmpty",
      "writeBusyState",
      "writeError",
      "writeErrorText",
      "writeWarnings",
      "writeDuration",
      "writeResultCounter",
      "historySearch",
      "historyClearBtn",
      "historyCount",
      "historyList",
      "historyEmpty",
      "historyEmptyTitle",
      "historyEmptyText",
      "settingsDialog",
      "settingsTitle",
      "settingsVersion",
      "settingsTabs",
      "settingsBody",
      "providerSelect",
      "providerHint",
      "baseUrlInput",
      "apiKeyInput",
      "revealKeyBtn",
      "keyLink",
      "apiKeyHint",
      "modelInput",
      "catalogBtn",
      "connectBtn",
      "connectStatus",
      "installHint",
      "installCommand",
      "installCopyBtn",
      "modelsCount",
      "modelFilter",
      "modelList",
      "modelsHint",
      "fallbackToggle",
      "fallbackBody",
      "fallbackProviderSelect",
      "fallbackBaseInput",
      "fallbackKeyInput",
      "fallbackModelInput",
      "fallbackModelOptions",
      "fallbackLoadBtn",
      "fallbackHint",
      "fallbackStatus",
      "temperatureRange",
      "temperatureValue",
      "topPRange",
      "topPValue",
      "topKRange",
      "topKValue",
      "repetitionRange",
      "repetitionValue",
      "contextRange",
      "contextValue",
      "promptStyleChips",
      "promptToneChips",
      "promptTarget",
      "promptPreview",
      "autoTranslateToggle",
      "debounceRow",
      "debounceRange",
      "debounceValue",
      "keepHistoryToggle",
      "loginItem",
      "loginItemToggle",
      "loginItemError",
      "loginItemApproval",
      "loginItemSettings",
      "warmUpToggle",
      "trayToggle",
      "interfaceLanguageSelect",
      "voiceSelect",
      "hotkeyStandard",
      "hotkeySelection",
      "resetHotkey",
      "resetSelectionHotkey",
      "hotkeyMessage",
      "selectionHotkeyMessage",
      "hotkeyError",
      "hotkeyExample",
      "aboutVersion",
      "aboutSettingsPath",
      "aboutHistoryPath",
      "aboutSecretBackend",
      "settingsCancel",
      "settingsSave",
      "catalogDialog",
      "catalogTitle",
      "catalogCount",
      "catalogProvider",
      "catalogFree",
      "catalogSearch",
      "catalogFetch",
      "catalogBody",
      "catalogServerSection",
      "catalogServerList",
      "catalogServerCount",
      "catalogRecommendedSection",
      "catalogRecommendedList",
      "catalogModelsSection",
      "catalogModelsList",
      "catalogEmpty",
      "catalogClose",
      "confirmDialog",
      "confirmTitle",
      "confirmText",
      "confirmCancel",
      "confirmOk",
    ].forEach((id) => {
      els[id] = $(id);
    });
  }

  function buildStaticOptions() {
    // Language pickers (source includes Auto-detect).
    const languageOptions = LANGS.map((item) => ({
      value: item.code,
      label: tr(item.name),
    }));
    fillSelect(
      els.sourceLang,
      [{ value: "auto", label: tr("Auto-detect") }].concat(languageOptions)
    );
    fillSelect(
      els.targetLang,
      languageOptions.filter((item) => item.value !== "auto")
    );
    fillSelect(els.fileTarget, languageOptions);
    fillSelect(els.writeTarget, languageOptions);
    fillSelect(els.promptTarget, languageOptions);

    // Providers.
    fillSelect(
      els.providerSelect,
      PROVIDERS.map((item) => ({ value: item.value, label: item.title }))
    );
    fillSelect(
      els.fallbackProviderSelect,
      PROVIDERS.map((item) => ({ value: item.value, label: item.title }))
    );
    fillSelect(
      els.catalogProvider,
      [{ value: "", label: tr("All providers") }].concat(
        PROVIDERS.map((item) => ({ value: item.value, label: item.title }))
      )
    );

    // Interface languages.
    fillSelect(
      els.interfaceLanguageSelect,
      UI_LANGS.map((item) => ({ value: item.code, label: item.title }))
    );

    // Voices (Automatic first, then whatever the platform reported).
    updateVoiceOptions();

    els.settingsVersion.textContent = "DeepL-oFM";
    els.aboutVersion.textContent = "";
    els.progressPercent.textContent = "0%";
    setSegment(els.styleChips, "style", state.style);
    setSegment(els.toneChips, "tone", state.tone);
    setSegment(els.viewSwitch, "view", state.resultView);
    setSegment(els.promptStyleChips, "style", local.promptStyle);
    setSegment(els.promptToneChips, "tone", local.promptTone);
    setSegment(els.writeViewSwitch, "view", local.writeView);
    fillCompactSelect(els.styleCompact, els.styleChips, "style");
    fillCompactSelect(els.toneCompact, els.toneChips, "tone");
    syncCompactControls();
  }

  function fillSelect(select, options) {
    if (!select) return;
    const previous = select.value;
    select.replaceChildren();
    options.forEach((option) => {
      const node = el("option", null, option.label);
      node.value = option.value;
      select.append(node);
    });
    if (options.some((option) => option.value === previous)) select.value = previous;
  }

  function ensureSelectOption(select, value, label) {
    if (!select || !value) return;
    if (Array.from(select.options).some((option) => option.value === value)) return;
    const option = el("option", null, label || value);
    option.value = value;
    select.append(option);
  }

  function updateVoiceOptions() {
    if (!els.voiceSelect) return;
    const previous = els.voiceSelect.value;
    els.voiceSelect.replaceChildren();
    const automatic = el("option", null, tr("Automatic"));
    automatic.value = "";
    els.voiceSelect.append(automatic);
    local.voices.forEach((voice) => {
      const option = el("option", null, voice.label || voice.id);
      option.value = voice.id;
      els.voiceSelect.append(option);
    });
    if (previous) els.voiceSelect.value = previous;
  }

  /* -------------------------------------------------------------- localising */

  function localize() {
    document.querySelectorAll("[data-i18n]").forEach((node) => {
      const key = node.getAttribute("data-i18n");
      if (key) node.textContent = tr(key);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
      const key = node.getAttribute("data-i18n-placeholder");
      if (key) node.setAttribute("placeholder", tr(key));
    });
    document.querySelectorAll("[data-i18n-aria]").forEach((node) => {
      const key = node.getAttribute("data-i18n-aria");
      if (key) node.setAttribute("aria-label", tr(key));
    });
    document.querySelectorAll("[data-i18n-title]").forEach((node) => {
      const key = node.getAttribute("data-i18n-title");
      if (key) node.setAttribute("title", tr(key));
    });
    document.title = "DeepL-oFM";
    if (!els.settingsTitle.textContent) els.settingsTitle.textContent = tr("Settings");
    buildStaticOptions();
    render();
    updateStyleToneMode(local.translateBarWidth);
  }

  function setSegment(group, attribute, value) {
    if (!group) return;
    group.querySelectorAll("[data-" + attribute + "]").forEach((button) => {
      const active = button.getAttribute("data-" + attribute) === value;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  /* -------------------------------------------------- responsive bar state */

  function fullChipsThreshold() {
    const characters = CHIP_LABELS.reduce(
      (total, label) => total + Array.from(tr(label)).length,
      0
    );
    return FULL_CHIPS_BASE_WIDTH + characters * FULL_CHIPS_PER_CHARACTER;
  }

  function updateStyleToneMode(width) {
    if (!els.chipsFull || !els.chipsCompact) return;
    const compact = width > 0 && width < fullChipsThreshold();
    els.chipsFull.hidden = compact;
    els.chipsCompact.hidden = !compact;
    document.body.classList.toggle("has-compact-controls", compact);
  }

  function fillCompactSelect(select, group, attribute) {
    if (!select || !group) return;
    const previous = select.value;
    select.replaceChildren();
    group.querySelectorAll("[data-" + attribute + "]").forEach((button) => {
      const option = el("option", null, button.textContent.trim());
      option.value = button.getAttribute("data-" + attribute);
      select.append(option);
    });
    if (previous) select.value = previous;
  }

  function syncCompactControls() {
    [
      [els.styleCompact, "style", "Style"],
      [els.toneCompact, "tone", "Tone"],
    ].forEach(([select, key, caption]) => {
      if (!select) return;
      if (select.value !== state[key]) select.value = state[key];
      const option = select.selectedOptions && select.selectedOptions[0];
      select.title = option ? tr(caption) + " · " + option.textContent : tr(caption);
    });
  }

  function syncLanguageTitles() {
    [els.sourceLang, els.targetLang].forEach((select) => {
      if (!select) return;
      const option = select.selectedOptions && select.selectedOptions[0];
      select.title = option ? option.textContent : "";
    });
  }

  function observeTranslateBar() {
    if (!els.translateTop) return;
    if (typeof ResizeObserver === "undefined") return;
    local.translateObserver = new ResizeObserver((entries) => {
      const entry = entries[entries.length - 1];
      if (!entry) return;
      local.translateBarWidth = entry.contentRect.width;
      updateStyleToneMode(local.translateBarWidth);
    });
    local.translateObserver.observe(els.translateTop);
  }

  /* ---------------------------------------------------------------- rendering */

  function render() {
    renderTabs();
    renderHeader();
    renderStatusBar();
    renderTranslate();
    renderFiles();
    renderWrite();
    renderHistory();
    renderDialogs();
  }

  function renderTabs() {
    const tabs = els.tabs.querySelectorAll("[data-tab]");
    tabs.forEach((button) => {
      const active = button.getAttribute("data-tab") === state.tab;
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.tabIndex = active ? 0 : -1;
    });
    ["translate", "files", "write", "history"].forEach((name) => {
      const pane = $("pane-" + name);
      if (pane) pane.hidden = state.tab !== name;
    });
  }

  function statusLabel(status) {
    switch (status) {
      case "connected":
        return tr("Connected");
      case "checking":
        return tr("Checking connection…");
      case "warming":
        return tr("Loading the translator…");
      case "failed":
        return tr("Server unavailable");
      default:
        return tr("Not checked yet");
    }
  }

  function renderHeader() {
    const settings = state.settings;
    const model = settings.model || tr("No model");
    els.connDot.dataset.state = state.backendStatus || "unknown";
    els.connCapsuleLabel.textContent = providerTitle(settings.provider) + " · " + model;
    els.connCapsule.title = state.probeMessage || tr("Connection status");
    els.settingsBtn.disabled = false;
  }

  function renderStatusBar() {
    els.statusDot.dataset.state = state.backendStatus || "unknown";
    const model = state.settings.model || tr("No model");
    const parts = [statusLabel(state.backendStatus), providerTitle(state.settings.provider), model];
    els.statusText.textContent = parts.join(" · ");
    els.statusText.title = state.probeMessage || "";
    let message = state.errorMessage || "";
    if (!message && state.historyError && state.tab === "history") {
      message = tr("Could not read or save translation history.");
    }
    if (!message && state.hotkeyMessage && state.tab !== "translate") {
      message = state.hotkeyMessage;
    }
    els.statusError.textContent = message;
    els.statusError.title = message;
    els.stopSpeaking.hidden = !state.speaking;
    els.statusMetrics.textContent = "";
  }

  function sourceCount() {
    return Array.from(state.sourceText || "").length;
  }

  function renderTranslate() {
    if (els.sourceLang.value !== state.sourceLanguage) els.sourceLang.value = state.sourceLanguage;
    if (els.targetLang.value !== state.targetLanguage) els.targetLang.value = state.targetLanguage;
    syncLanguageTitles();
    setSegment(els.styleChips, "style", state.style);
    setSegment(els.toneChips, "tone", state.tone);
    syncCompactControls();
    setSegment(els.viewSwitch, "view", state.resultView);

    // Never clobber the textarea while the user is typing in it.
    if (document.activeElement !== els.sourceInput && els.sourceInput.value !== state.sourceText) {
      els.sourceInput.value = state.sourceText;
    }
    els.sourceCounter.textContent = state.sourceText ? characters(sourceCount()) : "";
    els.resultCounter.textContent = state.translatedText
      ? characters(Array.from(state.translatedText).length)
      : "";

    // Source Markdown preview: swap the editor for the shared renderer.
    const canPreview = !!state.sourceText.trim();
    if (!canPreview && local.sourcePreview) local.sourcePreview = false;
    const previewing = local.sourcePreview;
    els.sourceInput.hidden = previewing;
    els.sourcePreview.hidden = !previewing;
    if (previewing) paintResult(els.sourcePreview, state.sourceText, "preview");
    els.sourcePreviewBtn.disabled = !canPreview;
    els.sourcePreviewBtn.classList.toggle("is-active", previewing);
    const previewLabel = tr(
      previewing ? "Show Markdown source" : "Show rendered Markdown"
    );
    els.sourcePreviewBtn.setAttribute("aria-label", previewLabel);
    els.sourcePreviewBtn.setAttribute("title", previewLabel);
    const previewUse = els.sourcePreviewBtn.querySelector("use");
    if (previewUse) previewUse.setAttribute("href", previewing ? "#i-code" : "#i-eye");

    const translating = !!state.isTranslating;
    const hasResult = !!state.translatedText;
    const errorMessage = state.errorMessage || "";

    const showProgress = translating;
    const showError = !translating && !!errorMessage && !hasResult;
    // A streaming translation is painted while the progress bar stays visible;
    // the text is a preview until the final result replaces it.
    const showResult = hasResult && !showError;
    const showEmpty = !translating && !showError && !hasResult;

    els.resultProgress.hidden = !showProgress;
    els.resultError.hidden = !showError;
    els.resultView.hidden = !showResult;
    els.resultEmpty.hidden = !showEmpty;

    if (showProgress) {
      const total = state.total || 0;
      const completed = Math.min(state.completed || 0, total || state.completed || 0);
      const percent = total > 0 ? Math.round((completed / total) * 100) : 0;
      els.progressFill.style.width = percent + "%";
      els.progressTrack.setAttribute("aria-valuenow", String(percent));
      els.progressPercent.textContent = percent + "%";
      els.progressStatus.textContent = total > 0 ? tr("%d of %d", completed, total) : "";
      els.progressTitle.textContent = tr("Translating…");
      els.stopBtn.disabled = false;
    }

    if (showResult) {
      paintResult(els.resultView, state.translatedText, state.resultView);
    }

    if (showError) {
      els.errorText.textContent = errorMessage;
    }

    const banner = !!errorMessage && !translating && hasResult;
    els.errorBanner.hidden = !banner;
    if (banner) els.bannerText.textContent = errorMessage;

    els.copyBtn.disabled = !hasResult || translating;
    els.copyBtn.setAttribute("title", tr("Copy translation"));
    const copied = local.copyFeedback === "translation";
    els.copyBtnLabel.textContent = copied ? tr("Copied") : tr("Copy");
    const copyUse = els.copyBtn.querySelector("use");
    if (copyUse) copyUse.setAttribute("href", copied ? "#i-check" : "#i-copy");

    els.againBtn.disabled = !state.sourceText.trim();
    els.translateNowBtn.disabled = translating;
    els.speakResultBtn.disabled = !hasResult || translating;
    els.speakSourceBtn.disabled = !state.sourceText.trim() && !translating;
    els.copySourceBtn.disabled = !state.sourceText;
    els.clearSourceBtn.disabled = !state.sourceText;
    els.speakSourceBtn.classList.toggle("is-active", state.speaking === "source");
    els.speakResultBtn.classList.toggle("is-active", state.speaking === "translation");

    // Warning pill.
    if (state.warningCount > 0) {
      els.warningPill.hidden = false;
      els.warningPill.textContent = tr(
        state.warningCount === 1 ? "%d warning" : "%d warnings",
        state.warningCount
      );
    } else {
      els.warningPill.hidden = true;
    }

    // Footer.
    const auto = state.sourceLanguage === "auto";
    const detected = auto && state.detectedLanguage;
    els.detectedWrap.hidden = !detected;
    if (detected) {
      els.detectedLabel.textContent = tr("Detected: %@", languageName(state.detectedLanguage));
    }

    els.fallbackPill.hidden = !state.usingFallback;
    els.modelLabel.textContent = state.settings.model || tr("No model");

    const metrics = [];
    if (state.tokensPerSecond !== null && state.tokensPerSecond !== undefined) {
      metrics.push(state.tokensPerSecond.toFixed(1) + " " + tr("t/s"));
    }
    if (state.lastDurationMs !== null && state.lastDurationMs !== undefined) {
      metrics.push(formatSeconds(state.lastDurationMs));
    }
    els.metricsLabel.textContent = metrics.join("  ·  ");
    if (els.metricSep) els.metricSep.hidden = metrics.length === 0;

    // Transient copy feedback under the source pane.
    const feedback = els.copyFeedback;
    if (local.copyFeedback && local.copyFeedback !== "translation") {
      feedback.hidden = false;
      feedback.textContent = local.copyFeedback === "source" ? tr("Source text copied") : tr("Copied");
    } else {
      feedback.hidden = true;
      feedback.textContent = "";
    }
  }

  function paintResult(container, text, mode) {
    const key = mode + "\u0000" + text;
    if (container.dataset.renderKey === key) return;
    container.dataset.renderKey = key;
    container.replaceChildren();
    if (!text) return;
    if (mode === "preview") {
      container.innerHTML = renderMarkdown(text);
    } else if (mode === "markdown") {
      const pre = el("pre", "markdown-source");
      const code = el("code");
      code.textContent = text;
      pre.append(code);
      container.append(pre);
    } else {
      const pre = el("pre", "plain-text");
      pre.textContent = markdownToPlain(text);
      container.append(pre);
    }
  }

  function renderFiles() {
    const job = state.fileJob;
    const running = !!job && RUNNING_FILE_STATES.includes(job.state);
    const done = !!job && job.state === "done";
    const failed = !!job && job.state === "failed";
    const cancelled = !!job && job.state === "cancelled";

    els.dropZone.hidden = !!job;
    els.fileSelected.hidden = !job;
    els.fileActions.hidden = !job || running;
    els.fileProgress.hidden = !running;
    els.fileResult.hidden = !done;
    els.fileError.hidden = !failed;

    if (!job) return;

    els.fileSelectedName.textContent = job.name || basename(job.path);
    const details = [];
    if (job.kind) details.push(String(job.kind).toUpperCase());
    if (job.size > 0) details.push(fileSize(job.size));
    els.fileSelectedMeta.textContent = details.join(" · ");

    // The Files tab keeps its own language: never mirror the Translate tab
    // after the initial default, and never push it through set_target_language.
    if (!local.fileTarget) local.fileTarget = defaultFileTarget();
    const wanted = local.fileTarget;
    ensureSelectOption(els.fileTarget, wanted, languageName(wanted));
    if (els.fileTarget.value !== wanted) els.fileTarget.value = wanted;
    els.fileTarget.disabled = running;
    els.translateFileBtn.disabled = running;
    els.removeFileBtn.disabled = running;
    els.fileTryAgainBtn.hidden = !(failed && !!job.path);

    if (running) {
      const percent = job.percent || (job.total > 0 ? Math.round((job.completed / job.total) * 100) : 0);
      els.fileProgressName.textContent = job.name || basename(job.path);
      els.fileProgressPercent.textContent = percent + "%";
      els.fileProgressFill.style.width = percent + "%";
      els.fileProgressTrack.setAttribute("aria-valuenow", String(percent));
      let label = tr("Translating…");
      if (job.state === "reading") label = tr("Preparing file…");
      else if (job.state === "writing") label = tr("Saving…");
      if (job.total > 0) {
        label = tr("%d of %d", job.completed, job.total);
      }
      els.fileProgressState.textContent = label;
    }

    if (done) {
      const output = job.output || "";
      els.fileResultName.textContent = job.resultName || (output ? basename(output) : "");
      if (job.warnings > 0) {
        els.fileWarnings.hidden = false;
        els.fileWarnings.textContent = tr(
          "Some paragraphs are still in the original language (%d).",
          job.warnings
        );
      } else {
        els.fileWarnings.hidden = true;
      }
      els.fileFallback.hidden = !job.fallback;
      const suffix = job.fallbackLabel ? " · " + job.fallbackLabel : "";
      els.fileFallback.textContent = tr("Fallback") + suffix;
      if (job.saveError) {
        els.fileSaveError.hidden = false;
        els.fileSaveError.textContent = job.saveError;
      } else {
        els.fileSaveError.hidden = true;
      }
      els.saveFileBtn.disabled = !output;
      els.showFolderBtn.disabled = !(output || job.path);
    }

    if (failed) {
      els.fileErrorText.textContent = job.message || tr("The file could not be translated.");
    }

    if (cancelled) {
      // Keep the file card and controls; the toast communicates the cancel.
    }
  }

  function renderWrite() {
    if (document.activeElement !== els.writeInput && els.writeInput.value !== local.writeText) {
      els.writeInput.value = local.writeText;
    }
    els.writeCounter.textContent = local.writeText ? characters(Array.from(local.writeText).length) : "";
    const write = state.write;
    const busy = !!(write.running || local.writeBusy);
    const stale = !!local.writeStale;
    const output = stale ? "" : write.output || "";
    const message = stale ? "" : write.error || "";
    const warnings = stale ? 0 : write.warnings || 0;
    // Rust writes the localised sentence into `error` even on success when
    // paragraphs were left untranslated; with output it is a warning, not a
    // fatal error.
    const warningText =
      output && (warnings > 0 || message)
        ? message || tr(warnings === 1 ? "%d warning" : "%d warnings", warnings)
        : "";
    const fatalError = message && !output ? message : "";

    // Show the language the model used for an automatic choice until the user
    // picks one explicitly. `local.writeTarget` stays empty while auto.
    if (local.writeTargetChosen && local.writeTarget) {
      ensureSelectOption(els.writeTarget, local.writeTarget, languageName(local.writeTarget));
      if (els.writeTarget.value !== local.writeTarget) els.writeTarget.value = local.writeTarget;
    } else {
      const detected = write.detectedCode;
      const fallback = defaultWriteTarget();
      const display = detected || fallback;
      ensureSelectOption(els.writeTarget, display, languageName(display));
      if (els.writeTarget.value !== display) els.writeTarget.value = display;
    }

    els.improveBtn.disabled = busy || !local.writeText.trim();
    els.improveBtn.classList.toggle("is-busy", busy);
    els.improveLabel.textContent = busy ? tr("Improving…") : tr("Improve text");
    const spinner = els.improveBtn.querySelector(".spinner");
    if (spinner) spinner.hidden = !busy;
    els.cancelWriteBtn.hidden = !busy;
    els.clearWriteBtn.disabled = busy || !local.writeText;
    els.writeTarget.disabled = busy;
    els.copyWriteBtn.disabled = !output || busy;

    setSegment(els.writeViewSwitch, "view", local.writeView);

    const showError = !busy && !!fatalError;
    const showOutput = !busy && !!output;
    const showEmpty = !busy && !showError && !showOutput;

    els.writeError.hidden = !showError;
    els.writeResultView.hidden = !showOutput;
    els.writeEmpty.hidden = !showEmpty;
    els.writeBusyState.hidden = !busy;
    els.writeWarnings.hidden = !(showOutput && warningText);

    if (showError) els.writeErrorText.textContent = fatalError;
    if (showOutput) {
      paintResult(els.writeResultView, output, local.writeView);
      els.writeResultCounter.textContent = characters(Array.from(output).length);
      els.writeWarnings.textContent = warningText;
    } else if (!showError) {
      els.writeResultCounter.textContent = "";
      els.writeResultView.replaceChildren();
      els.writeResultView.dataset.renderKey = "";
      els.writeWarnings.textContent = "";
    }
    els.writeDuration.textContent = showOutput ? formatDuration(write.durationMs) : "";
  }

  function defaultFileTarget() {
    const code = local.fileTarget || state.settings.lastTargetCode || state.targetLanguage || "en";
    return code === "auto" ? "en" : code;
  }

  function defaultWriteTarget() {
    const code = state.settings.lastTargetCode || state.targetLanguage || "en";
    return code === "auto" ? "en" : code;
  }

  function writeOutput() {
    return local.writeStale ? "" : state.write.output || "";
  }

  function historyEntryMatches(entry, needle) {
    const haystack = [
      entry.sourceText,
      entry.translatedText,
      entry.engine,
      languageName(entry.sourceCode),
      languageName(entry.targetCode),
      tr(styleLabel(entry.style)),
      tr(toneLabel(entry.tone)),
    ];
    return haystack.some((value) =>
      String(value || "").toLowerCase().includes(needle)
    );
  }

  function historyVisibleEntries() {
    const query = local.historyQuery.trim();
    if (!query) return state.history;
    const needle = query.toLowerCase();
    // history_search only looks at the two texts; extend it locally so the
    // engine, style, tone and localised language names are searchable too.
    const matches = state.history.filter((entry) => historyEntryMatches(entry, needle));
    if (!Array.isArray(local.historyResults)) return matches;
    const seen = new Set(matches.map((entry) => entry.id));
    const extra = local.historyResults.filter((entry) => !seen.has(entry.id));
    return extra.length ? matches.concat(extra) : matches;
  }

  function renderHistory() {
    const query = local.historyQuery.trim();
    const entries = historyVisibleEntries();
    els.historyCount.textContent = String(entries.length);
    if (els.historySearch.value !== local.historyQuery) els.historySearch.value = local.historyQuery;

    const empty = entries.length === 0;
    els.historyEmpty.hidden = !empty;
    if (empty) {
      if (!state.history.length) {
        els.historyEmptyTitle.textContent = tr("History is empty");
        els.historyEmptyText.textContent = tr("Translations will be saved here automatically.");
      } else {
        els.historyEmptyTitle.textContent = tr("Nothing found");
        els.historyEmptyText.textContent = tr("Try another query.");
      }
    }

    const rows = entries.map(historyRow);
    els.historyList.replaceChildren(...rows);
    els.historyClearBtn.disabled = !state.history.length;
  }

  function historyRow(entry) {
    const row = el("div", "history-row");
    row.dataset.id = entry.id;

    const main = el("div", "history-main");
    const meta = el("div", "history-meta");

    const sourceChip = el("span", "lang-chip", languageName(entry.sourceCode));
    const arrow = el("span", "lang-arrow", "→");
    const targetChip = el("span", "lang-chip", languageName(entry.targetCode));
    meta.append(sourceChip, arrow, targetChip);
    const styleChip = el("span", "tag-chip", tr(styleLabel(entry.style)));
    meta.append(styleChip);
    if (entry.tone && entry.tone !== "standard") {
      meta.append(el("span", "lang-chip", tr(toneLabel(entry.tone))));
    }
    if (entry.engine) meta.append(el("span", "engine", entry.engine));
    const date = el("span", "history-date");
    date.append(el("span", null, relativeDate(entry.date)));
    if (entry.durationMs) {
      date.append(el("span", "dot-sep", "·"));
      date.append(el("span", "history-duration", formatDuration(entry.durationMs)));
    }
    meta.append(date);
    main.append(meta);
    main.append(el("p", "history-source", entry.sourceText));
    main.append(el("p", "history-translation", entry.translatedText));

    const actions = el("div", "history-actions");
    actions.append(
      historyButton("restore", "translate", tr("Translate again")),
      historyButton("copy", "copy", tr("Copy translation")),
      historyButton("delete", "trash", tr("Delete entry"))
    );

    row.append(main, actions);
    return row;
  }

  function historyButton(action, iconName, label) {
    const button = el("button", "icon-btn");
    button.type = "button";
    button.dataset.action = action;
    button.setAttribute("aria-label", label);
    button.setAttribute("title", label);
    button.append(icon(iconName));
    return button;
  }

  function styleLabel(value) {
    switch (value) {
      case "literal":
        return "Literal";
      case "natural":
        return "Natural";
      default:
        return "Auto";
    }
  }

  function toneLabel(value) {
    switch (value) {
      case "formal":
        return "Formal";
      case "casual":
        return "Casual";
      default:
        return "Default";
    }
  }

  /* -------------------------------------------------------------- settings UI */

  function renderDialogs() {
    if (els.settingsDialog.open) {
      els.settingsVersion.textContent = "DeepL-oFM" + (diagnosticsVersion() ? " " + diagnosticsVersion() : "");
      renderConnectStatus();
      renderModels();
      renderFallbackModels();
      renderHotkeyMessages();
      renderLoginItem();
      renderInstallHint();
      renderAboutDiagnostics();
      if (local.settingsDraft) updateProviderDetails(local.settingsDraft);
      els.revealKeyBtn.textContent = tr(els.apiKeyInput.type === "text" ? "Hide" : "Show");
    }
    if (els.catalogDialog.open) {
      renderCatalog();
    }
  }

  function openSettings(tab) {
    if (!els.settingsDialog.open) {
      local.settingsSnapshot = cloneSettings(state.settings);
      local.settingsModelsSnapshot = state.providerModels.slice();
      local.settingsFallbackModelsSnapshot = state.fallbackModels.slice();
      rememberProviderKeys(state.settings);
      local.settingsDraft = cloneSettings(state.settings);
      local.modelFilter = "";
      els.modelFilter.value = "";
      local.promptStyle = state.style;
      local.promptTone = state.tone;
      local.promptTarget =
        state.targetLanguage && state.targetLanguage !== "auto"
          ? state.targetLanguage
          : state.settings.lastTargetCode || "en";
      populateSettings(local.settingsDraft);
      els.settingsDialog.showModal();
      dialogStackPush(els.settingsDialog);
      syncModalState();
      els.settingsBody.classList.add("scroll-fade");
      focusDialogShell(els.settingsDialog);
      requestAnimationFrame(() => syncScrollFade(els.settingsBody));
      void loadDiagnostics();
      void ensureCatalogEntries().then(() => renderInstallHint());
      if (state.backendStatus === "unknown") {
        send("check_connection");
        pollState(() => state.backendStatus === "checking", 8000, 4000);
      }
    }
    selectSettingsTab(tab || local.settingsTab);
    refreshPromptPreview();
  }

  function cloneSettings(settings) {
    return JSON.parse(JSON.stringify(settings));
  }

  function settingsFormDiffersFromSnapshot() {
    const snapshot = local.settingsSnapshot;
    if (!snapshot) return false;
    try {
      return JSON.stringify(collectSettings()) !== JSON.stringify(snapshot);
    } catch (error) {
      return true;
    }
  }

  /** Restore the Settings snapshot; Connect/Load/Catalogue changes go away. */
  async function cancelSettings() {
    if (!els.settingsDialog.open) return;
    const snapshot = local.settingsSnapshot;
    const models = local.settingsModelsSnapshot;
    const fallbackModels = local.settingsFallbackModelsSnapshot;
    const changed = settingsFormDiffersFromSnapshot();
    local.settingsDraft = snapshot ? cloneSettings(snapshot) : null;
    local.settingsSnapshot = null;
    if (snapshot) {
      state.settings = normalizeSettings(snapshot);
      if (Array.isArray(models)) state.providerModels = models.slice();
      if (Array.isArray(fallbackModels)) state.fallbackModels = fallbackModels.slice();
      // Reset the form widgets too, so reopening shows the snapshot even before
      // the next get_state round-trip.
      if (local.settingsDraft) populateSettings(local.settingsDraft);
    }
    els.settingsDialog.close();
    if (!snapshot) return;
    local.settingsDraft = null;
    render();
    if (changed) {
      try {
        await invoke("save_settings", { settings: snapshot });
        // Confirm the controller really is back on the snapshot (rather than
        // trusting the form we restored).
        const restored = await invoke("get_settings");
        if (restored && typeof restored === "object") {
          state.settings = normalizeSettings(restored);
          render();
        }
      } catch (error) {
        showToast(errorText(error));
      }
    }
  }

  function syncScrollFade(element) {
    if (!element) return;
    const scrollable = element.scrollHeight > element.clientHeight + 2;
    const atBottom = element.scrollTop + element.clientHeight >= element.scrollHeight - 3;
    element.classList.toggle("has-fade", scrollable && !atBottom);
  }

  function syncModalState() {
    const open = [els.settingsDialog, els.catalogDialog, els.confirmDialog].some(
      (dialog) => dialog && dialog.open
    );
    document.body.classList.toggle("has-modal", open);
  }

  function dialogStackPush(dialog) {
    if (!dialog) return;
    local.dialogStack = local.dialogStack.filter((item) => item !== dialog);
    local.dialogStack.push(dialog);
  }

  function dialogStackRemove(dialog) {
    local.dialogStack = local.dialogStack.filter((item) => item !== dialog);
  }

  /** Last opened still-open dialog; Esc always closes this one first. */
  function topDialog() {
    for (let index = local.dialogStack.length - 1; index >= 0; index -= 1) {
      const dialog = local.dialogStack[index];
      if (dialog && dialog.open) return dialog;
    }
    const fallback = [els.settingsDialog, els.catalogDialog, els.confirmDialog].find(
      (dialog) => dialog && dialog.open
    );
    return fallback || null;
  }

  function closeTopDialog() {
    const dialog = topDialog();
    if (!dialog) return false;
    if (dialog === els.settingsDialog) {
      void cancelSettings();
    } else {
      dialog.close();
    }
    return true;
  }

  function isTextField(target) {
    if (!target || !target.tagName) return false;
    const tag = target.tagName.toUpperCase();
    return (
      tag === "INPUT" ||
      tag === "TEXTAREA" ||
      tag === "SELECT" ||
      target.isContentEditable === true
    );
  }

  function focusDialogShell(dialog) {
    // A modal autofocuses its first control, which paints a focus ring before
    // the user has interacted. Focus the dialog surface instead; Tab then moves
    // through the controls in reading order.
    const shell = dialog && dialog.querySelector(".dialog-shell");
    if (!shell) return;
    try {
      shell.focus({ preventScroll: true });
    } catch (error) {
      shell.focus();
    }
  }

  function populateSettings(draft) {
    ensureSelectOption(els.providerSelect, draft.provider, providerInfo(draft.provider).title);
    ensureSelectOption(
      els.fallbackProviderSelect,
      draft.fallbackProvider,
      providerInfo(draft.fallbackProvider).title
    );
    els.providerSelect.value = draft.provider;
    els.baseUrlInput.value = draft.baseUrl;
    // Each key field starts on the provider it belongs to; `switchKeyField`
    // moves it again whenever the provider changes in this dialog.
    local.primaryKeys[draft.provider] = draft.apiKey || "";
    local.fallbackKeys[draft.fallbackProvider] = draft.fallbackApiKey || "";
    local.settingsKeyProvider = draft.provider;
    local.settingsFallbackKeyProvider = draft.fallbackProvider;
    local.settingsKeyDirty = false;
    local.settingsFallbackKeyDirty = false;
    local.settingsKeyAwaiting = null;
    local.settingsFallbackKeyAwaiting = null;
    els.apiKeyInput.value = draft.apiKey;
    els.apiKeyInput.type = "password";
    els.revealKeyBtn.textContent = tr("Show");
    els.modelInput.value = draft.model;
    els.fallbackToggle.checked = draft.fallbackEnabled;
    els.fallbackBody.hidden = !draft.fallbackEnabled;
    els.fallbackProviderSelect.value = draft.fallbackProvider;
    els.fallbackBaseInput.value = draft.fallbackBaseUrl;
    els.fallbackKeyInput.value = draft.fallbackApiKey;
    els.fallbackModelInput.value = draft.fallbackModel;

    setRange(els.temperatureRange, els.temperatureValue, draft.temperature, "decimal");
    setRange(els.topPRange, els.topPValue, draft.topP, "decimal");
    setRange(els.topKRange, els.topKValue, draft.topK, "integer");
    setRange(els.repetitionRange, els.repetitionValue, draft.repetitionPenalty, "decimal");
    setRange(els.contextRange, els.contextValue, draft.contextWindow, "thousands");

    els.autoTranslateToggle.checked = draft.autoTranslate;
    setRange(els.debounceRange, els.debounceValue, draft.debounce, "seconds");
    els.debounceRange.disabled = !draft.autoTranslate;
    els.keepHistoryToggle.checked = draft.keepHistory;
    els.warmUpToggle.checked = draft.warmUpOnLaunch;
    els.trayToggle.checked = draft.showInMenuBar;
    els.interfaceLanguageSelect.value = draft.interfaceLanguage;
    els.voiceSelect.value = draft.speechVoiceId || "";
    if (els.voiceSelect.value !== (draft.speechVoiceId || "")) {
      // Keep an unknown saved voice selectable instead of silently dropping it.
      if (draft.speechVoiceId) {
        const option = el("option", null, draft.speechVoiceId);
        option.value = draft.speechVoiceId;
        els.voiceSelect.append(option);
        els.voiceSelect.value = draft.speechVoiceId;
      }
    }

    els.hotkeyStandard.textContent = comboDisplay(draft.hotKey);
    els.hotkeySelection.textContent = comboDisplay(draft.selectionHotKey);
    els.hotkeyStandard.dataset.combo = JSON.stringify(draft.hotKey);
    els.hotkeySelection.dataset.combo = JSON.stringify(draft.selectionHotKey);
    hideHotkeyError();

    els.settingsVersion.textContent =
      "DeepL-oFM" + (diagnosticsVersion() ? " " + diagnosticsVersion() : "");
    els.aboutVersion.textContent = diagnosticsVersion()
      ? tr("Version %@", diagnosticsVersion())
      : "";
    els.settingsBody.scrollTop = 0;
    renderConnectStatus();
    renderModels();
    renderFallbackModels();
    renderHotkeyMessages();
    renderLoginItem();
    updateProviderDetails(draft);
    renderPromptChips();
    void refreshPromptPreview();
  }

  function selectSettingsTab(tab) {
    const target = SETTINGS_TABS.includes(tab) ? tab : "model";
    local.settingsTab = target;
    els.settingsTabs.querySelectorAll("[data-settings-tab]").forEach((button) => {
      const active = button.getAttribute("data-settings-tab") === target;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.tabIndex = active ? 0 : -1;
    });
    document.querySelectorAll("[data-settings-panel]").forEach((panel) => {
      panel.hidden = panel.getAttribute("data-settings-panel") !== target;
    });
    if (target === "about" && !local.diagnostics) void loadDiagnostics();
    els.settingsBody.scrollTop = 0;
    requestAnimationFrame(() => syncScrollFade(els.settingsBody));
  }

  function updateProviderDetails(draft) {
    const provider = providerInfo(draft.provider);
    els.providerHint.textContent = tr(provider.detail);
    els.keyLink.hidden = !provider.keyUrl;
    els.keyLink.onclick = provider.keyUrl
      ? () => openExternal(provider.keyUrl)
      : null;
    if (provider.requiresKey) {
      els.apiKeyHint.textContent = tr("Required for this provider. Stored securely on this computer.");
    } else if (provider.local) {
      els.apiKeyHint.textContent = tr("Can be empty for local servers. Stored securely on this computer.");
    } else {
      els.apiKeyHint.textContent = tr("Uses the stored key for this provider.");
    }
  }

  /* ------------------------------------------------------ provider API keys */

  function keyField(kind) {
    return kind === "fallback" ? els.fallbackKeyInput : els.apiKeyInput;
  }

  function keyCache(kind) {
    return kind === "fallback" ? local.fallbackKeys : local.primaryKeys;
  }

  function keyOwner(kind) {
    return kind === "fallback"
      ? local.settingsFallbackKeyProvider
      : local.settingsKeyProvider;
  }

  function setKeyOwner(kind, provider) {
    if (kind === "fallback") local.settingsFallbackKeyProvider = provider;
    else local.settingsKeyProvider = provider;
  }

  function keyDirty(kind) {
    return kind === "fallback" ? local.settingsFallbackKeyDirty : local.settingsKeyDirty;
  }

  function setKeyDirty(kind, dirty) {
    if (kind === "fallback") local.settingsFallbackKeyDirty = dirty;
    else local.settingsKeyDirty = dirty;
  }

  function keyAwaiting(kind) {
    return kind === "fallback"
      ? local.settingsFallbackKeyAwaiting
      : local.settingsKeyAwaiting;
  }

  function setKeyAwaiting(kind, provider) {
    if (kind === "fallback") local.settingsFallbackKeyAwaiting = provider;
    else local.settingsKeyAwaiting = provider;
  }

  /** Remember every provider's session key the shell has reported. */
  function rememberProviderKeys(settings) {
    if (!settings || typeof settings !== "object") return;
    if (settings.provider) local.primaryKeys[settings.provider] = settings.apiKey || "";
    if (settings.fallbackProvider) {
      local.fallbackKeys[settings.fallbackProvider] = settings.fallbackApiKey || "";
    }
  }

  /**
   * Move a key field to `provider`'s own key.
   *
   * The text typed for the previous provider stays under that provider; a
   * provider with no known key shows an empty field, and the controller loads
   * that provider's stored key when the dialog is saved. This is what stops a
   * catalogue click from saving an OpenRouter key as a Groq key.
   */
  function switchKeyField(kind, provider) {
    const field = keyField(kind);
    if (!field || !provider) return;
    const cache = keyCache(kind);
    const owner = keyOwner(kind);
    if (owner && keyDirty(kind)) cache[owner] = field.value;
    const known = Object.prototype.hasOwnProperty.call(cache, provider);
    const value = known ? cache[provider] : "";
    field.value = value;
    setKeyOwner(kind, provider);
    setKeyDirty(kind, false);
    // An unknown provider's stored key arrives with the next settings payload;
    // until then the field stays empty instead of showing another key.
    setKeyAwaiting(kind, known ? null : provider);
    const draft = local.settingsDraft;
    if (draft) {
      if (kind === "fallback") draft.fallbackApiKey = value;
      else draft.apiKey = value;
    }
  }

  /**
   * Refresh a key field from a settings payload (catalogue or state event).
   *
   * Never overwrites text the user typed for the provider on screen; it fills
   * the field that `switchKeyField` emptied for a newly selected provider.
   */
  function refreshKeyField(kind, provider, key) {
    if (!provider) return;
    keyCache(kind)[provider] = key || "";
    const draft = local.settingsDraft;
    if (!draft) return;
    const draftProvider = kind === "fallback" ? draft.fallbackProvider : draft.provider;
    if (draftProvider !== provider) return;
    if (keyDirty(kind) && keyOwner(kind) === provider) return;
    // A field that already holds this provider's key keeps it; only the field
    // emptied by a provider switch is filled from the payload.
    if (keyOwner(kind) === provider && keyAwaiting(kind) !== provider) return;
    const field = keyField(kind);
    if (!field) return;
    field.value = key || "";
    setKeyOwner(kind, provider);
    setKeyDirty(kind, false);
    setKeyAwaiting(kind, null);
    if (kind === "fallback") draft.fallbackApiKey = key || "";
    else draft.apiKey = key || "";
  }

  function setRange(range, output, value, format) {
    if (!range) return;
    range.value = String(value);
    if (output) output.textContent = formatRangeValue(range, format);
    updateRangeFill(range);
  }

  function formatRangeValue(range, format) {
    const value = Number(range.value);
    switch (format) {
      case "integer":
        return formatNumber(value);
      case "thousands":
        return formatNumber(value);
      case "seconds":
        return value.toFixed(2) + " s";
      default:
        return value.toFixed(2);
    }
  }

  function updateRangeFill(range) {
    const min = Number(range.min) || 0;
    const max = Number(range.max) || 100;
    const value = Number(range.value);
    const percent = max > min ? ((value - min) / (max - min)) * 100 : 0;
    range.style.setProperty("--fill", percent + "%");
  }

  function renderConnectStatus() {
    const status = state.backendStatus;
    let text = statusLabel(status);
    let kind = "muted";
    if (status === "connected") {
      kind = "success";
      text = tr("Connected");
    } else if (status === "failed") {
      kind = "danger";
      text = state.probeMessage || tr("Server unavailable");
    } else if (status === "checking" || status === "warming") {
      kind = "warning";
    }
    els.connectStatus.textContent = text;
    els.connectStatus.dataset.state = kind;
    els.connectStatus.title = state.probeMessage || "";
    els.fallbackStatus.textContent = "";
    if (state.fallbackModelsLoading) {
      els.fallbackStatus.textContent = tr("Checking connection…");
      els.fallbackStatus.dataset.state = "warning";
    } else if (state.fallbackModelsError) {
      els.fallbackStatus.textContent = state.fallbackModelsError;
      els.fallbackStatus.dataset.state = "danger";
    } else if (state.fallbackModels.length) {
      els.fallbackStatus.textContent = tr("Fallback provider works.");
      els.fallbackStatus.dataset.state = "success";
    } else {
      els.fallbackStatus.dataset.state = "muted";
    }
    renderInstallHint();
  }

  function diagnosticsVersion() {
    const value =
      (local.diagnostics && local.diagnostics.version) || state.version || "";
    return String(value || "");
  }

  function renderAboutDiagnostics() {
    const data = local.diagnostics || {};
    const placeholder = "—";
    els.aboutSettingsPath.textContent = data.settingsPath || placeholder;
    els.aboutHistoryPath.textContent = data.historyPath || placeholder;
    els.aboutSecretBackend.textContent = data.secretBackend || placeholder;
    els.aboutVersion.textContent = diagnosticsVersion()
      ? tr("Version %@", diagnosticsVersion())
      : "";
    els.settingsVersion.textContent =
      "DeepL-oFM" + (diagnosticsVersion() ? " " + diagnosticsVersion() : "");
  }

  async function loadDiagnostics() {
    try {
      const value = await invoke("get_diagnostics");
      if (value && typeof value === "object") local.diagnostics = value;
    } catch (error) {
      /* The About rows stay on the em dash when diagnostics are unavailable. */
    }
    renderAboutDiagnostics();
  }

  /** True when the last probe failed because the selected model is absent. */
  function probeReportsMissingModel(model) {
    if (!model) return false;
    const message = String(state.modelsError || state.probeMessage || "").trim();
    const lowered = message.toLowerCase();
    if (lowered && (lowered.includes("missing") || lowered.includes("not found"))) return true;
    if (message) {
      const exact = tr("Model “%@” not found", model);
      if (message === exact) return true;
      const template = tr("Server responds, but model “%@” is missing. Available: %@.");
      const before = template.split("%@")[0] || "";
      if (before && message.startsWith(before)) return true;
    }
    const listed = state.providerModels || [];
    return (
      listed.length > 0 &&
      !listed.some((name) => String(name).toLowerCase() === model.toLowerCase())
    );
  }

  function installCommandFor(model) {
    if (!model) return "";
    const entry = local.catalogEntries.find(
      (item) => item.modelId.toLowerCase() === model.toLowerCase()
    );
    return entry ? entry.installCommand || "" : "";
  }

  function renderInstallHint() {
    if (!els.installHint) return;
    const model = String(
      (local.settingsDraft && local.settingsDraft.model) ||
        (els.modelInput && els.modelInput.value) ||
        state.settings.model ||
        ""
    ).trim();
    const visible =
      !!els.settingsDialog.open &&
      !state.modelsLoading &&
      probeReportsMissingModel(model);
    const command = visible ? installCommandFor(model) : "";
    els.installHint.hidden = !command;
    els.installCommand.textContent = command;
    els.installCopyBtn.disabled = !command;
  }

  async function ensureCatalogEntries(force) {
    if (local.catalogLoading) return;
    if (!force && local.catalogEntries.length) return;
    local.catalogLoading = true;
    try {
      const list = await invoke("get_catalog");
      local.catalogEntries = normalizeCatalog(list);
    } catch (error) {
      /* The hint and catalogue simply stay empty. */
    } finally {
      local.catalogLoading = false;
      renderInstallHint();
      if (els.catalogDialog.open) renderCatalog();
    }
  }

  function renderModels() {
    const models = state.providerModels || [];
    const query = local.modelFilter.trim().toLowerCase();
    const filtered = query
      ? models.filter((name) => name.toLowerCase().includes(query))
      : models;
    els.modelsCount.textContent = tr("Models: %d", models.length);

    els.modelList.replaceChildren();
    if (state.modelsLoading) {
      els.modelList.append(el("div", "model-empty", tr("Checking connection…")));
      els.modelsHint.textContent = tr("Checking connection…");
      return;
    }
    if (state.modelsError) {
      els.modelList.append(el("div", "model-empty", state.modelsError));
      els.modelsHint.textContent = state.modelsError;
      return;
    }
    if (!filtered.length) {
      els.modelList.append(
        el(
          "div",
          "model-empty",
          models.length ? tr("Nothing found") : tr("The server returned no models.")
        )
      );
      els.modelsHint.textContent = tr("Select a model from the list or type its ID.");
      return;
    }
    const draft = local.settingsDraft;
    filtered.forEach((name) => {
      const button = el("button", "model-item");
      button.type = "button";
      button.dataset.model = name;
      button.setAttribute("role", "option");
      const selected = draft && draft.model === name;
      button.classList.toggle("is-selected", !!selected);
      button.setAttribute("aria-selected", selected ? "true" : "false");
      button.append(icon("check", "check"), el("span", "model-name", name));
      els.modelList.append(button);
    });
    els.modelsHint.textContent = tr("Select a model from the list or type its ID.");
  }

  function renderFallbackModels() {
    const models = state.fallbackModels || [];
    els.fallbackModelOptions.replaceChildren();
    models.forEach((name) => {
      const option = el("option");
      option.value = name;
      els.fallbackModelOptions.append(option);
    });
  }

  function renderHotkeyMessages() {
    const apply = (node, message) => {
      if (message) {
        node.hidden = false;
        node.textContent = message;
        node.dataset.state = "danger";
      } else {
        node.hidden = true;
        node.textContent = "";
      }
    };
    apply(els.hotkeyMessage, state.hotkeyMessage);
    apply(els.selectionHotkeyMessage, state.selectionHotkeyMessage);
  }

  /* ------------------------------------------------------------ login item */

  function renderLoginItem() {
    if (!els.loginItem) return;
    // Platforms without login items hide the whole row, like the Python port.
    const status = state.loginItemStatus || "disabled";
    const supported = status !== "unsupported";
    els.loginItem.hidden = !supported;
    if (!supported) return;
    els.loginItemToggle.checked = status === "enabled";
    const error = state.loginItemError || "";
    els.loginItemError.hidden = !error;
    els.loginItemError.textContent = error;
    // macOS asks the user to approve the item in System Settings.
    els.loginItemApproval.hidden = status !== "requiresApproval";
  }

  /** Read the authoritative status back after a change. */
  async function refreshLoginItem() {
    try {
      const value = await invoke("get_login_item");
      if (value && typeof value === "object") {
        state.loginItemStatus = String(value.status || "disabled");
        state.loginItemError = value.error ? String(value.error) : null;
      }
    } catch (error) {
      /* the state snapshot still carries both fields */
    }
    renderLoginItem();
  }

  async function setLoginItem(enabled) {
    if (!els.loginItem) return;
    if (state.loginItemStatus === "requiresApproval") {
      // The system still needs the user's approval, so there is nothing to
      // toggle here: send them to the page that grants it.
      renderLoginItem();
      send("open_login_item_settings");
      return;
    }
    els.loginItemError.hidden = true;
    els.loginItemError.textContent = "";
    try {
      await invoke("set_login_item", { enabled: enabled });
    } catch (error) {
      showToast(errorText(error));
    }
    await refreshLoginItem();
  }

  function renderPromptChips() {
    setSegment(els.promptStyleChips, "style", local.promptStyle);
    setSegment(els.promptToneChips, "tone", local.promptTone);
    if (els.promptTarget.value !== local.promptTarget) {
      els.promptTarget.value = local.promptTarget;
    }
  }

  // Fallback prompt preview, byte-identical to
  // ofm_text::PromptBuilder::preview (crates/text/src/prompts.rs). `preview_prompt`
  // is authoritative when it answers; this is used while it is in flight and
  // when the mock or a stale shell does not implement it.
  const PROMPT_STYLE_NATURAL =
    "natural and idiomatic, conveying the meaning rather than the wording";
  const PROMPT_STYLE_LITERAL = "literal, word for word";
  const PROMPT_TONE_FORMAL = "formal and professional";
  const PROMPT_TONE_CASUAL = "casual and conversational";
  const PROMPT_SAMPLE = "Hello, world!";

  function promptPreview(style, tone, targetCode) {
    const target = languageName(targetCode || "en");
    if ((!style || style === "auto") && (!tone || tone === "standard")) {
      return (
        "Translate the following text into " +
        target +
        ". Note that you should only output the translated result without any additional explanation:\n\n" +
        PROMPT_SAMPLE
      );
    }
    let descriptor = style === "literal" ? PROMPT_STYLE_LITERAL : PROMPT_STYLE_NATURAL;
    if (tone === "formal") descriptor += "; " + PROMPT_TONE_FORMAL;
    else if (tone === "casual") descriptor += "; " + PROMPT_TONE_CASUAL;
    return (
      "Please translate the following text into " +
      target +
      ". Note that the translation style must strictly conform to [" +
      descriptor +
      "]:\n\n" +
      PROMPT_SAMPLE
    );
  }

  function refreshPromptPreview() {
    if (!local.settingsDraft) return;
    const key = [local.promptStyle, local.promptTone, local.promptTarget].join("|");
    if (local.promptPreviewCache === key && els.promptPreview.textContent) return;
    local.promptPreviewCache = key;
    const fallback = promptPreview(local.promptStyle, local.promptTone, local.promptTarget);
    els.promptPreview.textContent = fallback;
    invoke("preview_prompt", {
      style: local.promptStyle,
      tone: local.promptTone,
      targetCode: local.promptTarget,
    })
      .then((value) => {
        if (local.promptPreviewCache !== key) return;
        const text =
          typeof value === "string" ? value : pick(value, ["prompt", "text"], "");
        if (text) els.promptPreview.textContent = String(text);
      })
      .catch(() => {
        /* the locally composed preview already matches PromptBuilder */
      });
  }

  function collectSettings() {
    const draft = local.settingsDraft || cloneSettings(state.settings);
    draft.provider = els.providerSelect.value;
    draft.baseUrl = els.baseUrlInput.value.trim();
    // Only send a key the field still holds for the selected provider; a stale
    // text left over from another provider must never reach the controller.
    draft.apiKey =
      local.settingsKeyProvider === draft.provider ? els.apiKeyInput.value : "";
    draft.model = els.modelInput.value.trim();
    draft.fallbackEnabled = els.fallbackToggle.checked;
    draft.fallbackProvider = els.fallbackProviderSelect.value;
    draft.fallbackBaseUrl = els.fallbackBaseInput.value.trim();
    draft.fallbackApiKey =
      local.settingsFallbackKeyProvider === draft.fallbackProvider
        ? els.fallbackKeyInput.value
        : "";
    draft.fallbackModel = els.fallbackModelInput.value.trim();
    draft.temperature = Number(els.temperatureRange.value);
    draft.topP = Number(els.topPRange.value);
    draft.topK = Number(els.topKRange.value);
    draft.repetitionPenalty = Number(els.repetitionRange.value);
    draft.contextWindow = Number(els.contextRange.value);
    draft.autoTranslate = els.autoTranslateToggle.checked;
    draft.debounce = Number(els.debounceRange.value);
    draft.keepHistory = els.keepHistoryToggle.checked;
    draft.warmUpOnLaunch = els.warmUpToggle.checked;
    draft.showInMenuBar = els.trayToggle.checked;
    draft.interfaceLanguage = els.interfaceLanguageSelect.value;
    draft.speechVoiceId = els.voiceSelect.value;
    draft.hotKey = parseCombo(els.hotkeyStandard.dataset.combo || comboDisplay(draft.hotKey));
    draft.selectionHotKey = parseCombo(
      els.hotkeySelection.dataset.combo || comboDisplay(draft.selectionHotKey)
    );
    return draft;
  }

  async function saveSettings() {
    const settings = collectSettings();
    if (!settings.model) {
      els.modelInput.focus();
      showToast(tr("Choose a model in Settings."));
      return;
    }
    const language = settings.interfaceLanguage;
    const previousLanguage = state.settings.interfaceLanguage;
    try {
      // Exactly one save with the final object; Connect/Load are reverted by
      // Cancel when the user backs out.
      await invoke("save_settings", { settings: settings });
      // Keep the controller's i18n state in step even when save_settings does
      // not reload the catalogue itself.
      if (language && language !== previousLanguage) {
        try {
          await invoke("set_interface_language", { code: language });
        } catch (error) {
          /* save_settings already persisted the language. */
        }
      }
      await loadState();
      void refreshCatalogue();
      local.settingsSnapshot = null;
      local.settingsModelsSnapshot = null;
      local.settingsFallbackModelsSnapshot = null;
      local.settingsDraft = null;
      els.settingsDialog.close();
      showToast(tr("Saved"));
      scheduleRefresh(40);
    } catch (error) {
      showToast(errorText(error));
    }
  }

  async function connectProvider() {
    const settings = collectSettings();
    try {
      // The contract exposes no per-request connection probe, so the draft is
      // persisted before probing. See ui/README.md.
      await invoke("save_settings", { settings: settings });
      await invoke("connect_and_load_models");
      scheduleRefresh(60);
      pollState(
        () => state.backendStatus === "checking" || state.modelsLoading,
        20000,
        4000
      );
    } catch (error) {
      showToast(errorText(error));
    }
  }

  async function loadFallbackModels() {
    const settings = collectSettings();
    try {
      await invoke("save_settings", { settings: settings });
      await invoke("load_fallback_models");
      scheduleRefresh(60);
      pollState(() => state.fallbackModelsLoading, 20000, 4000);
    } catch (error) {
      showToast(errorText(error));
    }
  }

  /* --------------------------------------------------------------- hotkeys */

  function startCapture(which) {
    if (!local.settingsDraft) return;
    local.capture = which;
    const field = which === "standard" ? els.hotkeyStandard : els.hotkeySelection;
    field.classList.add("is-capturing");
    field.textContent = tr("Press a combination…");
    document.addEventListener("keydown", captureKeydown, true);
  }

  function stopCapture() {
    if (!local.capture) return;
    const which = local.capture;
    local.capture = null;
    const field = which === "standard" ? els.hotkeyStandard : els.hotkeySelection;
    field.classList.remove("is-capturing");
    document.removeEventListener("keydown", captureKeydown, true);
    const draft = local.settingsDraft;
    if (draft) {
      field.textContent = comboDisplay(which === "standard" ? draft.hotKey : draft.selectionHotKey);
    }
    hideHotkeyError();
  }

  function hideHotkeyError() {
    els.hotkeyError.hidden = true;
    els.hotkeyError.textContent = "";
  }

  function captureKeydown(event) {
    if (!local.capture) return;
    event.preventDefault();
    event.stopPropagation();
    if (event.key === "Escape") {
      stopCapture();
      return;
    }
    if (["Control", "Shift", "Alt", "Meta", "CapsLock"].includes(event.key)) return;
    const combo = {
      key: String(event.key).toLowerCase(),
      ctrl: event.ctrlKey,
      alt: event.altKey,
      shift: event.shiftKey,
      meta: event.metaKey,
    };
    if (!comboIsValid(combo)) {
      els.hotkeyError.hidden = false;
      els.hotkeyError.textContent = tr(
        "At least one modifier is required — Ctrl, Alt or ⌘. Press Esc to cancel."
      );
      return;
    }
    const draft = local.settingsDraft;
    if (local.capture === "standard") draft.hotKey = combo;
    else draft.selectionHotKey = combo;
    const field = local.capture === "standard" ? els.hotkeyStandard : els.hotkeySelection;
    field.dataset.combo = JSON.stringify(combo);
    field.textContent = comboDisplay(combo);
    local.capture = null;
    field.classList.remove("is-capturing");
    document.removeEventListener("keydown", captureKeydown, true);
    hideHotkeyError();
  }

  /* --------------------------------------------------------------- catalogue */

  async function openCatalog() {
    if (!els.catalogDialog.open) {
      els.catalogDialog.showModal();
      dialogStackPush(els.catalogDialog);
      syncModalState();
      els.catalogBody.classList.add("scroll-fade");
      focusDialogShell(els.catalogDialog);
      if (els.catalogDialog.open) renderCatalog();
      requestAnimationFrame(() => syncScrollFade(els.catalogBody));
    }
    if (local.catalogEntries.length || local.catalogLoading) return;
    renderCatalog();
    await ensureCatalogEntries();
    renderCatalog();
  }

  function catalogMatches(entry) {
    if (local.catalogProvider && entry.providerValue !== local.catalogProvider) return false;
    if (local.catalogFree && !entry.isFree) return false;
    const query = local.catalogFilter.trim().toLowerCase();
    if (!query) return true;
    return [entry.name, entry.modelId, entry.note, entry.provider, entry.badges.join(" ")]
      .join(" ")
      .toLowerCase()
      .includes(query);
  }

  function renderCatalog() {
    const entries = local.catalogEntries.filter(catalogMatches);
    const recommended = entries.filter((entry) =>
      entry.badges.some((badge) => String(badge).toLowerCase() === "recommended")
    );
    const rest = entries.filter((entry) => !recommended.includes(entry));

    els.catalogCount.textContent = local.catalogLoading
      ? tr("Connecting…")
      : String(entries.length);

    els.catalogRecommendedSection.hidden = !recommended.length;
    els.catalogRecommendedList.replaceChildren(...recommended.map(catalogCard));

    els.catalogModelsSection.hidden = !rest.length && !local.catalogLoading;
    if (local.catalogLoading && !entries.length) {
      els.catalogModelsList.replaceChildren(el("div", "model-empty", tr("Connecting…")));
    } else {
      els.catalogModelsList.replaceChildren(...rest.map(catalogCard));
    }

    const server = local.catalogServerModels.filter((name) => {
      const query = local.catalogFilter.trim().toLowerCase();
      return !query || name.toLowerCase().includes(query);
    });
    els.catalogServerSection.hidden = !server.length;
    els.catalogServerCount.textContent = server.length ? String(server.length) : "";
    els.catalogServerList.replaceChildren(...server.map(serverModelCard));

    const nothing = !local.catalogLoading && !entries.length && !server.length;
    els.catalogEmpty.hidden = !nothing;
    requestAnimationFrame(() => syncScrollFade(els.catalogBody));
  }

  function catalogCard(entry) {
    const card = el("div", "catalog-card");
    const head = el("div", "catalog-card-head");
    head.append(el("h3", null, entry.name));
    if (entry.provider) {
      head.append(el("span", "badge badge-accent", entry.provider));
    }
    entry.badges.forEach((badge) => {
      if (String(badge).toLowerCase() === "recommended") {
        head.append(el("span", "badge badge-accent", tr(String(badge))));
      } else if (String(badge).toLowerCase() === "free") {
        head.append(el("span", "badge badge-free", tr(String(badge))));
      } else {
        head.append(el("span", "badge", tr(String(badge))));
      }
    });
    if (entry.isFree && !entry.badges.some((badge) => String(badge).toLowerCase() === "free")) {
      head.append(el("span", "badge badge-free", tr("Free")));
    }
    card.append(head);
    card.append(el("div", "catalog-id", entry.modelId));
    if (entry.note) card.append(el("p", "catalog-note", tr(entry.note)));

    const use = el("button", "btn btn-secondary btn-sm catalog-use", tr("Use this model"));
    use.type = "button";
    use.dataset.useModel = entry.modelId;
    use.dataset.provider = entry.providerValue || entry.provider;
    card.append(use);

    if (entry.installCommand) {
      const command = el("div", "catalog-command");
      command.append(el("span", "command-text", entry.installCommand));
      const copy = el("button", "icon-btn");
      copy.type = "button";
      copy.dataset.copyCommand = entry.installCommand;
      copy.setAttribute("aria-label", tr("Copy install command"));
      copy.setAttribute("title", tr("Copy install command"));
      copy.append(icon("copy"));
      command.append(copy);
      card.append(command);
    }
    return card;
  }

  function serverModelCard(name) {
    const card = el("div", "catalog-card");
    const head = el("div", "catalog-card-head");
    head.append(el("h3", null, name));
    head.append(el("span", "badge", tr("Found on the server")));
    card.append(head);
    card.append(el("div", "catalog-id", name));
    const use = el("button", "btn btn-secondary btn-sm catalog-use", tr("Use this model"));
    use.type = "button";
    use.dataset.useModel = name;
    use.dataset.provider = state.settings.provider;
    card.append(use);
    return card;
  }

  async function fetchServerModels() {
    if (local.catalogFetching) return;
    local.catalogFetching = true;
    els.catalogFetch.disabled = true;
    els.catalogFetch.textContent = tr("Connecting…");
    try {
      const models = await invoke("list_models");
      local.catalogServerModels = (Array.isArray(models) ? models : []).map(String).filter(Boolean);
      if (!local.catalogServerModels.length) showToast(tr("The server returned no models."));
    } catch (error) {
      showToast(errorText(error));
    } finally {
      local.catalogFetching = false;
      els.catalogFetch.disabled = false;
      els.catalogFetch.textContent = tr("Fetch from server");
      renderCatalog();
    }
  }

  async function useCatalogModel(modelId, provider) {
    try {
      const entry = local.catalogEntries.find((item) => item.modelId === modelId);
      // Catalogue entries carry their provider and base URL; models discovered
      // with "Fetch from server" have to go through apply_model, which selects
      // any id and saves immediately.
      if (entry) await invoke("apply_catalog_entry", { modelId: modelId });
      else await invoke("apply_model", { modelId: modelId });
      if (els.settingsDialog.open && local.settingsDraft) {
        const draft = local.settingsDraft;
        draft.model = modelId;
        if (provider && PROVIDERS.some((item) => item.value === provider)) {
          draft.provider = provider;
          const info = providerInfo(provider);
          draft.baseUrl = info.baseUrl;
          ensureSelectOption(els.providerSelect, provider, info.title);
          els.providerSelect.value = provider;
          els.baseUrlInput.value = info.baseUrl;
          // The applied provider's key replaces the previous provider's text;
          // the settings event that follows carries the stored key.
          switchKeyField("primary", provider);
        }
        els.modelInput.value = modelId;
        updateProviderDetails(draft);
        renderModels();
        renderInstallHint();
      }
      showToast(tr("Model “%@” selected.", modelId));
      els.catalogDialog.close();
      scheduleRefresh(80);
    } catch (error) {
      showToast(errorText(error));
    }
  }

  /* --------------------------------------------------------------- history */

  function confirmClearHistory() {
    if (!els.confirmDialog.open) {
      els.confirmDialog.showModal();
      dialogStackPush(els.confirmDialog);
      syncModalState();
    }
  }

  async function clearHistory() {
    els.confirmDialog.close();
    try {
      await invoke("history_clear");
      local.historyResults = null;
      scheduleRefresh(40);
    } catch (error) {
      showToast(errorText(error));
    }
  }

  function searchHistoryDebounced() {
    clearTimeout(local.historySearchTimer);
    local.historyResults = null;
    renderHistory();
    const query = local.historyQuery.trim();
    if (!query) return;
    local.historySearchTimer = setTimeout(async () => {
      try {
        const results = await invoke("history_search", { query: query });
        if (local.historyQuery.trim() === query) {
          local.historyResults = normalizeHistory(results);
          renderHistory();
        }
      } catch (error) {
        // Fall back to the local substring filter; state.history is present.
      }
    }, 140);
  }

  /* ---------------------------------------------------------------- actions */

  function selectTab(tab) {
    if (!TABS.includes(tab)) return;
    state.tab = tab;
    renderTabs();
    send("set_tab", { tab: tab });
    if (tab === "history") void refreshHistoryList();
  }

  async function refreshHistoryList() {
    try {
      const list = await invoke("history_list");
      if (Array.isArray(list)) {
        state.history = normalizeHistory(list);
        renderHistory();
      }
    } catch (error) {
      /* get_state still carries the history list. */
    }
  }

  function translateNow(force) {
    if (!state.sourceText.trim()) {
      els.sourceInput.focus();
      return;
    }
    state.errorMessage = null;
    state.isTranslating = true;
    state.completed = 0;
    state.total = 0;
    state.translatedText = "";
    renderTranslate();
    send("translate_text", { force: force !== false });
    pollState(() => state.isTranslating, 180000, 2000);
  }

  function copyTranslation() {
    if (!state.translatedText) return;
    send("copy_translation");
    showCopyFeedback("translation");
  }

  function copySourceText() {
    if (!state.sourceText) return;
    send("copy_source");
    showCopyFeedback("source");
  }

  function showCopyFeedback(kind) {
    local.copyFeedback = kind;
    clearTimeout(local.copyFeedbackTimer);
    renderTranslate();
    local.copyFeedbackTimer = setTimeout(() => {
      local.copyFeedback = "";
      renderTranslate();
    }, 1600);
  }

  function commitSourceText(text) {
    state.sourceText = String(text === null || text === undefined ? "" : text);
    els.sourceInput.value = state.sourceText;
    if (!state.sourceText.trim()) local.sourcePreview = false;
    els.sourceCounter.textContent = state.sourceText
      ? characters(Array.from(state.sourceText).length)
      : "";
    els.translateNowBtn.disabled = !state.sourceText.trim();
    els.againBtn.disabled = !state.sourceText.trim();
    send("set_source_text", { text: state.sourceText });
    renderTranslate();
  }

  async function readClipboardText() {
    try {
      return unwrapText(await invoke("read_clipboard"));
    } catch (error) {
      return "";
    }
  }

  async function pasteIntoSource() {
    const text = await readClipboardText();
    if (!text) {
      showToast(tr("The clipboard is empty."));
      return;
    }
    commitSourceText(text);
  }

  function insertAtSourceCursor(text) {
    const value = String(text || "");
    if (!value) return;
    const start =
      typeof els.sourceInput.selectionStart === "number"
        ? els.sourceInput.selectionStart
        : els.sourceInput.value.length;
    const end =
      typeof els.sourceInput.selectionEnd === "number"
        ? els.sourceInput.selectionEnd
        : start;
    const current = els.sourceInput.value;
    const next = current.slice(0, start) + value + current.slice(end);
    const caret = start + value.length;
    commitSourceText(next);
    try {
      els.sourceInput.selectionStart = caret;
      els.sourceInput.selectionEnd = caret;
    } catch (error) {
      /* selection is unavailable while the preview is showing */
    }
  }

  async function handleRichPaste(event) {
    const data = event.clipboardData;
    if (!data) return;
    const types = data.types ? Array.from(data.types) : [];
    const hasRich = types.includes("text/html") || !!data.getData("text/html");
    if (!hasRich) return; // plain text: let the browser paste normally
    event.preventDefault();
    const plain = data.getData("text/plain") || "";
    const markdown = (await readClipboardText()) || plain;
    if (!markdown) return;
    insertAtSourceCursor(markdown);
    // A rich paste is already Markdown; show the rendered result like Python.
    if (state.sourceText.trim()) {
      local.sourcePreview = true;
      renderTranslate();
    }
  }

  function speak(target) {
    const active = state.speaking === target;
    if (active) {
      send("stop_speaking");
      state.speaking = "";
      renderTranslate();
      scheduleRefresh(400);
      return;
    }
    send("speak", { target: target });
    state.speaking = target;
    renderTranslate();
    scheduleRefresh(400);
  }

  function pickFile() {
    invoke("pick_file")
      .then((value) => {
        const path = unwrapPath(value);
        if (path) startFileTranslation(path, defaultFileTarget());
        else showToast(tr("No file was chosen."));
      })
      .catch((error) => {
        showToast(errorText(error));
      });
  }

  function startFileTranslation(path, target) {
    if (!path) return;
    const code =
      target === undefined || target === null || target === ""
        ? local.fileTarget || defaultFileTarget()
        : String(target);
    local.fileJobTarget = code;
    // The Files tab owns its language: pass it as `target` instead of mutating
    // the Translate tab through set_target_language.
    send("translate_file", { path: path, target: code }).then(() => {
      scheduleRefresh(60);
      pollState(
        () => !!state.fileJob && RUNNING_FILE_STATES.includes(state.fileJob.state),
        600000,
        5000
      );
    });
  }

  function retryFileTranslation() {
    const job = state.fileJob;
    if (!job || !job.path) {
      pickFile();
      return;
    }
    startFileTranslation(job.path, local.fileJobTarget || local.fileTarget);
  }

  function handleDroppedPath(path) {
    if (!path) return;
    startFileTranslation(path);
  }

  async function saveTranslatedFile() {
    const job = state.fileJob;
    if (!job || !job.output) return;
    const suggested = job.resultName || basename(job.output);
    let destination = null;
    try {
      destination = unwrapPath(await invoke("pick_save_path", { suggestedName: suggested }));
    } catch (error) {
      showToast(errorText(error));
      return;
    }
    if (!destination) return;
    // commands.rs: save_translated_file(path: String).
    send("save_translated_file", { path: destination }).then(() => scheduleRefresh(80));
  }

  function revealFile() {
    const job = state.fileJob;
    if (!job) return;
    // Prefer the saved file once it exists; before the first save the staged
    // copy is the only file there is.
    const path = job.savedPath || job.output || job.path;
    if (!path) return;
    send("reveal_in_folder", { path: path });
  }

  /**
   * Replace the Write draft through the same path as typing or pasting it.
   *
   * The counter, the button states, the stale-result reset and the cancel of an
   * older rewrite all follow from one place, so `--write-text` and a pasted
   * draft cannot drift apart.
   */
  function setWriteDraft(text, options) {
    const value = text === null || text === undefined ? "" : String(text);
    local.writeText = value;
    if (els.writeInput.value !== value) els.writeInput.value = value;
    els.writeCounter.textContent = value ? characters(Array.from(value).length) : "";
    els.improveBtn.disabled = !value.trim() || state.write.running;
    els.clearWriteBtn.disabled = !value;
    // Editing invalidates the previous result: Copy must never return text for
    // an older draft. Stop any rewrite still in flight.
    const active = !!(
      state.write.running ||
      local.writeBusy ||
      state.write.output ||
      state.write.error
    );
    if (active) {
      local.writeStale = true;
      local.writePending = false;
      local.writeSawRunning = false;
      local.writeBusy = false;
      state.write.running = false;
      if (!local.writeCancelSent) {
        local.writeCancelSent = true;
        send("cancel_write");
      }
    }
    if (options && options.focus) {
      try {
        els.writeInput.focus({ preventScroll: true });
      } catch (error) {
        els.writeInput.focus();
      }
    }
    renderWrite();
  }

  function improveText() {
    if (!local.writeText.trim() || state.write.running || local.writeBusy) return;
    local.writeBusy = true;
    local.writeBusyAt = Date.now();
    local.writePending = true;
    local.writeSubmittedAt = Date.now();
    local.writeSawRunning = false;
    local.writeCancelSent = false;
    local.writeView = local.writeView || "preview";
    // `null` means "detect the draft's language"; only an explicit pick sends a
    // code, so a Ukrainian draft is never rewritten in English.
    const targetCode = local.writeTargetChosen ? local.writeTarget || null : null;
    send("write_text", {
      text: local.writeText,
      targetCode: targetCode,
    });
    pollState(() => local.writeBusy || state.write.running, 180000, 2000);
    clearTimeout(local.writeBusyTimer);
    local.writeBusyTimer = setTimeout(() => {
      if (!state.write.running) {
        local.writeBusy = false;
        renderWrite();
      }
    }, 20000);
    renderWrite();
  }

  function cancelWrite() {
    local.writeBusy = false;
    local.writeStale = true;
    local.writePending = false;
    local.writeSawRunning = false;
    local.writeCancelSent = true;
    clearTimeout(local.writeBusyTimer);
    send("cancel_write");
    state.write.running = false;
    renderWrite();
  }

  function copyWriteOutput() {
    const output = writeOutput();
    if (!output) return;
    send("copy_text", { text: output });
    showToast(tr("Copied"));
  }

  function newTranslation() {
    local.sourcePreview = false;
    state.sourceText = "";
    state.translatedText = "";
    state.errorMessage = null;
    state.isTranslating = false;
    state.warningCount = 0;
    state.detectedLanguage = null;
    state.tokensPerSecond = null;
    state.lastDurationMs = null;
    els.sourceInput.value = "";
    send("clear_source");
    selectTab("translate");
    renderTranslate();
    focusSourceEditor();
  }

  function focusSourceEditor() {
    if (!els.sourceInput || els.sourceInput.hidden) return;
    try {
      els.sourceInput.focus({ preventScroll: true });
    } catch (error) {
      els.sourceInput.focus();
    }
  }

  function focusInitialEditor() {
    if (topDialog()) return;
    if (state.tab === "write") {
      try {
        els.writeInput.focus({ preventScroll: true });
      } catch (error) {
        els.writeInput.focus();
      }
      return;
    }
    focusSourceEditor();
  }

  function openExternal(url) {
    if (!url) return;
    send("open_url", { url: url });
  }

  function showToast(message) {
    if (!message) return;
    const id = ++toastSequence;
    const node = el("div", "toast");
    node.dataset.toast = String(id);
    node.append(icon("check"), el("span", null, message));
    els.toastRegion.append(node);
    while (els.toastRegion.children.length > 3) {
      els.toastRegion.firstElementChild.remove();
    }
    setTimeout(() => {
      node.classList.add("is-leaving");
      setTimeout(() => node.remove(), 200);
    }, 2600);
  }

  /* ----------------------------------------------------------------- events */

  function scheduleRefresh(delay) {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(loadState, typeof delay === "number" ? delay : 100);
  }

  // Some AppEvent variants cannot be serialised by serde's internally-tagged
  // enum (a newtype of a primitive), so the UI cannot rely on events alone.
  // While a job is running it polls the authoritative snapshot.
  let pollTimer = 0;
  let pollCondition = null;
  let pollDeadline = 0;
  let pollGraceUntil = 0;

  // `graceMs` keeps polling after the command even if the first snapshot does
  // not show the job yet (the Rust command may start it asynchronously).
  function pollState(condition, timeoutMs, graceMs) {
    pollCondition = condition;
    pollDeadline = Date.now() + (timeoutMs || 30000);
    pollGraceUntil = Date.now() + (graceMs === undefined ? 2500 : graceMs);
    if (pollTimer) return;
    pollTimer = setInterval(() => {
      const now = Date.now();
      const inGrace = now < pollGraceUntil;
      const done = now > pollDeadline || (!inGrace && pollCondition && !pollCondition());
      if (done) {
        clearInterval(pollTimer);
        pollTimer = 0;
        return;
      }
      loadState();
    }, 700);
  }

  async function loadState() {
    const sequence = ++refreshSequence;
    try {
      const raw = await invoke("get_state");
      if (sequence !== refreshSequence) return;
      applyState(raw);
    } catch (error) {
      // Keep the last good snapshot; surface the reason once.
      showToast(errorText(error));
    }
  }

  /**
   * Adopt a WriteState snapshot without letting a cancelled request resurrect
   * text for an older draft. `writeStale` is set on every edit; a changed
   * output, or the end of a request we dispatched, clears it.
   */
  function adoptWrite(next, previousWrite) {
    const previous = previousWrite || state.write;
    if (next.running) local.writeSawRunning = true;
    let fresh = false;
    if (next.output && next.output !== previous.output) fresh = true;
    if (
      local.writePending &&
      !next.running &&
      local.writeSawRunning &&
      Date.now() - local.writeSubmittedAt > 400
    ) {
      fresh = true;
    }
    if (fresh) {
      local.writeStale = false;
      local.writePending = false;
      local.writeSawRunning = false;
    }
    return next;
  }

  function applyState(raw) {
    const next = normalizeState(raw);
    const previous = state;
    next.write = adoptWrite(next.write, previous.write);
    state = next;

    if (local.writeBusy) {
      if (state.write.running) {
        // The controller accepted the job; keep the busy affordance.
      } else if (state.write.output || state.write.error) {
        local.writeBusy = false;
      } else if (Date.now() - local.writeBusyAt > 8000) {
        // Never stay stuck if the backend rejected the request silently.
        local.writeBusy = false;
      }
    }

    if (!local.fileTarget) local.fileTarget = defaultFileTarget();
    if (state.settings.interfaceLanguage !== previous.settings.interfaceLanguage) {
      document.documentElement.lang = uiLanguageCode();
      void refreshCatalogue();
    }
    render();
  }

  function normalizeEventType(type) {
    return String(type || "").trim().toLowerCase();
  }

  function eventValue(event, type) {
    if (!event || typeof event !== "object") return undefined;
    if (Object.prototype.hasOwnProperty.call(event, "value")) return event.value;
    // ofm_app::AppEvent is `#[serde(tag = "type")]`. A newtype variant whose
    // payload is a struct (Settings, FileJob, Write) is serialised by merging
    // that struct's fields next to `type`, not under `value`.
    if (type === "settings") return event.settings || event;
    if (type === "filejob") return event.fileJob || event;
    if (type === "write") return event.write || event;
    // A newtype variant of a primitive cannot be serialised at all (serde
    // rejects it); tolerate a variant-named or camelCase field in case the Rust
    // enum is reshaped to a struct payload.
    const rawType = typeof event.type === "string" ? event.type : "";
    if (rawType && event[rawType] !== undefined) return event[rawType];
    if (event[type] !== undefined) return event[type];
    return undefined;
  }

  function handleEvent(event) {
    if (!event || typeof event !== "object") {
      scheduleRefresh();
      return;
    }
    if (event.payload && typeof event.payload === "object" && !event.type) {
      event = event.payload;
    }
    let type = normalizeEventType(event.type || event.kind || event.name);
    const value = eventValue(event, type);

    switch (type) {
      case "statechanged":
        if (value && typeof value === "object" && "tab" in value) applyState(value);
        else scheduleRefresh(20);
        return;
      case "progress": {
        const payload = value && typeof value === "object" ? value : event;
        const completed = pick(payload, ["completed"], state.completed);
        const total = pick(payload, ["total"], state.total);
        state.completed = Math.max(0, Number(completed) || 0);
        state.total = Math.max(0, Number(total) || 0);
        if (state.total > 0 && !state.translatedText) state.isTranslating = true;
        renderTranslate();
        return;
      }
      case "translating": {
        const flag = typeof value === "boolean" ? value : event.value;
        state.isTranslating = !!flag;
        if (!flag) scheduleRefresh(80);
        else renderTranslate();
        return;
      }
      case "translatedtext":
        if (value !== undefined && value !== null) state.translatedText = String(value);
        state.isTranslating = false;
        state.errorMessage = null;
        renderTranslate();
        return;
      case "translationpartial":
        // Streaming preview: keep the progress bar and the final-result rules
        // (history, metrics, warnings) untouched.
        if (value !== undefined && value !== null) state.translatedText = String(value);
        renderTranslate();
        return;
      case "sourcetext":
        if (value !== undefined && value !== null) state.sourceText = String(value);
        renderTranslate();
        return;
      case "languages": {
        const payload = value && typeof value === "object" ? value : event;
        const source = pick(payload, ["source"], null);
        const target = pick(payload, ["target"], null);
        if (source !== null) state.sourceLanguage = String(source);
        if (target !== null) state.targetLanguage = String(target);
        render();
        return;
      }
      case "detected":
        state.detectedLanguage = value !== undefined && value !== null ? String(value) : null;
        renderTranslate();
        return;
      case "error":
      case "translationfailed":
        state.errorMessage = value !== undefined && value !== null ? String(value) : null;
        if (type === "translationfailed") state.isTranslating = false;
        renderTranslate();
        return;
      case "backendstatus":
        state.backendStatus = value !== undefined && value !== null ? String(value) : "unknown";
        renderHeader();
        renderStatusBar();
        if (els.settingsDialog.open) renderConnectStatus();
        return;
      case "probemessage":
        state.probeMessage = value !== undefined && value !== null ? String(value) : "";
        renderHeader();
        return;
      case "models":
        state.providerModels = Array.isArray(value) ? value.map(String) : state.providerModels;
        state.modelsLoading = false;
        state.modelsError = null;
        if (els.settingsDialog.open) renderModels();
        return;
      case "modelsloading":
        state.modelsLoading = !!value;
        if (els.settingsDialog.open) renderModels();
        return;
      case "modelserror":
        state.modelsError = value !== undefined && value !== null && value !== "" ? String(value) : null;
        state.modelsLoading = false;
        if (els.settingsDialog.open) renderModels();
        return;
      case "fallbackmodels":
        state.fallbackModels = Array.isArray(value) ? value.map(String) : state.fallbackModels;
        state.fallbackModelsLoading = false;
        state.fallbackModelsError = null;
        if (els.settingsDialog.open) {
          renderFallbackModels();
          renderConnectStatus();
        }
        return;
      case "fallbackmodelsloading":
        state.fallbackModelsLoading = !!value;
        if (els.settingsDialog.open) renderConnectStatus();
        return;
      case "fallbackmodelserror":
        state.fallbackModelsError =
          value !== undefined && value !== null && value !== "" ? String(value) : null;
        state.fallbackModelsLoading = false;
        if (els.settingsDialog.open) renderConnectStatus();
        return;
      case "settings": {
        if (value && typeof value === "object") {
          const language = state.settings.interfaceLanguage;
          state.settings = normalizeSettings(value);
          rememberProviderKeys(state.settings);
          if (local.settingsDraft) {
            // The catalogue changes the provider outside the form; move the key
            // fields with it and fill them from the provider's stored key.
            refreshKeyField(
              "primary",
              state.settings.provider,
              state.settings.apiKey
            );
            refreshKeyField(
              "fallback",
              state.settings.fallbackProvider,
              state.settings.fallbackApiKey
            );
          }
          if (state.settings.interfaceLanguage !== language) void refreshCatalogue();
          render();
        } else {
          scheduleRefresh(20);
        }
        return;
      }
      case "interfacelanguage":
        state.settings.interfaceLanguage =
          value !== undefined && value !== null ? String(value) : state.settings.interfaceLanguage;
        void refreshCatalogue();
        scheduleRefresh(60);
        return;
      case "tab":
        state.tab = value !== undefined && value !== null ? String(value) : state.tab;
        renderTabs();
        return;
      case "loginitem":
        state.loginItemStatus =
          value !== undefined && value !== null ? String(value) : state.loginItemStatus;
        if (els.settingsDialog.open) {
          renderLoginItem();
          // The event carries the status only; the error text lives in state.
          void refreshLoginItem();
        }
        return;
      case "history":
        local.historyResults = null;
        scheduleRefresh(30);
        return;
      case "filejob":
        state.fileJob = normalizeFileJob(value);
        renderFiles();
        return;
      case "copyfeedback":
        showCopyFeedback("translation");
        return;
      case "metrics": {
        const payload = value && typeof value === "object" ? value : event;
        const tps = pick(payload, ["tokensPerSecond", "tokens_per_second"], undefined);
        const duration = pick(payload, ["lastDurationMs", "last_duration_ms"], undefined);
        if (tps !== undefined) state.tokensPerSecond = tps === null ? null : Number(tps);
        if (duration !== undefined) state.lastDurationMs = duration === null ? null : Number(duration);
        renderTranslate();
        return;
      }
      case "speaking":
        state.speaking = value !== undefined && value !== null ? String(value) : "";
        renderTranslate();
        return;
      case "style":
        state.style = value !== undefined ? String(value) : state.style;
        setSegment(els.styleChips, "style", state.style);
        return;
      case "tone":
        state.tone = value !== undefined ? String(value) : state.tone;
        setSegment(els.toneChips, "tone", state.tone);
        return;
      case "resultview":
        state.resultView = value !== undefined ? String(value) : state.resultView;
        setSegment(els.viewSwitch, "view", state.resultView);
        renderTranslate();
        return;
      case "write":
        // AppEvent::Write — a newtype of WriteState, merged next to `type`.
        if (value && typeof value === "object") {
          state.write = adoptWrite(normalizeWrite(value), state.write);
          if (!state.write.running) local.writeBusy = false;
          renderWrite();
        } else {
          scheduleRefresh(40);
        }
        return;
      default:
        scheduleRefresh(100);
    }
  }

  /* --------------------------------------------------------------- bindings */

  function bindEvents() {
    // Tabs ---------------------------------------------------------------
    els.tabs.addEventListener("click", (event) => {
      const button = closest(event.target, "[data-tab]");
      if (button) selectTab(button.getAttribute("data-tab"));
    });
    els.tabs.addEventListener("keydown", (event) => {
      const buttons = Array.from(els.tabs.querySelectorAll("[data-tab]"));
      const index = buttons.indexOf(document.activeElement);
      if (index < 0) return;
      let next = index;
      if (event.key === "ArrowRight") next = (index + 1) % buttons.length;
      else if (event.key === "ArrowLeft") next = (index - 1 + buttons.length) % buttons.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = buttons.length - 1;
      else return;
      event.preventDefault();
      buttons[next].focus();
      selectTab(buttons[next].getAttribute("data-tab"));
    });

    // Header menu --------------------------------------------------------
    els.moreBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleMenu(!local.menuOpen);
    });
    document.addEventListener("click", (event) => {
      if (local.menuOpen && !closest(event.target, ".menu-wrap")) toggleMenu(false);
    });
    els.moreMenu.addEventListener("click", (event) => {
      const item = closest(event.target, "[data-command]");
      if (!item) return;
      const command = item.getAttribute("data-command");
      toggleMenu(false);
      if (command === "open_settings") openSettings("model");
      else if (command === "check_connection") {
        send("check_connection");
        pollState(() => state.backendStatus === "checking", 15000, 4000);
      } else if (command === "history") {
        selectTab("history");
      } else if (command === "translate_clipboard") {
        send("translate_clipboard");
        pollState(() => state.isTranslating, 180000, 5000);
      } else if (command === "translate_selection") {
        send("translate_selection");
        pollState(() => state.isTranslating, 180000, 5000);
      } else if (command === "clear_source") {
        newTranslation();
      }
    });
    els.settingsBtn.addEventListener("click", () => openSettings("model"));
    els.connCapsule.addEventListener("click", () => openSettings("model"));

    // Translate ----------------------------------------------------------
    els.sourceLang.addEventListener("change", () => {
      state.sourceLanguage = els.sourceLang.value;
      syncLanguageTitles();
      send("set_source_language", { code: state.sourceLanguage });
    });
    els.targetLang.addEventListener("change", () => {
      state.targetLanguage = els.targetLang.value;
      syncLanguageTitles();
      send("set_target_language", { code: state.targetLanguage });
    });
    els.swapBtn.addEventListener("click", () => send("swap_languages"));
    els.styleChips.addEventListener("click", (event) => {
      const button = closest(event.target, "[data-style]");
      if (!button) return;
      state.style = button.getAttribute("data-style");
      setSegment(els.styleChips, "style", state.style);
      syncCompactControls();
      send("set_style", { style: state.style });
    });
    els.toneChips.addEventListener("click", (event) => {
      const button = closest(event.target, "[data-tone]");
      if (!button) return;
      state.tone = button.getAttribute("data-tone");
      setSegment(els.toneChips, "tone", state.tone);
      syncCompactControls();
      send("set_tone", { tone: state.tone });
    });
    els.styleCompact.addEventListener("change", () => {
      state.style = els.styleCompact.value;
      setSegment(els.styleChips, "style", state.style);
      syncCompactControls();
      send("set_style", { style: state.style });
    });
    els.toneCompact.addEventListener("change", () => {
      state.tone = els.toneCompact.value;
      setSegment(els.toneChips, "tone", state.tone);
      syncCompactControls();
      send("set_tone", { tone: state.tone });
    });
    els.viewSwitch.addEventListener("click", (event) => {
      const button = closest(event.target, "[data-view]");
      if (!button) return;
      state.resultView = button.getAttribute("data-view");
      setSegment(els.viewSwitch, "view", state.resultView);
      send("set_result_view", { mode: state.resultView });
      renderTranslate();
    });

    const sourceInput = debounce(() => {
      send("set_source_text", { text: state.sourceText });
    }, 90);
    els.sourceInput.addEventListener("input", () => {
      state.sourceText = els.sourceInput.value;
      if (!state.sourceText.trim()) local.sourcePreview = false;
      els.sourceCounter.textContent = state.sourceText
        ? characters(Array.from(state.sourceText).length)
        : "";
      sourceInput();
      els.translateNowBtn.disabled = !state.sourceText.trim();
      els.againBtn.disabled = !state.sourceText.trim();
    });
    // Ctrl+Enter is handled once by the delegated document handler below.
    els.sourceInput.addEventListener("paste", (event) => {
      void handleRichPaste(event);
    });
    els.sourcePreviewBtn.addEventListener("click", () => {
      if (!state.sourceText.trim()) return;
      local.sourcePreview = !local.sourcePreview;
      renderTranslate();
    });
    els.pasteBtn.addEventListener("click", pasteIntoSource);
    els.copySourceBtn.addEventListener("click", copySourceText);
    els.clearSourceBtn.addEventListener("click", () => {
      local.sourcePreview = false;
      send("clear_source");
    });
    els.speakSourceBtn.addEventListener("click", () => speak("source"));
    els.speakResultBtn.addEventListener("click", () => speak("translation"));
    els.copyBtn.addEventListener("click", copyTranslation);
    els.againBtn.addEventListener("click", () => translateNow(true));
    els.translateNowBtn.addEventListener("click", () => translateNow(true));
    els.stopBtn.addEventListener("click", () => send("cancel"));
    els.retryBtn.addEventListener("click", () => translateNow(true));
    els.bannerRetry.addEventListener("click", () => translateNow(true));
    els.stopSpeaking.addEventListener("click", () => {
      send("stop_speaking");
      state.speaking = "";
      renderTranslate();
    });
    bindMarkdownLinks(els.resultView);

    // Files ---------------------------------------------------------------
    els.chooseFileBtn.addEventListener("click", pickFile);
    els.fileRetryBtn.addEventListener("click", pickFile);
    els.fileTryAgainBtn.addEventListener("click", retryFileTranslation);
    ["dragenter", "dragover"].forEach((name) => {
      els.dropZone.addEventListener(name, (event) => {
        event.preventDefault();
        event.stopPropagation();
        els.dropZone.classList.add("is-dragover");
      });
    });
    ["dragleave", "dragend"].forEach((name) => {
      els.dropZone.addEventListener(name, (event) => {
        event.preventDefault();
        els.dropZone.classList.remove("is-dragover");
      });
    });
    els.dropZone.addEventListener("drop", (event) => {
      event.preventDefault();
      event.stopPropagation();
      els.dropZone.classList.remove("is-dragover");
      const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
      if (!file) return;
      // Browsers hide filesystem paths; Tauri exposes file.path, and the native
      // tauri://drag-drop listener below is the authoritative source.
      const path = file.path || file.name;
      handleDroppedPath(path);
    });
    els.removeFileBtn.addEventListener("click", () => send("clear_file_job"));
    els.fileTarget.addEventListener("change", () => {
      // Scoped to the Files tab; the Translate tab keeps its own language.
      local.fileTarget = els.fileTarget.value;
    });
    els.translateFileBtn.addEventListener("click", () => {
      const job = state.fileJob;
      if (job && job.path) startFileTranslation(job.path, local.fileTarget);
    });
    els.cancelFileBtn.addEventListener("click", () => {
      send("cancel_file_translation");
      showToast(tr("Cancelled"));
    });
    els.saveFileBtn.addEventListener("click", saveTranslatedFile);
    els.showFolderBtn.addEventListener("click", revealFile);
    els.anotherFileBtn.addEventListener("click", () => send("clear_file_job"));

    // Write ---------------------------------------------------------------
    els.writeInput.addEventListener("input", () => {
      setWriteDraft(els.writeInput.value);
    });
    // Ctrl+Enter is handled once by the delegated document handler below.
    els.writeTarget.addEventListener("change", () => {
      local.writeTarget = els.writeTarget.value;
      local.writeTargetChosen = true;
      renderWrite();
    });
    els.improveBtn.addEventListener("click", improveText);
    els.cancelWriteBtn.addEventListener("click", cancelWrite);
    els.copyWriteBtn.addEventListener("click", copyWriteOutput);
    els.clearWriteBtn.addEventListener("click", () => {
      local.writeText = "";
      els.writeInput.value = "";
      local.writeBusy = false;
      local.writePending = false;
      local.writeStale = true;
      if (state.write.running || state.write.output || state.write.error) {
        send("cancel_write");
      }
      state.write.running = false;
      renderWrite();
    });
    els.writeViewSwitch.addEventListener("click", (event) => {
      const button = closest(event.target, "[data-view]");
      if (!button) return;
      local.writeView = button.getAttribute("data-view");
      setSegment(els.writeViewSwitch, "view", local.writeView);
      renderWrite();
    });
    bindMarkdownLinks(els.writeResultView);
    bindMarkdownLinks(els.sourcePreview);

    // History -------------------------------------------------------------
    els.historySearch.addEventListener("input", () => {
      local.historyQuery = els.historySearch.value;
      searchHistoryDebounced();
    });
    els.historyClearBtn.addEventListener("click", confirmClearHistory);
    els.confirmCancel.addEventListener("click", () => els.confirmDialog.close());
    els.confirmOk.addEventListener("click", clearHistory);
    els.historyList.addEventListener("click", (event) => {
      const row = closest(event.target, ".history-row");
      if (!row) return;
      const id = row.dataset.id;
      const actionButton = closest(event.target, "[data-action]");
      if (!actionButton) return;
      const action = actionButton.getAttribute("data-action");
      if (action === "restore") {
        send("load_history_entry", { id: id }).then(() => {
          selectTab("translate");
          scheduleRefresh(60);
        });
      } else if (action === "copy") {
        const entry = state.history.find((item) => item.id === id);
        if (entry) {
          send("copy_text", { text: entry.translatedText });
          showToast(tr("Copied"));
        }
      } else if (action === "delete") {
        send("history_delete", { id: id }).then(() => scheduleRefresh(50));
      }
    });

    bindSettings();
    bindCatalog();
    els.settingsBody.addEventListener("scroll", () => syncScrollFade(els.settingsBody));
    els.catalogBody.addEventListener("scroll", () => syncScrollFade(els.catalogBody));

    // Dialogs -------------------------------------------------------------
    [els.settingsDialog, els.catalogDialog, els.confirmDialog].forEach((dialog) => {
      if (!dialog) return;
      dialog.addEventListener("close", () => {
        dialogStackRemove(dialog);
        if (dialog === els.settingsDialog) {
          local.settingsDraft = null;
          local.settingsSnapshot = null;
            }
        syncModalState();
      });
      // Native Esc would close whichever <dialog> receives the event; the
      // document handler below closes the topmost one instead.
      dialog.addEventListener("cancel", (event) => {
        event.preventDefault();
        if (dialog === topDialog()) closeTopDialog();
      });
      dialog.addEventListener("click", (event) => {
        if (event.target !== dialog) return;
        if (dialog === els.settingsDialog) void cancelSettings();
        else dialog.close();
      });
    });

    // Global shortcuts ----------------------------------------------------
    document.addEventListener("keydown", (event) => {
      if (local.capture) return;
      if (event.defaultPrevented) return;
      if (event.isComposing || event.repeat) return;
      if (event.key === "Escape") {
        if (topDialog()) {
          event.preventDefault();
          closeTopDialog();
          return;
        }
        if (local.menuOpen) {
          toggleMenu(false);
          els.moreBtn.focus();
        }
        return;
      }
      // Never act on the page behind a modal dialog.
      if (topDialog()) return;
      const mod = event.ctrlKey || event.metaKey;
      if (!mod) return;
      const key = event.key;
      const lower = key.toLowerCase();
      const inField = isTextField(event.target);
      if (!event.shiftKey && key === "Enter") {
        event.preventDefault();
        if (state.tab === "translate") translateNow(true);
        else if (state.tab === "write") improveText();
        return;
      }
      if (!event.shiftKey && lower === "n" && !event.altKey) {
        event.preventDefault();
        if (!inField) newTranslation();
        return;
      }
      if (!event.shiftKey && lower === "o" && !event.altKey) {
        event.preventDefault();
        if (!inField) {
          selectTab("files");
          pickFile();
        }
        return;
      }
      if (!event.shiftKey && lower === "s" && !event.altKey) {
        event.preventDefault();
        const job = state.fileJob;
        if (job && job.state === "done" && job.output) saveTranslatedFile();
        return;
      }
      if (!event.shiftKey && !event.altKey && (key === "," || event.code === "Comma")) {
        event.preventDefault();
        openSettings("model");
        return;
      }
      if (event.shiftKey && lower === "c") {
        event.preventDefault();
        copyTranslation();
        return;
      }
      if (event.shiftKey && lower === "s") {
        event.preventDefault();
        send("swap_languages");
      }
    });
  }

  function bindMarkdownLinks(container) {
    container.addEventListener("click", (event) => {
      const anchor = closest(event.target, "a[href]");
      if (!anchor) return;
      event.preventDefault();
      const href = anchor.getAttribute("href") || "";
      if (/^(https?:|mailto:)/i.test(href)) openExternal(href);
    });
  }

  function toggleMenu(open) {
    local.menuOpen = !!open;
    if (local.menuOpen) renderMoreMenu();
    els.moreMenu.hidden = !local.menuOpen;
    els.moreBtn.setAttribute("aria-expanded", local.menuOpen ? "true" : "false");
  }

  /** The More menu reflects the hot keys from the current settings snapshot. */
  function renderMoreMenu() {
    const settings = state.settings || {};
    const clipboardKey =
      settings.hotKey && settings.hotKey.key ? comboDisplay(settings.hotKey) : "";
    const selectionKey =
      settings.selectionHotKey && settings.selectionHotKey.key
        ? comboDisplay(settings.selectionHotKey)
        : "";
    updateMenuItem("translate_clipboard", tr("Translate clipboard"), clipboardKey);
    updateMenuItem("translate_selection", tr("Translate selection"), selectionKey);
  }

  function updateMenuItem(command, label, shortcut) {
    const item = els.moreMenu.querySelector('[data-command="' + command + '"]');
    if (!item) return;
    const labelNode = item.querySelector(".menu-label");
    if (labelNode) labelNode.textContent = label;
    const keyNode = item.querySelector(".menu-key");
    if (keyNode) keyNode.textContent = shortcut || "";
    const full = shortcut ? label + " (" + shortcut + ")" : label;
    item.setAttribute("aria-label", full);
    item.setAttribute("title", full);
  }

  function bindSettings() {
    els.settingsTabs.addEventListener("click", (event) => {
      const button = closest(event.target, "[data-settings-tab]");
      if (button) selectSettingsTab(button.getAttribute("data-settings-tab"));
    });
    els.settingsTabs.addEventListener("keydown", (event) => {
      const buttons = Array.from(els.settingsTabs.querySelectorAll("[data-settings-tab]"));
      const index = buttons.indexOf(document.activeElement);
      if (index < 0) return;
      let next = index;
      if (event.key === "ArrowRight") next = (index + 1) % buttons.length;
      else if (event.key === "ArrowLeft") next = (index - 1 + buttons.length) % buttons.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = buttons.length - 1;
      else return;
      event.preventDefault();
      buttons[next].focus();
      selectSettingsTab(buttons[next].getAttribute("data-settings-tab"));
    });
    els.settingsCancel.addEventListener("click", () => {
      void cancelSettings();
    });
    els.settingsSave.addEventListener("click", saveSettings);
    els.connectBtn.addEventListener("click", connectProvider);
    els.fallbackLoadBtn.addEventListener("click", loadFallbackModels);

    els.providerSelect.addEventListener("change", () => {
      if (!local.settingsDraft) return;
      const previous = local.settingsDraft.provider;
      const next = els.providerSelect.value;
      const previousInfo = providerInfo(previous);
      const nextInfo = providerInfo(next);
      if (!els.baseUrlInput.value.trim() || els.baseUrlInput.value.trim() === previousInfo.baseUrl) {
        els.baseUrlInput.value = nextInfo.baseUrl;
      }
      local.settingsDraft.provider = next;
      local.settingsDraft.baseUrl = els.baseUrlInput.value.trim();
      // The API key belongs to the provider it was issued for.
      switchKeyField("primary", next);
      updateProviderDetails(local.settingsDraft);
      renderModels();
    });
    els.baseUrlInput.addEventListener("input", () => {
      if (local.settingsDraft) local.settingsDraft.baseUrl = els.baseUrlInput.value.trim();
    });
    els.apiKeyInput.addEventListener("input", () => {
      local.settingsKeyDirty = true;
      if (local.settingsDraft) local.settingsDraft.apiKey = els.apiKeyInput.value;
    });
    els.modelInput.addEventListener("input", () => {
      if (!local.settingsDraft) return;
      local.settingsDraft.model = els.modelInput.value.trim();
      renderModels();
      renderInstallHint();
    });
    els.installCopyBtn.addEventListener("click", () => {
      const command = els.installCommand.textContent || "";
      if (!command) return;
      send("copy_text", { text: command });
      showToast(tr("Copied"));
    });
    els.revealKeyBtn.addEventListener("click", () => {
      const revealed = els.apiKeyInput.type === "text";
      els.apiKeyInput.type = revealed ? "password" : "text";
      els.revealKeyBtn.textContent = revealed ? tr("Show") : tr("Hide");
    });
    els.keyLink.addEventListener("click", () => {
      const provider = providerInfo(els.providerSelect.value);
      if (provider.keyUrl) openExternal(provider.keyUrl);
    });
    els.catalogBtn.addEventListener("click", openCatalog);
    els.modelFilter.addEventListener("input", () => {
      local.modelFilter = els.modelFilter.value;
      renderModels();
    });
    els.modelList.addEventListener("click", (event) => {
      const button = closest(event.target, ".model-item");
      if (!button || !local.settingsDraft) return;
      local.settingsDraft.model = button.dataset.model || "";
      els.modelInput.value = local.settingsDraft.model;
      renderModels();
    });
    els.fallbackToggle.addEventListener("change", () => {
      if (!local.settingsDraft) return;
      local.settingsDraft.fallbackEnabled = els.fallbackToggle.checked;
      els.fallbackBody.hidden = !els.fallbackToggle.checked;
    });
    els.fallbackProviderSelect.addEventListener("change", () => {
      if (!local.settingsDraft) return;
      const previous = local.settingsDraft.fallbackProvider;
      const next = els.fallbackProviderSelect.value;
      const previousInfo = providerInfo(previous);
      const nextInfo = providerInfo(next);
      if (!els.fallbackBaseInput.value.trim() || els.fallbackBaseInput.value.trim() === previousInfo.baseUrl) {
        els.fallbackBaseInput.value = nextInfo.baseUrl;
      }
      local.settingsDraft.fallbackProvider = next;
      local.settingsDraft.fallbackBaseUrl = els.fallbackBaseInput.value.trim();
      // The fallback key has the same rule: it is the new provider's key, never
      // the previous provider's text.
      switchKeyField("fallback", next);
    });
    els.fallbackBaseInput.addEventListener("input", () => {
      if (local.settingsDraft) local.settingsDraft.fallbackBaseUrl = els.fallbackBaseInput.value.trim();
    });
    els.fallbackKeyInput.addEventListener("input", () => {
      local.settingsFallbackKeyDirty = true;
      if (local.settingsDraft) local.settingsDraft.fallbackApiKey = els.fallbackKeyInput.value;
    });
    els.fallbackModelInput.addEventListener("input", () => {
      if (local.settingsDraft) local.settingsDraft.fallbackModel = els.fallbackModelInput.value.trim();
    });

    const rangeBindings = [
      [els.temperatureRange, els.temperatureValue, "decimal", (v) => { local.settingsDraft.temperature = v; }],
      [els.topPRange, els.topPValue, "decimal", (v) => { local.settingsDraft.topP = v; }],
      [els.topKRange, els.topKValue, "integer", (v) => { local.settingsDraft.topK = v; }],
      [els.repetitionRange, els.repetitionValue, "decimal", (v) => { local.settingsDraft.repetitionPenalty = v; }],
      [els.contextRange, els.contextValue, "thousands", (v) => { local.settingsDraft.contextWindow = v; }],
      [els.debounceRange, els.debounceValue, "seconds", (v) => { local.settingsDraft.debounce = v; }],
    ];
    rangeBindings.forEach(([range, output, format, apply]) => {
      range.addEventListener("input", () => {
        const value = Number(range.value);
        output.textContent = formatRangeValue(range, format);
        updateRangeFill(range);
        if (local.settingsDraft) apply(value);
      });
    });

    els.autoTranslateToggle.addEventListener("change", () => {
      if (!local.settingsDraft) return;
      local.settingsDraft.autoTranslate = els.autoTranslateToggle.checked;
      els.debounceRange.disabled = !els.autoTranslateToggle.checked;
      els.debounceRow.setAttribute("aria-disabled", els.debounceRange.disabled ? "true" : "false");
    });
    els.keepHistoryToggle.addEventListener("change", () => {
      if (local.settingsDraft) local.settingsDraft.keepHistory = els.keepHistoryToggle.checked;
    });
    els.loginItemToggle.addEventListener("change", () => {
      void setLoginItem(els.loginItemToggle.checked);
    });
    els.loginItemSettings.addEventListener("click", () => {
      send("open_login_item_settings");
    });
    els.warmUpToggle.addEventListener("change", () => {
      if (local.settingsDraft) local.settingsDraft.warmUpOnLaunch = els.warmUpToggle.checked;
    });
    els.trayToggle.addEventListener("change", () => {
      if (local.settingsDraft) local.settingsDraft.showInMenuBar = els.trayToggle.checked;
    });
    els.interfaceLanguageSelect.addEventListener("change", () => {
      if (local.settingsDraft) local.settingsDraft.interfaceLanguage = els.interfaceLanguageSelect.value;
    });
    els.voiceSelect.addEventListener("change", () => {
      if (local.settingsDraft) local.settingsDraft.speechVoiceId = els.voiceSelect.value;
    });

    els.promptStyleChips.addEventListener("click", (event) => {
      const button = closest(event.target, "[data-style]");
      if (!button) return;
      local.promptStyle = button.getAttribute("data-style");
      setSegment(els.promptStyleChips, "style", local.promptStyle);
      refreshPromptPreview();
    });
    els.promptToneChips.addEventListener("click", (event) => {
      const button = closest(event.target, "[data-tone]");
      if (!button) return;
      local.promptTone = button.getAttribute("data-tone");
      setSegment(els.promptToneChips, "tone", local.promptTone);
      refreshPromptPreview();
    });
    els.promptTarget.addEventListener("change", () => {
      local.promptTarget = els.promptTarget.value;
      refreshPromptPreview();
    });

    els.hotkeyStandard.addEventListener("click", () => startCapture("standard"));
    els.hotkeySelection.addEventListener("click", () => startCapture("selection"));
    els.resetHotkey.addEventListener("click", () => {
      if (!local.settingsDraft) return;
      local.settingsDraft.hotKey = { key: "t", ctrl: true, alt: true, shift: false, meta: false };
      els.hotkeyStandard.dataset.combo = JSON.stringify(local.settingsDraft.hotKey);
      els.hotkeyStandard.textContent = comboDisplay(local.settingsDraft.hotKey);
    });
    els.resetSelectionHotkey.addEventListener("click", () => {
      if (!local.settingsDraft) return;
      local.settingsDraft.selectionHotKey = { key: "c", ctrl: true, alt: true, shift: false, meta: false };
      els.hotkeySelection.dataset.combo = JSON.stringify(local.settingsDraft.selectionHotKey);
      els.hotkeySelection.textContent = comboDisplay(local.settingsDraft.selectionHotKey);
    });

    document.querySelectorAll("[data-url]").forEach((button) => {
      button.addEventListener("click", () => openExternal(button.getAttribute("data-url")));
    });
  }

  function bindCatalog() {
    els.catalogClose.addEventListener("click", () => els.catalogDialog.close());
    els.catalogProvider.addEventListener("change", () => {
      local.catalogProvider = els.catalogProvider.value;
      renderCatalog();
    });
    els.catalogFree.addEventListener("change", () => {
      local.catalogFree = els.catalogFree.checked;
      renderCatalog();
    });
    els.catalogSearch.addEventListener("input", () => {
      local.catalogFilter = els.catalogSearch.value;
      renderCatalog();
    });
    els.catalogFetch.addEventListener("click", fetchServerModels);
    els.catalogBody.addEventListener("click", (event) => {
      const copy = closest(event.target, "[data-copy-command]");
      if (copy) {
        send("copy_text", { text: copy.getAttribute("data-copy-command") });
        showToast(tr("Copied"));
        return;
      }
      const use = closest(event.target, "[data-use-model]");
      if (use) {
        useCatalogModel(use.getAttribute("data-use-model"), use.getAttribute("data-provider"));
      }
    });
  }

  /* ---------------------------------------------------------- setup / entry */

  function applyHashRoute() {
    const hash = String(location.hash || "").replace(/^#/, "");
    if (!hash) return;
    if (hash === "catalog") {
      openCatalog();
      return;
    }
    if (hash === "menu") {
      toggleMenu(true);
      return;
    }
    if (hash === "source-preview" || hash === "source-markdown-preview") {
      local.sourcePreview = true;
      renderTranslate();
      return;
    }
    if (hash === "settings" || hash.indexOf("settings-") === 0) {
      const tab = hash.indexOf("settings-") === 0 ? hash.slice("settings-".length) : "model";
      openSettings(SETTINGS_TABS.includes(tab) ? tab : "model");
      return;
    }
    if (TABS.includes(hash)) {
      if (MOCK) state.tab = hash;
      renderTabs();
    }
  }

  /** Apply `get_startup()` once, after the first state snapshot. */
  async function applyStartup() {
    if (local.startupApplied) return;
    local.startupApplied = true;
    let startup = null;
    try {
      startup = await invoke("get_startup");
    } catch (error) {
      return;
    }
    if (!startup || typeof startup !== "object") return;
    if (startup.catalog) openCatalog();
    if (typeof startup.writeText === "string" && startup.writeText.length > 0) {
      // A draft given on the command line takes the same path as a pasted one:
      // the stale-result reset, the cancellation of an older rewrite and the
      // "detect the draft's language" default all run.
      local.writeTargetChosen = false;
      local.writeTarget = "";
      selectTab("write");
      setWriteDraft(startup.writeText, { focus: true });
    }
    if (startup.tab && TABS.includes(String(startup.tab))) {
      selectTab(String(startup.tab));
    }
  }

  function applyTheme() {
    const params = new URLSearchParams(location.search);
    const theme = params.get("theme");
    if (theme === "dark" || theme === "light") {
      document.documentElement.dataset.theme = theme;
    }
    // Deterministic screenshots: ?still=1 removes entrance animations.
    if (params.has("still")) {
      document.documentElement.dataset.motion = "off";
    }
  }


  function listenNativeDrop() {
    if (!NATIVE || !window.__TAURI__.event || typeof window.__TAURI__.event.listen !== "function") {
      return;
    }
    window.__TAURI__.event
      .listen("tauri://drag-drop", (event) => {
        const payload = event && event.payload ? event.payload : {};
        const paths = Array.isArray(payload.paths) ? payload.paths : [];
        if (paths.length) handleDroppedPath(paths[0]);
      })
      .catch(() => {});
    ["tauri://drag-enter", "tauri://drag-over"].forEach((name) => {
      window.__TAURI__.event.listen(name, () => els.dropZone.classList.add("is-dragover")).catch(() => {});
    });
    window.__TAURI__.event
      .listen("tauri://drag-leave", () => els.dropZone.classList.remove("is-dragover"))
      .catch(() => {});
  }

  /** Fetch the active language catalogue and repaint the UI. */
  async function refreshCatalogue(force) {
    const language = state.settings.interfaceLanguage || "system";
    if (!force && local.catalogue && local.catalogueLang === language) return;
    const request = ++local.catalogueRequest;
    let map = {};
    try {
      const value = await invoke("get_translations");
      if (value && typeof value === "object" && !Array.isArray(value)) map = value;
    } catch (error) {
      // English from strings.js is still a complete fallback.
      map = {};
    }
    if (request !== local.catalogueRequest) return;
    local.catalogue = map;
    local.catalogueLang = language;
    document.documentElement.lang = uiLanguageCode();
    localize();
  }

  async function loadVoices() {
    try {
      const voices = await invoke("list_voices");
      if (!Array.isArray(voices)) return;
      local.voices = voices
        .map((voice) => {
          if (Array.isArray(voice)) return { id: String(voice[0] || ""), label: String(voice[1] || voice[0] || "") };
          if (!voice || typeof voice !== "object") return { id: "", label: "" };
          const id = String(voice.id || voice.name || "");
          return { id: id, label: String(voice.label || voice.name || id) };
        })
        .filter((voice) => voice.id);
      updateVoiceOptions();
      if (local.settingsDraft) els.voiceSelect.value = local.settingsDraft.speechVoiceId || "";
    } catch (error) {
      /* Speech is optional; the platform may not report any voices. */
    }
  }

  async function init() {
    cacheElements();
    applyTheme();
    buildStaticOptions();
    localize();
    observeTranslateBar();
    bindEvents();
    listenNativeDrop();
    subscribe(handleEvent);
    void loadVoices();

    try {
      await loadState();
    } catch (error) {
      showToast(errorText(error));
    }
    await refreshCatalogue();
    void ensureCatalogEntries();
    local.firstStateLoaded = true;
    // WriteState has no `text` field (the draft lives only in the webview), so
    // the standalone demo seeds the editor from the mock instead of AppState.
    if (!local.writeText && !NATIVE && MOCK && typeof MOCK.writeDraft === "string") {
      local.writeText = MOCK.writeDraft;
    }
    if (!local.fileTarget) local.fileTarget = defaultFileTarget();
    render();
    applyHashRoute();
    render();
    // Command-line actions come from Rust after the first snapshot. The other
    // flags are already applied before the webview loads. Startup wins over the
    // standalone hash scenario.
    await applyStartup();
    render();
    focusInitialEditor();

    // Expose a tiny hook so the Rust shell (or a translator) can inject a
    // different interface table without reloading the page.
    window.OFM_UI = {
      relocalize: localize,
      openSettings: openSettings,
      openCatalog: openCatalog,
      currentState: () => state,
      writeDraft: () => ({
        text: local.writeText,
        target: local.writeTarget,
        chosen: local.writeTargetChosen,
        select: els.writeTarget.value,
        stale: local.writeStale,
        preview: local.sourcePreview,
      }),
      // Exposed so tests (and the shell) can verify the renderer in isolation.
      renderMarkdown: (text) => renderMarkdown(text),
      markdownToPlain: (text) => markdownToPlain(text),
    };
  }

  /* ------------------------------------------------------------- markdown */

  const MD_ESCAPES = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };

  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value).replace(
      /[&<>"']/g,
      (character) => MD_ESCAPES[character]
    );
  }

  function decodeEntities(value) {
    return String(value)
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'");
  }

  function safeHref(raw) {
    const url = decodeEntities(String(raw || "")).trim();
    if (!url) return null;
    if (/^(https?:|mailto:)/i.test(url)) return url;
    if (/^(#|\/|\.\/|\.\.\/)/.test(url)) return url;
    return null;
  }

  function renderInline(source) {
    const protectedHtml = [];
    const protect = (html) => {
      protectedHtml.push(html);
      return "\u0000" + (protectedHtml.length - 1) + "\u0000";
    };
    let text = escapeHtml(source);

    text = text.replace(/`([^`\n]+)`/g, (match, code) => protect("<code>" + code + "</code>"));

    text = text.replace(
      /\[([^\]\n]+)\]\(((?:[^()\s]|\([^()\s]*\))*)(?:\s+&quot;[^&]*&quot;)?\)/g,
      (match, label, url) => {
        const href = safeHref(url);
        if (!href) return label;
        return protect(
          '<a href="' +
            escapeHtml(href) +
            '" target="_blank" rel="noreferrer noopener">' +
            label +
            "</a>"
        );
      }
    );

    text = text.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/__([^_\n]+)__/g, "<strong>$1</strong>");
    text = text.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    text = text.replace(/(^|[^_\w])_([^_\n]+)_/g, "$1<em>$2</em>");
    text = text.replace(/\n/g, "<br>");

    return text.replace(/\u0000(\d+)\u0000/g, (match, index) => protectedHtml[Number(index)] || "");
  }

  function indentWidth(line) {
    let width = 0;
    for (const character of line) {
      if (character === " ") width += 1;
      else if (character === "\t") width += 4;
      else break;
    }
    return width;
  }

  function parseBlocks(source) {
    const lines = String(source === null || source === undefined ? "" : source)
      .replace(/\r\n?/g, "\n")
      .split("\n");
    const blocks = [];
    const fenceRe = /^ {0,3}(`{3,}|~{3,})(.*)$/;
    const headingRe = /^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$/;
    const quoteRe = /^ {0,3}>[ \t]?(.*)$/;
    const ulRe = /^(\s*)[-*+][ \t]+(.*)$/;
    const olRe = /^(\s*)(\d{1,9})[.)][ \t]+(.*)$/;
    const hrRe = /^ {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$/;

    const startsBlock = (line) =>
      fenceRe.test(line) ||
      headingRe.test(line) ||
      quoteRe.test(line) ||
      ulRe.test(line) ||
      olRe.test(line) ||
      hrRe.test(line);

    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (!line.trim()) {
        i += 1;
        continue;
      }

      const fence = fenceRe.exec(line);
      if (fence) {
        const marker = fence[1][0];
        const length = fence[1].length;
        const language = (fence[2] || "").trim().split(/\s+/)[0] || "";
        i += 1;
        const codeLines = [];
        const closeRe = new RegExp("^\\s*" + (marker === "`" ? "`" : "~") + "{" + length + ",}\\s*$");
        while (i < lines.length) {
          if (closeRe.test(lines[i])) {
            i += 1;
            break;
          }
          codeLines.push(lines[i]);
          i += 1;
        }
        blocks.push({ type: "code", text: codeLines.join("\n"), language: language });
        continue;
      }

      const heading = headingRe.exec(line);
      if (heading) {
        blocks.push({ type: "heading", level: heading[1].length, text: heading[2].trim() });
        i += 1;
        continue;
      }

      if (hrRe.test(line)) {
        blocks.push({ type: "hr" });
        i += 1;
        continue;
      }

      if (quoteRe.test(line)) {
        const quoted = [];
        while (i < lines.length) {
          const match = quoteRe.exec(lines[i]);
          if (!match) break;
          quoted.push(match[1]);
          i += 1;
        }
        blocks.push({ type: "quote", children: parseBlocks(quoted.join("\n")) });
        continue;
      }

      const unordered = ulRe.exec(line);
      const ordered = olRe.exec(line);
      if (unordered || ordered) {
        const isOrdered = !!ordered;
        const base = indentWidth((ordered || unordered)[1] || "");
        const start = ordered ? Number(ordered[2]) : 1;
        const items = [];
        while (i < lines.length) {
          const current = isOrdered ? olRe.exec(lines[i]) : ulRe.exec(lines[i]);
          if (!current) break;
          const indent = indentWidth(current[1] || "");
          if (indent !== base) break;
          let content = isOrdered ? current[3] : current[2];
          i += 1;
          const continuation = [];
          while (i < lines.length) {
            const candidate = lines[i];
            if (!candidate.trim()) {
              if (i + 1 < lines.length && indentWidth(lines[i + 1]) > base) {
                continuation.push("");
                i += 1;
                continue;
              }
              break;
            }
            if (indentWidth(candidate) > base) {
              continuation.push(candidate.trim());
              i += 1;
              continue;
            }
            break;
          }
          if (continuation.length) content += "\n" + continuation.join("\n");
          items.push(content);
          if (i < lines.length && !lines[i].trim()) {
            const lookahead = lines[i + 1] || "";
            const next = isOrdered ? olRe.exec(lookahead) : ulRe.exec(lookahead);
            if (next && indentWidth(lookahead) === base) {
              i += 1;
              continue;
            }
            break;
          }
        }
        blocks.push({ type: "list", ordered: isOrdered, start: start, items: items });
        continue;
      }

      const paragraph = [];
      while (i < lines.length && lines[i].trim() && !startsBlock(lines[i])) {
        paragraph.push(lines[i].trim());
        i += 1;
      }
      if (paragraph.length) {
        blocks.push({ type: "paragraph", text: paragraph.join("\n") });
      } else {
        // Defensive: never spin on a block marker that was not handled.
        blocks.push({ type: "paragraph", text: lines[i].trim() });
        i += 1;
      }
    }
    return blocks;
  }

  function renderBlocks(blocks) {
    return blocks
      .map((block) => {
        switch (block.type) {
          case "heading": {
            const level = Math.min(6, Math.max(1, block.level));
            return "<h" + level + ">" + renderInline(block.text) + "</h" + level + ">";
          }
          case "paragraph":
            return "<p>" + renderInline(block.text) + "</p>";
          case "code": {
            const language = String(block.language || "")
              .toLowerCase()
              .replace(/[^a-z0-9+#._-]/g, "");
            return (
              "<pre><code" +
              (language ? ' class="language-' + language + '"' : "") +
              ">" +
              escapeHtml(block.text) +
              "</code></pre>"
            );
          }
          case "quote":
            return "<blockquote>" + renderBlocks(block.children) + "</blockquote>";
          case "list": {
            const tag = block.ordered ? "ol" : "ul";
            const start = block.ordered && block.start !== 1 ? ' start="' + block.start + '"' : "";
            return (
              "<" +
              tag +
              start +
              ">" +
              block.items.map((item) => "<li>" + renderInline(item) + "</li>").join("") +
              "</" +
              tag +
              ">"
            );
          }
          case "hr":
            return "<hr>";
          default:
            return "";
        }
      })
      .join("");
  }

  function stripInline(text) {
    return String(text)
      .replace(/`([^`]+)`/g, "$1")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
      .replace(/(\*\*|__)(.*?)\1/g, "$2")
      .replace(/(^|[^*])\*([^*]+)\*/g, "$1$2")
      .replace(/(^|[^_\w])_([^_]+)_/g, "$1$2")
      .trim();
  }

  function blocksToPlain(blocks) {
    const out = [];
    blocks.forEach((block) => {
      switch (block.type) {
        case "heading":
        case "paragraph":
          out.push(stripInline(block.text));
          break;
        case "code":
          out.push(block.text);
          break;
        case "quote":
          out.push(blocksToPlain(block.children));
          break;
        case "list": {
          const lines = block.items.map((item, index) => {
            const prefix = block.ordered ? String(block.start + index) + ". " : "• ";
            return prefix + stripInline(item.replace(/\n/g, " "));
          });
          out.push(lines.join("\n"));
          break;
        }
        case "hr":
          break;
        default:
          break;
      }
    });
    return out.filter((item) => item.length).join("\n\n");
  }

  function renderMarkdown(text) {
    return renderBlocks(parseBlocks(text));
  }

  function markdownToPlain(text) {
    return blocksToPlain(parseBlocks(text));
  }

  /* ---------------------------------------------------------------- start */

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
