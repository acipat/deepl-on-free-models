//! Curated model catalogue.
//!
//! Ported from `windows/deepl_ofm/core/catalog.py` (itself a port of
//! `Sources/HyMT/Models/ModelCatalog.swift`). Every entry keeps the Swift badge
//! order and free flag verbatim, and [`ModelCatalog::install_command`] resolves
//! the Ollama command that installs a model, exactly like the Swift helper.

use crate::providers::Provider;

/// One model the app knows how to apply with a single click.
#[derive(Clone, Copy, Debug)]
pub struct CatalogEntry {
    /// Display name of the card.
    pub name: &'static str,
    /// Model identifier sent to the provider.
    pub model_id: &'static str,
    /// Provider the entry belongs to.
    pub provider: Provider,
    /// Human readable size ("≈4.6 GB", "30B-A3B", "large").
    pub size: &'static str,
    /// Language coverage note ("33 languages", empty when unknown).
    pub languages: &'static str,
    /// One-line description shown on the card.
    pub note: &'static str,
    /// Ollama command that installs the model, empty for cloud models.
    pub install_command: &'static str,
    /// Badges in the order the macOS cards display them.
    pub badges: &'static [&'static str],
    /// True when the model can be used without paying.
    pub is_free: bool,
}

/// Local Ollama models.
const LOCAL_ENTRIES: &[CatalogEntry] = &[
    CatalogEntry {
        name: "Hy-MT2 7B",
        model_id: "hy-mt2:7b",
        provider: Provider::Ollama,
        size: "≈4.6 GB",
        languages: "33 languages",
        note: "Tencent's specialised translation model. The default for this app.",
        install_command:
            "ollama pull maternion/hy-mt2:7b && ollama cp maternion/hy-mt2:7b hy-mt2:7b",
        badges: &["33 languages", "≈4.6 GB", "recommended"],
        is_free: true,
    },
    CatalogEntry {
        name: "Hy-MT2 1.8B",
        model_id: "hy-mt2:1.8b",
        provider: Provider::Ollama,
        size: "1.8B",
        languages: "33 languages",
        note: "The same model in a lighter size: fast even on weaker Macs.",
        install_command:
            "ollama pull maternion/hy-mt2:1.8b && ollama cp maternion/hy-mt2:1.8b hy-mt2:1.8b",
        badges: &["33 languages", "light", "fast"],
        is_free: true,
    },
    CatalogEntry {
        name: "Hy-MT2 30B-A3B",
        model_id: "hy-mt2:30b",
        provider: Provider::Ollama,
        size: "30B-A3B",
        languages: "33 languages",
        note: "The highest-quality MoE version. Needs a lot of memory.",
        install_command:
            "ollama pull maternion/hy-mt2:30b-a3b && ollama cp maternion/hy-mt2:30b-a3b hy-mt2:30b",
        badges: &["33 languages", "MoE", "large"],
        is_free: true,
    },
    CatalogEntry {
        name: "TranslateGemma 4B",
        model_id: "translategemma:4b",
        provider: Provider::Ollama,
        size: "≈3 GB",
        languages: "55 languages",
        note: "Google's translation model built on Gemma 3.",
        install_command: "ollama pull translategemma:4b",
        badges: &["55 languages", "≈3 GB"],
        is_free: true,
    },
    CatalogEntry {
        name: "TranslateGemma 12B",
        model_id: "translategemma:12b",
        provider: Provider::Ollama,
        size: "≈8 GB",
        languages: "55 languages",
        note: "A larger TranslateGemma for stronger machines.",
        install_command: "ollama pull translategemma:12b",
        badges: &["55 languages", "≈8 GB"],
        is_free: true,
    },
    CatalogEntry {
        name: "Qwen3.5-MT 2B",
        model_id: "qwen3.5-mt:2b",
        provider: Provider::Ollama,
        size: "2B",
        languages: "",
        note: "A compact model tuned only to translate — no explanations or reasoning.",
        install_command: "ollama pull kaelri/qwen3.5-mt:2b",
        badges: &["translation", "2B"],
        is_free: true,
    },
    CatalogEntry {
        name: "Aya Expanse 8B",
        model_id: "aya-expanse:8b",
        provider: Provider::Ollama,
        size: "8B",
        languages: "23 languages",
        note: "Cohere's multilingual model with a good speed-quality balance.",
        install_command: "ollama pull aya-expanse:8b",
        badges: &["23 languages", "8B"],
        is_free: true,
    },
    CatalogEntry {
        name: "Qwen3 8B",
        model_id: "qwen3:8b",
        provider: Provider::Ollama,
        size: "8B",
        languages: "",
        note: "A general model; translates well but may add explanations.",
        install_command: "ollama pull qwen3:8b",
        badges: &["universal", "8B"],
        is_free: true,
    },
];

