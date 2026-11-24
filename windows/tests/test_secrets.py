"""Tests for ``deepl_ofm.services.secrets`` (port of Keychain.swift)."""
from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

from deepl_ofm.services.secrets import SecretStore


def make_store(tmp_path: Path) -> SecretStore:
    return SecretStore(tmp_path / "secrets.json")


def test_backend_name() -> None:
    store = make_store(Path("/nonexistent/DeepL-oFM"))
    assert isinstance(store.backend_name(), str)
    if sys.platform == "win32":
        # An explicit path selects the file backend: DPAPI, or plain if it fails.
        assert store.backend_name() in {"dpapi", "plain"}
    else:
        assert store.backend_name() == "plain"


def test_default_backend_name() -> None:
    store = SecretStore()
    assert isinstance(store.backend_name(), str)
    if sys.platform == "win32":
        assert store.backend_name() in {"keyring", "dpapi", "plain"}
    else:
        assert store.backend_name() == "plain"


def test_round_trip_with_non_ascii(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    assert store.read("provider:openai") == ""

    store.write("provider:openai", "sk-ключ-🔑-ü")
    assert store.read("provider:openai") == "sk-ключ-🔑-ü"

    other = SecretStore(tmp_path / "secrets.json")
    assert other.read("provider:openai") == "sk-ключ-🔑-ü"


def test_write_trims_whitespace_like_the_swift_store(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.write("provider:groq", "  gsk-123\n")
    assert store.read("provider:groq") == "gsk-123"


def test_multiple_accounts(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.write("provider:openai", "one")
    store.write("provider:groq", "two")
    assert store.read("provider:openai") == "one"
    assert store.read("provider:groq") == "two"

    store.delete("provider:openai")
    assert store.read("provider:openai") == ""
    assert store.read("provider:groq") == "two"


def test_empty_value_deletes_account(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.write("provider:openai", "sk-1")
    store.write("provider:openai", "   ")
    assert store.read("provider:openai") == ""


def test_delete_missing_account_is_silent(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.delete("never-written")
    store.delete("")
    assert store.read("never-written") == ""


def test_missing_account_and_missing_file(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    assert store.read("provider:openai") == ""
    assert not (tmp_path / "secrets.json").exists()


def test_file_permissions_are_owner_only(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    if sys.platform == "win32" or store.backend_name() != "plain":
        pytest.skip("POSIX file modes do not apply to this backend")
    store.write("account", "value")
    mode = stat.S_IMODE((tmp_path / "secrets.json").stat().st_mode)
    assert mode == 0o600


def test_file_document_shape(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.write("account", "value")
    document = json.loads((tmp_path / "secrets.json").read_text(encoding="utf-8"))
    assert document["version"] == 1
    assert document["backend"] == store.backend_name()
    if store.backend_name() == "plain":
        assert document["values"] == {"account": "value"}
    else:
        assert set(document["values"]) == {"account"}
        assert document["values"]["account"] != "value"


def test_corrupt_file_degrades_and_recovers(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    path.write_text("{not json", encoding="utf-8", newline="")
    store = make_store(tmp_path)

    assert store.read("account") == ""
    store.write("account", "value")
    assert store.read("account") == "value"
    values = json.loads(path.read_text(encoding="utf-8"))["values"]
    if store.backend_name() == "plain":
        assert values == {"account": "value"}
    else:
        assert set(values) == {"account"}


def test_directory_as_path_never_raises(tmp_path: Path) -> None:
    store = SecretStore(tmp_path)
    assert store.read("account") == ""
    store.write("account", "value")
    store.delete("account")
    assert store.read("account") == ""


def test_nested_directory_is_created(tmp_path: Path) -> None:
    store = SecretStore(tmp_path / "nested" / "deeper" / "secrets.json")
    store.write("account", "value")
    assert store.read("account") == "value"
    assert (tmp_path / "nested" / "deeper" / "secrets.json").is_file()


def test_read_never_raises_on_bad_types(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    path.write_text(json.dumps({"values": {"ok": "yes", "bad": 12}}), encoding="utf-8", newline="")
    store = make_store(tmp_path)
    if store.backend_name() == "plain":
        assert store.read("ok") == "yes"
    else:
        assert store.read("ok") == ""
    assert store.read("bad") == ""
