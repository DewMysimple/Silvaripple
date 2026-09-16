from __future__ import annotations

import hashlib
import os
import string
import ctypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

try:
    import winreg
except ImportError:  # pragma: no cover - Windows-only module
    winreg = None

from .config import windows_documents_directory
from .models import KeyCoverage, WechatAccount
from .redaction import stable_id


DB_GLOBS = (
    "db_storage/session/*.db",
    "db_storage/contact/*.db",
    "db_storage/message/*.db",
    "db_storage/media/*.db",
    "db_storage/hardlink/*.db",
    "db_storage/emoticon/*.db",
)

OPTIONAL_DB_GLOBS = (
    "db_storage/head_image/*.db",
)

ROOT_NAMES = ("xwechat_files", "WeChat Files")


@dataclass(frozen=True, slots=True)
class DataRootCandidate:
    path: Path
    source: str
    account_count: int
    latest_database_write: datetime | None = None

    def to_dict(self, selected: Path | None = None) -> dict[str, object]:
        return {
            "path": str(self.path),
            "source": self.source,
            "account_count": self.account_count,
            "latest_database_write": (
                self.latest_database_write.astimezone().isoformat(timespec="seconds")
                if self.latest_database_write
                else None
            ),
            "selected": bool(selected and _same_path(self.path, selected)),
        }


def database_files(account_dir: Path) -> list[Path]:
    found: dict[str, Path] = {}
    for pattern in DB_GLOBS:
        for path in account_dir.glob(pattern):
            if path.is_file() and not path.name.endswith(("-wal", "-shm")):
                found[str(path).casefold()] = path
    return sorted(found.values(), key=lambda item: str(item).casefold())


def optional_database_files(account_dir: Path) -> list[Path]:
    found: dict[str, Path] = {}
    for pattern in OPTIONAL_DB_GLOBS:
        for path in account_dir.glob(pattern):
            if path.is_file() and not path.name.endswith(("-wal", "-shm")):
                found[str(path).casefold()] = path
    return sorted(found.values(), key=lambda item: str(item).casefold())


def _same_path(left: Path, right: Path) -> bool:
    try:
        return os.path.normcase(str(left.resolve(strict=False))) == os.path.normcase(
            str(right.resolve(strict=False))
        )
    except OSError:
        return os.path.normcase(str(left)) == os.path.normcase(str(right))


def _account_directories(root: Path) -> list[Path]:
    try:
        children = list(root.iterdir()) if root.is_dir() else []
    except (OSError, PermissionError):
        return []
    return [
        child
        for child in children
        if child.is_dir() and child.name.casefold().startswith("wxid_") and database_files(child)
    ]


def normalize_data_root(value: Path) -> Path | None:
    """Return the account-container directory represented by a user selection.

    Users commonly select ``Documents``, ``WeChat Files``, ``xwechat_files`` or
    a single ``wxid_*`` account folder.  Accept all four shapes, but keep the
    search bounded to known WeChat folder names so choosing a drive root never
    triggers an expensive recursive scan.
    """
    path = value.expanduser().resolve(strict=False)
    if path.name.casefold().startswith("wxid_") and database_files(path):
        return path.parent
    if _account_directories(path):
        return path

    candidates = (
        path / "xwechat_files",
        path / "WeChat Files" / "xwechat_files",
        path / "WeChat Files",
    )
    for candidate in candidates:
        if _account_directories(candidate):
            return candidate.resolve(strict=False)
    return None


def _logical_drive_roots() -> Iterable[Path]:
    if os.name != "nt":
        return ()
    # Avoid probing network mappings.  Existing local drive letters are cheap
    # to inspect because only a few exact WeChat paths are tested under each.
    system_drive = os.environ.get("SystemDrive", "C:")
    values: list[Path] = []
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:\\")
        try:
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(str(root))  # type: ignore[attr-defined]
            if drive_type == 3 and root.is_dir():  # DRIVE_FIXED
                values.append(root)
        except OSError:
            continue
    system_root = Path(system_drive + "\\")
    if system_root.is_dir() and not any(_same_path(system_root, item) for item in values):
        values.insert(0, system_root)
    return values


def _registry_data_root_hints() -> list[Path]:
    """Read path-like WeChat settings without traversing user data files."""
    if winreg is None:
        return []
    hints: list[Path] = []
    documents = windows_documents_directory()
    keys = (
        r"Software\Tencent\xwechat",
        r"Software\Tencent\WeChat",
        r"Software\Tencent\Weixin",
    )
    for key_name in keys:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_name) as key:
                index = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, index)
                    except OSError:
                        break
                    index += 1
                    if not isinstance(value, str) or not any(
                        token in name.casefold() for token in ("path", "dir", "save", "document")
                    ):
                        continue
                    cleaned = os.path.expandvars(value.strip().strip('"'))
                    if cleaned.casefold().startswith("mydocument:"):
                        suffix = cleaned.partition(":")[2].lstrip("\\/")
                        hints.append(documents / suffix if suffix else documents)
                    elif cleaned:
                        hints.append(Path(cleaned))
        except OSError:
            continue
    unique: dict[str, Path] = {}
    for hint in hints:
        key = os.path.normcase(str(hint.expanduser().resolve(strict=False)))
        unique.setdefault(key, hint)
    return list(unique.values())