/// Ollama Cloud models.
const OLLAMA_CLOUD_ENTRIES: &[CatalogEntry] = &[
    CatalogEntry {
        name: "Gemma 4 31B",
        model_id: "gemma4:31b",
        provider: Provider::OllamaCloud,
        size: "31B",
        languages: "",
        note: "Gemma 4 in Ollama Cloud. Fast and strong for general translation.",
        install_command: "",
        badges: &["Cloud", "31B", "fast"],
        is_free: false,
    },
    CatalogEntry {
        name: "DeepSeek V4.1 Flash",
        model_id: "deepseek-v4.1-flash",
        provider: Provider::OllamaCloud,
        size: "1M",
        languages: "",
        note: "A fast cloud model from DeepSeek with a large context.",
        install_command: "",
        badges: &["Cloud", "1M", "fast"],
        is_free: false,
    },
    CatalogEntry {
        name: "Mistral Large 4",
        model_id: "mistral-large-4",
        provider: Provider::OllamaCloud,
        size: "large",
        languages: "",
        note: "Mistral's general-purpose model in Ollama Cloud.",
        install_command: "",
        badges: &["Cloud", "large"],
        is_free: false,
    },
    CatalogEntry {
        name: "Nemotron 3 Ultra",
        model_id: "nemotron-3-ultra",
        provider: Provider::OllamaCloud,
        size: "large",
        languages: "",
        note: "NVIDIA's high-throughput model for difficult texts.",
        install_command: "",
        badges: &["Cloud", "large", "slower"],
        is_free: false,
    },
];

/// OpenRouter models.
const OPEN_ROUTER_ENTRIES: &[CatalogEntry] = &[
    CatalogEntry {
        name: "Hy-MT2 7B",
        model_id: "tencent/hy-mt2-7b",
        provider: Provider::OpenRouter,
        size: "7B",
        languages: "33 languages",
        note: "The same translation model in the cloud. Very cheap, no download.",
        install_command: "",
        badges: &["33 languages", "specialised", "cheap"],
        is_free: false,
    },
    CatalogEntry {
        name: "Hy-MT2 1.8B",
        model_id: "tencent/hy-mt2-1.8b",
        provider: Provider::OpenRouter,
        size: "1.8B",
        languages: "33 languages",
        note: "The cheapest Hy-MT2 option on OpenRouter.",
        install_command: "",
        badges: &["33 languages", "cheapest"],
        is_free: false,
    },
    CatalogEntry {
        name: "Hy-MT2 30B-A3B",
        model_id: "tencent/hy-mt2-30b-a3b",
        provider: Provider::OpenRouter,
        size: "30B-A3B",
        languages: "33 languages",
        note: "The highest-quality Hy-MT2 version on OpenRouter.",
        install_command: "",
        badges: &["33 languages", "MoE"],
        is_free: false,
    },
    CatalogEntry {
        name: "Gemma 4 31B",
        model_id: "google/gemma-4-31b-it:free",
        provider: Provider::OpenRouter,
        size: "31B",
        languages: "",
        note: "Google's free model with a large context. Good general translation.",
        install_command: "",
        badges: &["Free", "262K", "31B"],
        is_free: true,
    },
    CatalogEntry {
        name: "Gemma 4 26B A4B",
        model_id: "google/gemma-4-26b-a4b-it:free",
        provider: Provider::OpenRouter,
        size: "26B A4B",
        languages: "",
        note: "A free MoE version of Gemma 4: faster than 31B.",
        install_command: "",
        badges: &["Free", "MoE", "fast"],
        is_free: true,
    },
    CatalogEntry {
        name: "Nemotron 3 Ultra",
        model_id: "nvidia/nemotron-3-ultra-550b-a55b:free",
        provider: Provider::OpenRouter,
        size: "550B",
        languages: "",
        note: "A large free NVIDIA model for difficult texts.",
        install_command: "",
        badges: &["Free", "550B", "slower"],
        is_free: true,
    },
    CatalogEntry {
        name: "Ling 3.2 Flash",
        model_id: "inclusionai/ling-3.2-flash:free",
        provider: Provider::OpenRouter,
        size: "1M",
        languages: "",
        note: "A free fast model with a 1M-token context.",
        install_command: "",
        badges: &["Free", "1M", "fast"],
        is_free: true,
    },
    CatalogEntry {
        name: "Gemini 3.1 Flash Lite",
        model_id: "google/gemini-3.1-flash-lite",
        provider: Provider::OpenRouter,
        size: "1M",
        languages: "",
        note: "Cheap and very fast general translation from Google.",
        install_command: "",
        badges: &["1M", "fast", "cheap"],
        is_free: false,
    },
    CatalogEntry {
        name: "Qwen3.7 Flash",
        model_id: "qwen/qwen3.7-flash",
        provider: Provider::OpenRouter,
        size: "1M",
        languages: "",
        note: "The cheapest fast Qwen model for bulk translation.",
        install_command: "",
        badges: &["1M", "cheapest"],
        is_free: false,
    },
    CatalogEntry {
        name: "GPT-5 Mini",
        model_id: "openai/gpt-5-mini",
        provider: Provider::OpenRouter,
        size: "400K",
        languages: "",
        note: "Reliable general translation from OpenAI.",
        install_command: "",
        badges: &["400K", "universal"],
        is_free: false,
    },
];

