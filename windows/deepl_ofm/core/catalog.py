"""Curated model catalogue.

Ported from ``Sources/HyMT/Models/ModelCatalog.swift``. Every curated entry is
kept with the Swift badges and free flag, and :meth:`ModelCatalog.install_command`
resolves the Ollama command that installs a model, exactly like the Swift helper.
"""
from __future__ import annotations

from dataclasses import dataclass

from deepl_ofm.core.providers import Provider


@dataclass(frozen=True)
class CatalogEntry:
    """One model the app knows how to apply with a single click."""

    name: str
    model_id: str
    provider: Provider
    size: str
    languages: str
    note: str
    install_command: str = ""
    badges: tuple[str, ...] = ()
    is_free: bool = False


_LOCAL_ENTRIES: list[CatalogEntry] = [
    CatalogEntry(
        name="Hy-MT2 7B",
        model_id="hy-mt2:7b",
        provider=Provider.OLLAMA,
        size="≈4.6 GB",
        languages="33 languages",
        note="Tencent's specialised translation model. The default for this app.",
        install_command=(
            "ollama pull maternion/hy-mt2:7b && ollama cp maternion/hy-mt2:7b hy-mt2:7b"
        ),
        badges=("33 languages", "≈4.6 GB", "recommended"),
        is_free=True,
    ),
    CatalogEntry(
        name="Hy-MT2 1.8B",
        model_id="hy-mt2:1.8b",
        provider=Provider.OLLAMA,
        size="1.8B",
        languages="33 languages",
        note="The same model in a lighter size: fast even on weaker Macs.",
        install_command=(
            "ollama pull maternion/hy-mt2:1.8b && ollama cp maternion/hy-mt2:1.8b hy-mt2:1.8b"
        ),
        badges=("33 languages", "light", "fast"),
        is_free=True,
    ),
    CatalogEntry(
        name="Hy-MT2 30B-A3B",
        model_id="hy-mt2:30b",
        provider=Provider.OLLAMA,
        size="30B-A3B",
        languages="33 languages",
        note="The highest-quality MoE version. Needs a lot of memory.",
        install_command=(
            "ollama pull maternion/hy-mt2:30b-a3b && ollama cp maternion/hy-mt2:30b-a3b "
            "hy-mt2:30b"
        ),
        badges=("33 languages", "MoE", "large"),
        is_free=True,
    ),
    CatalogEntry(
        name="TranslateGemma 4B",
        model_id="translategemma:4b",
        provider=Provider.OLLAMA,
        size="≈3 GB",
        languages="55 languages",
        note="Google's translation model built on Gemma 3.",
        install_command="ollama pull translategemma:4b",
        badges=("55 languages", "≈3 GB"),
        is_free=True,
    ),
    CatalogEntry(
        name="TranslateGemma 12B",
        model_id="translategemma:12b",
        provider=Provider.OLLAMA,
        size="≈8 GB",
        languages="55 languages",
        note="A larger TranslateGemma for stronger machines.",
        install_command="ollama pull translategemma:12b",
        badges=("55 languages", "≈8 GB"),
        is_free=True,
    ),
    CatalogEntry(
        name="Qwen3.5-MT 2B",
        model_id="qwen3.5-mt:2b",
        provider=Provider.OLLAMA,
        size="2B",
        languages="",
        note="A compact model tuned only to translate — no explanations or reasoning.",
        install_command="ollama pull kaelri/qwen3.5-mt:2b",
        badges=("translation", "2B"),
        is_free=True,
    ),
    CatalogEntry(
        name="Aya Expanse 8B",
        model_id="aya-expanse:8b",
        provider=Provider.OLLAMA,
        size="8B",
        languages="23 languages",
        note="Cohere's multilingual model with a good speed-quality balance.",
        install_command="ollama pull aya-expanse:8b",
        badges=("23 languages", "8B"),
        is_free=True,
    ),
    CatalogEntry(
        name="Qwen3 8B",
        model_id="qwen3:8b",
        provider=Provider.OLLAMA,
        size="8B",
        languages="",
        note="A general model; translates well but may add explanations.",
        install_command="ollama pull qwen3:8b",
        badges=("universal", "8B"),
        is_free=True,
    ),
]

