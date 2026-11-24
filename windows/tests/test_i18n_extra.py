"""Consistency checks for the Windows-only translation table."""

from __future__ import annotations

import re

import pytest

from deepl_ofm.i18n import t
from deepl_ofm.i18n.extra import EXTRA

LANGUAGES = ("uk", "ru", "de", "fr", "es", "pl", "pt", "it")
PLACEHOLDER = re.compile(r"%(?:@|d|i|s|\.\d+f|f|g)")


def test_every_language_has_the_same_keys() -> None:
    reference = set(EXTRA["uk"])
    assert reference, "the extra table must not be empty"
    for code in LANGUAGES:
        assert set(EXTRA[code]) == reference, f"{code} has a different key set"
        assert all(value.strip() for value in EXTRA[code].values()), f"{code} has an empty value"


def test_placeholders_match_the_key() -> None:
    for code in LANGUAGES:
        for key, value in EXTRA[code].items():
            assert PLACEHOLDER.findall(key) == PLACEHOLDER.findall(value), (
                f"{code}: placeholder mismatch for {key!r} -> {value!r}"
            )


@pytest.mark.parametrize("code", LANGUAGES)
def test_extra_keys_are_reachable_through_t(code: str) -> None:
    for key, value in EXTRA[code].items():
        assert t(key, code) == value


def test_english_is_the_identity() -> None:
    for key in EXTRA["de"]:
        assert t(key, "en") == key


def test_generated_catalogue_wins_over_the_extra_table() -> None:
    from deepl_ofm.i18n import catalog

    for key in catalog.UKRAINIAN:
        assert key not in EXTRA["uk"] or EXTRA["uk"][key] == catalog.UKRAINIAN[key], (
            f"{key!r} is duplicated with a different translation"
        )