/// Groq models.
const GROQ_ENTRIES: &[CatalogEntry] = &[
    CatalogEntry {
        name: "GPT-OSS 120B",
        model_id: "openai/gpt-oss-120b",
        provider: Provider::Groq,
        size: "120B",
        languages: "",
        note: "OpenAI's flagship open model on Groq's fast inference.",
        install_command: "",
        badges: &["Free tier", "~500 t/s", "120B"],
        is_free: true,
    },
    CatalogEntry {
        name: "GPT-OSS 20B",
        model_id: "openai/gpt-oss-20b",
        provider: Provider::Groq,
        size: "20B",
        languages: "",
        note: "The fastest option for short texts.",
        install_command: "",
        badges: &["Free tier", "~1000 t/s", "20B"],
        is_free: true,
    },
    CatalogEntry {
        name: "Llama 3.3 70B",
        model_id: "llama-3.3-70b-versatile",
        provider: Provider::Groq,
        size: "70B",
        languages: "",
        note: "Meta's proven general-purpose model.",
        install_command: "",
        badges: &["~280 t/s", "70B"],
        is_free: false,
    },
    CatalogEntry {
        name: "Qwen3.8 27B",
        model_id: "qwen/qwen3.8-27b",
        provider: Provider::Groq,
        size: "27B",
        languages: "",
        note: "A fresh Qwen with strong translation; preview status.",
        install_command: "",
        badges: &["~450 t/s", "preview"],
        is_free: false,
    },
];

/// Cerebras models.
const CEREBRAS_ENTRIES: &[CatalogEntry] = &[
    CatalogEntry {
        name: "GPT-OSS 120B",
        model_id: "gpt-oss-120b",
        provider: Provider::Cerebras,
        size: "120B",
        languages: "",
        note: "Around 3000 tokens per second — the fastest option for long texts.",
        install_command: "",
        badges: &["Free tier", "~3000 t/s", "120B"],
        is_free: true,
    },
    CatalogEntry {
        name: "Qwen3.8 27B",
        model_id: "qwen-3.8-27b",
        provider: Provider::Cerebras,
        size: "27B",
        languages: "",
        note: "A fast Qwen with good multilingual translation.",
        install_command: "",
        badges: &["Free tier", "~1850 t/s"],
        is_free: true,
    },
];

/// The full curated catalogue, in Swift order.
///
/// The provider groups above are the single source of truth; this ordered list
/// mirrors the order of the Swift `ModelCatalog.Entries` array.
const ENTRIES: &[CatalogEntry] = &[
    LOCAL_ENTRIES[0],
    LOCAL_ENTRIES[1],
    LOCAL_ENTRIES[2],
    LOCAL_ENTRIES[3],
    LOCAL_ENTRIES[4],
    LOCAL_ENTRIES[5],
    LOCAL_ENTRIES[6],
    LOCAL_ENTRIES[7],
    OLLAMA_CLOUD_ENTRIES[0],
    OLLAMA_CLOUD_ENTRIES[1],
    OLLAMA_CLOUD_ENTRIES[2],
    OLLAMA_CLOUD_ENTRIES[3],
    OPEN_ROUTER_ENTRIES[0],
    OPEN_ROUTER_ENTRIES[1],
    OPEN_ROUTER_ENTRIES[2],
    OPEN_ROUTER_ENTRIES[3],
    OPEN_ROUTER_ENTRIES[4],
    OPEN_ROUTER_ENTRIES[5],
    OPEN_ROUTER_ENTRIES[6],
    OPEN_ROUTER_ENTRIES[7],
    OPEN_ROUTER_ENTRIES[8],
    OPEN_ROUTER_ENTRIES[9],
    GROQ_ENTRIES[0],
    GROQ_ENTRIES[1],
    GROQ_ENTRIES[2],
    GROQ_ENTRIES[3],
    CEREBRAS_ENTRIES[0],
    CEREBRAS_ENTRIES[1],
];

