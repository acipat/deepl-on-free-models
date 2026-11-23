//! Providers, wire protocols and backend configuration.
//!
//! Ported from `windows/deepl_ofm/core/providers.py` (itself a port of
//! `Sources/HyMT/Models/Provider.swift` and `BackendConfig.swift`). The English
//! `detail` sentences double as i18n keys: [`Provider::detail_key`] returns them
//! verbatim and [`Provider::detail`] resolves them through `ofm-i18n`.

use serde::{Deserialize, Deserializer, Serialize, Serializer};

/// Wire protocol used to talk to a provider.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum BackendKind {
    /// Ollama's native `/api/chat` protocol.
    Ollama,
    /// OpenAI-compatible `/chat/completions` protocol.
    OpenAI,
}

impl BackendKind {
    /// Stored representation, matching the Python enum values.
    pub fn value(self) -> &'static str {
        match self {
            BackendKind::Ollama => "ollama",
            BackendKind::OpenAI => "openAI",
        }
    }

    /// Base URL used when a provider has none configured.
    pub fn default_base_url(self) -> &'static str {
        match self {
            BackendKind::Ollama => "http://127.0.0.1:11434",
            BackendKind::OpenAI => "http://127.0.0.1:1234/v1",
        }
    }

    /// Tolerant lookup for stored values (case-insensitive, trimmed).
    ///
    /// Mirrors `BackendKind.from_stored`; returns `None` for anything unknown.
    pub fn from_stored(value: &str) -> Option<Self> {
        let text = value.trim();
        if text.is_empty() {
            return None;
        }
        if text.eq_ignore_ascii_case(Self::Ollama.value()) {
            Some(Self::Ollama)
        } else if text.eq_ignore_ascii_case(Self::OpenAI.value()) {
            Some(Self::OpenAI)
        } else {
            None
        }
    }
}

impl Serialize for BackendKind {
    /// Serialises as the stored value (`"ollama"`, `"openAI"`).
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_str(self.value())
    }
}

impl<'de> Deserialize<'de> for BackendKind {
    /// Accepts any spelling [`BackendKind::from_stored`] understands.
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let raw = String::deserialize(deserializer)?;
        BackendKind::from_stored(&raw)
            .ok_or_else(|| serde::de::Error::unknown_variant(&raw, &["ollama", "openAI"]))
    }
}

/// A place a model can run.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Provider {
    /// A local Ollama server.
    Ollama,
    /// Ollama Cloud through a direct API key.
    OllamaCloud,
    /// LM Studio's local server.
    LmStudio,
    /// An MLX server for Apple Silicon.
    Omlx,
    /// `llama-server --api`.
    LlamaCpp,
    /// OpenRouter's model marketplace.
    OpenRouter,
    /// Groq's cloud.
    Groq,
    /// Cerebras' cloud.
    Cerebras,
    /// Any OpenAI-compatible endpoint.
    Custom,
}