def _candidate_paths(saved_root: Path | None = None) -> list[tuple[Path, str]]:
    rows: list[tuple[Path, str]] = []
    if saved_root:
        rows.append((saved_root, "saved"))

    documents = windows_documents_directory()
    rows.extend((path, "registry") for path in _registry_data_root_hints())
    rows.extend(
        (
            (documents / "xwechat_files", "documents"),
            (documents / "WeChat Files" / "xwechat_files", "documents"),
            (documents / "WeChat Files", "documents"),
        )
    )
    fallback_documents = Path.home() / "Documents"
    if not _same_path(documents, fallback_documents):
        rows.extend(
            (
                (fallback_documents / "xwechat_files", "profile"),
                (fallback_documents / "WeChat Files" / "xwechat_files", "profile"),
            )
        )
    for key, value in os.environ.items():
        if key.casefold().startswith("onedrive") and value:
            root = Path(value) / "Documents"
            rows.extend(
                (
                    (root / "xwechat_files", "onedrive"),
                    (root / "WeChat Files" / "xwechat_files", "onedrive"),
                )
            )
    for key in ("APPDATA", "LOCALAPPDATA"):
        value = os.environ.get(key)
        if not value:
            continue
        root = Path(value) / "Tencent" / "WeChat" / "WeChat Files"
        rows.extend(
            (
                (root, "appdata"),
                (root / "xwechat_files", "appdata"),
            )
        )
    rows.extend(
        (
            (Path.home() / "WeChat Files", "profile"),
            (Path.home() / "WeChat Files" / "xwechat_files", "profile"),
            (Path.home() / "xwechat_files", "profile"),
        )
    )
    for drive in _logical_drive_roots():
        rows.extend(
            (
                (drive / "xwechat_files", "drive"),
                (drive / "WeChat Files" / "xwechat_files", "drive"),
                (drive / "WeChat Files", "drive"),
            )
        )
    return rows


def discover_data_roots(saved_root: Path | None = None) -> list[DataRootCandidate]:
    found: dict[str, DataRootCandidate] = {}
    for raw, source in _candidate_paths(saved_root):
        normalized = normalize_data_root(raw)
        if normalized is None:
            continue
        key = os.path.normcase(str(normalized))
        if key in found:
            continue
        accounts = _account_directories(normalized)
        latest = 0.0
        for account in accounts:
            for database in database_files(account):
                try:
                    latest = max(latest, database.stat().st_mtime)
                except OSError:
                    continue
        found[key] = DataRootCandidate(
            normalized,
            source,
            len(accounts),
            datetime.fromtimestamp(latest).astimezone() if latest else None,
        )
    return sorted(
        found.values(),
        key=lambda item: (
            item.source != "saved",
            -item.account_count,
            -(item.latest_database_write.timestamp() if item.latest_database_write else 0),
        ),
    )


def _tree_size(root: Path) -> int:
    total = 0
    for current, _, files in os.walk(root):
        for name in files:
            try:
                total += (Path(current) / name).stat().st_size
            except OSError:
                continue
    return total


def _salt_id(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.sha256(stream.read(16)).hexdigest()[:16]


def discover_accounts(data_root: Path, covered: dict[str, set[str]] | None = None) -> list[WechatAccount]:
    if not data_root.is_dir():
        return []
    covered = covered or {}
    rows: list[tuple[Path, list[Path], float]] = []
    for child in data_root.iterdir():
        if not child.is_dir() or not child.name.lower().startswith("wxid_"):
            continue
        databases = database_files(child)
        if not databases:
            continue
        latest = max((path.stat().st_mtime for path in databases), default=0.0)
        rows.append((child, databases, latest))
    newest = max((row[2] for row in rows), default=0.0)
    accounts: list[WechatAccount] = []
    for directory, databases, latest in rows:
        account_id = stable_id(directory.name)
        salts = {_salt_id(path) for path in databases if path.stat().st_size >= 16}
        known = covered.get(account_id, set())
        accounts.append(
            WechatAccount(
                account_id=account_id,
                directory=directory,
                display_name=f"未授权账号 {account_id[:6]}" if not known else f"微信账号 {account_id[:6]}",
                active=latest == newest,
                last_database_write=datetime.fromtimestamp(latest).astimezone() if latest else None,
                size_bytes=_tree_size(directory),
                database_count=len(databases),
                coverage=KeyCoverage(
                    covered=len(salts & known),
                    total=len(salts),
                    missing_databases=[path.name for path in databases if _salt_id(path) not in known],
                ),
            )
        )
    return sorted(accounts, key=lambda account: (not account.active, -(account.last_database_write.timestamp() if account.last_database_write else 0)))