_OLLAMA_CLOUD_ENTRIES: list[CatalogEntry] = [
    CatalogEntry(
        name="Gemma 4 31B",
        model_id="gemma4:31b",
        provider=Provider.OLLAMA_CLOUD,
        size="31B",
        languages="",
        note="Gemma 4 in Ollama Cloud. Fast and strong for general translation.",
        badges=("Cloud", "31B", "fast"),
        is_free=False,
    ),
    CatalogEntry(
        name="DeepSeek V4.1 Flash",
        model_id="deepseek-v4.1-flash",
        provider=Provider.OLLAMA_CLOUD,
        size="1M",
        languages="",
        note="A fast cloud model from DeepSeek with a large context.",
        badges=("Cloud", "1M", "fast"),
        is_free=False,
    ),
    CatalogEntry(
        name="Mistral Large 4",
        model_id="mistral-large-4",
        provider=Provider.OLLAMA_CLOUD,
        size="large",
        languages="",
        note="Mistral's general-purpose model in Ollama Cloud.",
        badges=("Cloud", "large"),
        is_free=False,
    ),
    CatalogEntry(
        name="Nemotron 3 Ultra",
        model_id="nemotron-3-ultra",
        provider=Provider.OLLAMA_CLOUD,
        size="large",
        languages="",
        note="NVIDIA's high-throughput model for difficult texts.",
        badges=("Cloud", "large", "slower"),
        is_free=False,
    ),
]

_OPEN_ROUTER_ENTRIES: list[CatalogEntry] = [
    CatalogEntry(
        name="Hy-MT2 7B",
        model_id="tencent/hy-mt2-7b",
        provider=Provider.OPEN_ROUTER,
        size="7B",
        languages="33 languages",
        note="The same translation model in the cloud. Very cheap, no download.",
        badges=("33 languages", "specialised", "cheap"),
        is_free=False,
    ),
    CatalogEntry(
        name="Hy-MT2 1.8B",
        model_id="tencent/hy-mt2-1.8b",
        provider=Provider.OPEN_ROUTER,
        size="1.8B",
        languages="33 languages",
        note="The cheapest Hy-MT2 option on OpenRouter.",
        badges=("33 languages", "cheapest"),
        is_free=False,
    ),
    CatalogEntry(
        name="Hy-MT2 30B-A3B",
        model_id="tencent/hy-mt2-30b-a3b",
        provider=Provider.OPEN_ROUTER,
        size="30B-A3B",
        languages="33 languages",
        note="The highest-quality Hy-MT2 version on OpenRouter.",
        badges=("33 languages", "MoE"),
        is_free=False,
    ),
    CatalogEntry(
        name="Gemma 4 31B",
        model_id="google/gemma-4-31b-it:free",
        provider=Provider.OPEN_ROUTER,
        size="31B",
        languages="",
        note="Google's free model with a large context. Good general translation.",
        badges=("Free", "262K", "31B"),
        is_free=True,
    ),
    CatalogEntry(
        name="Gemma 4 26B A4B",
        model_id="google/gemma-4-26b-a4b-it:free",
        provider=Provider.OPEN_ROUTER,
        size="26B A4B",
        languages="",
        note="A free MoE version of Gemma 4: faster than 31B.",
        badges=("Free", "MoE", "fast"),
        is_free=True,
    ),
    CatalogEntry(
        name="Nemotron 3 Ultra",
        model_id="nvidia/nemotron-3-ultra-550b-a55b:free",
        provider=Provider.OPEN_ROUTER,
        size="550B",
        languages="",
        note="A large free NVIDIA model for difficult texts.",
        badges=("Free", "550B", "slower"),
        is_free=True,
    ),
    CatalogEntry(
        name="Ling 3.2 Flash",
        model_id="inclusionai/ling-3.2-flash:free",
        provider=Provider.OPEN_ROUTER,
        size="1M",
        languages="",
        note="A free fast model with a 1M-token context.",
        badges=("Free", "1M", "fast"),
        is_free=True,
    ),
    CatalogEntry(
        name="Gemini 3.1 Flash Lite",
        model_id="google/gemini-3.1-flash-lite",
        provider=Provider.OPEN_ROUTER,
        size="1M",
        languages="",
        note="Cheap and very fast general translation from Google.",
        badges=("1M", "fast", "cheap"),
        is_free=False,
    ),
    CatalogEntry(
        name="Qwen3.7 Flash",
        model_id="qwen/qwen3.7-flash",
        provider=Provider.OPEN_ROUTER,
        size="1M",
        languages="",
        note="The cheapest fast Qwen model for bulk translation.",
        badges=("1M", "cheapest"),
        is_free=False,
    ),
    CatalogEntry(
        name="GPT-5 Mini",
        model_id="openai/gpt-5-mini",
        provider=Provider.OPEN_ROUTER,
        size="400K",
        languages="",
        note="Reliable general translation from OpenAI.",
        badges=("400K", "universal"),
        is_free=False,
    ),
]

