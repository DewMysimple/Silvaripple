from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import tempfile
from ctypes import wintypes
from pathlib import Path
from typing import Any

from .config import APP_DIR
from .redaction import fingerprint


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data: bytes) -> tuple[DATA_BLOB, Any]:
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def protect(data: bytes, entropy: bytes = b"ChatWechat/key-store/v1") -> bytes:
    if os.name != "nt":
        raise RuntimeError("DPAPI is available only on Windows")
    source, source_buffer = _blob(data)
    extra, extra_buffer = _blob(entropy)
    output = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    if not crypt32.CryptProtectData(
        ctypes.byref(source), "ChatWechat", ctypes.byref(extra), None, None, 0x01, ctypes.byref(output)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)
        del source_buffer, extra_buffer


def unprotect(data: bytes, entropy: bytes = b"ChatWechat/key-store/v1") -> bytes:
    if os.name != "nt":
        raise RuntimeError("DPAPI is available only on Windows")
    source, source_buffer = _blob(data)
    extra, extra_buffer = _blob(entropy)
    output = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, ctypes.byref(extra), None, None, 0x01, ctypes.byref(output)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)
        del source_buffer, extra_buffer


def salt_id(salt: bytes) -> str:
    return hashlib.sha256(salt).hexdigest()[:16]


class KeyStore:
    def __init__(self, app_dir: Path = APP_DIR):
        self.app_dir = app_dir
        self.path = app_dir / "keys.dpapi.json"

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if value.get("version") == 1 else {"version": 1, "accounts": {}}
        except (FileNotFoundError, json.JSONDecodeError, OSError, AttributeError):
            return {"version": 1, "accounts": {}}

    def _save(self, value: dict[str, Any]) -> None:
        self.app_dir.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix="keys-", suffix=".tmp", dir=self.app_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.path)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        finally:
            Path(temp_name).unlink(missing_ok=True)

    def put_database_key(self, account_id: str, salt: bytes, key: bytes) -> str:
        if len(salt) != 16 or len(key) != 32:
            raise ValueError("database salt must be 16 bytes and key must be 32 bytes")
        value = self._load()
        account = value["accounts"].setdefault(account_id, {"databases": {}, "images": {}})
        sid = salt_id(salt)
        account["databases"][sid] = {
            "protected": base64.b64encode(protect(key)).decode("ascii"),
            "fingerprint": fingerprint(key),
        }
        self._save(value)
        return sid

    def get_database_key(self, account_id: str, salt: bytes) -> bytes | None:
        row = self._load().get("accounts", {}).get(account_id, {}).get("databases", {}).get(salt_id(salt))
        if not row:
            return None
        return unprotect(base64.b64decode(row["protected"], validate=True))

    def put_image_key(self, account_id: str, kind: str, key: bytes) -> None:
        if not key:
            raise ValueError("image key cannot be empty")
        value = self._load()
        account = value["accounts"].setdefault(account_id, {"databases": {}, "images": {}})
        account["images"][kind] = {
            "protected": base64.b64encode(protect(key)).decode("ascii"),
            "fingerprint": fingerprint(key),
        }
        self._save(value)

    def get_image_key(self, account_id: str, kind: str) -> bytes | None:
        row = self._load().get("accounts", {}).get(account_id, {}).get("images", {}).get(kind)
        return unprotect(base64.b64decode(row["protected"], validate=True)) if row else None

    def covered_salts(self) -> dict[str, set[str]]:
        return {
            account_id: set(account.get("databases", {}))
            for account_id, account in self._load().get("accounts", {}).items()
        }

    def status(self, account_id: str) -> dict[str, Any]:
        account = self._load().get("accounts", {}).get(account_id, {})
        rows = list(account.get("databases", {}).values())
        return {
            "covered": len(rows),
            "fingerprints": sorted({row.get("fingerprint") for row in rows if row.get("fingerprint")}),
            "image_keys": sorted(account.get("images", {})),
        }