impl Provider {
    /// English display name; localised at the call site with `t(title)`.
    pub fn title(self) -> &'static str {
        match self {
            Provider::Ollama => "Ollama",
            Provider::OllamaCloud => "Ollama Cloud",
            Provider::LmStudio => "LM Studio",
            Provider::Omlx => "oMLX",
            Provider::LlamaCpp => "llama.cpp",
            Provider::OpenRouter => "OpenRouter",
            Provider::Groq => "Groq",
            Provider::Cerebras => "Cerebras",
            Provider::Custom => "Custom",
        }
    }

    /// Default server address for the provider.
    pub fn base_url(self) -> &'static str {
        match self {
            Provider::Ollama => "http://127.0.0.1:11434",
            Provider::OllamaCloud => "https://ollama.com/v1",
            Provider::LmStudio => "http://127.0.0.1:1234/v1",
            Provider::Omlx => "http://127.0.0.1:50220/v1",
            Provider::LlamaCpp => "http://127.0.0.1:8080/v1",
            Provider::OpenRouter => "https://openrouter.ai/api/v1",
            Provider::Groq => "https://api.groq.com/openai/v1",
            Provider::Cerebras => "https://api.cerebras.ai/v1",
            Provider::Custom => "http://127.0.0.1:1234/v1",
        }
    }

    /// Wire protocol spoken by the provider.
    pub fn kind(self) -> BackendKind {
        match self {
            Provider::Ollama => BackendKind::Ollama,
            _ => BackendKind::OpenAI,
        }
    }

    /// True when the model normally runs on this machine.
    pub fn is_local(self) -> bool {
        matches!(
            self,
            Provider::Ollama | Provider::LmStudio | Provider::Omlx | Provider::LlamaCpp
        )
    }

    /// True when an API key is mandatory.
    pub fn requires_key(self) -> bool {
        matches!(
            self,
            Provider::OllamaCloud | Provider::OpenRouter | Provider::Groq | Provider::Cerebras
        )
    }

    /// Where the user can create an API key, when the provider needs one.
    pub fn key_url(self) -> Option<&'static str> {
        match self {
            Provider::OllamaCloud => Some("https://ollama.com/settings/keys"),
            Provider::OpenRouter => Some("https://openrouter.ai/keys"),
            Provider::Groq => Some("https://console.groq.com/keys"),
            Provider::Cerebras => Some("https://cloud.cerebras.ai"),
            _ => None,
        }
    }

    /// Account name used by `ofm_store::SecretStore`: `provider:<value>`.
    pub fn key_account(self) -> String {
        format!("provider:{}", self.value())
    }

    /// English sentence describing the provider (an i18n key).
    pub fn detail_key(self) -> &'static str {
        match self {
            Provider::Ollama => "Local Ollama server. The model must be pulled with ollama pull.",
            Provider::OllamaCloud => {
                "Ollama Cloud through a direct API key. No local server is needed."
            }
            Provider::LmStudio => {
                "LM Studio with its local server enabled. The model ID is shown in LM Studio."
            }
            Provider::Omlx => {
                "oMLX — an MLX server for Apple Silicon. Enable the OpenAI-compatible API."
            }
            Provider::LlamaCpp => "llama-server with --api. The default address is port 8080.",
            Provider::OpenRouter => {
                "Hundreds of models with one key. Free models are marked :free."
            }
            Provider::Groq => "Very fast cloud. Has a free tier with request limits.",
            Provider::Cerebras => "Fastest inference for open models. Has a free tier with limits.",
            Provider::Custom => {
                "Any OpenAI-compatible server: your proxy, vLLM, LocalAI, Together, and so on."
            }
        }
    }

    /// Localised description shown under the provider button.
    pub fn detail(self) -> String {
        ofm_i18n::t_in(self.detail_key(), ofm_i18n::current_language()).to_string()
    }

    /// Stored representation, matching the Python/Swift raw values.
    pub fn value(self) -> &'static str {
        match self {
            Provider::Ollama => "ollama",
            Provider::OllamaCloud => "ollamaCloud",
            Provider::LmStudio => "lmStudio",
            Provider::Omlx => "omlx",
            Provider::LlamaCpp => "llamaCpp",
            Provider::OpenRouter => "openRouter",
            Provider::Groq => "groq",
            Provider::Cerebras => "cerebras",
            Provider::Custom => "custom",
        }
    }

    /// Tolerant lookup accepting raw values, variant names and display titles.
    pub fn from_value(value: &str) -> Option<Self> {
        let key = alias_key(value);
        if key.is_empty() {
            return None;
        }
        Provider::all().iter().copied().find(|provider| {
            alias_key(provider.value()) == key
                || alias_key(provider.variant_name()) == key
                || alias_key(provider.title()) == key
        })
    }

    /// Every provider in the order used by the UI.
    pub fn all() -> &'static [Provider] {
        &[
            Provider::Ollama,
            Provider::OllamaCloud,
            Provider::LmStudio,
            Provider::Omlx,
            Provider::LlamaCpp,
            Provider::OpenRouter,
            Provider::Groq,
            Provider::Cerebras,
            Provider::Custom,
        ]
    }

    /// Guess the provider from the backend kind and the configured URL.
    ///
    /// The order of the checks matters: cloud host names win over the local
    /// port heuristics, and an Ollama backend is always plain Ollama unless the
    /// URL points at `ollama.com`.
    pub fn infer(kind: BackendKind, base_url: &str) -> Provider {
        let value = base_url.to_lowercase();
        if value.contains("ollama.com") {
            return Provider::OllamaCloud;
        }
        if kind == BackendKind::Ollama {
            return Provider::Ollama;
        }
        if value.contains("openrouter.ai") {
            return Provider::OpenRouter;
        }
        if value.contains("api.groq.com") {
            return Provider::Groq;
        }
        if value.contains("cerebras.ai") {
            return Provider::Cerebras;
        }
        if value.contains(":1234") {
            return Provider::LmStudio;
        }
        if value.contains(":50220") {
            return Provider::Omlx;
        }
        if value.contains(":8080") {
            return Provider::LlamaCpp;
        }
        Provider::Custom
    }

    /// Rust variant name, accepted as an extra spelling by [`Provider::from_value`].
    fn variant_name(self) -> &'static str {
        match self {
            Provider::Ollama => "Ollama",
            Provider::OllamaCloud => "OllamaCloud",
            Provider::LmStudio => "LmStudio",
            Provider::Omlx => "Omlx",
            Provider::LlamaCpp => "LlamaCpp",
            Provider::OpenRouter => "OpenRouter",
            Provider::Groq => "Groq",
            Provider::Cerebras => "Cerebras",
            Provider::Custom => "Custom",
        }
    }
}

