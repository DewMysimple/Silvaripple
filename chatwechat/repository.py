from __future__ import annotations

import shutil
import sqlite3
import base64
import hashlib
import re
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .discovery import database_files, optional_database_files
from .errors import AuthorizationRequired, CorruptDatabase, OperationCancelled, SnapshotChanged
from .keystore import KeyStore
from .message_parser import TYPE_NAMES, normalize_message
from .models import AccountStatisticsReport, Conversation, ConversationStatistics, WechatAccount, WechatMessage
from .redaction import stable_id
from .snapshot import ReadOnlySnapshotter, TempManager


USERNAME_COLUMNS = ("username", "user_name", "session_id", "talker", "chat_name")


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _pick(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    lookup = {column.casefold(): column for column in columns}
    return next((lookup[name.casefold()] for name in candidates if name.casefold() in lookup), None)


def _connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro&immutable=1", uri=True)


def _account_usernames(directory_name: str) -> list[str]:
    """Return local account identifiers, including WeChat 4's directory suffix form."""
    values = [directory_name]
    base, separator, suffix = directory_name.rpartition("_")
    if separator and base.startswith("wxid_") and len(suffix) == 4 and all(char in "0123456789abcdefABCDEF" for char in suffix):
        values.insert(0, base)
    return values


class SchemaInspector:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def tables(self) -> list[str]:
        return [row[0] for row in self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]

    def columns(self, table: str) -> list[str]:
        return [row[1] for row in self.connection.execute(f"PRAGMA table_info({_quote(table)})")]


class WechatRepository:
    def __init__(
        self,
        account: WechatAccount,
        store: KeyStore | None = None,
        snapshotter: ReadOnlySnapshotter | None = None,
    ):
        self.account = account
        self.store = store or KeyStore()
        self.snapshotter = snapshotter or ReadOnlySnapshotter()
        self.task_dir = self.snapshotter.manager.create_task_dir()
        self.decrypted: dict[str, Path] = {}
        self._conversations: dict[str, Conversation] = {}
        self._resource_paths: dict[str, list[str]] | None = None
        self._contact_names_cache: dict[str, str] | None = None
        self._contact_original_names_cache: dict[str, str] | None = None
        self._contact_avatar_urls_cache: dict[str, str] | None = None
        self._emoticon_metadata_cache: dict[str, dict[str, str]] | None = None
        self._avatar_data_cache: dict[str, str | None] = {}
        self._decrypt_lock = threading.RLock()

    def close(self) -> None:
        with self._decrypt_lock:
            shutil.rmtree(self.task_dir, ignore_errors=True)
            self.decrypted.clear()

    def _decrypt(self, source: Path) -> Path:
        # pywebview calls and export workers can overlap. Serializing snapshot
        # creation prevents two readers from overwriting or deleting the same
        # temporary database on Windows (WinError 32).
        with self._decrypt_lock:
            key = str(source).casefold()
            if key in self.decrypted:
                return self.decrypted[key]
            with source.open("rb") as stream:
                salt = stream.read(16)
            page_key = self.store.get_database_key(self.account.account_id, salt)
            if page_key is None:
                raise AuthorizationRequired(f"数据库 {source.name} 尚未授权")
            encrypted = self.snapshotter.copy_consistent(source, self.task_dir)
            target = self.task_dir / f"{len(self.decrypted):04d}-{source.stem}.sqlite"
            self.snapshotter.decrypt(encrypted, page_key, target)
            self.decrypted[key] = target
            return target

    def _core_sources(self, kind: str) -> list[Path]:
        return [path for path in database_files(self.account.directory) if kind in {part.casefold() for part in path.parts}]

    def _message_sources(self) -> list[Path]:
        """Return only actual message shards, excluding FTS/resource/media helpers."""
        result = []
        for path in self._core_sources("message"):
            stem = path.stem.casefold()
            prefix, separator, shard = stem.rpartition("_")
            if separator and shard.isdigit() and prefix in {"message", "biz_message"}:
                result.append(path)
        return result

    def _contact_names(self) -> dict[str, str]:
        if self._contact_names_cache is not None:
            return self._contact_names_cache
        names: dict[str, str] = {}
        # Search-index databases do not contain authoritative contact profiles and
        # require WeChat's private tokenizer, so only inspect the primary contact DBs.
        sources = [path for path in self._core_sources("contact") if not path.stem.casefold().endswith("_fts")]
        for source in sources:
            path = self._decrypt(source)
            with closing(_connect_readonly(path)) as connection:
                connection.row_factory = sqlite3.Row
                inspector = SchemaInspector(connection)
                for table in inspector.tables():
                    columns = inspector.columns(table)
                    username = _pick(columns, USERNAME_COLUMNS)
                    display_columns = [
                        column for candidate in ("remark", "remark_name", "nickname", "nick_name", "display_name", "alias")
                        if (column := _pick(columns, (candidate,)))
                    ]
                    if not username or not display_columns:
                        continue
                    try:
                        for row in connection.execute(
                            f"SELECT {_quote(username)}, {', '.join(_quote(column) for column in display_columns)} FROM {_quote(table)}"
                        ):
                            display = next((str(value).strip() for value in row[1:] if value and str(value).strip()), "")
                            if row[0] and display:
                                names[str(row[0])] = display
                    except sqlite3.DatabaseError:
                        continue
        self._contact_names_cache = names
        return names

    def contact_original_names(self) -> dict[str, str]:
        """Return WeChat profile nicknames without applying local remarks.

        The regular conversation browser intentionally follows the names visible
        in the signed-in account (where a local remark may take precedence).  An
        archive is different: it should identify people by the name from their
        WeChat profile, so remark/remark_name and alias are never candidates here.
        """
        if self._contact_original_names_cache is not None:
            return dict(self._contact_original_names_cache)
        names: dict[str, str] = {}
        sources = [path for path in self._core_sources("contact") if not path.stem.casefold().endswith("_fts")]
        for source in sources:
            path = self._decrypt(source)
            with closing(_connect_readonly(path)) as connection:
                inspector = SchemaInspector(connection)
                for table in inspector.tables():
                    columns = inspector.columns(table)
                    username = _pick(columns, USERNAME_COLUMNS)
                    nickname_columns = [
                        column for candidate in ("nickname", "nick_name")
                        if (column := _pick(columns, (candidate,)))
                    ]
                    # Some older schemas only expose display_name. It is accepted
                    # as a last-resort profile field, but local remarks and aliases
                    # are deliberately excluded.
                    if not nickname_columns:
                        display = _pick(columns, ("display_name",))
                        if display:
                            nickname_columns.append(display)
                    if not username or not nickname_columns:
                        continue
                    try:
                        rows = connection.execute(
                            f"SELECT {_quote(username)}, {', '.join(_quote(column) for column in nickname_columns)} "
                            f"FROM {_quote(table)}"
                        )
                        for row in rows:
                            profile_name = next(
                                (str(value).strip() for value in row[1:] if value and str(value).strip()), ""
                            )
                            if row[0] and profile_name:
                                names[str(row[0])] = profile_name
                    except sqlite3.DatabaseError:
                        continue
        self._contact_original_names_cache = names
        return dict(names)

    def _contact_avatar_urls(self) -> dict[str, str]:
        if self._contact_avatar_urls_cache is not None:
            return self._contact_avatar_urls_cache
        result: dict[str, str] = {}
        sources = [path for path in self._core_sources("contact") if not path.stem.casefold().endswith("_fts")]
        for source in sources:
            path = self._decrypt(source)
            with closing(_connect_readonly(path)) as connection:
                inspector = SchemaInspector(connection)
                for table in inspector.tables():
                    columns = inspector.columns(table)
                    username = _pick(columns, USERNAME_COLUMNS)
                    small = _pick(columns, ("small_head_url", "small_head_img_url"))
                    big = _pick(columns, ("big_head_url", "big_head_img_url"))
                    if not username or not (small or big):
                        continue
                    selected = [username] + ([small] if small else []) + ([big] if big else [])
                    try:
                        for row in connection.execute(
                            f"SELECT {', '.join(_quote(column) for column in selected)} FROM {_quote(table)}"
                        ):
                            url = next((str(value).strip() for value in row[1:] if value and str(value).strip()), "")
                            if row[0] and url:
                                result[str(row[0])] = url
                    except sqlite3.DatabaseError:
                        continue
        self._contact_avatar_urls_cache = result
        return result

    @staticmethod
    def _image_data_url(value: bytes) -> str | None:
        if not value or len(value) > 2 * 1024 * 1024:
            return None
        mime = None
        if value.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        elif value.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        elif value.startswith((b"GIF87a", b"GIF89a")):
            mime = "image/gif"
        elif value.startswith(b"RIFF") and value[8:12] == b"WEBP":
            mime = "image/webp"
        if not mime:
            return None
        return f"data:{mime};base64,{base64.b64encode(value).decode('ascii')}"

    def avatar_data_urls(self, usernames: Iterable[str]) -> dict[str, str]:
        requested = {str(username) for username in usernames if username}
        missing = {username for username in requested if username not in self._avatar_data_cache}
        if missing:
            # WeChat occasionally leaves a small offline cache keyed by MD5(url).
            urls = self._contact_avatar_urls()
            cache_dir = self.account.directory / "temp" / "head_image"
            for username in list(missing):
                url = urls.get(username)
                candidate = cache_dir / hashlib.md5(url.encode("utf-8")).hexdigest() if url else None
                if candidate and candidate.is_file():
                    try:
                        data_url = self._image_data_url(candidate.read_bytes())
                    except OSError:
                        data_url = None
                    if data_url:
                        self._avatar_data_cache[username] = data_url
                        missing.discard(username)

        sources = optional_database_files(self.account.directory)
        for source in sources:
            if not missing:
                break
            try:
                path = self._decrypt(source)
            except AuthorizationRequired:
                break
            with closing(_connect_readonly(path)) as connection:
                inspector = SchemaInspector(connection)
                for table in inspector.tables():
                    columns = inspector.columns(table)
                    username_col = _pick(columns, USERNAME_COLUMNS)
                    image_col = _pick(columns, ("image_buffer", "image_data", "buffer", "data", "blob"))
                    if not username_col or not image_col:
                        continue
                    placeholders = ",".join("?" for _ in missing)
                    try:
                        rows = connection.execute(
                            f"SELECT {_quote(username_col)}, {_quote(image_col)} FROM {_quote(table)} "
                            f"WHERE {_quote(username_col)} IN ({placeholders})",
                            list(missing),
                        )
                        for username, image in rows:
                            if isinstance(image, (bytes, bytearray, memoryview)):
                                data_url = self._image_data_url(bytes(image))
                                if data_url:
                                    self._avatar_data_cache[str(username)] = data_url
                                    missing.discard(str(username))
                    except sqlite3.DatabaseError:
                        continue
        for username in missing:
            self._avatar_data_cache[username] = None
        return {
            username: value for username in requested
            if (value := self._avatar_data_cache.get(username)) is not None
        }

    def resolve_account_display_name(self, names: dict[str, str] | None = None) -> str:
        names = names if names is not None else self._contact_names()
        for username in _account_usernames(self.account.directory.name):
            display_name = names.get(username, "").strip()
            if display_name:
                self.account.display_name = display_name
                break
        return self.account.display_name

    def resolve_account_avatar_data_url(self) -> str | None:
        """Resolve the signed-in account avatar from local contact/cache data only."""
        usernames = _account_usernames(self.account.directory.name)
        avatars = self.avatar_data_urls(usernames)
        self.account.avatar_data_url = next(
            (avatars[username] for username in usernames if username in avatars),
            None,
        )
        return self.account.avatar_data_url

    @staticmethod
    def _kind(username: str) -> str:
        if username.endswith("@chatroom"):
            return "group"
        if username.startswith("gh_"):
            return "official"
        if username.startswith("biz_"):
            return "business"
        return "private"

    def list_conversations(self) -> list[Conversation]:
        names = self._contact_names()
        self.resolve_account_display_name(names)
        found: dict[str, Conversation] = {}
        for source in self._core_sources("session"):
            path = self._decrypt(source)
            connection = _connect_readonly(path)
            connection.row_factory = sqlite3.Row
            inspector = SchemaInspector(connection)
            for table in inspector.tables():
                columns = inspector.columns(table)
                username_column = _pick(columns, USERNAME_COLUMNS)
                if not username_column:
                    continue
                time_columns = [
                    column for candidate in ("last_timestamp", "sort_timestamp", "last_time", "last_msg_time", "update_time")
                    if (column := _pick(columns, (candidate,)))
                ]
                # Name2Id and several auxiliary session tables also contain a
                # username. They are indexes, not conversations, and have no
                # authoritative last-message time.
                if not time_columns:
                    continue
                unread_column = _pick(columns, ("unread_count", "unread", "unread_num"))
                selected = [username_column, *time_columns] + ([unread_column] if unread_column else [])
                try:
                    rows = connection.execute(
                        f"SELECT {', '.join(_quote(column) for column in selected)} FROM {_quote(table)}"
                    )
                    for row in rows:
                        username = str(row[0] or "").strip()
                        if not username:
                            continue
                        timestamps: list[float] = []
                        for value in row[1 : 1 + len(time_columns)]:
                            try:
                                numeric = float(value or 0)
                                while numeric > 32_503_680_000:
                                    numeric /= 1000
                                if numeric > 0:
                                    timestamps.append(numeric)
                            except (ValueError, TypeError):
                                continue
                        try:
                            last = datetime.fromtimestamp(max(timestamps)).astimezone() if timestamps else None
                        except (OSError, OverflowError):
                            last = None
                        unread_index = 1 + len(time_columns) if unread_column else None
                        conversation_id = stable_id(username, 20)
                        candidate = Conversation(
                            conversation_id=conversation_id,
                            username=username,
                            display_name=names.get(username) or username,
                            kind=self._kind(username),  # type: ignore[arg-type]
                            last_message_at=last,
                            unread_count=int(row[unread_index] or 0) if unread_index is not None else 0,
                        )
                        previous = found.get(username)
                        if previous is None or (candidate.last_message_at or datetime.min.replace(tzinfo=timezone.utc)) > (
                            previous.last_message_at or datetime.min.replace(tzinfo=timezone.utc)
                        ):
                            found[username] = candidate
                except sqlite3.DatabaseError:
                    continue
            connection.close()
        self._conversations = {item.conversation_id: item for item in found.values()}
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc).astimezone()
        return sorted(found.values(), key=lambda item: item.last_message_at or epoch, reverse=True)

    def conversation(self, conversation_id: str) -> Conversation:
        if not self._conversations:
            self.list_conversations()
        if conversation_id not in self._conversations:
            raise KeyError("会话不存在")
        return self._conversations[conversation_id]

    @staticmethod
    def _name_map(connection: sqlite3.Connection, inspector: SchemaInspector) -> dict[str, set[str]]:
        mapping: dict[str, set[str]] = {}
        for table in inspector.tables():
            if "name2id" not in table.casefold():
                continue
            columns = inspector.columns(table)
            user_col = _pick(columns, USERNAME_COLUMNS + ("name",))
            id_col = _pick(columns, ("id", "name_id", "nameid", "chat_name_id", "table_id"))
            table_col = _pick(columns, ("table_name", "tablename"))
            if not user_col:
                continue
            selected = [user_col] + ([id_col] if id_col else []) + ([table_col] if table_col else [])
            try:
                for row in connection.execute(
                    f"SELECT {', '.join(_quote(column) for column in selected)} FROM {_quote(table)}"
                ):
                    values = mapping.setdefault(str(row[0]), set())
                    digest = hashlib.md5(str(row[0]).encode("utf-8")).hexdigest()
                    values.update((digest, f"Msg_{digest}"))
                    values.update(str(item) for item in row[1:] if item is not None)
            except sqlite3.DatabaseError:
                continue
        return mapping

    def iter_messages(
        self, conversation_id: str, allow_partial: bool = False, limit: int | None = None, offset: int = 0
    ) -> Iterable[WechatMessage]:
        conversation = self.conversation(conversation_id)
        collected: list[WechatMessage] = []
        contact_names = self._contact_names()
        own_usernames = set(_account_usernames(self.account.directory.name))
        for source in self._message_sources():
            try:
                path = self._decrypt(source)
            except AuthorizationRequired:
                if allow_partial:
                    continue
                raise
            connection = _connect_readonly(path)
            connection.row_factory = sqlite3.Row
            inspector = SchemaInspector(connection)
            identifiers = self._name_map(connection, inspector).get(conversation.username, set())
            sender_ids: dict[str, str] = {}
            for name_table in inspector.tables():
                if "name2id" not in name_table.casefold():
                    continue
                columns = inspector.columns(name_table)
                sender_column = _pick(columns, USERNAME_COLUMNS + ("name",))
                if sender_column:
                    try:
                        sender_ids.update({
                            str(row[0]): str(row[1]) for row in connection.execute(
                                f"SELECT rowid, {_quote(sender_column)} FROM {_quote(name_table)}"
                            ) if row[1]
                        })
                    except sqlite3.DatabaseError:
                        continue
            for table in inspector.tables():
                columns = inspector.columns(table)
                type_column = _pick(columns, ("local_type", "msg_type", "type"))
                time_column = _pick(columns, ("create_time", "createtime", "msg_time", "time"))
                content_column = _pick(columns, ("message_content", "content", "msg_content", "compress_content"))
                if not type_column or not time_column or not content_column:
                    continue
                user_column = _pick(columns, USERNAME_COLUMNS)
                name_id_column = _pick(columns, ("chat_name_id", "name_id", "nameid"))
                suffix = table.rsplit("_", 1)[-1]
                table_matches = bool(identifiers) and (suffix in identifiers or table in identifiers)
                where, params = "", []
                if user_column:
                    where, params = f" WHERE {_quote(user_column)} = ?", [conversation.username]
                elif name_id_column and identifiers:
                    placeholders = ",".join("?" for _ in identifiers)
                    where, params = f" WHERE CAST({_quote(name_id_column)} AS TEXT) IN ({placeholders})", list(identifiers)
                elif not table_matches:
                    continue
                try:
                    query_limit = (int(limit) + max(0, int(offset))) if limit else None
                    rows = connection.execute(
                        f"SELECT rowid AS __rowid__, * FROM {_quote(table)}{where} "
                        f"ORDER BY {_quote(time_column)} {'DESC' if limit else 'ASC'}, rowid {'DESC' if limit else 'ASC'}"
                        + (f" LIMIT {query_limit}" if query_limit else ""),
                        params,
                    )
                    for row in rows:
                        raw = dict(row)
                        sender_id = raw.get("real_sender_id")
                        if sender_id is not None and str(sender_id) in sender_ids:
                            raw["__sender_username"] = sender_ids[str(sender_id)]
                        message = normalize_message(raw, conversation_id, len(collected) + 1)
                        if message.sender_id:
                            message.sender_name = contact_names.get(message.sender_id)
                            message.outgoing = message.sender_id in own_usernames
                        if message.quote_preview and message.quote_preview.sender_id and not message.quote_preview.sender_name:
                            message.quote_preview.sender_name = contact_names.get(message.quote_preview.sender_id)
                        event = message.system_event
                        if event and event.kind == "pat":
                            event.actor_name = (
                                self.account.display_name if event.actor_id in own_usernames
                                else contact_names.get(event.actor_id or "")
                            )
                            event.target_name = (
                                self.account.display_name if event.target_id in own_usernames
                                else contact_names.get(event.target_id or "")
                            )
                            if event.actor_name and event.target_name:
                                event.text = (
                                    f'"{event.actor_name}" 拍了拍自己'
                                    if event.actor_id == event.target_id
                                    else f'"{event.actor_name}" 拍了拍 "{event.target_name}"'
                                )
                            elif "wxid_" in event.text.casefold():
                                event.text = "有人拍了拍群成员"
                            message.text = event.text
                            message.display_text = event.text
                        collected.append(message)
                except sqlite3.DatabaseError:
                    continue
            connection.close()
        collected.sort(key=lambda item: (item.sent_at, item.sequence))
        if limit:
            end = max(0, len(collected) - max(0, int(offset)))
            collected = collected[max(0, end - int(limit)) : end]
        for sequence, message in enumerate(collected, 1):
            message.sequence = sequence
            self._enrich_resource_paths(message, allow_partial)
            self._enrich_emoticon_metadata(message, allow_partial)
            self._enrich_voice_blob(message, conversation, allow_partial)
            yield message

    def message_summary(self, conversation_id: str, allow_partial: bool = False) -> dict[str, Any]:
        """Count locally available rows and report their complete time range."""
        conversation = self.conversation(conversation_id)
        total = 0
        earliest: datetime | None = None
        latest: datetime | None = None
        for source in self._message_sources():
            try:
                path = self._decrypt(source)
            except AuthorizationRequired:
                if allow_partial:
                    continue
                raise
            with closing(_connect_readonly(path)) as connection:
                inspector = SchemaInspector(connection)
                identifiers = self._name_map(connection, inspector).get(conversation.username, set())
                for table in inspector.tables():
                    columns = inspector.columns(table)
                    type_column = _pick(columns, ("local_type", "msg_type", "type"))
                    time_column = _pick(columns, ("create_time", "createtime", "msg_time", "time"))
                    content_column = _pick(columns, ("message_content", "content", "msg_content", "compress_content"))
                    if not type_column or not time_column or not content_column:
                        continue
                    user_column = _pick(columns, USERNAME_COLUMNS)
                    name_id_column = _pick(columns, ("chat_name_id", "name_id", "nameid"))
                    suffix = table.rsplit("_", 1)[-1]
                    table_matches = bool(identifiers) and (suffix in identifiers or table in identifiers)
                    where, params = "", []
                    if user_column:
                        where, params = f" WHERE {_quote(user_column)} = ?", [conversation.username]
                    elif name_id_column and identifiers:
                        placeholders = ",".join("?" for _ in identifiers)
                        where = f" WHERE CAST({_quote(name_id_column)} AS TEXT) IN ({placeholders})"
                        params = list(identifiers)
                    elif not table_matches:
                        continue
                    try:
                        count, minimum, maximum = connection.execute(
                            f"SELECT COUNT(*), MIN({_quote(time_column)}), MAX({_quote(time_column)}) "
                            f"FROM {_quote(table)}{where}", params
                        ).fetchone()
                    except sqlite3.DatabaseError:
                        continue
                    total += int(count or 0)
                    for raw, is_minimum in ((minimum, True), (maximum, False)):
                        try:
                            numeric = float(raw or 0)
                            while numeric > 32_503_680_000:
                                numeric /= 1000
                            value = datetime.fromtimestamp(numeric).astimezone() if numeric > 0 else None
                        except (TypeError, ValueError, OSError, OverflowError):
                            value = None
                        if value and is_minimum and (earliest is None or value < earliest):
                            earliest = value
                        if value and not is_minimum and (latest is None or value > latest):
                            latest = value
        return {"total": total, "earliest_at": earliest, "latest_at": latest}

    @staticmethod
    def _statistics_type(raw: Any) -> str:
        try:
            number = int(raw or 0) & 0xFFFFFFFF
        except (TypeError, ValueError):
            return "unknown"
        return TYPE_NAMES.get(number, "unknown")

    def account_statistics(self, fingerprint: str, cancel: threading.Event, progress: Any) -> AccountStatisticsReport:
        """Aggregate private/group message rows without reading message bodies."""
        names = self._contact_names()
        sessions = {row.username: row for row in self.list_conversations()}
        aggregates: dict[str, dict[str, Any]] = {}
        sources = self._message_sources()
        processed_rows = 0

        def add(username: str, raw_type: Any, count: Any, minimum: Any, maximum: Any) -> None:
            nonlocal processed_rows
            username = str(username or "").strip()
            if not username or self._kind(username) not in {"private", "group"}:
                return
            amount = int(count or 0)
            if amount <= 0:
                return
            row = aggregates.setdefault(username, {"count": 0, "min": None, "max": None, "types": {}})
            row["count"] += amount
            processed_rows += amount
            kind = self._statistics_type(raw_type)
            row["types"][kind] = row["types"].get(kind, 0) + amount
            for raw, key, chooser in ((minimum, "min", min), (maximum, "max", max)):
                try:
                    numeric = float(raw or 0)
                    while numeric > 32_503_680_000:
                        numeric /= 1000
                except (TypeError, ValueError):
                    numeric = 0
                if numeric > 0:
                    row[key] = numeric if row[key] is None else chooser(row[key], numeric)

        for source_index, source in enumerate(sources):
            if cancel.is_set():
                raise OperationCancelled("统计已取消")
            path = self._decrypt(source)
            with closing(_connect_readonly(path)) as connection:
                inspector = SchemaInspector(connection)
                mapping = self._name_map(connection, inspector)
                reverse: dict[str, str] = {}
                for username, identifiers in mapping.items():
                    for identifier in identifiers:
                        reverse[str(identifier)] = username
                tables = inspector.tables()
                for table_index, table in enumerate(tables):
                    if cancel.is_set():
                        raise OperationCancelled("统计已取消")
                    columns = inspector.columns(table)
                    type_column = _pick(columns, ("local_type", "msg_type", "type"))
                    time_column = _pick(columns, ("create_time", "createtime", "msg_time", "time"))
                    if not type_column or not time_column:
                        continue
                    user_column = _pick(columns, USERNAME_COLUMNS)
                    name_id_column = _pick(columns, ("chat_name_id", "name_id", "nameid"))
                    try:
                        if user_column:
                            query = (
                                f"SELECT {_quote(user_column)}, {_quote(type_column)}, COUNT(*), "
                                f"MIN({_quote(time_column)}), MAX({_quote(time_column)}) FROM {_quote(table)} "
                                f"GROUP BY {_quote(user_column)}, {_quote(type_column)}"
                            )
                            for username, raw_type, count, minimum, maximum in connection.execute(query):
                                add(str(username or ""), raw_type, count, minimum, maximum)
                        elif name_id_column:
                            query = (
                                f"SELECT CAST({_quote(name_id_column)} AS TEXT), {_quote(type_column)}, COUNT(*), "
                                f"MIN({_quote(time_column)}), MAX({_quote(time_column)}) FROM {_quote(table)} "
                                f"GROUP BY CAST({_quote(name_id_column)} AS TEXT), {_quote(type_column)}"
                            )
                            for identifier, raw_type, count, minimum, maximum in connection.execute(query):
                                username = reverse.get(str(identifier))
                                if username:
                                    add(username, raw_type, count, minimum, maximum)
                        else:
                            suffix = table.rsplit("_", 1)[-1]
                            username = reverse.get(table) or reverse.get(suffix)
                            if username:
                                query = (
                                    f"SELECT {_quote(type_column)}, COUNT(*), MIN({_quote(time_column)}), "
                                    f"MAX({_quote(time_column)}) FROM {_quote(table)} GROUP BY {_quote(type_column)}"
                                )
                                for raw_type, count, minimum, maximum in connection.execute(query):
                                    add(username, raw_type, count, minimum, maximum)
                    except sqlite3.DatabaseError:
                        continue
                    ratio = (source_index + (table_index + 1) / max(1, len(tables))) / max(1, len(sources))
                    progress(0.08 + ratio * 0.84, "正在统计全部会话", {
                        "phase": "messages", "database": source.name, "table": table,
                        "processed_messages": processed_rows, "conversation_count": len(aggregates),
                    })

        rows: list[ConversationStatistics] = []
        by_kind: dict[str, int] = {}
        by_type: dict[str, int] = {}
        earliest: float | None = None
        latest: float | None = None
        for username, values in aggregates.items():
            kind = self._kind(username)
            session = sessions.get(username)
            fallback = "未命名群聊" if kind == "group" else "未命名私聊"
            display = names.get(username) or (session.display_name if session and not session.display_name.startswith("wxid_") else fallback)
            minimum, maximum = values["min"], values["max"]
            earliest = minimum if minimum and earliest is None else min(earliest, minimum) if minimum else earliest
            latest = maximum if maximum and latest is None else max(latest, maximum) if maximum else latest
            by_kind[kind] = by_kind.get(kind, 0) + 1
            for key, value in values["types"].items():
                by_type[key] = by_type.get(key, 0) + value
            rows.append(ConversationStatistics(
                stable_id(username, 20), display, kind, values["count"],
                datetime.fromtimestamp(minimum).astimezone().isoformat(timespec="seconds") if minimum else None,
                datetime.fromtimestamp(maximum).astimezone().isoformat(timespec="seconds") if maximum else None,
                dict(sorted(values["types"].items())),
            ))
        rows.sort(key=lambda item: (-item.message_count, item.display_name.casefold()))
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        return AccountStatisticsReport(
            self.account.account_id, fingerprint, now, self.account.coverage.complete,
            conversation_count=len(rows), message_count=sum(item.message_count for item in rows),
            earliest_at=datetime.fromtimestamp(earliest).astimezone().isoformat(timespec="seconds") if earliest else None,
            latest_at=datetime.fromtimestamp(latest).astimezone().isoformat(timespec="seconds") if latest else None,
            by_conversation_kind=by_kind, by_message_type=dict(sorted(by_type.items())), conversations=rows,
        )

    @staticmethod
    def _value(row: sqlite3.Row | dict[str, Any], *names: str) -> Any:
        lookup = {str(key).casefold(): row[key] for key in row.keys()}
        return next((lookup[name.casefold()] for name in names if name.casefold() in lookup), None)

    def _load_resource_paths(self, allow_partial: bool) -> dict[str, list[str]]:
        if self._resource_paths is not None:
            return self._resource_paths
        result: dict[str, list[str]] = {}
        sources = [
            path for path in self._core_sources("message")
            if "resource" in path.name.casefold() or "hardlink" in path.name.casefold()
        ] + self._core_sources("hardlink")
        for source in dict.fromkeys(sources):
            try:
                path = self._decrypt(source)
            except AuthorizationRequired:
                if allow_partial:
                    continue
                raise
            connection = _connect_readonly(path)
            connection.row_factory = sqlite3.Row
            inspector = SchemaInspector(connection)
            for table in inspector.tables():
                columns = inspector.columns(table)
                identity_columns = [column for column in columns if any(
                    token in column.casefold() for token in ("local_id", "svr_id", "server_id", "msg_id", "md5")
                )]
                path_columns = [column for column in columns if any(
                    token in column.casefold() for token in ("path", "file_name", "filename")
                )]
                if not identity_columns or not path_columns:
                    continue
                selected = identity_columns + path_columns
                try:
                    for row in connection.execute(
                        f"SELECT {', '.join(_quote(column) for column in selected)} FROM {_quote(table)}"
                    ):
                        paths = [str(row[index]) for index in range(len(identity_columns), len(selected)) if row[index]]
                        for index in range(len(identity_columns)):
                            if row[index] is not None:
                                result.setdefault(str(row[index]), []).extend(paths)
                except sqlite3.DatabaseError:
                    continue
            connection.close()
        self._resource_paths = {key: list(dict.fromkeys(values)) for key, values in result.items()}
        return self._resource_paths

    def _enrich_resource_paths(self, message: WechatMessage, allow_partial: bool) -> None:
        if not message.attachments:
            return
        try:
            paths = self._load_resource_paths(allow_partial)
        except (SnapshotChanged, CorruptDatabase, OSError):
            for attachment in message.attachments:
                if not attachment.reason:
                    attachment.reason = "媒体资源索引暂时被占用或无法读取；聊天正文仍会正常导出"
            return
        identities = [
            self._value(message.raw_fields, "local_id", "id", "rowid"),
            self._value(message.raw_fields, "server_id", "svr_id", "msg_svr_id"),
        ]
        found: list[str] = []
        for identity in identities:
            if identity is not None:
                found.extend(paths.get(str(identity), []))
        if found:
            for attachment in message.attachments:
                current = list(attachment.metadata.get("candidates", []))
                attachment.metadata["candidates"] = list(dict.fromkeys(current + found))
        for attachment in message.attachments:
            current = list(attachment.metadata.get("candidates", []))
            linked: list[str] = []
            for identity in current:
                linked.extend(paths.get(str(identity), []))
            if linked:
                attachment.metadata["candidates"] = list(dict.fromkeys(current + linked))

    def _emoticon_metadata(self, allow_partial: bool) -> dict[str, dict[str, str]]:
        if self._emoticon_metadata_cache is not None:
            return self._emoticon_metadata_cache
        result: dict[str, dict[str, str]] = {}
        for source in self._core_sources("emoticon"):
            try:
                path = self._decrypt(source)
            except AuthorizationRequired:
                if allow_partial:
                    continue
                raise
            except (SnapshotChanged, CorruptDatabase, OSError):
                continue
            with closing(_connect_readonly(path)) as connection:
                inspector = SchemaInspector(connection)
                for table in inspector.tables():
                    columns = inspector.columns(table)
                    md5_column = _pick(columns, ("md5", "md5_"))
                    if not md5_column:
                        continue
                    wanted = [
                        column for name in (
                            "aes_key", "thumb_url", "tp_url", "cdn_url", "extern_url",
                            "extern_md5", "encrypt_url",
                        ) if (column := _pick(columns, (name,)))
                    ]
                    if not wanted:
                        continue
                    try:
                        rows = connection.execute(
                            f"SELECT {_quote(md5_column)}, {', '.join(_quote(column) for column in wanted)} "
                            f"FROM {_quote(table)}"
                        )
                        for row in rows:
                            md5 = str(row[0] or "").lower()
                            if not re.fullmatch(r"[0-9a-f]{32}", md5):
                                continue
                            values = {
                                wanted[index]: str(value) for index, value in enumerate(row[1:]) if value
                            }
                            if values:
                                result.setdefault(md5, {}).update(values)
                    except sqlite3.DatabaseError:
                        continue
        self._emoticon_metadata_cache = result
        return result

    def _enrich_emoticon_metadata(self, message: WechatMessage, allow_partial: bool) -> None:
        if message.message_type != "emoji" or not message.attachments:
            return
        attachment = message.attachments[0]
        md5 = next((
            str(value).lower() for key, value in attachment.metadata.items()
            if "md5" in str(key).casefold() and re.fullmatch(r"[0-9a-fA-F]{32}", str(value or ""))
        ), None)
        if not md5:
            return
        values = self._emoticon_metadata(allow_partial).get(md5, {})
        aliases = {
            "aes_key": "xml:aeskey", "thumb_url": "xml:thumburl", "tp_url": "xml:tpurl",
            "cdn_url": "xml:cdnurl", "extern_url": "xml:externurl",
            "extern_md5": "xml:externmd5", "encrypt_url": "xml:encrypturl",
        }
        for key, value in values.items():
            alias = aliases.get(key, f"db:{key}")
            if key == "aes_key" and attachment.metadata.get(alias) not in (None, "", value):
                attachment.metadata["db:aes_key"] = value
            else:
                attachment.metadata.setdefault(alias, value)

    @staticmethod
    def _decode_blob(value: Any) -> bytes | None:
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value)
        if isinstance(value, str):
            text = value.strip()
            try:
                return bytes.fromhex(text) if len(text) % 2 == 0 else None
            except ValueError:
                return None
        return None

    def _media_chat_ids(self, connection: sqlite3.Connection, inspector: SchemaInspector, username: str) -> list[int]:
        ids: list[int] = []
        for table in inspector.tables():
            if "name2id" not in table.casefold():
                continue
            columns = inspector.columns(table)
            user_column = _pick(columns, ("user_name", "username", "name"))
            if not user_column:
                continue
            try:
                rows = connection.execute(
                    f"SELECT rowid FROM {_quote(table)} WHERE {_quote(user_column)} = ?", (username,)
                )
                ids.extend(int(row[0]) for row in rows)
            except (sqlite3.DatabaseError, TypeError, ValueError):
                continue
        return ids

    def _enrich_voice_blob(self, message: WechatMessage, conversation: Conversation, allow_partial: bool) -> None:
        if message.message_type != "audio" or not message.attachments:
            return
        create_time = self._value(message.raw_fields, "create_time", "createtime", "time")
        server_id = self._value(message.raw_fields, "server_id", "svr_id", "msg_svr_id")
        sources = [path for path in self._core_sources("message") if path.name.casefold().startswith("media_")]
        for source in sources:
            try:
                path = self._decrypt(source)
            except AuthorizationRequired:
                if allow_partial:
                    continue
                raise
            except (SnapshotChanged, CorruptDatabase, OSError):
                if not message.attachments[0].reason:
                    message.attachments[0].reason = "语音媒体库暂时被占用或无法读取；聊天正文仍会正常导出"
                continue
            connection = _connect_readonly(path)
            connection.row_factory = sqlite3.Row
            inspector = SchemaInspector(connection)
            chat_ids = self._media_chat_ids(connection, inspector, conversation.username)
            for table in inspector.tables():
                if "voice" not in table.casefold():
                    continue
                columns = inspector.columns(table)
                data_column = _pick(columns, ("voice_data", "buf", "voicebuf", "data"))
                time_column = _pick(columns, ("create_time", "createtime", "time"))
                server_column = _pick(columns, ("msg_svr_id", "svr_id", "server_id", "msgsvrid"))
                chat_column = _pick(columns, ("chat_name_id", "chatnameid", "chat_nameid"))
                if not data_column:
                    continue
                filters: list[str] = []
                params: list[Any] = []
                if server_column and server_id not in (None, "", 0, "0"):
                    filters.append(f"CAST({_quote(server_column)} AS TEXT) = ?")
                    params.append(str(server_id))
                elif time_column and create_time not in (None, "", 0, "0"):
                    filters.append(f"{_quote(time_column)} = ?")
                    params.append(create_time)
                else:
                    continue
                if chat_column and chat_ids:
                    placeholders = ",".join("?" for _ in chat_ids)
                    filters.append(f"{_quote(chat_column)} IN ({placeholders})")
                    params.extend(chat_ids)
                try:
                    row = connection.execute(
                        f"SELECT {_quote(data_column)} FROM {_quote(table)} WHERE {' AND '.join(filters)} ORDER BY rowid LIMIT 1",
                        params,
                    ).fetchone()
                except sqlite3.DatabaseError:
                    continue
                blob = self._decode_blob(row[0]) if row else None
                if blob:
                    target = self.task_dir / f"voice-{message.message_id}.silk"
                    target.write_bytes(blob)
                    attachment = message.attachments[0]
                    candidates = list(attachment.metadata.get("candidates", []))
                    attachment.metadata["candidates"] = [str(target), *candidates]
                    connection.close()
                    return
            connection.close()