/// The curated catalogue and the install-command lookup.
pub struct ModelCatalog;

impl ModelCatalog {
    /// All curated entries in Swift order (28 of them).
    pub fn entries() -> &'static [CatalogEntry] {
        ENTRIES
    }

    /// The curated entry for `model_id`, or `None` when unknown.
    pub fn entry(model_id: &str) -> Option<&'static CatalogEntry> {
        ENTRIES.iter().find(|entry| entry.model_id == model_id)
    }

    /// Ollama install command for `model_id`, or `None` when unknown/cloud.
    pub fn install_command(model_id: &str) -> Option<&'static str> {
        let command = Self::entry(model_id)?.install_command;
        if command.is_empty() {
            None
        } else {
            Some(command)
        }
    }

    /// Entries relevant to a provider, mirroring `ModelCatalog.entries(for:)`.
    pub fn for_provider(provider: Provider) -> Vec<&'static CatalogEntry> {
        let group: &'static [CatalogEntry] = match provider {
            Provider::Custom => &[],
            Provider::Ollama | Provider::LmStudio | Provider::Omlx | Provider::LlamaCpp => {
                LOCAL_ENTRIES
            }
            Provider::OllamaCloud => OLLAMA_CLOUD_ENTRIES,
            Provider::OpenRouter => OPEN_ROUTER_ENTRIES,
            Provider::Groq => GROQ_ENTRIES,
            Provider::Cerebras => CEREBRAS_ENTRIES,
        };
        group.iter().collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Badge tuples copied verbatim from the Swift catalogue, in card order.
    const SWIFT_BADGES: &[(&str, &[&str])] = &[
        ("hy-mt2:7b", &["33 languages", "≈4.6 GB", "recommended"]),
        ("hy-mt2:1.8b", &["33 languages", "light", "fast"]),
        ("hy-mt2:30b", &["33 languages", "MoE", "large"]),
        ("translategemma:4b", &["55 languages", "≈3 GB"]),
        ("translategemma:12b", &["55 languages", "≈8 GB"]),
        ("qwen3.5-mt:2b", &["translation", "2B"]),
        ("aya-expanse:8b", &["23 languages", "8B"]),
        ("qwen3:8b", &["universal", "8B"]),
        ("gemma4:31b", &["Cloud", "31B", "fast"]),
        ("deepseek-v4.1-flash", &["Cloud", "1M", "fast"]),
        ("mistral-large-4", &["Cloud", "large"]),
        ("nemotron-3-ultra", &["Cloud", "large", "slower"]),
        (
            "tencent/hy-mt2-7b",
            &["33 languages", "specialised", "cheap"],
        ),
        ("tencent/hy-mt2-1.8b", &["33 languages", "cheapest"]),
        ("tencent/hy-mt2-30b-a3b", &["33 languages", "MoE"]),
        ("google/gemma-4-31b-it:free", &["Free", "262K", "31B"]),
        ("google/gemma-4-26b-a4b-it:free", &["Free", "MoE", "fast"]),
        (
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            &["Free", "550B", "slower"],
        ),
        ("inclusionai/ling-3.2-flash:free", &["Free", "1M", "fast"]),
        ("google/gemini-3.1-flash-lite", &["1M", "fast", "cheap"]),
        ("qwen/qwen3.7-flash", &["1M", "cheapest"]),
        ("openai/gpt-5-mini", &["400K", "universal"]),
        ("openai/gpt-oss-120b", &["Free tier", "~500 t/s", "120B"]),
        ("openai/gpt-oss-20b", &["Free tier", "~1000 t/s", "20B"]),
        ("llama-3.3-70b-versatile", &["~280 t/s", "70B"]),
        ("qwen/qwen3.8-27b", &["~450 t/s", "preview"]),
        ("gpt-oss-120b", &["Free tier", "~3000 t/s", "120B"]),
        ("qwen-3.8-27b", &["Free tier", "~1850 t/s"]),
    ];

    #[test]
    fn catalogue_keeps_all_28_entries() {
        let entries = ModelCatalog::entries();
        assert_eq!(entries.len(), 28);
        let mut ids: Vec<&str> = entries.iter().map(|entry| entry.model_id).collect();
        ids.sort_unstable();
        ids.dedup();
        assert_eq!(ids.len(), 28);
        let names: Vec<&str> = entries.iter().map(|entry| entry.name).collect();
        assert_eq!(&names[..2], ["Hy-MT2 7B", "Hy-MT2 1.8B"]);
    }

    #[test]
    fn every_entry_has_badges_and_an_explicit_free_flag() {
        for entry in ModelCatalog::entries() {
            assert!(!entry.badges.is_empty(), "{} needs a badge", entry.model_id);
            assert!(entry.badges.iter().all(|badge| !badge.is_empty()));
            assert!(!entry.name.is_empty());
            assert!(!entry.note.is_empty());
        }
        assert!(ModelCatalog::entries()
            .iter()
            .any(|entry| entry.badges.contains(&"recommended")));
        assert!(ModelCatalog::entries().iter().any(|entry| entry.is_free));
        assert!(ModelCatalog::entries().iter().any(|entry| !entry.is_free));
    }

    #[test]
    fn badges_match_the_swift_catalogue_in_order() {
        assert_eq!(
            ModelCatalog::entries().len(),
            SWIFT_BADGES.len(),
            "the expectation table and the catalogue must agree"
        );
        for (entry, (model_id, badges)) in ModelCatalog::entries().iter().zip(SWIFT_BADGES) {
            assert_eq!(entry.model_id, *model_id);
            assert_eq!(entry.badges, *badges, "badges of {}", entry.model_id);
        }
    }

    #[test]
    fn free_flags_match_the_swift_catalogue() {
        let mut free: Vec<&str> = ModelCatalog::entries()
            .iter()
            .filter(|entry| entry.is_free)
            .map(|entry| entry.model_id)
            .collect();
        free.sort_unstable();
        assert_eq!(free.len(), 16);
        for model_id in [
            "hy-mt2:7b",
            "hy-mt2:1.8b",
            "hy-mt2:30b",
            "translategemma:4b",
            "translategemma:12b",
            "qwen3.5-mt:2b",
            "aya-expanse:8b",
            "qwen3:8b",
            "google/gemma-4-31b-it:free",
            "google/gemma-4-26b-a4b-it:free",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "inclusionai/ling-3.2-flash:free",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "gpt-oss-120b",
            "qwen-3.8-27b",
        ] {
            assert!(free.contains(&model_id), "{model_id} should be free");
        }
        let cloud = ModelCatalog::for_provider(Provider::OllamaCloud);
        assert!(!cloud.is_empty());
        assert!(cloud.iter().all(|entry| !entry.is_free));
    }

    #[test]
    fn entry_lookup_and_install_commands() {
        let entry = ModelCatalog::entry("hy-mt2:30b").expect("curated entry");
        assert_eq!(entry.name, "Hy-MT2 30B-A3B");
        assert_eq!(
            ModelCatalog::install_command("hy-mt2:30b"),
            Some(
                "ollama pull maternion/hy-mt2:30b-a3b && \
                 ollama cp maternion/hy-mt2:30b-a3b hy-mt2:30b"
            )
        );
        // Cloud entries are curated but have no Ollama install command.
        assert!(ModelCatalog::entry("gemma4:31b").is_some());
        assert_eq!(ModelCatalog::install_command("gemma4:31b"), None);
        assert!(ModelCatalog::entry("does-not-exist").is_none());
        assert_eq!(ModelCatalog::install_command("does-not-exist"), None);
        for entry in ModelCatalog::for_provider(Provider::Ollama) {
            assert!(!entry.install_command.is_empty());
            assert_eq!(
                ModelCatalog::install_command(entry.model_id),
                Some(entry.install_command)
            );
        }
    }

    #[test]
    fn provider_grouping_is_preserved() {
        assert!(ModelCatalog::for_provider(Provider::Custom).is_empty());
        let local: Vec<&str> = ModelCatalog::for_provider(Provider::Ollama)
            .iter()
            .map(|entry| entry.model_id)
            .collect();
        let head: Vec<&str> = ModelCatalog::entries()[..8]
            .iter()
            .map(|entry| entry.model_id)
            .collect();
        assert_eq!(local, head);
        assert_eq!(ModelCatalog::for_provider(Provider::LmStudio).len(), 8);
        assert_eq!(ModelCatalog::for_provider(Provider::Omlx).len(), 8);
        assert_eq!(ModelCatalog::for_provider(Provider::LlamaCpp).len(), 8);
        assert_eq!(ModelCatalog::for_provider(Provider::OllamaCloud).len(), 4);
        assert_eq!(ModelCatalog::for_provider(Provider::OpenRouter).len(), 10);
        assert_eq!(ModelCatalog::for_provider(Provider::Groq).len(), 4);
        assert_eq!(ModelCatalog::for_provider(Provider::Cerebras).len(), 2);
    }
}
