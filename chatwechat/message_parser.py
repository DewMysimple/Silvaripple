from __future__ import annotations

import base64
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

from .models import Attachment, QuotePreview, SystemEvent, WechatMessage
from .redaction import stable_id
from .text_emoji import render_text_emoji


TYPE_NAMES = {
    1: "text",
    3: "image",
    34: "audio",
    37: "friend_request",
    40: "contact_recommendation",
    42: "contact_card",
    43: "video",
    47: "emoji",
    48: "location",
    49: "app",
    50: "call",
    51: "status",
    53: "video_call",
    10000: "system",
    10002: "revoke",
}

APP_NAMES = {
    5: "link", 6: "file", 8: "emoji", 19: "forwarded_collection", 33: "mini_program",
    36: "mini_program", 57: "quote", 62: "pat", 2000: "transfer", 2001: "red_packet",
}


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        if len(value) <= 256 * 1024:
            return {"encoding": "base64", "data": base64.b64encode(value).decode("ascii")}
        return {"encoding": "omitted", "size": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return str(value)


def decode_content(value: Any, compressed: Any = None) -> str:
    candidate = compressed if compressed not in (None, b"", "") else value
    if candidate is None:
        return ""
    if isinstance(candidate, str):
        return candidate
    if not isinstance(candidate, (bytes, bytearray, memoryview)):
        return str(candidate)
    data = bytes(candidate)
    if data[:4] == b"\x28\xb5\x2f\xfd":
        try:
            import zstandard

            data = zstandard.ZstdDecompressor().decompress(data, max_output_size=64 * 1024 * 1024)
        except Exception:
            return "[Zstandard 内容无法解压]"
    for encoding in ("utf-8", "utf-16le", "gb18030"):
        try:
            return data.decode(encoding).rstrip("\x00")
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _timestamp(value: Any) -> datetime:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0
    while number > 32_503_680_000:
        number /= 1000
    if number <= 0:
        return datetime(1970, 1, 1, tzinfo=timezone.utc).astimezone()
    try:
        return datetime.fromtimestamp(number).astimezone()
    except (OverflowError, OSError, ValueError):
        return datetime(1970, 1, 1, tzinfo=timezone.utc).astimezone()


def _xml_root(text: str) -> ET.Element | None:
    start = text.find("<")
    if start < 0:
        return None
    try:
        return ET.fromstring(text[start:])
    except ET.ParseError:
        return None


def _find_text(root: ET.Element | None, *paths: str) -> str | None:
    if root is None:
        return None
    for path in paths:
        node = root.find(path)
        if node is not None and node.text:
            return node.text.strip()
    return None


def _strip_group_prefix(text: str | None, sender: str | None) -> tuple[str | None, str | None]:
    if not text:
        return sender, text
    match = re.match(r"^(wxid_[^:\r\n]+):\r?\n", text)
    if not match:
        return sender, text
    prefixed_sender = match.group(1)
    if sender and sender != prefixed_sender:
        return sender, text
    return sender or prefixed_sender, text[match.end():]


def _quote_display_text(text: str | None, raw_type: str | None) -> str | None:
    if not text or _xml_root(text) is None:
        return text
    try:
        type_number = int(raw_type or 0) & 0xFFFFFFFF
    except (TypeError, ValueError):
        type_number = 0
    labels = {
        3: "[图片]", 34: "[语音]", 43: "[视频]", 47: "[表情]",
        48: "[位置]", 49: "[引用消息]", 10000: "[系统消息]", 10002: "[撤回消息]",
    }
    return labels.get(type_number, "[引用内容]")


def _packed_tokens(value: Any, depth: int = 0) -> list[str]:
    """Extract validated 32-hex media tokens from WeChat's small protobuf blob."""
    if depth > 3 or not isinstance(value, (bytes, bytearray, memoryview)):
        return []
    data = bytes(value)
    if not data or len(data) > 1024 * 1024:
        return []

    def varint(offset: int) -> tuple[int, int]:
        result = shift = 0
        while offset < len(data) and shift <= 63:
            byte = data[offset]
            offset += 1
            result |= (byte & 0x7F) << shift
            if byte < 0x80:
                return result, offset
            shift += 7
        raise ValueError("invalid protobuf varint")

    tokens: list[str] = []
    offset = 0
    try:
        while offset < len(data):
            tag, offset = varint(offset)
            wire = tag & 7
            if wire == 0:
                _, offset = varint(offset)
            elif wire == 1:
                offset += 8
            elif wire == 5:
                offset += 4
            elif wire == 2:
                size, offset = varint(offset)
                if size < 0 or offset + size > len(data):
                    break
                chunk = data[offset : offset + size]
                offset += size
                try:
                    text = chunk.decode("ascii")
                except UnicodeDecodeError:
                    text = ""
                if re.fullmatch(r"[0-9a-fA-F]{32}", text):
                    tokens.append(text.lower())
                tokens.extend(_packed_tokens(chunk, depth + 1))
            else:
                break
    except (ValueError, IndexError):
        return tokens
    return list(dict.fromkeys(tokens))


def _attachment(category: str, row: dict[str, Any], root: ET.Element | None, content: str) -> Attachment:
    candidates: list[str] = []
    metadata: dict[str, Any] = {}
    for key, value in row.items():
        lower = key.casefold()
        if value and any(token in lower for token in ("path", "file", "md5", "cdn", "thumb", "url")):
            text = str(value)
            metadata[key] = text
            if "path" in lower or "file" in lower or "md5" in lower:
                candidates.append(text)
    if root is not None:
        for element in root.iter():
            tag = str(element.tag).rsplit("}", 1)[-1].casefold()
            element_text = (element.text or "").strip()
            if element_text and any(token in tag for token in ("path", "file", "md5", "cdn", "thumb", "url", "aeskey")):
                metadata.setdefault(f"xml:{tag}", element_text)
                if "path" in tag or "file" in tag or "md5" in tag:
                    candidates.append(element_text)
            for key, value in element.attrib.items():
                if value and any(token in key.casefold() for token in ("path", "md5", "cdn", "url", "aeskey")):
                    metadata[f"xml:{key}"] = value
                    if "path" in key.casefold() or "md5" in key.casefold():
                        candidates.append(value)
    packed = next((value for key, value in row.items() if key.casefold() == "packed_info_data"), None)
    packed_tokens = _packed_tokens(packed)
    if packed_tokens:
        metadata["packed:tokens"] = packed_tokens
        candidates.extend(packed_tokens)
    metadata["candidates"] = list(dict.fromkeys(candidates))
    name = _find_text(root, ".//title", ".//filename")
    return Attachment(
        attachment_id=stable_id(json.dumps(metadata, sort_keys=True, ensure_ascii=False) + content[:80]),
        category=category,  # type: ignore[arg-type]
        original_name=name,
        metadata=metadata,
    )


def normalize_message(row: dict[str, Any], conversation_id: str, sequence: int) -> WechatMessage:
    def first(*keys: str, default: Any = None) -> Any:
        lowered = {key.casefold(): value for key, value in row.items()}
        return next((lowered[key.casefold()] for key in keys if key.casefold() in lowered), default)

    raw_type = first("local_type", "type", "msg_type", default=0)
    try:
        packed_type = int(raw_type)
    except (TypeError, ValueError):
        packed_type = 0
    # WeChat 4.x packs app subtype into the high 32 bits and the base message
    # type into the low 32 bits (for example 0x39_00000031 = quote/app 57/49).
    type_number = packed_type & 0xFFFFFFFF
    packed_app_type = (packed_type >> 32) & 0xFFFFFFFF
    content = decode_content(first("message_content", "content", "msg_content"), first("compress_content", "compressed_content"))
    root = _xml_root(content)
    message_type = TYPE_NAMES.get(type_number, "unknown")
    text: str | None = content or None
    attachments: list[Attachment] = []
    quote_preview: QuotePreview | None = None
    system_event: SystemEvent | None = None
    if type_number == 49:
        app_type_raw = _find_text(root, ".//appmsg/type") or first("app_type", default=packed_app_type)
        try:
            app_type = int(app_type_raw)
        except (TypeError, ValueError):
            app_type = 0
        message_type = APP_NAMES.get(app_type, "app_unknown")
        title = _find_text(root, ".//appmsg/title", ".//title")
        description = _find_text(root, ".//appmsg/des", ".//des")
        text = "\n".join(part for part in (title, description) if part) or content or None
        refer = root.find(".//refermsg") if root is not None else None
        if refer is not None:
            quoted_sender_id = _find_text(refer, "./chatusr", "./fromusr", "./fromusername")
            quoted_sender_name = _find_text(refer, "./displayname")
            if quoted_sender_name and quoted_sender_name.startswith("wxid_"):
                quoted_sender_name = None
            quoted_text = _find_text(refer, "./content")
            quoted_sender_id, quoted_text = _strip_group_prefix(quoted_text, quoted_sender_id)
            quoted_type = _find_text(refer, "./type")
            quoted_text = _quote_display_text(quoted_text, quoted_type)
            quote_preview = QuotePreview(
                sender_id=quoted_sender_id,
                sender_name=quoted_sender_name,
                text=quoted_text,
                message_type=quoted_type,
                message_id=_find_text(refer, "./svrid"),
            )
        if app_type == 6:
            attachments.append(_attachment("file", row, root, content))
        elif app_type == 62:
            pat = root.find(".//patinfo") if root is not None else None
            actor_id = _find_text(pat, "./fromusername")
            target_id = _find_text(pat, "./pattedusername")
            template = _find_text(pat, "./template")
            text = title or "拍了拍"
            system_event = SystemEvent(
                "pat", text, actor_id=actor_id, target_id=target_id, template=template
            )
    elif message_type in {"image", "video", "audio", "emoji"}:
        category = {"image": "image", "video": "video", "audio": "audio", "emoji": "emoji"}[message_type]
        attachments.append(_attachment(category, row, root, content))
        text = None
    elif message_type == "location":
        location = root.find(".//location") if root is not None else None
        if location is not None:
            label = location.attrib.get("label") or location.attrib.get("poiname") or "位置"
            text = label
    if root is not None and root.tag == "sysmsg" and root.attrib.get("type") == "revokemsg":
        message_type = "revoke"
        text = _find_text(root, ".//revokemsg/content") or "撤回了一条消息"
        system_event = SystemEvent("revoke", text)
    elif message_type in {"system", "revoke"}:
        if root is not None:
            readable = _find_text(root, ".//content", ".//tips", ".//plain")
            text = readable or "系统消息"
        system_event = SystemEvent(message_type, text or "系统消息")
    sender = first("__sender_username", "sender_username", "sender", "from_username")
    sender = str(sender) if sender else None
    if message_type == "text":
        sender, text = _strip_group_prefix(text, sender)
    if root is not None and message_type in {"unknown", "app_unknown"}:
        text = "未识别的 XML 消息"
    outgoing = bool(first("is_sender", "is_send", "is_outgoing", default=0))
    local_id = first("local_id", "id", "rowid", default=sequence)
    server_id = first("server_id", "svr_id", "msg_svr_id", default="")
    message_id = stable_id(f"{conversation_id}:{local_id}:{server_id}:{sequence}", 20)
    raw_xml = content if root is not None else None
    return WechatMessage(
        message_id=message_id,
        conversation_id=conversation_id,
        sequence=sequence,
        sent_at=_timestamp(first("create_time", "createtime", "msg_time", "time", default=0)),
        sender_id=sender,
        sender_name=None,
        outgoing=outgoing,
        message_type=message_type,
        text=text,
        display_text=render_text_emoji(text),
        attachments=attachments,
        quoted_message_id=_find_text(root, ".//refermsg/svrid") if root is not None else None,
        quote_preview=quote_preview,
        system_event=system_event,
        raw_type=raw_type,
        raw_fields=json_safe(row),
        raw_xml=raw_xml,
    )
