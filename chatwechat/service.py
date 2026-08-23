from __future__ import annotations

import shutil
import os
import json
import re
import sqlite3
import tempfile
import threading
import traceback
import uuid
import hashlib
import ctypes
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import __version__
from .config import APP_DIR, Settings, SettingsStore
from .discovery import database_files, discover_accounts
from .errors import ChatWechatError, OperationCancelled
from .exporters import export_archive
from .key_capture import authorize, is_admin, run_elevated
from .keystore import KeyStore
from .models import (
    AccountStatisticsReport, ExportEstimate, ExportPreset, ExportRequest, MediaIssue, MediaRecoveryItem,
    MediaRecoveryReport, SearchResult, WechatAccount,
)
from .redaction import redact
from .repository import WechatRepository
from .snapshot import TempManager
from .infrastructure.runtime import RuntimeLocator


@dataclass(slots=True)
class Operation:
    operation_id: str
    kind: str
    status: str = "pending"
    progress: float = 0.0
    message: str = "等待开始"
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))
    progress_detail: dict[str, Any] = field(default_factory=dict)
    cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "kind": self.kind,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "progress_detail": self.progress_detail,
        }


class OperationManager:
    def __init__(self):
        self.operations: dict[str, Operation] = {}
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="chatwechat")

    def start(self, kind: str, worker: Any, completion: Any | None = None) -> Operation:
        operation = Operation(uuid.uuid4().hex, kind)
        with self.lock:
            self.operations[operation.operation_id] = operation

        def run() -> None:
            with self.lock:
                operation.status = "running"
                operation.message = "正在处理"

            def progress(value: float, message: str, detail: dict[str, Any] | None = None) -> None:
                with self.lock:
                    operation.progress = max(operation.progress, min(1.0, float(value)))
                    operation.message = message
                    if detail is not None:
                        operation.progress_detail = dict(detail)

            try:
                result = worker(operation.cancel, progress)
                with self.lock:
                    operation.status = "completed"
                    operation.progress = 1.0
                    operation.message = "已完成"
                    operation.result = result
            except Exception as error:
                with self.lock:
                    operation.status = "cancelled" if operation.cancel.is_set() else "failed"
                    operation.message = "已取消" if operation.cancel.is_set() else "处理失败"
                    operation.error = redact(error)
            finally:
                if completion:
                    try:
                        # Keep terminal state and its persistent history update
                        # observable as one unit to polling clients.
                        with self.lock:
                            completion(operation)
                    except Exception:
                        pass

        self.executor.submit(run)
        return operation

    def get(self, operation_id: str) -> dict[str, Any]:
        with self.lock:
            operation = self.operations.get(operation_id)
            if operation is None:
                raise ChatWechatError("任务不存在")
            return operation.to_dict()

    def cancel(self, operation_id: str) -> dict[str, Any]:
        with self.lock:
            operation = self.operations.get(operation_id)
            if operation is None:
                raise ChatWechatError("任务不存在")
            operation.cancel.set()
            operation.message = "正在取消"
            return operation.to_dict()


class JsonListStore:
    """Small atomic metadata store. It never receives messages or search text."""

    def __init__(self, path: Path, maximum: int = 100):
        self.path = path
        self.maximum = maximum
        self.lock = threading.RLock()

    def load(self) -> list[dict[str, Any]]:
        with self.lock:
            try:
                value = json.loads(self.path.read_text(encoding="utf-8"))
                return value if isinstance(value, list) else []
            except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
                return []

    def save(self, rows: list[dict[str, Any]]) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temp_name = tempfile.mkstemp(prefix=self.path.stem + "-", suffix=".tmp", dir=self.path.parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                    json.dump(rows[-self.maximum :], stream, ensure_ascii=False, indent=2)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_name, self.path)
            finally:
                Path(temp_name).unlink(missing_ok=True)

