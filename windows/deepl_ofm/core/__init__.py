"""Pure-Python domain models: languages, providers, shortcuts, catalogue, settings.

This package re-exports the public names of the modules owned by the Windows
port: :mod:`deepl_ofm.core.languages`, :mod:`deepl_ofm.core.providers`,
:mod:`deepl_ofm.core.keycombo`, :mod:`deepl_ofm.core.catalog` and
:mod:`deepl_ofm.core.settings`.
"""
from __future__ import annotations

from deepl_ofm.core.catalog import CatalogEntry, ModelCatalog
from deepl_ofm.core.keycombo import KeyCombo
from deepl_ofm.core.languages import (
    ALL,
    AUTO,
    AppLanguage,
    Language,
    LanguageTable,
    coerce_app_language,
    detect_language,
    get_language,
    translate,
)
from deepl_ofm.core.providers import BackendConfig, BackendKind, Provider
from deepl_ofm.core.settings import AppSettings

__all__ = [
    "ALL",
    "AUTO",
    "AppLanguage",
    "AppSettings",
    "BackendConfig",
    "BackendKind",
    "CatalogEntry",
    "KeyCombo",
    "Language",
    "LanguageTable",
    "ModelCatalog",
    "Provider",
    "coerce_app_language",
    "detect_language",
    "get_language",
    "translate",
]