_GROQ_ENTRIES: list[CatalogEntry] = [
    CatalogEntry(
        name="GPT-OSS 120B",
        model_id="openai/gpt-oss-120b",
        provider=Provider.GROQ,
        size="120B",
        languages="",
        note="OpenAI's flagship open model on Groq's fast inference.",
        badges=("Free tier", "~500 t/s", "120B"),
        is_free=True,
    ),
    CatalogEntry(
        name="GPT-OSS 20B",
        model_id="openai/gpt-oss-20b",
        provider=Provider.GROQ,
        size="20B",
        languages="",
        note="The fastest option for short texts.",
        badges=("Free tier", "~1000 t/s", "20B"),
        is_free=True,
    ),
    CatalogEntry(
        name="Llama 3.3 70B",
        model_id="llama-3.3-70b-versatile",
        provider=Provider.GROQ,
        size="70B",
        languages="",
        note="Meta's proven general-purpose model.",
        badges=("~280 t/s", "70B"),
        is_free=False,
    ),
    CatalogEntry(
        name="Qwen3.8 27B",
        model_id="qwen/qwen3.8-27b",
        provider=Provider.GROQ,
        size="27B",
        languages="",
        note="A fresh Qwen with strong translation; preview status.",
        badges=("~450 t/s", "preview"),
        is_free=False,
    ),
]

_CEREBRAS_ENTRIES: list[CatalogEntry] = [
    CatalogEntry(
        name="GPT-OSS 120B",
        model_id="gpt-oss-120b",
        provider=Provider.CEREBRAS,
        size="120B",
        languages="",
        note="Around 3000 tokens per second — the fastest option for long texts.",
        badges=("Free tier", "~3000 t/s", "120B"),
        is_free=True,
    ),
    CatalogEntry(
        name="Qwen3.8 27B",
        model_id="qwen-3.8-27b",
        provider=Provider.CEREBRAS,
        size="27B",
        languages="",
        note="A fast Qwen with good multilingual translation.",
        badges=("Free tier", "~1850 t/s"),
        is_free=True,
    ),
]


class ModelCatalog:
    """The full curated catalogue and the install-command lookup."""

    ENTRIES: list[CatalogEntry] = (
        _LOCAL_ENTRIES
        + _OLLAMA_CLOUD_ENTRIES
        + _OPEN_ROUTER_ENTRIES
        + _GROQ_ENTRIES
        + _CEREBRAS_ENTRIES
    )

    @staticmethod
    def entry(for_model: str) -> CatalogEntry | None:
        """The curated entry for *model*, or ``None`` when unknown."""
        for entry in ModelCatalog.ENTRIES:
            if entry.model_id == for_model:
                return entry
        return None

    @staticmethod
    def install_command(for_model: str) -> str | None:
        """Ollama install command for *model*, or ``None`` when unknown."""
        entry = ModelCatalog.entry(for_model)
        if entry is None:
            return None
        return entry.install_command or None

    @staticmethod
    def for_provider(provider: Provider) -> list[CatalogEntry]:
        """Entries relevant to a provider, mirroring ``ModelCatalog.entries(for:)``."""
        if provider is Provider.CUSTOM:
            return []
        if provider in (Provider.OLLAMA, Provider.LM_STUDIO, Provider.OMLX,
                        Provider.LLAMA_CPP):
            return list(_LOCAL_ENTRIES)
        if provider is Provider.OLLAMA_CLOUD:
            return list(_OLLAMA_CLOUD_ENTRIES)
        if provider is Provider.OPEN_ROUTER:
            return list(_OPEN_ROUTER_ENTRIES)
        if provider is Provider.GROQ:
            return list(_GROQ_ENTRIES)
        if provider is Provider.CEREBRAS:
            return list(_CEREBRAS_ENTRIES)
        return []
