from __future__ import annotations

import base64
import html
import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .errors import OperationCancelled
from .media import MediaExporter, safe_filename, sha256_file
from .models import Conversation, ExportRequest, ExportResult, WechatAccount, WechatMessage
from .redaction import stable_id
from .repository import WechatRepository


Progress = Callable[[float, str], None]
INTERNAL_ID = re.compile(r"\bwxid_[A-Za-z0-9_-]+\b", re.IGNORECASE)


def _retry_sharing(operation, attempts: int = 10):
    for attempt in range(attempts):
        try:
            return operation()
        except OSError as error:
            if getattr(error, "winerror", None) not in {32, 33} or attempt + 1 == attempts:
                raise
            time.sleep(0.1 * (attempt + 1))


def _matches(message: WechatMessage, request: ExportRequest) -> bool:
    if request.start_at and message.sent_at < request.start_at:
        return False
    if request.end_at and message.sent_at > request.end_at:
        return False
    return not request.message_types or message.message_type in request.message_types


def _safe_display(value: str | None, replacements: dict[str, str] | None = None, fallback: str = "未知成员") -> str:
    replacements = replacements or {}
    if not value:
        return fallback
    if INTERNAL_ID.fullmatch(value.strip()):
        return replacements.get(value, fallback)
    return INTERNAL_ID.sub(lambda match: replacements.get(match.group(0), fallback), value)


def _sender_name(message: WechatMessage, account_name: str, replacements: dict[str, str]) -> str:
    if message.outgoing:
        return _safe_display(message.sender_name, replacements, account_name) if message.sender_name else account_name
    return _safe_display(message.sender_name, replacements)


def _display_text(message: WechatMessage, replacements: dict[str, str]) -> str:
    if message.system_event:
        return _safe_display(message.system_event.text, replacements, "系统消息")
    value = message.display_text if message.display_text is not None else message.text
    if value:
        return _safe_display(value, replacements, f"[{message.message_type}]")
    return "" if message.attachments else f"[{message.message_type}]"


def _attachment_markdown(attachment) -> list[str]:
    label = _safe_display(attachment.original_name, fallback=attachment.category)
    if attachment.available and attachment.exported_path:
        link = attachment.exported_path.replace(" ", "%20")
        if attachment.category in {"image", "emoji"} and (attachment.mime_type or "").startswith("image/"):
            return [f"![{label}]({link})"]
        return [f"[{label}]({link})"]
    lines = [f"> {attachment.reason or '本地媒体不可用'}"]
    if attachment.exported_path:
        reason_code = attachment.reason_code or "local_cache_unrecognized"
        lines.extend(
            (
                "",
                "<details>",
                "<summary>诊断详情</summary>",
                "",
                f"- 原因代码：`{reason_code}`",
                f"- [打开原始缓存文件]({attachment.exported_path.replace(' ', '%20')})",
                "",
                "</details>",
            )
        )
    return lines


def _render_markdown(
    message: WechatMessage,
    account_name: str,
    replacements: dict[str, str],
    include_day: bool,
) -> str:
    text = _display_text(message, replacements)
    lines: list[str] = []
    if include_day:
        lines.extend((f"## {message.sent_at.strftime('%Y-%m-%d')}", ""))
    if message.system_event or message.message_type in {"system", "revoke", "pat"}:
        lines.extend((f"> {message.sent_at.strftime('%H:%M:%S')} · {text}", ""))
        return "\n".join(lines) + "\n"

    sender = _sender_name(message, account_name, replacements)
    lines.extend((f"### {message.sent_at.strftime('%H:%M:%S')} · {sender}", "", text))
    quote = message.quote_preview
    if quote:
        quote_sender = _safe_display(quote.sender_name, replacements)
        quote_text = _safe_display(quote.text, replacements, "[引用内容]")
        lines.extend(("", f"> **{quote_sender}**", f"> {quote_text.replace(chr(10), chr(10) + '> ')}"))
    for attachment in message.attachments:
        lines.extend(("", *_attachment_markdown(attachment)))
    lines.extend(("", ""))
    return "\n".join(lines)


