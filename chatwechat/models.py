from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal


def _iso(value: datetime | None) -> str | None:
    return value.astimezone().isoformat(timespec="seconds") if value else None


@dataclass(slots=True)
class KeyCoverage:
    covered: int = 0
    total: int = 0
    fingerprint: str | None = None
    missing_databases: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.total > 0 and self.covered == self.total

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "complete": self.complete}


@dataclass(slots=True)
class WechatAccount:
    account_id: str
    directory: Path
    display_name: str
    active: bool
    last_database_write: datetime | None
    size_bytes: int
    database_count: int
    coverage: KeyCoverage = field(default_factory=KeyCoverage)
    avatar_data_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["directory"] = str(self.directory)
        value["last_database_write"] = _iso(self.last_database_write)
        value["coverage"] = self.coverage.to_dict()
        return value


@dataclass(slots=True)
class Conversation:
    conversation_id: str
    username: str
    display_name: str
    kind: Literal["private", "group", "official", "business", "unknown"]
    last_message_at: datetime | None = None
    message_count: int | None = None
    unread_count: int = 0
    avatar_path: str | None = None

    def to_dict(self, include_username: bool = False) -> dict[str, Any]:
        value = {**asdict(self), "last_message_at": _iso(self.last_message_at)}
        if not include_username:
            value.pop("username", None)
        return value


@dataclass(slots=True)
class Attachment:
    attachment_id: str
    category: Literal["image", "video", "audio", "file", "emoji", "other"]
    source_path: str | None = None
    exported_path: str | None = None
    original_name: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    available: bool = False
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    status: Literal["pending", "exported", "raw_preserved", "missing", "failed", "download_on_export"] = "pending"
    source_kind: Literal["local", "network", "legacy_http", "private_cdn", "none"] = "none"
    quality: Literal["original", "medium", "thumbnail", "unknown"] = "unknown"
    reason_code: str | None = None
    recovery_method: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("source_path", None)
        value["metadata"] = {
            key: item for key, item in self.metadata.items() if key != "candidates"
        }
        return value


@dataclass(slots=True)
class QuotePreview:
    sender_id: str | None = None
    sender_name: str | None = None
    text: str | None = None
    message_type: str | None = None
    message_id: str | None = None


@dataclass(slots=True)
class SystemEvent:
    kind: str
    text: str
    actor_id: str | None = None
    target_id: str | None = None
    actor_name: str | None = None
    target_name: str | None = None
    template: str | None = None


@dataclass(slots=True)
class WechatMessage:
    message_id: str
    conversation_id: str
    sequence: int
    sent_at: datetime
    sender_id: str | None
    sender_name: str | None
    outgoing: bool
    message_type: str
    text: str | None = None
    attachments: list[Attachment] = field(default_factory=list)
    quoted_message_id: str | None = None
    quote_preview: QuotePreview | None = None
    system_event: SystemEvent | None = None
    raw_type: int | str | None = None
    raw_fields: dict[str, Any] = field(default_factory=dict)
    raw_xml: str | None = None
    display_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["sent_at"] = _iso(self.sent_at)
        value["attachments"] = [attachment.to_dict() for attachment in self.attachments]
        return value


@dataclass(slots=True)
class ExportRequest:
    account_id: str
    conversation_ids: list[str]
    output_directory: Path
    start_at: datetime | None = None
    end_at: datetime | None = None
    message_types: list[str] = field(default_factory=list)
    media_categories: list[str] = field(default_factory=list)
    formats: list[Literal["html", "markdown", "json"]] = field(
        default_factory=lambda: ["html", "markdown", "json"]
    )
    include_media: bool = True
    allow_partial: bool = False
    download_missing_media: bool = True
    allow_legacy_http_media: bool = True
    visual_download_limit_mib: int = 50
    audio_download_limit_mib: int = 100
    large_download_limit_mib: int = 500
    folder_layout: Literal["flat", "by_type", "account_by_type"] = "by_type"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ExportRequest":
        def parse_time(raw: Any) -> datetime | None:
            if not raw:
                return None
            parsed = datetime.fromisoformat(str(raw))
            return parsed.astimezone() if parsed.tzinfo else parsed.astimezone()

        def parse_limit(name: str, default: int) -> int:
            try:
                return min(2048, max(1, int(value.get(name, default))))
            except (TypeError, ValueError):
                return default

        return cls(
            account_id=str(value["account_id"]),
            conversation_ids=[str(x) for x in value.get("conversation_ids", [])],
            output_directory=Path(value["output_directory"]),
            start_at=parse_time(value.get("start_at")),
            end_at=parse_time(value.get("end_at")),
            message_types=list(value.get("message_types", [])),
            media_categories=list(value.get("media_categories", [])),
            formats=list(value.get("formats", ["html", "markdown", "json"])),
            include_media=bool(value.get("include_media", True)),
            allow_partial=bool(value.get("allow_partial", False)),
            download_missing_media=bool(value.get("download_missing_media", True)),
            allow_legacy_http_media=bool(value.get("allow_legacy_http_media", True)),
            visual_download_limit_mib=parse_limit("visual_download_limit_mib", 50),
            audio_download_limit_mib=parse_limit("audio_download_limit_mib", 100),
            large_download_limit_mib=parse_limit("large_download_limit_mib", 500),
            folder_layout=(
                str(value.get("folder_layout", "by_type"))
                if str(value.get("folder_layout", "by_type")) in {"flat", "by_type", "account_by_type"}
                else "by_type"
            ),  # type: ignore[arg-type]
        )


