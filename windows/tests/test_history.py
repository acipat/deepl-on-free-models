"""Tests for ``deepl_ofm.services.history`` (port of HistoryStoreTests.swift)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from deepl_ofm.services.history import HistoryEntry, HistoryStore


def entry(
    source: str,
    translated: str,
    target: str = "uk",
    **kwargs,
) -> HistoryEntry:
    return HistoryEntry(
        source_text=source,
        translated_text=translated,
        target_code=target,
        **kwargs,
    )


def test_add_keeps_newest_first_and_persists(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    store = HistoryStore(path)
    first = entry("Hello", "Привіт")
    second = entry("Good morning", "Доброго ранку")

    store.add(first)
    store.add(second)

    assert [item.id for item in store.entries] == [second.id, first.id]
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert [item["id"] for item in stored] == [second.id, first.id]

    reloaded = HistoryStore(path)
    assert [item.id for item in reloaded.entries] == [second.id, first.id]
    assert reloaded.entries[0].source_text == "Good morning"


def test_add_skips_empty_text(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history.json")
    store.add(entry("   ", "Привіт"))
    store.add(entry("Hello", "\n\t"))
    assert store.entries == []


def test_add_suppresses_identical_head(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history.json")
    first = entry("Hello", "Привіт")
    store.add(first)
    store.add(entry("Hello", "Привіт"))
    assert len(store.entries) == 1

    # A different target language is a different translation, like the Swift code.
    store.add(entry("Hello", "Привіт", target="de"))
    assert [item.target_code for item in store.entries] == ["de", "uk"]


def test_cap_at_400_entries(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history.json")
    for index in range(HistoryStore.ENTRIES + 5):
        store.add(entry(f"Source {index}", f"Target {index}"))

    assert len(store.entries) == HistoryStore.ENTRIES
    assert store.entries[0].source_text == "Source 404"
    assert store.entries[-1].source_text == "Source 5"


def test_remove_and_unknown_id(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history.json")
    first = entry("One", "Uno")
    second = entry("Two", "Dos")
    store.add(first)
    store.add(second)

    store.remove(first.id)
    assert [item.id for item in store.entries] == [second.id]
    store.remove("missing-id")
    assert [item.id for item in store.entries] == [second.id]


def test_clear_writes_empty_list(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    store = HistoryStore(path)
    store.add(entry("Hello", "Привіт"))
    store.clear()

    assert store.entries == []
    assert json.loads(path.read_text(encoding="utf-8")) == []
    assert HistoryStore(path).entries == []


def test_search_is_case_insensitive_on_both_sides(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history.json")
    store.add(entry("Hello world", "Привіт, світе"))
    store.add(entry("Good morning", "Доброго ранку"))
    store.add(entry("Evening", "HeLLo again"))

    assert [item.source_text for item in store.search("HELLO")] == [
        "Evening",
        "Hello world",
    ]
    assert [item.source_text for item in store.search("привіт")] == [
        "Hello world"
    ]
    assert len(store.search("")) == 3
    assert store.search("absent") == []


def test_corrupt_file_is_tolerated_and_recovered(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    path.write_text("{definitely not json", encoding="utf-8", newline="")

    store = HistoryStore(path)
    assert store.entries == []
    assert store.has_storage_error is True
    assert store.search("anything") == []

    store.add(entry("Hello", "Привіт"))
    assert store.has_storage_error is False
    assert len(store.entries) == 1
    assert json.loads(path.read_text(encoding="utf-8"))[0]["source_text"] == "Hello"


def test_malformed_entries_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    path.write_text(
        json.dumps(
            [
                {"id": "a", "source_text": "Hello", "translated_text": "Привіт"},
                42,
                {"date": "2026-01-01T00:00:00+00:00"},
            ]
        ),
        encoding="utf-8",
    )

    store = HistoryStore(path)
    assert len(store.entries) == 2
    assert store.entries[0].id == "a"
    assert store.has_storage_error is False


def test_atomic_write_failure_keeps_previous_file(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "history.json"
    store = HistoryStore(path)
    first = entry("One", "Uno")
    store.add(first)
    before = path.read_text(encoding="utf-8")

    def broken_replace(source, destination):
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", broken_replace)
        store.add(entry("Two", "Dos"))

    assert store.has_storage_error is True
    assert [item.id for item in store.entries] == [first.id]
    assert path.read_text(encoding="utf-8") == before
    assert list(path.parent.glob("history.json.*.tmp")) == []


def test_write_recovers_after_transient_failure(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "history.json"
    store = HistoryStore(path)

    def broken_replace(source, destination):
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", broken_replace)
        store.add(entry("Lost", "Загублено"))
    assert store.has_storage_error is True
    assert store.entries == []

    store.add(entry("Kept", "Збережено"))
    assert store.has_storage_error is False
    assert [item.source_text for item in store.entries] == ["Kept"]
    assert json.loads(path.read_text(encoding="utf-8"))[0]["source_text"] == "Kept"


def test_nested_directory_is_created(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "nested" / "history.json"
    store = HistoryStore(path)
    store.add(entry("Hello", "Привіт"))
    assert path.is_file()


def test_entry_dict_round_trip_and_aliases() -> None:
    original = entry(
        "Hello",
        "Привіт",
        source_code="en",
        style="natural",
        tone="formal",
        engine="ollama",
        duration_ms=123,
    )
    restored = HistoryEntry.from_dict(original.to_dict())
    assert restored == original

    camel = HistoryEntry.from_dict(
        {
            "sourceText": "Hi",
            "translatedText": "Привіт",
            "sourceCode": "en",
            "targetCode": "uk",
            "durationMs": "42",
        }
    )
    assert camel.source_text == "Hi"
    assert camel.target_code == "uk"
    assert camel.duration_ms == 42
    assert camel.id


def test_default_path_follows_appdata(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    expected = tmp_path / "Roaming" / "DeepL-oFM" / "history.json"
    assert HistoryStore.default_path() == expected


def test_default_path_falls_back_to_home(monkeypatch) -> None:
    monkeypatch.delenv("APPDATA", raising=False)
    expected = Path.home() / ".config" / "DeepL-oFM" / "history.json"
    assert HistoryStore.default_path() == expected