class ChatWechatService:
    _INTERNAL_CONVERSATION_NAMES = {
        "brandsessionholder",
        "brandservicesessionholder",
        "placeholder_foldgroup",
        "placeholder_flodgroup",
        "服务通知",
    }

    @classmethod
    def _is_internal_conversation(cls, row: Any) -> bool:
        """Hide WeChat navigation placeholders that are not real conversations."""
        values = {
            str(getattr(row, "username", "") or "").strip().lstrip("@").casefold(),
            str(getattr(row, "display_name", "") or "").strip().lstrip("@").casefold(),
        }
        return bool(values & cls._INTERNAL_CONVERSATION_NAMES)

    def __init__(self):
        self.settings_store = SettingsStore()
        self.settings = self.settings_store.load()
        self.key_store = KeyStore()
        self.temp_manager = TempManager()
        self.temp_manager.cleanup_stale()
        self.operations = OperationManager()
        self.history_store = JsonListStore(APP_DIR / "operation-history.json")
        self.preset_store = JsonListStore(APP_DIR / "export-presets.json", maximum=50)
        self.statistics_store = JsonListStore(APP_DIR / "account-statistics.json", maximum=20)
        self.repositories: dict[str, WechatRepository] = {}
        self.accounts: dict[str, WechatAccount] = {}
        self.estimate_cache: dict[str, dict[str, Any]] = {}
        self.approved_output_dirs = {str(Path(self.settings.output_directory).resolve())}
        self.active_export_roots: set[str] = set()
        self.lock = threading.RLock()
        self._migrate_operation_history()

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def _migrate_operation_history(self) -> None:
        rows = self.history_store.load()
        changed = False
        for row in rows:
            if row.get("status") in {"pending", "running"}:
                row["status"] = "interrupted"
                row["completed_at"] = self._now()
                row["error_summary"] = "应用在任务完成前退出"
                changed = True
            path = row.get("current_path") or row.get("result_path")
            defaults = {
                "duration_seconds": None, "error_summary": None, "result_summary": {},
                "directory_health": "missing" if row.get("kind") == "export" and path else "not_applicable",
                "original_path": row.get("result_path"), "current_path": path,
                "archive_id": None, "deleted_at": None,
                "storage_mode": "batch", "export_id": None,
                "conversation_archives": [], "superseded_count": 0,
            }
            for key, value in defaults.items():
                if key not in row:
                    row[key] = value
                    changed = True
        if changed:
            self.history_store.save(rows)

    def _begin_history(self, kind: str, result_summary: dict[str, Any] | None = None) -> str:
        history_id = uuid.uuid4().hex
        rows = self.history_store.load()
        rows.append({
            "history_id": history_id, "kind": kind, "status": "running",
            "created_at": self._now(), "completed_at": "", "result_path": None,
            "conversation_count": 0, "message_count": 0, "media_count": 0,
            "formats": [], "warnings": [], "warning_details": [],
            "duration_seconds": None, "error_summary": None,
            "result_summary": result_summary or {}, "directory_health": "not_applicable",
            "original_path": None, "current_path": None, "archive_id": None, "deleted_at": None,
            "storage_mode": "batch", "export_id": None,
            "conversation_archives": [], "superseded_count": 0,
        })
        self.history_store.save(rows)
        return history_id

    def _update_history(self, history_id: str, value: dict[str, Any]) -> dict[str, Any] | None:
        rows = self.history_store.load()
        found = None
        for row in rows:
            if row.get("history_id") == history_id:
                row.update(value)
                found = row
                break
        if found is not None:
            self.history_store.save(rows)
        return found

    def _finish_history(self, history_id: str, operation: Operation, extra: dict[str, Any] | None = None) -> None:
        try:
            started = datetime.fromisoformat(operation.created_at)
            duration = max(0.0, (datetime.now().astimezone() - started).total_seconds())
        except (TypeError, ValueError):
            duration = None
        value = {
            "status": operation.status, "completed_at": self._now(),
            "duration_seconds": duration, "error_summary": operation.error,
        }
        if extra:
            value.update(extra)
        self._update_history(history_id, value)

    def _database_fingerprint(self, account: WechatAccount) -> str:
        rows = []
        for path in database_files(account.directory):
            try:
                stat = path.stat()
                rows.append((path.relative_to(account.directory).as_posix(), stat.st_size, stat.st_mtime_ns))
            except OSError:
                continue
        payload = {"files": rows, "coverage": account.coverage.fingerprint or "", "covered": account.coverage.covered}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _read_root_manifest(path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads((path / "_chatwechat_export.json").read_text(encoding="utf-8"))
            return value if isinstance(value, dict) and value.get("archive_id") else None
        except (OSError, ValueError, TypeError):
            return None

    @staticmethod
    def _read_conversation_manifest(path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads((path / "_export_manifest.json").read_text(encoding="utf-8"))
            return value if isinstance(value, dict) and value.get("conversation_archive_id") else None
        except (OSError, ValueError, TypeError):
            return None

    def _shared_archive_index(self, root: Path | None = None) -> dict[str, Path]:
        root = (root or Path(self.settings.output_directory)).resolve()
        if not root.is_dir():
            return {}
        result: dict[str, Path] = {}
        root_parts = len(root.parts)
        checked = 0
        for current, directories, files in os.walk(root, followlinks=False):
            current_path = Path(current)
            depth = len(current_path.parts) - root_parts
            directories[:] = [name for name in directories if not name.startswith((".", "$"))]
            if depth >= 4:
                directories[:] = []
            checked += 1
            if checked > 4000 or "_export_manifest.json" not in files:
                continue
            manifest = self._read_conversation_manifest(current_path)
            if manifest and manifest.get("storage_mode") == "shared":
                result[str(manifest["conversation_archive_id"])] = current_path
        return result

    @staticmethod
    def _is_legacy_archive(path: Path) -> bool:
        try:
            for manifest_path in path.glob("*/*/_export_manifest.json"):
                try:
                    value = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, ValueError, TypeError):
                    continue
                if not isinstance(value, dict) or value.get("storage_mode") != "shared":
                    return True
            return False
        except OSError:
            return False

    def _validate_archive(self, path: Path) -> tuple[bool, str | None]:
        manifest = self._read_root_manifest(path)
        if manifest:
            return True, str(manifest.get("archive_id"))
        return self._is_legacy_archive(path), None

    def _archive_index(self) -> tuple[dict[str, Path], dict[str, Path]]:
        root = Path(self.settings.output_directory)
        if not root.is_dir():
            return {}, {}
        by_id: dict[str, Path] = {}
        by_name: dict[str, Path] = {}
        checked = 0
        root_parts = len(root.resolve().parts)
        for current, dirs, _files in os.walk(root, followlinks=False):
            current_path = Path(current)
            depth = len(current_path.resolve().parts) - root_parts
            dirs[:] = [name for name in dirs if not name.startswith((".", "$"))]
            if depth >= 4:
                dirs[:] = []
            checked += 1
            if checked > 2000:
                break
            manifest = self._read_root_manifest(current_path)
            if manifest:
                by_id[str(manifest["archive_id"])] = current_path
            elif self._is_legacy_archive(current_path):
                by_name.setdefault(current_path.name, current_path)
        return by_id, by_name

    def _find_archive_in_output(
        self, row: dict[str, Any], index: tuple[dict[str, Path], dict[str, Path]] | None = None
    ) -> Path | None:
        by_id, by_name = index or self._archive_index()
        wanted_id = str(row.get("archive_id") or "")
        wanted_name = Path(str(row.get("original_path") or row.get("result_path") or "")).name
        return by_id.get(wanted_id) if wanted_id else by_name.get(wanted_name)

    def _history_health(
        self,
        row: dict[str, Any],
        archive_index: tuple[dict[str, Path], dict[str, Path]] | None = None,
        shared_index: dict[str, Path] | None = None,
    ) -> str:
        if row.get("kind") != "export":
            return "not_applicable"
        if row.get("deleted_at"):
            return "trashed"
        if row.get("storage_mode") == "shared":
            archives = list(row.get("conversation_archives") or [])
            if not archives:
                return "incomplete"
            index = shared_index if shared_index is not None else self._shared_archive_index()
            available = 0
            superseded = 0
            inaccessible = False
            for archive in archives:
                archive_id = str(archive.get("archive_id") or "")
                path = Path(str(archive.get("path") or ""))
                if not path.is_dir() and archive_id in index:
                    path = index[archive_id]
                    archive["path"] = str(path.resolve())
                try:
                    manifest = self._read_conversation_manifest(path)
                except PermissionError:
                    inaccessible = True
                    continue
                if not manifest or str(manifest.get("conversation_archive_id")) != archive_id:
                    continue
                available += 1
                if str(manifest.get("export_id") or "") != str(archive.get("export_id") or row.get("export_id") or ""):
                    superseded += 1
            row["conversation_archives"] = archives
            row["superseded_count"] = superseded
            current_paths = [str(item.get("path")) for item in archives if item.get("path")]
            if current_paths:
                try:
                    row["current_path"] = os.path.commonpath(current_paths)
                    row["result_path"] = row["current_path"]
                    self.approved_output_dirs.add(str(Path(row["current_path"]).resolve()))
                except ValueError:
                    pass
            if inaccessible:
                return "inaccessible"
            return "healthy" if available == len(archives) else ("missing" if available == 0 else "incomplete")
        raw = row.get("current_path") or row.get("result_path")
        if not raw:
            return "missing"
        path = Path(str(raw))
        try:
            if not path.exists():
                moved = self._find_archive_in_output(row, archive_index)
                if moved:
                    row["current_path"] = str(moved.resolve())
                    row["result_path"] = row["current_path"]
                    self.approved_output_dirs.add(row["current_path"])
                    return "moved"
                return "missing"
            if not path.is_dir():
                return "incomplete"
            valid, archive_id = self._validate_archive(path)
            if not valid:
                return "incomplete"
            if archive_id:
                row["archive_id"] = archive_id
            original = row.get("original_path")
            return "moved" if original and Path(str(original)).resolve() != path.resolve() else "healthy"
        except PermissionError:
            return "inaccessible"
        except OSError:
            return "inaccessible"

    def _clear_estimate_cache(self, account_id: str | None = None) -> None:
        with self.lock:
            if account_id is None:
                self.estimate_cache.clear()
            else:
                prefix = f"{account_id}:"
                self.estimate_cache = {
                    key: value for key, value in self.estimate_cache.items()
                    if not key.startswith(prefix)
                }

    def close(self) -> None:
        for repository in list(self.repositories.values()):
            repository.close()
        self.repositories.clear()
        self.operations.executor.shutdown(wait=False, cancel_futures=True)

    def _scan(self) -> list[WechatAccount]:
        self._clear_estimate_cache()
        previous = self.accounts
        rows = discover_accounts(Path(self.settings.data_root), self.key_store.covered_salts())
        for account in rows:
            status = self.key_store.status(account.account_id)
            account.coverage.fingerprint = ", ".join(status["fingerprints"][:2]) or None
            old = previous.get(account.account_id)
            if old and not old.display_name.startswith("微信账号 "):
                account.display_name = old.display_name
            if old and old.avatar_data_url:
                account.avatar_data_url = old.avatar_data_url
        self.accounts = {account.account_id: account for account in rows}
        for account_id, repository in self.repositories.items():
            if account_id in self.accounts:
                repository.account = self.accounts[account_id]
        return rows

    def bootstrap(self) -> dict[str, Any]:
        accounts = self._scan()
        self._resolve_available_account_profiles(accounts)
        selected_account_id = self.settings.last_account_id if self.settings.last_account_id in self.accounts else ""
        if not selected_account_id:
            preferred = next((account for account in accounts if account.active and account.coverage.covered), None)
            preferred = preferred or next((account for account in accounts if account.coverage.covered), None)
            selected_account_id = preferred.account_id if preferred else ""
        return {
            "version": __version__,
            "settings": asdict(self.settings),
            "accounts": [account.to_dict() for account in accounts],
            "selected_account_id": selected_account_id or None,
            "capabilities": {
                "windows_cng": True,
                "dpapi": True,
                "voice_decoder": bool(RuntimeLocator.current().tool("node")),
                "offline": True,
            },
        }

    def scan_accounts(self) -> dict[str, Any]:
        accounts = self._scan()
        self._resolve_available_account_profiles(accounts)
        return {"accounts": [account.to_dict() for account in accounts]}

    def _resolve_available_account_profiles(self, accounts: list[WechatAccount]) -> None:
        """Resolve local account names and avatars when contact data is authorized."""
        for account in accounts:
            if not account.coverage.covered:
                continue
            try:
                repository = self._repository(account.account_id)
                repository.resolve_account_display_name()
                repository.resolve_account_avatar_data_url()
            except (ChatWechatError, OSError, ValueError, sqlite3.DatabaseError):
                # Account discovery must remain usable when an old account has no
                # currently valid contact key or a snapshot changes under WeChat.
                continue

    def _account(self, account_id: str) -> WechatAccount:
        if account_id not in self.accounts:
            self._scan()
        account = self.accounts.get(account_id)
        if account is None:
            raise ChatWechatError("账号不存在，请重新扫描")
        return account

    def authorize_account(self, account_id: str) -> dict[str, Any]:
        account = self._account(account_id)
        if is_admin():
            result = authorize(account.directory, self.key_store)
        else:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            descriptor, result_name = tempfile.mkstemp(prefix="authorize-", suffix=".json", dir=APP_DIR)
            os.close(descriptor)
            result_file = Path(result_name)
            result_file.unlink(missing_ok=True)
            result = run_elevated(account.directory, result_file)
        with self.lock:
            previous = self.repositories.pop(account_id, None)
            if previous is not None:
                previous.close()
        self._clear_estimate_cache(account_id)
        accounts = self._scan()
        self._resolve_available_account_profiles(accounts)
        return {**result, "account": self.accounts[account_id].to_dict()}

    def _repository(self, account_id: str) -> WechatRepository:
        with self.lock:
            repository = self.repositories.get(account_id)
            if repository is None:
                repository = WechatRepository(self._account(account_id), self.key_store)
                self.repositories[account_id] = repository
            return repository

    def list_conversations(self, account_id: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        repository = self._repository(account_id)
        rows = [row for row in repository.list_conversations() if not self._is_internal_conversation(row)]
        query = str(options.get("query", "")).casefold().strip()
        kind = str(options.get("kind", "all"))
        exclude_kinds = {
            str(value) for value in options.get("exclude_kinds", [])
            if str(value).strip()
        }
        if exclude_kinds:
            rows = [row for row in rows if row.kind not in exclude_kinds]
        if query:
            rows = [row for row in rows if query in row.display_name.casefold()]
        if kind != "all":
            rows = [row for row in rows if row.kind == kind]
        page = max(1, int(options.get("page", 1)))
        page_size = min(200, max(20, int(options.get("page_size", 100))))
        start = (page - 1) * page_size
        return {
            "account": repository.account.to_dict(),
            "items": self._conversation_dicts(repository, rows[start : start + page_size]),
            "total": len(rows),
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    def _conversation_dicts(repository: WechatRepository, rows: list[Any]) -> list[dict[str, Any]]:
        avatars = repository.avatar_data_urls(row.username for row in rows)
        result = []
        for row in rows:
            value = row.to_dict()
            value["avatar_data_url"] = avatars.get(row.username)
            result.append(value)
        return result

    def preview_messages(self, account_id: str, conversation_id: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        limit = min(200, max(20, int(options.get("limit", 100))))
        offset = max(0, int(options.get("offset", 0)))
        repository = self._repository(account_id)
        conversation = repository.conversation(conversation_id)
        rows = list(repository.iter_messages(conversation_id, allow_partial=True, limit=limit, offset=offset))
        summary = repository.message_summary(conversation_id, allow_partial=True)
        usernames = [row.sender_id for row in rows if row.sender_id]
        usernames.append(conversation.username)
        avatars = repository.avatar_data_urls(usernames)
        from .media import MediaExporter

        media_previewer = MediaExporter(account_id, self._account(account_id).directory, self.key_store)
        items = []
        for row in rows:
            value = row.to_dict()
            value["sender_avatar_data_url"] = avatars.get(row.sender_id or "")
            if not value["sender_avatar_data_url"] and not row.outgoing and conversation.kind == "private":
                value["sender_avatar_data_url"] = avatars.get(conversation.username)
            for index, attachment in enumerate(row.attachments):
                preview = media_previewer.preview_data_url(attachment)
                if preview:
                    value["attachments"][index]["preview_data_url"] = preview
                else:
                    status, reason_code, reason = media_previewer.preview_diagnostic(attachment)
                    value["attachments"][index]["status"] = status
                    value["attachments"][index]["reason_code"] = reason_code
                    value["attachments"][index]["reason"] = reason
            items.append(value)
        return {
            "items": items,
            "partial": account_id in self.accounts and not self.accounts[account_id].coverage.complete,
            "returned": len(rows),
            "offset": offset,
            "total": summary["total"],
            "earliest_at": summary["earliest_at"].isoformat(timespec="seconds") if summary["earliest_at"] else None,
            "latest_at": summary["latest_at"].isoformat(timespec="seconds") if summary["latest_at"] else None,
        }

    def estimate_export(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = ExportRequest.from_dict(payload)
        cache_payload = {
            "account_id": request.account_id,
            "conversation_ids": sorted(request.conversation_ids),
            "start_at": request.start_at.isoformat() if request.start_at else None,
            "end_at": request.end_at.isoformat() if request.end_at else None,
            "message_types": sorted(request.message_types),
            "media_categories": sorted(request.media_categories),
            "formats": sorted(request.formats),
            "include_media": request.include_media,
            "output_directory": str(request.output_directory.resolve()),
        }
        cache_key = f"{request.account_id}:" + json.dumps(cache_payload, sort_keys=True, ensure_ascii=True)
        with self.lock:
            cached = self.estimate_cache.get(cache_key)
        if cached is not None:
            return dict(cached)
        repository = self._repository(request.account_id)
        count = media_count = media_bytes = 0
        attachments = []
        for conversation_id in request.conversation_ids:
            for message in repository.iter_messages(conversation_id, request.allow_partial):
                if request.start_at and message.sent_at < request.start_at:
                    continue
                if request.end_at and message.sent_at > request.end_at:
                    continue
                if request.message_types and message.message_type not in request.message_types:
                    continue
                count += 1
                attachments.extend(
                    item for item in message.attachments
                    if not request.media_categories or item.category in request.media_categories
                )
        details: dict[str, Any] = {
            "referenced": 0, "known_bytes": 0, "local_recoverable": 0,
            "network_candidates": 0, "unavailable": 0, "by_category": {},
        }
        if request.include_media:
            from .media import MediaExporter

            inspector = MediaExporter(
                request.account_id, self._account(request.account_id).directory, self.key_store
            )
            details = inspector.estimate_details(attachments)
            media_count = int(details["referenced"])
            media_bytes = int(details["known_bytes"])
        estimated = media_bytes + count * 1200
        free = shutil.disk_usage(request.output_directory).free if request.output_directory.exists() else 0
        warnings = []
        if free and estimated > free * 0.9:
            warnings.append("目标磁盘空间可能不足")
        if count > 500_000:
            warnings.append("记录量较大，单文件打开可能较慢")
        result = asdict(ExportEstimate(
            len(request.conversation_ids), count, media_count, estimated, free, warnings,
            known_bytes=estimated,
            remote_size_unknown_count=int(details["network_candidates"]),
            local_recoverable_count=int(details["local_recoverable"]),
            network_candidate_count=int(details["network_candidates"]),
            unavailable_count=int(details["unavailable"]),
            by_category=dict(details["by_category"]),
            calculated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        ))
        with self.lock:
            self.estimate_cache[cache_key] = dict(result)
        return result

    def start_export(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = ExportRequest.from_dict(payload)
        output_key = str(request.output_directory.resolve()).casefold()
        self.approved_output_dirs.add(str(request.output_directory.resolve()))
        account = self._account(request.account_id)
        if not request.conversation_ids:
            raise ChatWechatError("请至少选择一个会话")
        if not request.formats:
            raise ChatWechatError("请至少选择一种导出格式")
        if not account.coverage.complete and not request.allow_partial:
            raise ChatWechatError("数据库密钥覆盖不完整；重新授权，或明确允许部分导出")
        with self.lock:
            if output_key in self.active_export_roots:
                raise ChatWechatError("该输出目录已有导出任务正在运行，请等待完成后重试")
            self.active_export_roots.add(output_key)
        history_id = self._begin_history("export", {"formats": list(request.formats)})

        def worker(cancel: threading.Event, progress: Any) -> dict[str, Any]:
            # Export owns an isolated repository/snapshot set. UI preview,
            # re-scan and authorization can no longer close or overwrite files
            # used by the worker, which avoids Windows sharing violations.
            repository = WechatRepository(account, self.key_store)
            try:
                repository.list_conversations()
                result = export_archive(account, repository, request, cancel, progress).to_dict()
                return result
            finally:
                repository.close()

        def completed(operation: Operation) -> None:
            result = operation.result or {}
            root = str(result.get("root") or "") or None
            open_path = str(result.get("open_path") or root or "") or None
            archives = list(result.get("conversation_archives") or [])
            for value in [root, open_path, *[str(item.get("path") or "") for item in archives]]:
                if value:
                    self.approved_output_dirs.add(str(Path(value).resolve()))
            extra = {
                "result_path": open_path, "original_path": open_path, "current_path": open_path,
                "output_root": root,
                "archive_id": None, "storage_mode": "shared",
                "export_id": result.get("export_id"), "conversation_archives": archives,
                "superseded_count": 0,
                "directory_health": "healthy" if root else "not_applicable",
                "conversation_count": int(result.get("conversation_count", 0)),
                "message_count": int(result.get("message_count", 0)),
                "media_count": int(result.get("media_count", 0)),
                "formats": list(request.formats), "warnings": list(result.get("warnings", [])),
                "warning_details": list(result.get("warning_details", [])),
                "result_summary": {
                    "conversation_count": int(result.get("conversation_count", 0)),
                    "message_count": int(result.get("message_count", 0)),
                    "media_count": int(result.get("media_count", 0)),
                    "created_count": int(result.get("created_count", 0)),
                    "replaced_count": int(result.get("replaced_count", 0)),
                },
            }
            try:
                self._finish_history(history_id, operation, extra)
            finally:
                with self.lock:
                    self.active_export_roots.discard(output_key)

        return self.operations.start("export", worker, completed).to_dict()

    def cancel_operation(self, operation_id: str) -> dict[str, Any]:
        return self.operations.cancel(operation_id)

    def get_operation(self, operation_id: str) -> dict[str, Any]:
        return self.operations.get(operation_id)

    @staticmethod
    def _display_name(value: str | None, fallback: str) -> str:
        text = str(value or "").strip()
        if not text or re.fullmatch(r"wxid_[A-Za-z0-9_-]+", text):
            return fallback
        return text

    def search_messages(self, payload: dict[str, Any]) -> dict[str, Any]:
        account_id = str(payload.get("account_id") or "")
        query = str(payload.get("query") or "").strip()
        if not query:
            raise ChatWechatError("请输入搜索内容")
        query_folded = query.casefold()
        limit = min(500, max(20, int(payload.get("limit", 200))))
        wanted_types = {str(value) for value in payload.get("message_types", []) if value}
        wanted_conversations = {str(value) for value in payload.get("conversation_ids", []) if value}

        def parse_bound(raw: Any, end: bool = False) -> datetime | None:
            if not raw:
                return None
            text = str(raw)
            parsed = datetime.fromisoformat(text)
            if len(text) <= 10:
                parsed = parsed.replace(hour=23, minute=59, second=59) if end else parsed.replace(hour=0, minute=0, second=0)
            return parsed.astimezone() if parsed.tzinfo else parsed.astimezone()

        start_at = parse_bound(payload.get("start_at"))
        end_at = parse_bound(payload.get("end_at"), True)

        def worker(cancel: threading.Event, progress: Any) -> dict[str, Any]:
            repository = WechatRepository(self._account(account_id), self.key_store)
            try:
                conversations = [
                    row for row in repository.list_conversations()
                    if not self._is_internal_conversation(row)
                ]
                if wanted_conversations:
                    conversations = [row for row in conversations if row.conversation_id in wanted_conversations]
                results: list[dict[str, Any]] = []
                for index, conversation in enumerate(conversations):
                    if cancel.is_set() or len(results) >= limit:
                        break
                    progress(index / max(1, len(conversations)), "正在搜索聊天记录")
                    for message in repository.iter_messages(conversation.conversation_id, allow_partial=True):
                        if cancel.is_set() or len(results) >= limit:
                            break
                        if wanted_types and message.message_type not in wanted_types:
                            continue
                        if start_at and message.sent_at < start_at:
                            continue
                        if end_at and message.sent_at > end_at:
                            continue
                        text = str(message.display_text or message.text or "")
                        if not text or query_folded not in text.casefold():
                            continue
                        cleaned = re.sub(r"wxid_[A-Za-z0-9_-]+", "未知成员", text)
                        position = cleaned.casefold().find(query_folded)
                        start = max(0, position - 36)
                        snippet = cleaned[start : start + 120].replace("\r", " ").replace("\n", " ")
                        results.append(SearchResult(
                            conversation.conversation_id,
                            self._display_name(conversation.display_name, "未命名会话"),
                            message.message_id,
                            message.sent_at,
                            self._display_name(message.sender_name, "未知成员"),
                            message.message_type,
                            snippet,
                            conversation.kind,
                        ).to_dict())
                if cancel.is_set():
                    raise OperationCancelled("搜索已取消")
                return {"items": results, "truncated": len(results) >= limit, "limit": limit}
            finally:
                repository.close()

        return self.operations.start("search", worker).to_dict()

    def start_media_scan(self, account_id: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        account = self._account(account_id)
        options = options or {}
        wanted = {str(value) for value in options.get("conversation_ids", []) if value}
        detailed = bool(options.get("detailed", False))
        detail_limit = min(500, max(1, int(options.get("limit", 500))))
        history_id = self._begin_history("media_scan", {"scope": "selected" if wanted else "account"})

        def worker(cancel: threading.Event, progress: Any) -> dict[str, Any]:
            from .media import MediaExporter

            repository = WechatRepository(account, self.key_store)
            report = MediaRecoveryReport()
            issue_counts: dict[tuple[str, str, str | None], int] = {}
            try:
                conversations = [
                    row for row in repository.list_conversations()
                    if not self._is_internal_conversation(row)
                ]
                if wanted:
                    conversations = [row for row in conversations if row.conversation_id in wanted]
                inspector = MediaExporter(account_id, account.directory, self.key_store)
                for index, conversation in enumerate(conversations):
                    if cancel.is_set():
                        break
                    progress(index / max(1, len(conversations)), "正在检查本地媒体")
                    for message in repository.iter_messages(conversation.conversation_id, allow_partial=True):
                        if cancel.is_set():
                            break
                        for attachment in message.attachments:
                            report.referenced += 1
                            status, reason = inspector.inspect_local(attachment)
                            category = report.by_category.setdefault(attachment.category, {
                                "referenced": 0, "recoverable": 0, "missing": 0, "unsupported": 0,
                            })
                            category["referenced"] += 1
                            category[status] += 1
                            setattr(report, status, getattr(report, status) + 1)
                            if status != "recoverable":
                                key = (attachment.category, status, reason)
                                issue_counts[key] = issue_counts.get(key, 0) + 1
                            if detailed and status != "recoverable":
                                if len(report.items) < detail_limit:
                                    report.items.append(MediaRecoveryItem(
                                        conversation.conversation_id,
                                        self._display_name(conversation.display_name, "未命名会话"),
                                        message.sent_at,
                                        attachment.category,
                                        status,
                                        reason,
                                    ))
                                else:
                                    report.truncated += 1
                report.issues = [MediaIssue(category, status, reason, count) for (category, status, reason), count in sorted(issue_counts.items())]
                if cancel.is_set():
                    raise OperationCancelled("媒体扫描已取消")
                self._clear_estimate_cache(account_id)
                return report.to_dict()
            finally:
                repository.close()

        def completed(operation: Operation) -> None:
            result = operation.result or {}
            self._finish_history(history_id, operation, {
                "media_count": int(result.get("referenced", 0)),
                "result_summary": {
                    "referenced": int(result.get("referenced", 0)),
                    "recoverable": int(result.get("recoverable", 0)),
                    "missing": int(result.get("missing", 0)),
                    "unsupported": int(result.get("unsupported", 0)),
                },
            })

        return self.operations.start("media_scan", worker, completed).to_dict()

    def get_media_report(self, operation_id: str) -> dict[str, Any]:
        operation = self.operations.get(operation_id)
        if operation.get("kind") != "media_scan":
            raise ChatWechatError("该任务不是媒体扫描")
        return operation

    def get_account_statistics(self, account_id: str) -> dict[str, Any]:
        account = self._account(account_id)
        rows = self.statistics_store.load()
        row = next((item for item in rows if item.get("account_id") == account_id), None)
        if not row:
            return {"report": None}
        value = dict(row)
        value["stale"] = value.get("database_fingerprint") != self._database_fingerprint(account)
        return {"report": value}

    def start_account_statistics_scan(self, account_id: str) -> dict[str, Any]:
        account = self._account(account_id)
        history_id = self._begin_history("account_statistics", {"account_id": account_id})

        def worker(cancel: threading.Event, progress: Any) -> dict[str, Any]:
            fingerprint = self._database_fingerprint(account)
            progress(0.02, "正在清点消息数据库", {"phase": "inventory", "processed_messages": 0, "conversation_count": 0})
            repository = WechatRepository(account, self.key_store)
            try:
                report = repository.account_statistics(fingerprint, cancel, progress)
                filtered = []
                for item in report.conversations:
                    stub = type("ConversationStub", (), {"username": "", "display_name": item.display_name})()
                    if not self._is_internal_conversation(stub):
                        filtered.append(item)
                report.conversations = filtered
                report.conversation_count = len(filtered)
                report.message_count = sum(item.message_count for item in filtered)
                report.by_conversation_kind = {}
                report.by_message_type = {}
                earliest_values = [item.earliest_at for item in filtered if item.earliest_at]
                latest_values = [item.latest_at for item in filtered if item.latest_at]
                report.earliest_at = min(earliest_values) if earliest_values else None
                report.latest_at = max(latest_values) if latest_values else None
                for item in filtered:
                    report.by_conversation_kind[item.kind] = report.by_conversation_kind.get(item.kind, 0) + 1
                    for key, count in item.by_message_type.items():
                        report.by_message_type[key] = report.by_message_type.get(key, 0) + count
                progress(0.96, "正在保存统计结果", {
                    "phase": "saving", "processed_messages": report.message_count,
                    "conversation_count": report.conversation_count,
                })
                rows = [item for item in self.statistics_store.load() if item.get("account_id") != account_id]
                rows.append(report.to_dict())
                self.statistics_store.save(rows)
                return report.to_dict()
            finally:
                repository.close()

        def completed(operation: Operation) -> None:
            result = operation.result or {}
            self._finish_history(history_id, operation, {
                "conversation_count": int(result.get("conversation_count", 0)),
                "message_count": int(result.get("message_count", 0)),
                "result_summary": {
                    "conversation_count": int(result.get("conversation_count", 0)),
                    "message_count": int(result.get("message_count", 0)),
                    "complete": bool(result.get("complete", False)),
                },
            })

        return self.operations.start("account_statistics", worker, completed).to_dict()

    def list_operation_history(self) -> dict[str, Any]:
        rows = self.history_store.load()
        needs_search = any(
            row.get("kind") == "export" and not row.get("deleted_at")
            and row.get("current_path") and not Path(str(row.get("current_path"))).exists()
            for row in rows
        )
        archive_index = self._archive_index() if needs_search else ({}, {})
        shared_index = self._shared_archive_index() if any(row.get("storage_mode") == "shared" for row in rows) else {}
        changed = False
        for row in rows:
            before = (
                row.get("directory_health"), row.get("current_path"), row.get("archive_id"),
                row.get("superseded_count"), json.dumps(row.get("conversation_archives", []), sort_keys=True),
            )
            row["directory_health"] = self._history_health(row, archive_index, shared_index)
            after = (
                row.get("directory_health"), row.get("current_path"), row.get("archive_id"),
                row.get("superseded_count"), json.dumps(row.get("conversation_archives", []), sort_keys=True),
            )
            changed = changed or before != after
        if changed:
            self.history_store.save(rows)
        return {"items": list(reversed(rows))}

    def clear_operation_history(self) -> dict[str, Any]:
        rows = self.history_store.load()
        running = [row for row in rows if row.get("status") in {"pending", "running"}]
        deleted_count = len(rows) - len(running)
        self.history_store.save(running)
        return {
            "items": list(reversed(running)),
            "deleted_count": deleted_count,
            "preserved_running_count": len(running),
        }

    def clear_abnormal_operation_history(self) -> dict[str, Any]:
        abnormal_statuses = {"failed", "interrupted"}
        abnormal_health = {"missing", "incomplete", "inaccessible"}
        rows = self.history_store.load()
        retained: list[dict[str, Any]] = []
        deleted_count = 0
        preserved_running_count = 0
        for row in rows:
            status = str(row.get("status", ""))
            if status in {"pending", "running"}:
                retained.append(row)
                preserved_running_count += 1
                continue
            if status in abnormal_statuses or str(row.get("directory_health", "")) in abnormal_health:
                deleted_count += 1
            else:
                retained.append(row)
        self.history_store.save(retained)
        return {
            "items": list(reversed(retained)),
            "deleted_count": deleted_count,
            "preserved_running_count": preserved_running_count,
        }

    def delete_operation_history_entries(self, history_ids: list[str]) -> dict[str, Any]:
        wanted = {str(value) for value in history_ids}
        existing = self.history_store.load()
        rows = [row for row in existing if row.get("history_id") not in wanted]
        self.history_store.save(rows)
        return {"items": list(reversed(rows)), "deleted": len(existing) - len(rows)}

    def delete_operation_history_entry(self, history_id: str) -> dict[str, Any]:
        return self.delete_operation_history_entries([history_id])

    def relink_operation_history_entry(self, history_id: str, value: str) -> dict[str, Any]:
        existing = next((item for item in self.history_store.load() if item.get("history_id") == history_id), None)
        if existing is None or existing.get("kind") != "export":
            raise ChatWechatError("导出记录不存在")
        path = Path(value).resolve()
        if not path.is_dir():
            raise ChatWechatError("请选择存在的导出目录")
        if existing.get("storage_mode") == "shared":
            index = self._shared_archive_index(path)
            archives = list(existing.get("conversation_archives") or [])
            found = 0
            for archive in archives:
                located = index.get(str(archive.get("archive_id") or ""))
                if located:
                    archive["path"] = str(located.resolve())
                    found += 1
            if not found:
                raise ChatWechatError("所选目录中没有该记录对应的会话归档")
            paths = [str(item["path"]) for item in archives if item.get("path")]
            current_path = os.path.commonpath(paths) if paths else str(path)
            row = self._update_history(history_id, {
                "conversation_archives": archives, "current_path": current_path,
                "result_path": current_path, "directory_health": "moved", "deleted_at": None,
            })
            self.approved_output_dirs.add(str(Path(current_path).resolve()))
            return {"item": row}
        valid, archive_id = self._validate_archive(path)
        if not valid:
            raise ChatWechatError("所选目录不是可验证的 ChatWechat 归档")
        row = self._update_history(history_id, {
            "current_path": str(path), "result_path": str(path), "archive_id": archive_id,
            "directory_health": "moved", "deleted_at": None,
        })
        self.approved_output_dirs.add(str(path))
        return {"item": row}

    @staticmethod
    def _move_to_recycle_bin(path: Path) -> None:
        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint),
                ("pFrom", ctypes.c_wchar_p), ("pTo", ctypes.c_wchar_p),
                ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", ctypes.c_bool),
                ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p),
            ]
        operation = SHFILEOPSTRUCTW()
        operation.wFunc = 3  # FO_DELETE
        operation.pFrom = str(path) + "\0\0"
        operation.fFlags = 0x0040 | 0x0010 | 0x0004  # allow undo, no confirmation, silent
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
        if result != 0 or operation.fAnyOperationsAborted:
            raise ChatWechatError("无法将归档移入 Windows 回收站")

    def trash_export_result(self, history_id: str) -> dict[str, Any]:
        rows = self.history_store.load()
        row = next((item for item in rows if item.get("history_id") == history_id), None)
        if not row or row.get("kind") != "export":
            raise ChatWechatError("导出记录不存在")
        if row.get("storage_mode") == "shared":
            deleted = 0
            skipped = 0
            for archive in list(row.get("conversation_archives") or []):
                path = Path(str(archive.get("path") or "")).resolve()
                manifest = self._read_conversation_manifest(path) if path.is_dir() else None
                if not manifest or str(manifest.get("conversation_archive_id")) != str(archive.get("archive_id") or ""):
                    skipped += 1
                    continue
                if str(manifest.get("export_id") or "") != str(archive.get("export_id") or row.get("export_id") or ""):
                    skipped += 1
                    continue
                output_root = Path(str(row.get("output_root") or self.settings.output_directory)).resolve()
                data_root = Path(self.settings.data_root).resolve()
                if path in {output_root, data_root} or data_root in path.parents or output_root not in path.parents:
                    raise ChatWechatError("会话归档路径未通过安全验证")
                self._move_to_recycle_bin(path)
                deleted += 1
            if not deleted and skipped:
                raise ChatWechatError("这些会话已被后续导出更新，未删除当前归档")
            row.update({"directory_health": "trashed", "deleted_at": self._now()})
            self.history_store.save(rows)
            return {"item": row, "deleted_count": deleted, "skipped_count": skipped}
        raw = row.get("current_path") or row.get("result_path")
        if not raw:
            raise ChatWechatError("该记录没有可删除的归档目录")
        path = Path(str(raw)).resolve()
        output_root = Path(self.settings.output_directory).resolve()
        data_root = Path(self.settings.data_root).resolve()
        if path in {output_root, data_root} or data_root == path or data_root in path.parents:
            raise ChatWechatError("拒绝删除微信数据目录或输出根目录")
        valid, _archive_id = self._validate_archive(path)
        if not valid:
            raise ChatWechatError("目录无法验证为 ChatWechat 归档，已拒绝删除")
        self._move_to_recycle_bin(path)
        row.update({"directory_health": "trashed", "deleted_at": self._now()})
        self.history_store.save(rows)
        return {"item": row}

    def list_export_presets(self) -> dict[str, Any]:
        settings = getattr(self, "settings", Settings())
        rows = self.preset_store.load()
        for row in rows:
            row.setdefault("download_missing_media", settings.download_missing_media_default)
            row.setdefault("allow_legacy_http_media", settings.allow_legacy_http_media_default)
            row.setdefault("visual_download_limit_mib", settings.visual_download_limit_mib)
            row.setdefault("audio_download_limit_mib", settings.audio_download_limit_mib)
            row.setdefault("large_download_limit_mib", settings.large_download_limit_mib)
        return {"items": rows}

    def save_export_preset(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()[:40]
        if not name:
            raise ChatWechatError("请输入预设名称")
        settings = getattr(self, "settings", Settings())
        def media_limit(name: str, default: int) -> int:
            try:
                return min(2048, max(1, int(payload.get(name, default))))
            except (TypeError, ValueError):
                raise ChatWechatError("媒体下载上限必须是 1–2048 MiB 的整数") from None
        preset_id = str(payload.get("preset_id") or uuid.uuid4().hex)
        preset = asdict(ExportPreset(
            preset_id=preset_id,
            name=name,
            formats=[str(value) for value in payload.get("formats", ["html", "markdown", "json"])],
            message_types=[str(value) for value in payload.get("message_types", [])],
            media_categories=[str(value) for value in payload.get("media_categories", [])],
            include_media=bool(payload.get("include_media", True)),
            download_missing_media=bool(payload.get(
                "download_missing_media", settings.download_missing_media_default
            )),
            allow_legacy_http_media=bool(payload.get(
                "allow_legacy_http_media", settings.allow_legacy_http_media_default
            )),
            visual_download_limit_mib=media_limit("visual_download_limit_mib", settings.visual_download_limit_mib),
            audio_download_limit_mib=media_limit("audio_download_limit_mib", settings.audio_download_limit_mib),
            large_download_limit_mib=media_limit("large_download_limit_mib", settings.large_download_limit_mib),
            allow_partial=bool(payload.get("allow_partial", False)),
            start_at=str(payload.get("start_at")) if payload.get("start_at") else None,
            end_at=str(payload.get("end_at")) if payload.get("end_at") else None,
        ))
        rows = [row for row in self.preset_store.load() if row.get("preset_id") != preset_id]
        rows.append(preset)
        self.preset_store.save(rows)
        return {"preset": preset, "items": rows}

    def delete_export_preset(self, preset_id: str) -> dict[str, Any]:
        rows = [row for row in self.preset_store.load() if row.get("preset_id") != str(preset_id)]
        self.preset_store.save(rows)
        return {"items": rows}

    def open_result_folder(self, value: str) -> dict[str, Any]:
        path = Path(value).resolve()
        if not path.is_dir():
            raise ChatWechatError("结果目录不存在")
        known = {
            str(Path(row.get("current_path") or row.get("result_path", "")).resolve())
            for row in self.history_store.load() if row.get("current_path") or row.get("result_path")
        }
        if str(path) not in known and str(path) not in self.approved_output_dirs:
            raise ChatWechatError("只能打开已记录的导出目录")
        os.startfile(path)  # type: ignore[attr-defined]
        return {"path": str(path)}

    def save_settings(self, value: dict[str, Any]) -> dict[str, Any]:
        current = asdict(self.settings)
        for key in ("data_root", "output_directory", "theme", "conversation_kind", "last_account_id", "font_scale", "density", "export_folder_layout"):
            if key in value:
                current[key] = str(value[key])
        for key in (
            "download_missing_media_default", "allow_legacy_http_media_default",
            "open_result_folder_after_export",
        ):
            if key in value:
                current[key] = bool(value[key])
        for key in ("visual_download_limit_mib", "audio_download_limit_mib", "large_download_limit_mib"):
            if key in value:
                current[key] = value[key]
        self.settings = Settings.from_dict(current)
        self.settings_store.save(self.settings)
        self.approved_output_dirs.add(str(Path(self.settings.output_directory).resolve()))
        return {"settings": asdict(self.settings)}


from .desktop.bridge import Bridge

__all__ = [
    "Bridge",
    "ChatWechatService",
    "JsonListStore",
    "Operation",
    "OperationManager",
]