@dataclass(slots=True)
class ExportEstimate:
    conversation_count: int
    message_count: int
    media_count: int
    estimated_bytes: int
    free_bytes: int
    warnings: list[str] = field(default_factory=list)
    known_bytes: int = 0
    remote_size_unknown_count: int = 0
    local_recoverable_count: int = 0
    network_candidate_count: int = 0
    unavailable_count: int = 0
    by_category: dict[str, dict[str, int]] = field(default_factory=dict)
    calculated_at: str = ""


@dataclass(slots=True)
class ExportResult:
    root: Path
    conversation_count: int
    message_count: int
    media_count: int
    warnings: list[str] = field(default_factory=list)
    media_summary: dict[str, Any] = field(default_factory=dict)
    warning_details: list[dict[str, Any]] = field(default_factory=list)
    export_id: str = ""
    conversation_paths: list[str] = field(default_factory=list)
    conversation_archives: list[dict[str, str]] = field(default_factory=list)
    open_path: str = ""
    created_count: int = 0
    replaced_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "root": str(self.root)}


ThemePreference = Literal["system", "light", "dark"]


@dataclass(slots=True)
class SearchResult:
    conversation_id: str
    conversation_name: str
    message_id: str
    sent_at: datetime
    sender_name: str
    message_type: str
    snippet: str
    conversation_kind: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "sent_at": _iso(self.sent_at)}


@dataclass(slots=True)
class MediaIssue:
    category: str
    status: str
    reason_code: str | None
    count: int = 1


@dataclass(slots=True)
class MediaRecoveryItem:
    conversation_id: str
    conversation_name: str
    sent_at: datetime
    category: str
    status: str
    reason_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "sent_at": _iso(self.sent_at)}


@dataclass(slots=True)
class MediaRecoveryReport:
    referenced: int = 0
    recoverable: int = 0
    missing: int = 0
    unsupported: int = 0
    by_category: dict[str, dict[str, int]] = field(default_factory=dict)
    issues: list[MediaIssue] = field(default_factory=list)
    items: list[MediaRecoveryItem] = field(default_factory=list)
    truncated: int = 0

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["items"] = [item.to_dict() for item in self.items]
        return value


@dataclass(slots=True)
class OperationHistoryEntry:
    history_id: str
    kind: str
    status: str
    created_at: str
    completed_at: str
    result_path: str | None = None
    conversation_count: int = 0
    message_count: int = 0
    media_count: int = 0
    formats: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    warning_details: list[dict[str, Any]] = field(default_factory=list)
    duration_seconds: float | None = None
    error_summary: str | None = None
    result_summary: dict[str, Any] = field(default_factory=dict)
    directory_health: str = "not_applicable"
    original_path: str | None = None
    current_path: str | None = None
    archive_id: str | None = None
    deleted_at: str | None = None
    output_root: str | None = None
    storage_mode: Literal["batch", "shared"] = "batch"
    export_id: str | None = None
    conversation_archives: list[dict[str, str]] = field(default_factory=list)
    superseded_count: int = 0


@dataclass(slots=True)
class ConversationStatistics:
    conversation_id: str
    display_name: str
    kind: str
    message_count: int = 0
    earliest_at: str | None = None
    latest_at: str | None = None
    by_message_type: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class AccountStatisticsReport:
    account_id: str
    database_fingerprint: str
    calculated_at: str
    complete: bool
    stale: bool = False
    conversation_count: int = 0
    message_count: int = 0
    earliest_at: str | None = None
    latest_at: str | None = None
    by_conversation_kind: dict[str, int] = field(default_factory=dict)
    by_message_type: dict[str, int] = field(default_factory=dict)
    conversations: list[ConversationStatistics] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExportPreset:
    preset_id: str
    name: str
    formats: list[str] = field(default_factory=lambda: ["html", "markdown", "json"])
    message_types: list[str] = field(default_factory=list)
    media_categories: list[str] = field(default_factory=list)
    include_media: bool = True
    download_missing_media: bool = True
    allow_legacy_http_media: bool = True
    visual_download_limit_mib: int = 50
    audio_download_limit_mib: int = 100
    large_download_limit_mib: int = 500
    allow_partial: bool = False
    start_at: str | None = None
    end_at: str | None = None
