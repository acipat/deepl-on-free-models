"""JSON-backed translation history.

Ported from ``Sources/HyMT/Services/HistoryStore.swift``.  Entries are kept
newest-first, capped at 400, written atomically and loaded tolerantly so a
corrupt file never prevents the application from starting.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)

MAX_ENTRIES = 400

_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "id": ("id",),
    "date": ("date",),
    "source_text": ("source_text", "sourceText"),
    "translated_text": ("translated_text", "translatedText"),
    "source_code": ("source_code", "sourceCode"),
    "target_code": ("target_code", "targetCode"),
    "style": ("style",),
    "tone": ("tone",),
    "engine": ("engine",),
    "duration_ms": ("duration_ms", "durationMs"),
}


def _now_iso() -> str:
    """Local time with an explicit UTC offset, ISO-8601."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _pick(data: Mapping[str, Any], name: str, default: Any) -> Any:
    for key in _KEY_ALIASES.get(name, (name,)):
        if key in data and data[key] is not None:
            return data[key]
    return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class HistoryEntry:
    """One finished translation, matching the Swift ``HistoryEntry`` model."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    date: str = field(default_factory=_now_iso)
    source_text: str = ""
    translated_text: str = ""
    source_code: str = "auto"
    target_code: str = "en"
    style: str = "auto"
    tone: str = "standard"
    engine: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "date": self.date,
            "source_text": self.source_text,
            "translated_text": self.translated_text,
            "source_code": self.source_code,
            "target_code": self.target_code,
            "style": self.style,
            "tone": self.tone,
            "engine": self.engine,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def create(
        cls,
        source_text: str,
        translated_text: str,
        source_code: str = "auto",
        target_code: str = "en",
        style: str = "auto",
        tone: str = "standard",
        engine: str = "",
        duration_ms: int = 0,
    ) -> HistoryEntry:
        """Convenience constructor used by the controller (id/date generated)."""
        return cls(
            source_text=source_text,
            translated_text=translated_text,
            source_code=source_code,
            target_code=target_code,
            style=style,
            tone=tone,
            engine=engine,
            duration_ms=duration_ms,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> HistoryEntry:
        """Build an entry from stored JSON, tolerating missing/extra fields."""
        if not isinstance(data, Mapping):
            raise TypeError("history entry must be a JSON object")
        entry_id = str(_pick(data, "id", "") or "").strip() or str(uuid.uuid4())
        date = str(_pick(data, "date", "") or "").strip() or _now_iso()
        return cls(
            id=entry_id,
            date=date,
            source_text=str(_pick(data, "source_text", "") or ""),
            translated_text=str(_pick(data, "translated_text", "") or ""),
            source_code=str(_pick(data, "source_code", "auto") or "auto"),
            target_code=str(_pick(data, "target_code", "en") or "en"),
            style=str(_pick(data, "style", "auto") or "auto"),
            tone=str(_pick(data, "tone", "standard") or "standard"),
            engine=str(_pick(data, "engine", "") or ""),
            duration_ms=_as_int(_pick(data, "duration_ms", 0)),
        )


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (temp file in the same folder)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def _fsync_directory(folder: Path) -> None:
    """Make the rename itself durable on POSIX; a no-op on Windows."""
    if sys.platform == "win32":
        return
    try:
        fd = os.open(folder, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


class HistoryStore:
    """Thread-safe, disk-backed history — the counterpart of ``HistoryStore``."""

    ENTRIES = MAX_ENTRIES

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path is not None else self.default_path()
        self._lock = threading.Lock()
        self._entries: list[HistoryEntry] = []
        self._has_storage_error = False
        self.load()

    # -- public state -------------------------------------------------------

    @property
    def entries(self) -> list[HistoryEntry]:
        """Newest-first copy of the stored entries."""
        with self._lock:
            return list(self._entries)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def has_storage_error(self) -> bool:
        with self._lock:
            return self._has_storage_error

    # -- disk ---------------------------------------------------------------

    @staticmethod
    def default_path() -> Path:
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / ".config"
        return base / "DeepL-oFM" / "history.json"

    def load(self) -> None:
        """(Re)read the JSON file; never raises on corrupt or unreadable data."""
        with self._lock:
            self._load_locked()

    def _load_locked(self) -> None:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._entries = []
            self._has_storage_error = False
            return
        except OSError as exc:
            logger.warning("could not read history file %s: %s", self._path, exc)
            self._entries = []
            self._has_storage_error = True
            return

        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning("history file %s is not valid JSON", self._path)
            self._entries = []
            self._has_storage_error = True
            return

        if not isinstance(data, list):
            logger.warning("history file %s does not contain a list", self._path)
            self._entries = []
            self._has_storage_error = True
            return

        entries: list[HistoryEntry] = []
        for item in data:
            try:
                entries.append(HistoryEntry.from_dict(item))
            except (TypeError, ValueError, AttributeError):
                logger.warning("skipping a malformed history entry in %s", self._path)
        self._entries = entries[: self.ENTRIES]
        self._has_storage_error = False

    def _commit_locked(self, updated: list[HistoryEntry]) -> bool:
        try:
            payload = json.dumps(
                [entry.to_dict() for entry in updated],
                ensure_ascii=False,
                indent=2,
            )
            _atomic_write_text(self._path, payload + "\n")
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("could not write history file %s: %s", self._path, exc)
            self._has_storage_error = True
            return False
        self._entries = updated
        self._has_storage_error = False
        return True

    # -- mutations ----------------------------------------------------------

    def add(self, entry: HistoryEntry) -> None:
        """Insert at the top, like the Swift store: empty/duplicate heads skip."""
        if not entry.source_text.strip() or not entry.translated_text.strip():
            return
        with self._lock:
            head = self._entries[0] if self._entries else None
            if (
                head is not None
                and head.source_text == entry.source_text
                and head.translated_text == entry.translated_text
                and head.target_code == entry.target_code
            ):
                return
            updated = [entry, *self._entries]
            if len(updated) > self.ENTRIES:
                del updated[self.ENTRIES:]
            self._commit_locked(updated)

    def remove(self, entry_id: str) -> None:
        with self._lock:
            updated = [entry for entry in self._entries if entry.id != entry_id]
            if len(updated) == len(self._entries):
                return
            self._commit_locked(updated)

    def clear(self) -> None:
        with self._lock:
            self._commit_locked([])

    # -- queries ------------------------------------------------------------

    def search(self, query: str) -> list[HistoryEntry]:
        """Case-insensitive search over the source and translated text."""
        needle = (query or "").strip().casefold()
        with self._lock:
            entries = list(self._entries)
        if not needle:
            return entries
        return [
            entry
            for entry in entries
            if needle in entry.source_text.casefold()
            or needle in entry.translated_text.casefold()
        ]