impl Serialize for Provider {
    /// Serialises as the stored value (`"ollama"`, `"ollamaCloud"`, …).
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_str(self.value())
    }
}

impl<'de> Deserialize<'de> for Provider {
    /// Accepts any spelling [`Provider::from_value`] understands.
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let raw = String::deserialize(deserializer)?;
        Provider::from_value(&raw).ok_or_else(|| {
            serde::de::Error::unknown_variant(
                &raw,
                &[
                    "ollama",
                    "ollamaCloud",
                    "lmStudio",
                    "omlx",
                    "llamaCpp",
                    "openRouter",
                    "groq",
                    "cerebras",
                    "custom",
                ],
            )
        })
    }
}

/// Normalise a stored provider spelling for comparison: drop whitespace,
/// underscores and hyphens, then lower-case.
fn alias_key(value: &str) -> String {
    value
        .chars()
        .filter(|character| !character.is_whitespace() && *character != '_' && *character != '-')
        .flat_map(char::to_lowercase)
        .collect()
}

/// Everything a request needs: endpoint, model, credentials and sampling.
#[derive(Clone, Debug, PartialEq)]
pub struct BackendConfig {
    /// Wire protocol spoken by the endpoint.
    pub kind: BackendKind,
    /// Configured server address (not normalised; see [`Self::compatible_base`]).
    pub base_url: String,
    /// Model identifier sent to the server.
    pub model: String,
    /// Bearer token, empty when the endpoint is unauthenticated.
    pub api_key: String,
    /// Sampling temperature.
    pub temperature: f32,
    /// Nucleus sampling probability.
    pub top_p: f32,
    /// Top-K sampling cut-off.
    pub top_k: u32,
    /// Repetition penalty passed to Ollama.
    pub repetition_penalty: f32,
    /// Context window size in tokens.
    pub context_window: u32,
    /// True when the provider rejects unauthenticated requests.
    pub requires_api_key: bool,
}

impl Default for BackendConfig {
    fn default() -> Self {
        Self {
            kind: BackendKind::Ollama,
            base_url: Provider::Ollama.base_url().to_string(),
            model: String::new(),
            api_key: String::new(),
            temperature: 0.7,
            top_p: 0.6,
            top_k: 20,
            repetition_penalty: 1.05,
            context_window: 8192,
            requires_api_key: false,
        }
    }
}

impl BackendConfig {
    /// Base URL without trailing slashes, falling back to the kind default.
    pub fn compatible_base(&self) -> String {
        let mut value = self.base_url.trim().to_string();
        while value.ends_with('/') {
            value.pop();
        }
        if value.is_empty() {
            self.kind.default_base_url().to_string()
        } else {
            value
        }
    }

