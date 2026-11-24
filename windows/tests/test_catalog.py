"""Curated model catalogue: parity with ``Sources/HyMT/Models/ModelCatalog.swift``.

The badge tuples below are copied verbatim from the Swift catalogue, in the
order the macOS cards display them, so a stray edit to the Python table fails
the suite instead of silently diverging.
"""

from __future__ import annotations

from deepl_ofm.core.catalog import CatalogEntry, ModelCatalog
from deepl_ofm.core.providers import Provider

SWIFT_BADGES: dict[str, tuple[str, ...]] = {
    # Local Ollama
    "hy-mt2:7b": ("33 languages", "≈4.6 GB", "recommended"),
    "hy-mt2:1.8b": ("33 languages", "light", "fast"),
    "hy-mt2:30b": ("33 languages", "MoE", "large"),
    "translategemma:4b": ("55 languages", "≈3 GB"),
    "translategemma:12b": ("55 languages", "≈8 GB"),
    "qwen3.5-mt:2b": ("translation", "2B"),
    "aya-expanse:8b": ("23 languages", "8B"),
    "qwen3:8b": ("universal", "8B"),
    # Ollama Cloud
    "gemma4:31b": ("Cloud", "31B", "fast"),
    "deepseek-v4.1-flash": ("Cloud", "1M", "fast"),
    "mistral-large-4": ("Cloud", "large"),
    "nemotron-3-ultra": ("Cloud", "large", "slower"),
    # OpenRouter
    "tencent/hy-mt2-7b": ("33 languages", "specialised", "cheap"),
    "tencent/hy-mt2-1.8b": ("33 languages", "cheapest"),
    "tencent/hy-mt2-30b-a3b": ("33 languages", "MoE"),
    "google/gemma-4-31b-it:free": ("Free", "262K", "31B"),
    "google/gemma-4-26b-a4b-it:free": ("Free", "MoE", "fast"),
    "nvidia/nemotron-3-ultra-550b-a55b:free": ("Free", "550B", "slower"),
    "inclusionai/ling-3.2-flash:free": ("Free", "1M", "fast"),
    "google/gemini-3.1-flash-lite": ("1M", "fast", "cheap"),
    "qwen/qwen3.7-flash": ("1M", "cheapest"),
    "openai/gpt-5-mini": ("400K", "universal"),
    # Groq
    "openai/gpt-oss-120b": ("Free tier", "~500 t/s", "120B"),
    "openai/gpt-oss-20b": ("Free tier", "~1000 t/s", "20B"),
    "llama-3.3-70b-versatile": ("~280 t/s", "70B"),
    "qwen/qwen3.8-27b": ("~450 t/s", "preview"),
    # Cerebras
    "gpt-oss-120b": ("Free tier", "~3000 t/s", "120B"),
    "qwen-3.8-27b": ("Free tier", "~1850 t/s"),
}

FREE_MODEL_IDS = {
    # Local Ollama models run on the user's machine.
    "hy-mt2:7b",
    "hy-mt2:1.8b",
    "hy-mt2:30b",
    "translategemma:4b",
    "translategemma:12b",
    "qwen3.5-mt:2b",
    "aya-expanse:8b",
    "qwen3:8b",
    # OpenRouter's ":free" variants.
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "inclusionai/ling-3.2-flash:free",
    # Groq's free tier and both Cerebras models.
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "gpt-oss-120b",
    "qwen-3.8-27b",
}


def test_catalogue_keeps_all_28_entries() -> None:
    entries = ModelCatalog.ENTRIES
    assert len(entries) == 28
    assert len({entry.model_id for entry in entries}) == 28
    assert [entry.name for entry in entries][:2] == ["Hy-MT2 7B", "Hy-MT2 1.8B"]


def test_every_entry_has_badges_and_an_explicit_free_flag() -> None:
    for entry in ModelCatalog.ENTRIES:
        assert isinstance(entry, CatalogEntry)
        assert isinstance(entry.badges, tuple), entry.model_id
        assert entry.badges, f"{entry.model_id} needs at least one badge"
        assert all(isinstance(badge, str) and badge for badge in entry.badges)
        assert isinstance(entry.is_free, bool), entry.model_id

    assert any("recommended" in entry.badges for entry in ModelCatalog.ENTRIES)
    assert any(entry.is_free for entry in ModelCatalog.ENTRIES)
    assert any(not entry.is_free for entry in ModelCatalog.ENTRIES)


def test_badges_match_the_swift_catalogue_in_order() -> None:
    actual = {entry.model_id: entry.badges for entry in ModelCatalog.ENTRIES}
    assert actual == SWIFT_BADGES
    assert list(actual) == [entry.model_id for entry in ModelCatalog.ENTRIES]


def test_free_flags_match_the_swift_catalogue() -> None:
    actual = {entry.model_id for entry in ModelCatalog.ENTRIES if entry.is_free}
    assert actual == FREE_MODEL_IDS
    assert len(actual) == 16
    cloud = ModelCatalog.for_provider(Provider.OLLAMA_CLOUD)
    assert cloud and not any(entry.is_free for entry in cloud)


def test_entry_lookup_and_install_commands() -> None:
    entry = ModelCatalog.entry("hy-mt2:30b")
    assert entry is not None
    assert entry.name == "Hy-MT2 30B-A3B"
    assert ModelCatalog.install_command("hy-mt2:30b") == (
        "ollama pull maternion/hy-mt2:30b-a3b && "
        "ollama cp maternion/hy-mt2:30b-a3b hy-mt2:30b"
    )
    # Cloud entries are curated but have no Ollama install command.
    assert ModelCatalog.entry("gemma4:31b") is not None
    assert ModelCatalog.install_command("gemma4:31b") is None
    assert ModelCatalog.entry("does-not-exist") is None
    assert ModelCatalog.install_command("does-not-exist") is None
    for entry in ModelCatalog.for_provider(Provider.OLLAMA):
        assert entry.install_command
        assert ModelCatalog.install_command(entry.model_id) == entry.install_command


def test_provider_grouping_is_preserved() -> None:
    assert ModelCatalog.for_provider(Provider.CUSTOM) == []
    assert [
        entry.model_id for entry in ModelCatalog.for_provider(Provider.OLLAMA)
    ] == [entry.model_id for entry in ModelCatalog.ENTRIES[:8]]
    assert len(ModelCatalog.for_provider(Provider.LM_STUDIO)) == 8
    assert len(ModelCatalog.for_provider(Provider.OMLX)) == 8
    assert len(ModelCatalog.for_provider(Provider.LLAMA_CPP)) == 8
    assert len(ModelCatalog.for_provider(Provider.OLLAMA_CLOUD)) == 4
    assert len(ModelCatalog.for_provider(Provider.OPEN_ROUTER)) == 10
    assert len(ModelCatalog.for_provider(Provider.GROQ)) == 4
    assert len(ModelCatalog.for_provider(Provider.CEREBRAS)) == 2
