"""API-key storage.

Ported from ``Sources/HyMT/Support/Keychain.swift``.  On Windows the keys live
in the Credential Manager through :mod:`keyring`; when that is unavailable they
are encrypted with DPAPI (user scope) into ``secrets.dat``.  Everywhere else a
``0600`` JSON file is used.  Read/write/delete never raise — the application
degrades to an empty key and logs the problem.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SERVICE = "ua.admin.hymt"
_WINDOWS = sys.platform == "win32"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01

_dpapi_instance: _Dpapi | None = None
_dpapi_failed = False
_dpapi_lock = threading.Lock()


def _keyring_available() -> bool:
    """Whether keyring imports and has a usable (non-failing) backend."""
    try:
        import keyring
        from keyring.backends import fail
    except Exception:
        return False
    try:
        backend = keyring.get_keyring()
    except Exception:
        return False
    if backend is None:
        return False
    if isinstance(backend, fail.Keyring):
        return False
    name = f"{type(backend).__module__}.{type(backend).__name__}".lower()
    return "fail" not in name and "null" not in name


class _Dpapi:
    """Minimal ``CryptProtectData``/``CryptUnprotectData`` wrapper (user scope)."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class DataBlob(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char)),
            ]

        self._ctypes = ctypes
        self._DataBlob = DataBlob
        self._crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        blob_ptr = ctypes.POINTER(DataBlob)
        self._crypt32.CryptProtectData.argtypes = [
            blob_ptr,
            wintypes.LPCWSTR,
            blob_ptr,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            blob_ptr,
        ]
        # CryptUnprotectData's second parameter is an output LPWSTR*, not input.
        self._crypt32.CryptUnprotectData.argtypes = [
            blob_ptr,
            ctypes.POINTER(wintypes.LPWSTR),
            blob_ptr,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            blob_ptr,
        ]
        self._crypt32.CryptProtectData.restype = wintypes.BOOL
        self._crypt32.CryptUnprotectData.restype = wintypes.BOOL
        self._kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        self._kernel32.LocalFree.restype = wintypes.HLOCAL

    def _blob(self, data: bytes) -> tuple[Any, Any]:
        ctypes = self._ctypes
        buffer = ctypes.create_string_buffer(data, len(data))
        blob = self._DataBlob(
            len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))
        )
        return blob, buffer

    def _take_result(self, blob: Any) -> bytes:
        ctypes = self._ctypes
        try:
            return ctypes.string_at(blob.pbData, blob.cbData)
        finally:
            self._kernel32.LocalFree(
                ctypes.cast(blob.pbData, ctypes.c_void_p)
            )

    def protect(self, data: bytes) -> bytes:
        if not data:
            return b""
        ctypes = self._ctypes
        blob_in, _keep_alive = self._blob(data)
        blob_out = self._DataBlob()
        ok = self._crypt32.CryptProtectData(
            ctypes.byref(blob_in),
            None,
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(blob_out),
        )
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        return self._take_result(blob_out)

    def unprotect(self, data: bytes) -> bytes:
        if not data:
            return b""
        ctypes = self._ctypes
        blob_in, _keep_alive = self._blob(data)
        blob_out = self._DataBlob()
        ok = self._crypt32.CryptUnprotectData(
            ctypes.byref(blob_in),
            None,
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(blob_out),
        )
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        return self._take_result(blob_out)


def _get_dpapi() -> _Dpapi:
    global _dpapi_instance, _dpapi_failed
    with _dpapi_lock:
        if _dpapi_instance is None:
            if _dpapi_failed:
                raise OSError("DPAPI is not available")
            try:
                _dpapi_instance = _Dpapi()
            except Exception:
                _dpapi_failed = True
                raise
        return _dpapi_instance