HTML_HEAD = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
:root{{--bg:#ededed;--bar:#f7f7f7;--text:#171717;--muted:#858585;--line:#dedede;--in:#fff;--out:#95ec69;--quote:rgba(0,0,0,.055);--accent:#07c160}}
*{{box-sizing:border-box}}html{{background:var(--bg)}}body{{margin:0;color:var(--text);font:14px/1.55 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}}
header{{position:sticky;top:0;z-index:5;background:rgba(247,247,247,.96);border-bottom:1px solid var(--line);backdrop-filter:blur(14px)}}.head{{max-width:980px;margin:auto;padding:16px 22px}}
h1{{margin:0 0 10px;font-size:20px}}.filters{{display:grid;grid-template-columns:1fr 150px;gap:8px}}input,select{{border:1px solid #d4d4d4;border-radius:6px;padding:9px 11px;background:#fff;color:#222}}
main{{max-width:980px;margin:auto;padding:22px 18px 70px}}.day{{display:flex;justify-content:center;margin:26px 0 18px}}.day span,.system span{{padding:3px 9px;border-radius:4px;background:#d4d4d4;color:#fff;font-size:12px}}
.row{{display:flex;align-items:flex-start;gap:10px;margin:16px 0}}.row.mine{{flex-direction:row-reverse}}.avatar{{width:40px;height:40px;border-radius:4px;object-fit:cover;background:#cfd3d2;flex:0 0 40px}}
.avatar.text{{display:grid;place-items:center;color:#fff;font-size:14px;font-weight:650;background:#8aa09a}}.stack{{max-width:min(68%,680px)}}.mine .stack{{display:flex;flex-direction:column;align-items:flex-end}}.sender{{font-size:12px;color:var(--muted);margin:0 0 4px 2px}}
.bubble{{position:relative;padding:9px 12px;border-radius:5px;background:var(--in);box-shadow:0 1px 1px rgba(0,0,0,.05);white-space:pre-wrap;overflow-wrap:anywhere}}.mine .bubble{{background:var(--out)}}
.bubble:before{{content:"";position:absolute;left:-7px;top:12px;border-width:6px 8px 6px 0;border-style:solid;border-color:transparent var(--in) transparent transparent}}.mine .bubble:before{{left:auto;right:-7px;border-width:6px 0 6px 8px;border-color:transparent transparent transparent var(--out)}}
.time{{font-size:11px;color:#999;margin:4px 2px 0}}.quote{{margin:7px 0 0;padding:7px 9px;border-left:3px solid rgba(0,0,0,.18);border-radius:3px;background:var(--quote);color:#555;font-size:12px;white-space:pre-wrap}}.quote b{{display:block;margin-bottom:2px;color:#333}}
.system{{display:flex;justify-content:center;text-align:center;margin:16px 0}}.system span{{max-width:80%;background:transparent;color:#a0a0a0}}
.media{{display:block;max-width:min(420px,100%);max-height:560px;border-radius:5px;margin-top:8px;object-fit:contain;cursor:zoom-in}}.emoji{{max-width:150px;max-height:150px;background:transparent}}video,audio{{display:block;max-width:100%;margin-top:8px}}.missing{{margin-top:8px;padding:7px 9px;border-radius:4px;background:rgba(180,90,40,.09);color:#a75b36;font-size:12px}}.missing details{{margin-top:5px;color:#777}}.missing summary{{cursor:pointer;user-select:none}}.missing a{{color:#167250}}
.file{{display:inline-block;margin-top:8px;color:#167250;text-decoration:none}}.hidden{{display:none!important}}#lightbox{{position:fixed;inset:0;z-index:20;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.86);padding:28px}}#lightbox.open{{display:flex}}#lightbox img{{max-width:96vw;max-height:94vh;object-fit:contain}}
@media(max-width:640px){{.filters{{grid-template-columns:1fr}}main{{padding-inline:12px}}.stack{{max-width:78%}}.avatar{{width:36px;height:36px;flex-basis:36px}}}}
@media print{{header{{position:static}}.filters{{display:none}}main{{max-width:none}}}}
</style></head><body><header><div class="head"><h1>{title}</h1><div class="filters"><input id="search" type="search" placeholder="筛选正文、发送者或消息类型"><select id="type"><option value="">全部消息</option><option value="text">文字</option><option value="image">图片</option><option value="emoji">表情</option><option value="file">文件</option><option value="system">系统提示</option></select></div></div></header><main>
"""

HTML_FOOT = """</main><div id="lightbox"><img alt="图片预览"></div><script>
const search=document.querySelector('#search'),type=document.querySelector('#type'),rows=[...document.querySelectorAll('[data-message]')];
function filter(){const q=search.value.trim().toLowerCase(),t=type.value;rows.forEach(row=>row.classList.toggle('hidden',!!((q&&!row.dataset.search.includes(q))||(t&&row.dataset.type!==t&&!(t==='system'&&['system','revoke','pat'].includes(row.dataset.type))))));}
search.addEventListener('input',filter);type.addEventListener('change',filter);
const box=document.querySelector('#lightbox'),large=box.querySelector('img');document.querySelectorAll('img.media').forEach(img=>img.addEventListener('click',()=>{large.src=img.src;box.classList.add('open')}));box.addEventListener('click',()=>{box.classList.remove('open');large.removeAttribute('src')});document.addEventListener('keydown',e=>{if(e.key==='Escape')box.click()});
</script></body></html>"""


def _avatar_html(path: str | None, sender: str) -> str:
    if path:
        return f'<img class="avatar" loading="lazy" src="{html.escape(path, quote=True)}" alt="{html.escape(sender)}">'
    return f'<span class="avatar text">{html.escape((sender or "?")[:1])}</span>'


def _attachment_html(attachment) -> str:
    if attachment.available and attachment.exported_path:
        path = html.escape(attachment.exported_path, quote=True)
        label = html.escape(_safe_display(attachment.original_name, fallback=attachment.category))
        if attachment.category in {"image", "emoji"} and (attachment.mime_type or "").startswith("image/"):
            css = "media emoji" if attachment.category == "emoji" else "media"
            return f'<img class="{css}" loading="lazy" src="{path}" alt="{label}">'
        if attachment.category == "video":
            return f'<video controls preload="metadata" src="{path}"></video>'
        if attachment.category == "audio":
            return f'<audio controls preload="metadata" src="{path}"></audio>'
        return f'<a class="file" href="{path}">📎 {label}</a>'
    diagnostic = ""
    if attachment.exported_path:
        raw_path = html.escape(attachment.exported_path, quote=True)
        reason_code = html.escape(attachment.reason_code or "local_cache_unrecognized")
        diagnostic = (
            '<details><summary>诊断详情</summary>'
            f'<div>原因代码：<code>{reason_code}</code></div>'
            f'<a href="{raw_path}">打开原始缓存文件</a></details>'
        )
    return f'<div class="missing">{html.escape(attachment.reason or "本地媒体不可用")}{diagnostic}</div>'


def _render_html(
    message: WechatMessage,
    account_name: str,
    replacements: dict[str, str],
    avatar_path: str | None,
    include_day: bool,
) -> str:
    text = _display_text(message, replacements)
    day = f'<div class="day"><span>{message.sent_at.strftime("%Y年%m月%d日")}</span></div>' if include_day else ""
    search_sender = _sender_name(message, account_name, replacements)
    search = html.escape(f"{search_sender} {message.message_type} {text}".casefold(), quote=True)
    attrs = f'data-message data-type="{html.escape(message.message_type, quote=True)}" data-search="{search}"'
    if message.system_event or message.message_type in {"system", "revoke", "pat"}:
        return f'{day}<div class="system" {attrs}><span>{html.escape(text)}</span></div>\n'

    sender = search_sender
    quote_html = ""
    if message.quote_preview:
        quote_sender = _safe_display(message.quote_preview.sender_name, replacements)
        quote_text = _safe_display(message.quote_preview.text, replacements, "[引用内容]")
        quote_html = f'<div class="quote"><b>{html.escape(quote_sender)}</b>{html.escape(quote_text)}</div>'
    media = "".join(_attachment_html(item) for item in message.attachments)
    mine = " mine" if message.outgoing else ""
    return (
        f'{day}<article class="row{mine}" {attrs}>{_avatar_html(avatar_path, sender)}'
        f'<div class="stack"><div class="sender">{html.escape(sender)}</div>'
        f'<div class="bubble">{html.escape(text)}{quote_html}{media}</div>'
        f'<div class="time">{message.sent_at.strftime("%H:%M:%S")}</div></div></article>\n'
    )


class ConversationWriter:
    def __init__(self, directory: Path, conversation: Conversation, formats: list[str], account_name: str):
        self.directory = directory
        self.conversation = conversation
        self.formats = formats
        self.account_name = _safe_display(account_name, fallback="当前账号")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.json_stream = self.md_stream = self.html_stream = None
        self.first_json = True
        self.last_day: str | None = None
        self.participants: dict[str, dict[str, Any]] = {}
        self.replacements: dict[str, str] = {}
        title = _safe_display(conversation.display_name, fallback="微信会话")
        if "json" in formats:
            self.json_stream = (directory / "chat.json").open("w", encoding="utf-8", newline="\n")
            self.json_stream.write('{\n  "version": 2,\n  "conversation": ')
            json.dump(conversation.to_dict(include_username=True), self.json_stream, ensure_ascii=False, indent=2)
            self.json_stream.write(',\n  "messages": [\n')
        if "markdown" in formats:
            self.md_stream = (directory / "chat.md").open("w", encoding="utf-8", newline="\n")
            self.md_stream.write(f"# {title}\n\n")
        if "html" in formats:
            self.html_stream = (directory / "chat.html").open("w", encoding="utf-8", newline="\n")
            self.html_stream.write(HTML_HEAD.format(title=html.escape(title)))

    def _track_participant(self, message: WechatMessage, sender: str, avatar_path: str | None) -> None:
        if message.sender_id:
            self.replacements[message.sender_id] = sender
            self.participants[message.sender_id] = {
                "sender_id": message.sender_id,
                "display_name": sender,
                "avatar_path": avatar_path,
                "is_self": message.outgoing,
            }
        quote = message.quote_preview
        if quote and quote.sender_id:
            quote_name = _safe_display(quote.sender_name, self.replacements)
            if quote.sender_name:
                self.replacements[quote.sender_id] = quote_name
            self.participants.setdefault(quote.sender_id, {
                "sender_id": quote.sender_id,
                "display_name": quote_name,
                "avatar_path": None,
                "is_self": False,
            })

    def write(self, message: WechatMessage, avatar_path: str | None = None) -> None:
        sender = _sender_name(message, self.account_name, self.replacements)
        self._track_participant(message, sender, avatar_path)
        if self.json_stream:
            if not self.first_json:
                self.json_stream.write(",\n")
            value = message.to_dict()
            value["sender_display_name"] = sender
            encoded = json.dumps(value, ensure_ascii=False, indent=2)
            self.json_stream.write("    " + encoded.replace("\n", "\n    "))
            self.first_json = False
        day = message.sent_at.strftime("%Y-%m-%d")
        include_day = day != self.last_day
        if self.md_stream:
            self.md_stream.write(_render_markdown(message, self.account_name, self.replacements, include_day))
        if self.html_stream:
            self.html_stream.write(_render_html(message, self.account_name, self.replacements, avatar_path, include_day))
        self.last_day = day

    def close(self) -> None:
        if self.json_stream:
            self.json_stream.write('\n  ],\n  "participants": ')
            json.dump(list(self.participants.values()), self.json_stream, ensure_ascii=False, indent=2)
            self.json_stream.write("\n}\n")
            self.json_stream.close()
        if self.md_stream:
            self.md_stream.close()
        if self.html_stream:
            self.html_stream.write(HTML_FOOT)
            self.html_stream.close()


def _write_avatar(data_url: str, directory: Path, sender_id: str) -> str | None:
    match = re.fullmatch(r"data:(image/(?:jpeg|png|gif|webp));base64,([A-Za-z0-9+/=]+)", data_url or "")
    if not match:
        return None
    extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp"}[match.group(1)]
    try:
        data = base64.b64decode(match.group(2), validate=True)
    except ValueError:
        return None
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stable_id(sender_id, 20)}{extension}"
    if not path.exists():
        path.write_bytes(data)
    return path.as_posix()


def _relativize_attachment(attachment, folder: Path) -> None:
    if attachment.exported_path:
        try:
            attachment.exported_path = Path(attachment.exported_path).relative_to(folder).as_posix()
        except ValueError:
            pass


def _read_conversation_manifest(directory: Path) -> dict[str, Any] | None:
    try:
        value = json.loads((directory / "_export_manifest.json").read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def _shared_archive_index(output: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    checked = 0
    root_parts = len(output.parts)
    for current, directories, files in os.walk(output, followlinks=False):
        current_path = Path(current)
        depth = len(current_path.parts) - root_parts
        directories[:] = [name for name in directories if not name.startswith((".", "$"))]
        if depth >= 4:
            directories[:] = []
        checked += 1
        if checked > 4000 or "_export_manifest.json" not in files:
            continue
        manifest = _read_conversation_manifest(current_path)
        if manifest and manifest.get("storage_mode") == "shared" and manifest.get("conversation_archive_id"):
            result[str(manifest["conversation_archive_id"])] = current_path
    return result


def _layout_parent(output: Path, layout: str, account_name: str, kind: str) -> Path:
    kind_name = "群聊" if kind == "group" else "私聊"
    if layout == "flat":
        return output
    if layout == "account_by_type":
        return output / safe_filename(account_name, "未命名账号") / kind_name
    return output / kind_name


def _choose_target(
    parent: Path,
    title: str,
    account_name: str,
    account_id: str,
    archive_id: str,
    reserved: set[str],
) -> Path:
    base = safe_filename(title, "未命名会话")
    base_path = parent / base
    base_manifest = _read_conversation_manifest(base_path) if base_path.is_dir() else None
    cross_account_collision = bool(
        base_manifest
        and base_manifest.get("storage_mode") == "shared"
        and str(base_manifest.get("account_id") or "") != account_id
    )
    candidates = [base]
    if cross_account_collision:
        candidates.append(safe_filename(f"{base}（{account_name}）", base))
    suffix = 2
    while True:
        if candidates:
            name = candidates.pop(0)
        else:
            name = f"{base}（{suffix}）"
            suffix += 1
        candidate = parent / name
        key = str(candidate.resolve()).casefold()
        if key in reserved:
            continue
        manifest = _read_conversation_manifest(candidate) if candidate.is_dir() else None
        if not candidate.exists() or (
            manifest
            and manifest.get("storage_mode") == "shared"
            and manifest.get("conversation_archive_id") == archive_id
            and manifest.get("account_id") == account_id
        ):
            reserved.add(key)
            return candidate


def _account_identifiers(directory_name: str) -> set[str]:
    values = {directory_name}
    base, separator, suffix = directory_name.rpartition("_")
    if (
        separator
        and base.startswith("wxid_")
        and len(suffix) == 4
        and all(character in "0123456789abcdefABCDEF" for character in suffix)
    ):
        values.add(base)
    return values


def _apply_original_names(
    conversation: Conversation,
    message: WechatMessage,
    original_names: dict[str, str],
    account_usernames: set[str],
    account_name: str,
) -> None:
    """Apply profile nicknames to an export copy while retaining raw IDs in JSON."""
    if message.sender_id:
        message.sender_name = (
            account_name if message.sender_id in account_usernames
            else original_names.get(message.sender_id)
        )
    quote = message.quote_preview
    if quote and quote.sender_id:
        quote.sender_name = (
            account_name if quote.sender_id in account_usernames
            else original_names.get(quote.sender_id)
        )
    event = message.system_event
    if event:
        if event.actor_id:
            event.actor_name = account_name if event.actor_id in account_usernames else original_names.get(event.actor_id)
        if event.target_id:
            event.target_name = account_name if event.target_id in account_usernames else original_names.get(event.target_id)
        if event.kind == "pat" and event.actor_name and event.target_name:
            event.text = (
                f'“{event.actor_name}”拍了拍自己'
                if event.actor_id == event.target_id
                else f'“{event.actor_name}”拍了拍“{event.target_name}”'
            )
            message.text = event.text
            message.display_text = event.text


def _media_stats(messages: list[WechatMessage]) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    attachments = [item for message in messages for item in message.attachments if item.status != "pending"]
    categories: dict[str, dict[str, int]] = {}
    reasons: Counter[tuple[str, str, str]] = Counter()
    for item in attachments:
        row = categories.setdefault(item.category, {"referenced": 0, "local": 0, "network": 0, "legacy_http": 0, "private_cdn": 0, "raw_preserved": 0, "missing": 0, "failed": 0})
        row["referenced"] += 1
        if item.status == "exported" and item.source_kind in {"local", "network", "legacy_http", "private_cdn"}:
            row[item.source_kind] += 1
        if item.status in {"missing", "failed"}:
            row[item.status] += 1
        if item.status == "raw_preserved" or (item.exported_path and item.status == "failed"):
            row["raw_preserved"] += 1
        if item.reason_code:
            reasons[(item.reason_code, item.category, item.reason or "媒体不可用")] += 1
    summary = {
        "referenced": len(attachments),
        "local_recovered": sum(1 for item in attachments if item.status == "exported" and item.source_kind == "local"),
        "network_downloaded": sum(1 for item in attachments if item.status == "exported" and item.source_kind == "network"),
        "legacy_http_downloaded": sum(1 for item in attachments if item.status == "exported" and item.source_kind == "legacy_http"),
        "private_cdn_downloaded": sum(1 for item in attachments if item.status == "exported" and item.source_kind == "private_cdn"),
        "raw_preserved": sum(1 for item in attachments if item.status == "raw_preserved" or (item.exported_path and item.status == "failed")),
        "missing": sum(1 for item in attachments if item.status == "missing"),
        "failed": sum(1 for item in attachments if item.status == "failed"),
        "by_category": categories,
    }
    details = [
        {"code": code, "category": category, "count": count, "message": message}
        for (code, category, message), count in sorted(reasons.items())
    ]
    warnings = list(dict.fromkeys(detail["message"] for detail in details))
    return summary, details, warnings


def export_archive(
    account: WechatAccount,
    repository: WechatRepository,
    request: ExportRequest,
    cancel: threading.Event,
    progress: Progress,
) -> ExportResult:
    output = request.output_directory.resolve()
    output.mkdir(parents=True, exist_ok=True)
    original_name_source = hasattr(repository, "contact_original_names")
    original_names = repository.contact_original_names() if original_name_source else {}
    account_usernames = _account_identifiers(account.directory.name)
    account_name = next(
        (original_names[username] for username in account_usernames if original_names.get(username)),
        _safe_display(account.display_name, fallback="当前账号"),
    )
    staging_parent = Path(tempfile.mkdtemp(prefix=".chatwechat-", dir=output))
    staged_root = staging_parent / "new"
    backup_root = staging_parent / "previous"
    staged_root.mkdir()
    media_exporter = MediaExporter(
        account.account_id,
        account.directory,
        repository.store,
        download_missing_media=request.download_missing_media,
        allow_legacy_http_media=request.allow_legacy_http_media,
        visual_download_limit_mib=request.visual_download_limit_mib,
        audio_download_limit_mib=request.audio_download_limit_mib,
        large_download_limit_mib=request.large_download_limit_mib,
    )
    total_messages = total_media = processed_messages = 0
    aggregate_summary = {"referenced": 0, "local_recovered": 0, "network_downloaded": 0, "legacy_http_downloaded": 0, "private_cdn_downloaded": 0, "raw_preserved": 0, "missing": 0, "failed": 0, "by_category": {}}
    aggregate_details: Counter[tuple[str, str, str]] = Counter()
    export_id = uuid.uuid4().hex
    existing_archives = _shared_archive_index(output)
    reserved_targets: set[str] = set()
    actions: list[dict[str, Any]] = []
    try:
        expected_messages = sum(repository.message_summary(cid, request.allow_partial)["total"] for cid in request.conversation_ids)
        for conversation_id in request.conversation_ids:
            if cancel.is_set():
                raise OperationCancelled("导出已取消")
            conversation = repository.conversation(conversation_id)
            original_conversation_name = original_names.get(conversation.username)
            if conversation.kind == "private" and original_name_source:
                export_title = original_conversation_name or "未命名私聊"
            else:
                export_title = _safe_display(conversation.display_name, fallback="未命名会话")
            export_conversation = Conversation(
                conversation_id=conversation.conversation_id,
                username=conversation.username,
                display_name=export_title,
                kind=conversation.kind,
                last_message_at=conversation.last_message_at,
                message_count=conversation.message_count,
                unread_count=conversation.unread_count,
                avatar_path=conversation.avatar_path,
            )
            conversation_archive_id = stable_id(f"{account.account_id}:{conversation.username}", 32)
            target_parent = _layout_parent(output, request.folder_layout, account_name, conversation.kind)
            target = _choose_target(
                target_parent, export_title, account_name, account.account_id,
                conversation_archive_id, reserved_targets,
            )
            folder = staged_root / conversation_archive_id
            writer = ConversationWriter(folder, export_conversation, request.formats, account_name)
            exported_messages: list[WechatMessage] = []
            try:
                batch: list[WechatMessage] = []

                def flush() -> None:
                    nonlocal total_messages, total_media
                    if not batch:
                        return
                    if cancel.is_set():
                        raise OperationCancelled("导出已取消")
                    selected = [
                        attachment for message in batch for attachment in message.attachments
                        if request.include_media and (not request.media_categories or attachment.category in request.media_categories)
                    ]
                    media_exporter.export_many([(attachment, folder / "media") for attachment in selected])
                    for attachment in selected:
                        _relativize_attachment(attachment, folder)
                    total_media += sum(1 for item in selected if item.available)
                    usernames = [message.sender_id for message in batch if message.sender_id]
                    avatar_urls = repository.avatar_data_urls(usernames) if hasattr(repository, "avatar_data_urls") else {}
                    avatar_paths: dict[str, str] = {}
                    for sender_id, data_url in avatar_urls.items():
                        absolute = _write_avatar(data_url, folder / "media" / "avatars", sender_id)
                        if absolute:
                            avatar_paths[sender_id] = Path(absolute).relative_to(folder).as_posix()
                    for message in batch:
                        _apply_original_names(conversation, message, original_names, account_usernames, account_name)
                        writer.write(message, avatar_paths.get(message.sender_id or ""))
                        exported_messages.append(message)
                        total_messages += 1
                    batch.clear()

                for message in repository.iter_messages(conversation_id, request.allow_partial):
                    if cancel.is_set():
                        raise OperationCancelled("导出已取消")
                    processed_messages += 1
                    if processed_messages % 50 == 0 or processed_messages == expected_messages:
                        ratio = processed_messages / max(1, expected_messages)
                        progress(min(0.95, 0.05 + ratio * 0.90), f"正在读取全部记录：{processed_messages}/{expected_messages}")
                    if _matches(message, request):
                        batch.append(message)
                        if len(batch) >= 50:
                            flush()
                flush()
            finally:
                writer.close()

            summary, details, warnings = _media_stats(exported_messages)
            for key in ("referenced", "local_recovered", "network_downloaded", "legacy_http_downloaded", "private_cdn_downloaded", "raw_preserved", "missing", "failed"):
                aggregate_summary[key] += summary[key]
            for category, values in summary["by_category"].items():
                row = aggregate_summary["by_category"].setdefault(category, {key: 0 for key in values})
                for key, value in values.items():
                    row[key] += value
            for detail in details:
                aggregate_details[(detail["code"], detail["category"], detail["message"])] += detail["count"]

            manifest = {
                "version": 4,
                "storage_mode": "shared",
                "conversation_archive_id": conversation_archive_id,
                "export_id": export_id,
                "account_id": account.account_id,
                "conversation_hash": stable_id(conversation.username, 24),
                "conversation_id": conversation.conversation_id,
                "conversation_name": export_title,
                "conversation_kind": conversation.kind,
                "folder_layout": request.folder_layout,
                "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "message_count": len(exported_messages),
                "media_summary": summary,
                "warning_details": details,
                "warnings": warnings,
                "download_limits_mib": {
                    "visual": request.visual_download_limit_mib,
                    "audio": request.audio_download_limit_mib,
                    "large": request.large_download_limit_mib,
                },
                "files": [],
            }
            for path in folder.rglob("*"):
                if path.is_file() and path.name != "_export_manifest.json":
                    manifest["files"].append({
                        "path": path.relative_to(folder).as_posix(),
                        "size": path.stat().st_size,
                        "sha256": sha256_file(path),
                    })
            (folder / "_export_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            previous = existing_archives.get(conversation_archive_id)
            if previous is None and target.exists():
                target_manifest = _read_conversation_manifest(target)
                if target_manifest and target_manifest.get("conversation_archive_id") == conversation_archive_id:
                    previous = target
            actions.append({
                "archive_id": conversation_archive_id,
                "conversation_id": conversation.conversation_id,
                "staged": folder,
                "target": target,
                "previous": previous,
                "created": previous is None,
            })

        warning_details = [
            {"code": code, "category": category, "count": count, "message": message}
            for (code, category, message), count in sorted(aggregate_details.items())
        ]
        warnings = list(dict.fromkeys(detail["message"] for detail in warning_details))
        progress(0.99, "正在提交归档")
        committed: list[dict[str, Any]] = []
        try:
            backup_root.mkdir()
            for index, action in enumerate(actions):
                previous: Path | None = action["previous"]
                target: Path = action["target"]
                backup = backup_root / f"{index:04d}"
                target.parent.mkdir(parents=True, exist_ok=True)
                if previous and previous.exists():
                    _retry_sharing(lambda previous=previous, backup=backup: os.replace(previous, backup))
                    action["backup"] = backup
                _retry_sharing(lambda action=action, target=target: os.replace(action["staged"], target))
                committed.append(action)
        except Exception:
            for action in reversed(committed):
                target = action["target"]
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
            for action in reversed(actions):
                backup = action.get("backup")
                previous = action.get("previous")
                if backup and previous and Path(backup).exists():
                    Path(previous).parent.mkdir(parents=True, exist_ok=True)
                    _retry_sharing(lambda backup=Path(backup), previous=Path(previous): os.replace(backup, previous))
            raise
        conversation_paths = [str(action["target"].resolve()) for action in actions]
        conversation_archives = [
            {
                "archive_id": str(action["archive_id"]),
                "conversation_id": str(action["conversation_id"]),
                "path": str(action["target"].resolve()),
                "export_id": export_id,
            }
            for action in actions
        ]
        shutil.rmtree(staging_parent, ignore_errors=True)
        if len(conversation_paths) == 1:
            open_path = conversation_paths[0]
        else:
            open_path = os.path.commonpath(conversation_paths)
            if not Path(open_path).is_dir():
                open_path = str(output)
        progress(1.0, "导出完成")
        return ExportResult(
            output,
            len(request.conversation_ids),
            total_messages,
            total_media,
            warnings,
            aggregate_summary,
            warning_details,
            export_id,
            conversation_paths,
            conversation_archives,
            open_path,
            sum(1 for action in actions if action["created"]),
            sum(1 for action in actions if not action["created"]),
        )
    except Exception:
        shutil.rmtree(staging_parent, ignore_errors=True)
        raise
