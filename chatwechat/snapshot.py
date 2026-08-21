from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import time
import hashlib
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .config import temp_root
from .crypto import PAGE_SIZE, SQLITE_HEADER, WindowsCngAes, decrypt_page
from .errors import CorruptDatabase, SnapshotChanged
from .wal import apply_committed_wal


@dataclass(slots=True)
class FileState:
    size: int
    modified_ns: int


def _state(path: Path) -> FileState | None:
    try:
        stat = path.stat()
        return FileState(stat.st_size, stat.st_mtime_ns)
    except FileNotFoundError:
        return None


class TempManager:
    def __init__(self, root: Path | None = None):
        self.root = root or temp_root()
        self.root.mkdir(parents=True, exist_ok=True)

    def cleanup_stale(self, older_than_seconds: int = 24 * 3600) -> int:
        threshold = time.time() - older_than_seconds
        removed = 0
        for child in self.root.glob("task-*"):
            try:
                if child.stat().st_mtime < threshold:
                    shutil.rmtree(child)
                    removed += 1
            except OSError:
                continue
        return removed

    def create_task_dir(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="task-", dir=self.root))


class ReadOnlySnapshotter:
    def __init__(self, manager: TempManager | None = None, retries: int = 8):
        self.manager = manager or TempManager()
        self.retries = retries

    def copy_consistent(self, source: Path, task_dir: Path) -> Path:
        # Different WeChat database folders can contain the same basename.
        # Give every source a stable, private snapshot filename so concurrent
        # readers never contend for one Windows file handle.
        token = hashlib.sha256(str(source.resolve()).casefold().encode("utf-8")).hexdigest()[:12]
        destination = task_dir / f"{token}-{source.name}"
        wal_source = Path(str(source) + "-wal")
        for attempt in range(self.retries):
            before_db, before_wal = _state(source), _state(wal_source)
            if before_db is None:
                raise FileNotFoundError(source)
            wal_copy = task_dir / (destination.name + "-wal")
            try:
                shutil.copyfile(source, destination)
                if before_wal is not None:
                    shutil.copyfile(wal_source, wal_copy)
                else:
                    wal_copy.unlink(missing_ok=True)
            except OSError as error:
                destination.unlink(missing_ok=True)
                wal_copy.unlink(missing_ok=True)
                sharing_violation = getattr(error, "winerror", None) in {32, 33}
                changed_during_copy = isinstance(error, FileNotFoundError)
                if (sharing_violation or changed_during_copy) and attempt + 1 < self.retries:
                    time.sleep(min(0.6, 0.08 * (attempt + 1)))
                    continue
                if sharing_violation:
                    raise SnapshotChanged("微信正在使用数据库文件，多次重试仍无法建立只读快照；请稍后重试") from error
                if changed_during_copy:
                    raise SnapshotChanged("复制期间数据库或 WAL 已重置，请重试") from error
                raise
            after_db, after_wal = _state(source), _state(wal_source)
            if (before_db, before_wal) == (after_db, after_wal):
                if wal_copy.exists() and wal_copy.stat().st_size >= 32:
                    merged = apply_committed_wal(destination.read_bytes(), wal_copy.read_bytes())
                    destination.write_bytes(merged)
                return destination
            destination.unlink(missing_ok=True)
            wal_copy.unlink(missing_ok=True)
            time.sleep(min(0.6, 0.08 * (attempt + 1)))
        raise SnapshotChanged("复制期间数据库或 WAL 发生变化，请重试；持续失败时请暂时退出微信")

    def decrypt(self, encrypted: Path, key: bytes, output: Path | None = None) -> Path:
        output = output or encrypted.with_suffix(".sqlite")
        size = encrypted.stat().st_size
        if size < PAGE_SIZE or size % PAGE_SIZE:
            raise CorruptDatabase("数据库长度不是 4096 字节页的整数倍")
        with encrypted.open("rb") as stream:
            salt = stream.read(16)
        aes = WindowsCngAes()
        with encrypted.open("rb") as source, output.open("wb") as target:
            for page_number in range(1, size // PAGE_SIZE + 1):
                page = source.read(PAGE_SIZE)
                target.write(decrypt_page(page, page_number, key, salt, aes))
            target.flush()
            os.fsync(target.fileno())
        with output.open("rb") as stream:
            if stream.read(16) != SQLITE_HEADER:
                output.unlink(missing_ok=True)
                raise CorruptDatabase("解密结果缺少 SQLite 文件头")
        try:
            validate_sqlite_structure(output)
        except sqlite3.DatabaseError as error:
            output.unlink(missing_ok=True)
            raise CorruptDatabase("SQLite 结构检查失败") from error
        except CorruptDatabase:
            output.unlink(missing_ok=True)
            raise
        return output


def _pragma_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def validate_sqlite_structure(path: Path) -> None:
    """Validate a decrypted snapshot without loading WeChat's private FTS tokenizers.

    A database-wide quick_check initializes every virtual table. WeChat FTS databases
    reference MMFtsTokenizer, which is not part of Python's SQLite build. Checking each
    ordinary/shadow table preserves SQLite B-tree and index validation while leaving the
    virtual-table facade to WeChat. ``immutable=1`` also prevents read-only validation
    from creating WAL/SHM sidecars or retaining Windows file locks.
    """
    uri = f"file:{path.resolve().as_posix()}?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        tables = connection.execute(
            "SELECT name, COALESCE(sql, '') FROM sqlite_master "
            "WHERE type = 'table' ORDER BY name"
        ).fetchall()
        checkable = [
            str(name) for name, sql in tables
            if not str(sql).lstrip().casefold().startswith("create virtual table")
        ]
        checks = checkable or [None]
        for table in checks:
            statement = "PRAGMA quick_check" if table is None else f"PRAGMA quick_check({_pragma_string(table)})"
            results = connection.execute(statement).fetchall()
            if not results or any(str(row[0]).casefold() != "ok" for row in results):
                raise CorruptDatabase("SQLite 结构检查失败")