def _atomic_write_text(path: Path, text: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    temp_path = Path(temp_name)
    try:
        if mode is not None and not _WINDOWS:
            os.chmod(temp_name, mode)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        if mode is not None and not _WINDOWS:
            try:
                os.chmod(path, mode)
            except OSError:
                pass
    except BaseException:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


class SecretStore:
    """One secret per account, mirroring ``Keychain``'s read/write/delete API."""

    SERVICE = SERVICE

    def __init__(self, path: Path | None = None) -> None:
        self._lock = threading.RLock()
        if path is not None:
            # An explicit path always selects the file backend, which keeps
            # tests hermetic and lets callers relocate the vault.
            self._backend = self._file_backend()
            self._path = Path(path)
        else:
            self._backend = self._detect_backend()
            self._path = self._default_path(self._backend)

    # -- backend selection --------------------------------------------------

    @staticmethod
    def _file_backend() -> str:
        if _WINDOWS:
            try:
                _get_dpapi()
            except Exception:
                logger.warning("DPAPI is unavailable; storing secrets unencrypted")
                return "plain"
            return "dpapi"
        return "plain"

    @classmethod
    def _detect_backend(cls) -> str:
        if _WINDOWS and _keyring_available():
            return "keyring"
        return cls._file_backend()

    @staticmethod
    def _default_path(backend: str) -> Path:
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / ".config"
        name = "secrets.dat" if backend == "dpapi" else "secrets.json"
        return base / "DeepL-oFM" / name

    def backend_name(self) -> str:
        """``"keyring"``, ``"dpapi"`` or ``"plain"``."""
        return self._backend

    @property
    def path(self) -> Path:
        return self._path

    # -- public API ---------------------------------------------------------

    def read(self, account: str) -> str:
        name = (account or "").strip()
        if not name:
            return ""
        with self._lock:
            try:
                if self._backend == "keyring":
                    return self._keyring_read(name)
                return self._read_file().get(name, "")
            except Exception as exc:
                logger.warning("could not read secret %r: %s", name, exc)
                return ""

    def write(self, account: str, value: str) -> None:
        name = (account or "").strip()
        if not name:
            return
        secret = (value or "").strip()
        if not secret:
            self.delete(name)
            return
        with self._lock:
            try:
                if self._backend == "keyring":
                    self._keyring_write(name, secret)
                    return
                values = self._read_file()
                values[name] = secret
                self._write_file(values)
            except Exception as exc:
                logger.warning("could not store secret %r: %s", name, exc)

    def delete(self, account: str) -> None:
        name = (account or "").strip()
        if not name:
            return
        with self._lock:
            try:
                if self._backend == "keyring":
                    self._keyring_delete(name)
                    return
                values = self._read_file()
                if name not in values:
                    return
                del values[name]
                self._write_file(values)
            except Exception as exc:
                logger.warning("could not delete secret %r: %s", name, exc)

    # -- keyring ------------------------------------------------------------

    def _keyring_read(self, account: str) -> str:
        import keyring

        return keyring.get_password(self.SERVICE, account) or ""

    def _keyring_write(self, account: str, value: str) -> None:
        import keyring

        keyring.set_password(self.SERVICE, account, value)

    def _keyring_delete(self, account: str) -> None:
        import keyring
        from keyring.errors import PasswordDeleteError

        try:
            keyring.delete_password(self.SERVICE, account)
        except PasswordDeleteError:
            pass

    # -- file ---------------------------------------------------------------

    def _read_file(self) -> dict[str, str]:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except OSError as exc:
            logger.warning("could not read secret file %s: %s", self._path, exc)
            return {}
        try:
            document = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning("secret file %s is not valid JSON", self._path)
            return {}
        if not isinstance(document, dict):
            logger.warning("secret file %s does not contain an object", self._path)
            return {}
        values = document.get("values", document)
        if not isinstance(values, dict):
            return {}
        result: dict[str, str] = {}
        for account, stored in values.items():
            if not isinstance(account, str) or not isinstance(stored, str):
                continue
            if self._backend == "dpapi":
                try:
                    blob = base64.b64decode(stored.encode("ascii"), validate=True)
                    result[account] = _get_dpapi().unprotect(blob).decode("utf-8")
                except Exception as exc:
                    logger.warning("could not decrypt secret %r: %s", account, exc)
            else:
                result[account] = stored
        return result

    def _write_file(self, values: dict[str, str]) -> None:
        stored: dict[str, str] = {}
        for account, value in values.items():
            if self._backend == "dpapi":
                blob = _get_dpapi().protect(value.encode("utf-8"))
                stored[account] = base64.b64encode(blob).decode("ascii")
            else:
                stored[account] = value
        document = {
            "version": 1,
            "backend": self._backend,
            "values": stored,
        }
        payload = json.dumps(document, ensure_ascii=False, indent=2)
        _atomic_write_text(self._path, payload + "\n", mode=0o600)