    /// True when two configs address the same endpoint (Swift parity helper).
    pub fn uses_same_endpoint(&self, other: &Self) -> bool {
        self.kind == other.kind
            && self.base_url == other.base_url
            && self.model == other.model
            && self.api_key == other.api_key
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ofm_i18n::AppLanguage;

    #[test]
    fn provider_values_match_swift_raw_values() {
        let values: Vec<&str> = Provider::all()
            .iter()
            .map(|provider| provider.value())
            .collect();
        assert_eq!(
            values,
            [
                "ollama",
                "ollamaCloud",
                "lmStudio",
                "omlx",
                "llamaCpp",
                "openRouter",
                "groq",
                "cerebras",
                "custom",
            ]
        );
        assert_eq!(Provider::all().len(), 9);
    }

    #[test]
    fn provider_titles() {
        assert_eq!(Provider::Ollama.title(), "Ollama");
        assert_eq!(Provider::OllamaCloud.title(), "Ollama Cloud");
        assert_eq!(Provider::LmStudio.title(), "LM Studio");
        assert_eq!(Provider::Omlx.title(), "oMLX");
        assert_eq!(Provider::LlamaCpp.title(), "llama.cpp");
        assert_eq!(Provider::OpenRouter.title(), "OpenRouter");
        assert_eq!(Provider::Groq.title(), "Groq");
        assert_eq!(Provider::Cerebras.title(), "Cerebras");
        assert_eq!(Provider::Custom.title(), "Custom");
    }

    #[test]
    fn provider_base_urls() {
        assert_eq!(Provider::Ollama.base_url(), "http://127.0.0.1:11434");
        assert_eq!(Provider::OllamaCloud.base_url(), "https://ollama.com/v1");
        assert_eq!(Provider::LmStudio.base_url(), "http://127.0.0.1:1234/v1");
        assert_eq!(Provider::Omlx.base_url(), "http://127.0.0.1:50220/v1");
        assert_eq!(Provider::LlamaCpp.base_url(), "http://127.0.0.1:8080/v1");
        assert_eq!(
            Provider::OpenRouter.base_url(),
            "https://openrouter.ai/api/v1"
        );
        assert_eq!(Provider::Groq.base_url(), "https://api.groq.com/openai/v1");
        assert_eq!(Provider::Cerebras.base_url(), "https://api.cerebras.ai/v1");
        assert_eq!(Provider::Custom.base_url(), "http://127.0.0.1:1234/v1");
    }

    #[test]
    fn backend_kinds() {
        assert_eq!(Provider::Ollama.kind(), BackendKind::Ollama);
        for provider in Provider::all() {
            if *provider != Provider::Ollama {
                assert_eq!(provider.kind(), BackendKind::OpenAI);
            }
        }
    }

    #[test]
    fn locality_and_key_requirements() {
        let local: Vec<Provider> = Provider::all()
            .iter()
            .copied()
            .filter(|provider| provider.is_local())
            .collect();
        assert_eq!(
            local,
            [
                Provider::Ollama,
                Provider::LmStudio,
                Provider::Omlx,
                Provider::LlamaCpp,
            ]
        );
        let keyed: Vec<Provider> = Provider::all()
            .iter()
            .copied()
            .filter(|provider| provider.requires_key())
            .collect();
        assert_eq!(
            keyed,
            [
                Provider::OllamaCloud,
                Provider::OpenRouter,
                Provider::Groq,
                Provider::Cerebras,
            ]
        );
        assert!(!Provider::Custom.requires_key());
        assert!(!Provider::Custom.is_local());
    }

    #[test]
    fn key_url_and_account() {
        assert_eq!(
            Provider::OpenRouter.key_url(),
            Some("https://openrouter.ai/keys")
        );
        assert_eq!(
            Provider::Groq.key_url(),
            Some("https://console.groq.com/keys")
        );
        assert_eq!(
            Provider::Cerebras.key_url(),
            Some("https://cloud.cerebras.ai")
        );
        assert_eq!(
            Provider::OllamaCloud.key_url(),
            Some("https://ollama.com/settings/keys")
        );
        assert_eq!(Provider::Ollama.key_url(), None);
        assert_eq!(Provider::Groq.key_account(), "provider:groq");
        assert_eq!(Provider::OllamaCloud.key_account(), "provider:ollamaCloud");
    }

    #[test]
    fn detail_returns_english_translation_key() {
        assert_eq!(
            Provider::Ollama.detail(),
            "Local Ollama server. The model must be pulled with ollama pull."
        );
        assert_eq!(
            Provider::OpenRouter.detail(),
            "Hundreds of models with one key. Free models are marked :free."
        );
        assert_eq!(
            Provider::Custom.detail_key(),
            "Any OpenAI-compatible server: your proxy, vLLM, LocalAI, Together, and so on."
        );
        assert_eq!(
            ofm_i18n::t_in(Provider::Groq.detail_key(), AppLanguage::En),
            Provider::Groq.detail_key()
        );
    }

    #[test]
    fn all_providers_have_a_unique_detail_key() {
        let keys: Vec<&str> = Provider::all()
            .iter()
            .map(|provider| provider.detail_key())
            .collect();
        assert!(keys.iter().all(|key| !key.is_empty()));
        let mut unique = keys.clone();
        unique.sort_unstable();
        unique.dedup();
        assert_eq!(unique.len(), keys.len());
    }

    #[test]
    fn infer_provider_from_url() {
        let cases = [
            (
                BackendKind::Ollama,
                "http://127.0.0.1:11434",
                Provider::Ollama,
            ),
            (BackendKind::Ollama, "https://example.com", Provider::Ollama),
            (
                BackendKind::OpenAI,
                "https://ollama.com/v1",
                Provider::OllamaCloud,
            ),
            (
                BackendKind::OpenAI,
                "https://openrouter.ai/api/v1",
                Provider::OpenRouter,
            ),
            (
                BackendKind::OpenAI,
                "https://api.groq.com/openai/v1",
                Provider::Groq,
            ),
            (
                BackendKind::OpenAI,
                "https://api.cerebras.ai/v1",
                Provider::Cerebras,
            ),
            (
                BackendKind::OpenAI,
                "http://127.0.0.1:1234/v1",
                Provider::LmStudio,
            ),
            (
                BackendKind::OpenAI,
                "http://127.0.0.1:50220/v1",
                Provider::Omlx,
            ),
            (
                BackendKind::OpenAI,
                "http://127.0.0.1:8080/v1",
                Provider::LlamaCpp,
            ),
            (
                BackendKind::OpenAI,
                "http://localhost:9999/v1",
                Provider::Custom,
            ),
            (BackendKind::OpenAI, "", Provider::Custom),
        ];
        for (kind, url, expected) in cases {
            assert_eq!(Provider::infer(kind, url), expected, "{kind:?} {url}");
        }
    }

    #[test]
    fn infer_accepts_lowercase_urls() {
        assert_eq!(
            Provider::infer(BackendKind::OpenAI, "HTTPS://OPENROUTER.AI/API/V1"),
            Provider::OpenRouter
        );
        assert_eq!(
            Provider::infer(BackendKind::OpenAI, "HTTPS://OLLAMA.COM"),
            Provider::OllamaCloud
        );
    }

    #[test]
    fn from_value_is_tolerant() {
        assert_eq!(Provider::from_value("groq"), Some(Provider::Groq));
        assert_eq!(
            Provider::from_value("ollamaCloud"),
            Some(Provider::OllamaCloud)
        );
        assert_eq!(
            Provider::from_value("ollamacloud"),
            Some(Provider::OllamaCloud)
        );
        assert_eq!(
            Provider::from_value("OLLAMA_CLOUD"),
            Some(Provider::OllamaCloud)
        );
        assert_eq!(
            Provider::from_value("Ollama Cloud"),
            Some(Provider::OllamaCloud)
        );
        assert_eq!(Provider::from_value("LM Studio"), Some(Provider::LmStudio));
        assert_eq!(Provider::from_value("lm_studio"), Some(Provider::LmStudio));
        assert_eq!(Provider::from_value("llama.cpp"), Some(Provider::LlamaCpp));
        assert_eq!(Provider::from_value("cerebras"), Some(Provider::Cerebras));
        assert_eq!(Provider::from_value("klingon"), None);
        assert_eq!(Provider::from_value(""), None);
        assert_eq!(Provider::from_value("  "), None);
    }

    #[test]
    fn backend_kind_values_and_defaults() {
        assert_eq!(BackendKind::Ollama.value(), "ollama");
        assert_eq!(BackendKind::OpenAI.value(), "openAI");
        assert_eq!(
            BackendKind::Ollama.default_base_url(),
            "http://127.0.0.1:11434"
        );
        assert_eq!(
            BackendKind::OpenAI.default_base_url(),
            "http://127.0.0.1:1234/v1"
        );
        assert_eq!(
            BackendKind::from_stored("openAI"),
            Some(BackendKind::OpenAI)
        );
        assert_eq!(
            BackendKind::from_stored("openai"),
            Some(BackendKind::OpenAI)
        );
        assert_eq!(
            BackendKind::from_stored("ollama"),
            Some(BackendKind::Ollama)
        );
        assert_eq!(BackendKind::from_stored("nonsense"), None);
        assert_eq!(BackendKind::from_stored(""), None);
    }

    #[test]
    fn provider_serde_uses_stored_values() {
        for provider in Provider::all() {
            let json = serde_json::to_string(provider).expect("serialise provider");
            assert_eq!(json, format!("\"{}\"", provider.value()));
            let parsed: Provider = serde_json::from_str(&json).expect("parse provider");
            assert_eq!(parsed, *provider);
        }
        // Tolerant on the way in: titles and variant names still work.
        let parsed: Provider = serde_json::from_str("\"Ollama Cloud\"").expect("parse title");
        assert_eq!(parsed, Provider::OllamaCloud);
        assert!(serde_json::from_str::<Provider>("\"klingon\"").is_err());
    }

    #[test]
    fn backend_kind_serde_uses_stored_values() {
        assert_eq!(
            serde_json::to_string(&BackendKind::OpenAI).expect("serialise"),
            "\"openAI\""
        );
        assert_eq!(
            serde_json::to_string(&BackendKind::Ollama).expect("serialise"),
            "\"ollama\""
        );
        let parsed: BackendKind = serde_json::from_str("\"openAI\"").expect("parse");
        assert_eq!(parsed, BackendKind::OpenAI);
        assert!(serde_json::from_str::<BackendKind>("\"nonsense\"").is_err());
    }

    #[test]
    fn backend_config_defaults() {
        let config = BackendConfig {
            kind: BackendKind::Ollama,
            base_url: "http://x".to_string(),
            model: "m".to_string(),
            ..BackendConfig::default()
        };
        assert_eq!(config.api_key, "");
        assert_eq!(config.temperature, 0.7);
        assert_eq!(config.top_p, 0.6);
        assert_eq!(config.top_k, 20);
        assert_eq!(config.repetition_penalty, 1.05);
        assert_eq!(config.context_window, 8192);
        assert!(!config.requires_api_key);
    }

    #[test]
    fn backend_config_compatible_base() {
        let config = BackendConfig {
            kind: BackendKind::OpenAI,
            base_url: "  http://127.0.0.1:1234/v1///  ".to_string(),
            model: "m".to_string(),
            ..BackendConfig::default()
        };
        assert_eq!(config.compatible_base(), "http://127.0.0.1:1234/v1");

        let empty = BackendConfig {
            kind: BackendKind::Ollama,
            base_url: String::new(),
            ..BackendConfig::default()
        };
        assert_eq!(empty.compatible_base(), "http://127.0.0.1:11434");

        let blank = BackendConfig {
            kind: BackendKind::OpenAI,
            base_url: "   ".to_string(),
            ..BackendConfig::default()
        };
        assert_eq!(blank.compatible_base(), "http://127.0.0.1:1234/v1");
    }

    #[test]
    fn backend_config_same_endpoint() {
        let a = BackendConfig {
            kind: BackendKind::Ollama,
            base_url: "http://x".to_string(),
            model: "m".to_string(),
            ..BackendConfig::default()
        };
        let b = a.clone();
        let c = BackendConfig {
            api_key: "key".to_string(),
            ..a.clone()
        };
        assert!(a.uses_same_endpoint(&b));
        assert!(!a.uses_same_endpoint(&c));
    }
}
