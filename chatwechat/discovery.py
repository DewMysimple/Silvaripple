from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path

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
