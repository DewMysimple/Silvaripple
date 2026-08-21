from __future__ import annotations

import hashlib
import base64
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import zlib
import urllib.error
import urllib.parse
import urllib.request
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.padding import PKCS7
from cryptography.exceptions import InvalidTag
from PIL import Image, UnidentifiedImageError

from .keystore import KeyStore
from .models import Attachment


MIB = 1024 * 1024
MAX_NETWORK_FILE = 50 * MIB
MAX_NETWORK_LARGE_FILE = 500 * MIB
ALLOWED_MEDIA_HOSTS = {
    "vweixinf.tc.qq.com",
    "wxapp.tc.qq.com",
    "mmbiz.qpic.cn",
    "novac2c.cdn.weixin.qq.com",
}
VISUAL_KINDS = {"image", "emoji"}
SUBPROCESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def image_extension(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data.startswith(b"BM"):
        return ".bmp"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in {
        b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1",
    }:
        return ".heic"
    return None


def validate_image(data: bytes, extension: str) -> bool:
    """Fully parse untrusted downloaded images before they enter an archive."""
    if extension == ".heic":
        return len(data) >= 32 and image_extension(data) == ".heic"
    try:
        with Image.open(BytesIO(data)) as picture:
            picture.verify()
        return True
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return False


def _looks_wxgf(data: bytes) -> bool:
    return data[:4].lower() == b"wxgf" or b"WXGF" in data[:32]


def decrypt_dat(data: bytes, xor_key: int | None = None, aes_key: bytes | None = None) -> tuple[bytes, str] | None:
    """Decode legacy WeChat single-byte XOR images by validating real headers."""
    # V2 cache: a small header records the clear-text size followed by AES-ECB
    # data and an optional XOR tail. Keep this branch compatible with captured
    # WeChat 4.x samples.
    if data.startswith(b"\x07\x08V2\x08\x07") and len(data) >= 15 and aes_key:
        try:
            import struct

            aes_plain_size, xor_size = struct.unpack("<II", data[6:14])
            payload = data[15:]
            if xor_size > len(payload):
                return None
            # WeChat encrypts the first (at most 1 KiB) clear bytes plus a full
            # PKCS#7 block. Bytes between that prefix and the XOR tail are plain.
            aes_cipher_size = min((aes_plain_size // 16) * 16 + 16, len(payload))
            aes_cipher_size -= aes_cipher_size % 16
            decryptor = Cipher(algorithms.AES(aes_key[:16]), modes.ECB()).decryptor()
            decrypted = decryptor.update(payload[:aes_cipher_size]) + decryptor.finalize()
            plain = decrypted[:aes_plain_size]
            middle_end = len(payload) - xor_size
            middle = payload[aes_cipher_size:middle_end] if aes_cipher_size < middle_end else b""
            tail = payload[middle_end:]
            if xor_key is not None:
                tail = bytes(value ^ xor_key for value in tail)
            decoded = plain + middle + tail
            extension = image_extension(decoded)
            if extension:
                return decoded, extension.lstrip(".")
            if _looks_wxgf(decoded):
                return decoded, "wxgf"
        except (ValueError, TypeError, struct.error):
            pass

    headers = (
        (b"\xff\xd8\xff", ".jpg"),
        (b"\x89PNG", ".png"),
        (b"GIF8", ".gif"),
        (b"RIFF", ".webp"),
    )
    for header, extension in headers:
        if not data:
            return None
        key = data[0] ^ header[0]
        sample = bytes(value ^ key for value in data[: len(header)])
        if sample == header:
            decoded = bytes(value ^ key for value in data)
            if image_extension(decoded):
                return decoded, extension.lstrip(".")
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_filename(value: str, fallback: str = "media") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value or "")
    cleaned = cleaned.strip(" .")
    return (cleaned or fallback)[:120]


def _retry_windows_file(operation, attempts: int = 8):
    delay = 0.04
    for index in range(attempts):
        try:
            return operation()
        except PermissionError:
            if index + 1 == attempts:
                raise
            time.sleep(delay)
            delay = min(delay * 1.8, 0.45)


class MediaResolver:
    SEARCH_ROOTS = (
        "msg",
        "cache",
        "resource",
        "business/emoticon",
        "temp/RWTemp",
    )

    def __init__(self, account_dir: Path):
        self.account_dir = Path(account_dir)
        self._index: dict[str, list[Path]] | None = None
        self._lock = threading.Lock()

    @staticmethod
    def _is_url(value: str) -> bool:
        return value.lower().startswith(("http://", "https://"))

    def _build_index(self) -> dict[str, list[Path]]:
        index: dict[str, list[Path]] = {}
        for relative in self.SEARCH_ROOTS:
            root = self.account_dir / Path(relative)
            if not root.exists():
                continue
            try:
                paths = root.rglob("*")
                for path in paths:
                    try:
                        if not path.is_file():
                            continue
                    except OSError:
                        continue
                    for key in {path.name.lower(), path.stem.lower()}:
                        if key:
                            index.setdefault(key, []).append(path)
            except (OSError, PermissionError):
                continue
        return index

    def _get_index(self) -> dict[str, list[Path]]:
        with self._lock:
            if self._index is None:
                self._index = self._build_index()
            return self._index

    def candidates(self, attachment: Attachment) -> list[Path]:
        attachment_candidates = list(attachment.metadata.get("candidates", []))
        found: list[Path] = []

        def add(candidate: Path) -> None:
            try:
                resolved = candidate.resolve()
                if resolved.is_file() and resolved not in found:
                    found.append(resolved)
            except OSError:
                return

        md5 = MediaExporter._attachment_md5(attachment)
        index = self._get_index()
        if md5:
            for key in (md5.lower(),):
                for candidate in index.get(key, []):
                    add(candidate)

        # File messages often retain only the original filename after the
        # resource row has been compacted. Use it only when it identifies one
        # local file unambiguously; guessing between duplicate filenames could
        # silently archive the wrong attachment.
        original_name = Path(str(attachment.original_name or "")).name.casefold()
        if original_name:
            named = []
            for candidate in index.get(original_name, []):
                try:
                    resolved = candidate.resolve()
                    if resolved.is_file() and resolved not in named:
                        named.append(resolved)
                except OSError:
                    continue
            if len(named) == 1:
                add(named[0])

        direct_values = [attachment.source_path, *attachment_candidates]
        for value in direct_values:
            if not value or self._is_url(str(value)):
                continue
            candidate = Path(str(value))
            if not candidate.is_absolute():
                candidate = self.account_dir / candidate
            add(candidate)

        keys: list[str] = []
        for value in [md5, *attachment_candidates]:
            if not value or self._is_url(str(value)):
                continue
            name = Path(str(value)).name.lower()
            keys.extend((name, Path(name).stem))
        for key in keys:
            for candidate in index.get(key, []):
                add(candidate)
        return found

    def resolve(self, attachment: Attachment) -> Path | None:
        rows = self.candidates(attachment)
        return rows[0] if rows else None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class RestrictedMediaClient:
    def __init__(self, allow_legacy_http: bool = False):
        self._opener = urllib.request.build_opener(_NoRedirect())
        self.allow_legacy_http = bool(allow_legacy_http)

    @staticmethod
    def normalize_url(value: str, allow_legacy_http: bool = False) -> str | None:
        value = (value or "").strip()
        original_http = value.lower().startswith("http://")
        original_host = ""
        if original_http:
            try:
                original_host = (urllib.parse.urlsplit(value).hostname or "").lower().rstrip(".")
            except ValueError:
                return None
            # The one-time compatibility permission applies only to the one
            # legacy host. Other allowlisted HTTP URLs are always upgraded to
            # HTTPS, even while compatibility mode is enabled.
            if not (allow_legacy_http and original_host == "vweixinf.tc.qq.com"):
                value = "https://" + value[7:]
        try:
            parsed = urllib.parse.urlsplit(value)
        except ValueError:
            return None
        host = (parsed.hostname or "").lower().rstrip(".")
        try:
            port = parsed.port
        except ValueError:
            return None
        scheme = parsed.scheme.lower()
        legacy_allowed = allow_legacy_http and scheme == "http" and host == "vweixinf.tc.qq.com"
        if (scheme != "https" and not legacy_allowed) or host not in ALLOWED_MEDIA_HOSTS:
            return None
        allowed_ports = (None, 80) if legacy_allowed else (None, 443)
        if parsed.username or parsed.password or port not in allowed_ports:
            return None
        return urllib.parse.urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, ""))

    def _once(self, url: str, max_bytes: int = MAX_NETWORK_FILE) -> tuple[bytes | None, str | None, str | None]:
        current = url
        for _ in range(4):
            request = urllib.request.Request(
                current,
                headers={"User-Agent": "ChatWechat/2.0", "Accept": "*/*"},
                method="GET",
            )
            try:
                response = self._opener.open(request, timeout=10)
            except urllib.error.HTTPError as exc:
                if exc.code in {301, 302, 303, 307, 308}:
                    target = self.normalize_url(exc.headers.get("Location", ""), self.allow_legacy_http)
                    if not target:
                        return None, None, "redirect_not_allowed"
                    current = target
                    continue
                if exc.code in {401, 403}:
                    return None, None, "remote_access_denied"
                if exc.code == 404:
                    return None, None, "remote_not_found"
                if exc.code == 410:
                    return None, None, "remote_expired"
                return None, None, "remote_server_error" if exc.code >= 500 else "remote_http_error"
            except urllib.error.URLError as exc:
                if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                    return None, None, "network_timeout"
                return None, None, "network_unreachable"
            except (TimeoutError, socket.timeout):
                return None, None, "network_timeout"
            except OSError:
                return None, None, "network_unreachable"
            try:
                response.fp.raw._sock.settimeout(30)
            except (AttributeError, OSError):
                pass
            length = response.headers.get("Content-Length")
            if length and length.isdigit() and int(length) > max_bytes:
                response.close()
                return None, None, "file_too_large"
            chunks: list[bytes] = []
            size = 0
            try:
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        return None, None, "file_too_large"
                    chunks.append(chunk)
            except (TimeoutError, socket.timeout):
                return None, None, "network_timeout"
            except OSError:
                return None, None, "network_unreachable"
            finally:
                response.close()
            return b"".join(chunks), current, None
        return None, None, "too_many_redirects"

    def fetch(self, value: str, max_bytes: int = MAX_NETWORK_FILE) -> tuple[bytes | None, str | None, str | None]:
        url = self.normalize_url(value, self.allow_legacy_http)
        if not url:
            return None, None, "url_not_allowed"
        last_error = "network_unreachable"
        for attempt in range(3):
            data, final_url, error = self._once(url, max_bytes)
            if data is not None:
                return data, final_url, None
            last_error = error or last_error
            if last_error in {
                "url_not_allowed", "redirect_not_allowed", "file_too_large", "remote_expired",
                "remote_access_denied", "remote_not_found", "remote_http_error",
            }:
                break
            if attempt < 2:
                time.sleep(0.15 * (attempt + 1))
        return None, None, last_error

    @staticmethod
    def private_cdn_url(token: str) -> str | None:
        """Build the one supported credential-free Tencent CDN URL."""
        value = str(token or "").strip()
        if not value or len(value) > 8192 or value.lower().startswith(("http://", "https://")):
            return None
        try:
            if len(value) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", value):
                query_value = base64.b64encode(bytes.fromhex(value)).decode("ascii")
            else:
                base64.b64decode(value, validate=True)
                query_value = value
        except (ValueError, TypeError):
            return None
        query = urllib.parse.urlencode({"encrypted_query_param": query_value})
        return f"https://novac2c.cdn.weixin.qq.com/c2c/download?{query}"

    def fetch_private_token(self, token: str, max_bytes: int) -> tuple[bytes | None, str | None]:
        url = self.private_cdn_url(token)
        if not url:
            return None, "private_cdn_token_invalid"
        data, _, error = self.fetch(url, max_bytes)
        if data is not None:
            return data, None
        if error in {"remote_expired", "remote_not_found"}:
            return None, "private_cdn_token_expired"
        if error == "remote_access_denied":
            return None, "private_cdn_access_denied"
        if error in {"network_timeout", "network_unreachable", "remote_server_error", "remote_http_error"}:
            return None, error
        if error == "file_too_large":
            return None, "remote_too_large"
        return None, "private_cdn_token_invalid"


class MediaExporter:
    def __init__(
        self,
        account_id: str,
        account_dir: Path,
        store: KeyStore | None = None,
        download_missing_media: bool = False,
        allow_legacy_http_media: bool = False,
        visual_download_limit_mib: int = 50,
        audio_download_limit_mib: int = 100,
        large_download_limit_mib: int = 500,
    ):
        self.account_id = account_id
        self.account_dir = Path(account_dir)
        self.store = store
        self.resolver = MediaResolver(self.account_dir)
        self.download_missing_media = bool(download_missing_media)
        self.allow_legacy_http_media = bool(allow_legacy_http_media)
        self.visual_limit_bytes = min(2048, max(1, int(visual_download_limit_mib))) * MIB
        self.audio_limit_bytes = min(2048, max(1, int(audio_download_limit_mib))) * MIB
        self.large_limit_bytes = min(2048, max(1, int(large_download_limit_mib))) * MIB
        self.client = RestrictedMediaClient(self.allow_legacy_http_media) if self.download_missing_media else None
        self._hash_paths: dict[str, Path] = {}
        self._hash_lock = threading.Lock()

    @staticmethod
    def _reason_text(kind: str, reason_code: str) -> str:
        texts = {
            "download_on_export": "预览只读取本地缓存；导出时将联网补全",
            "local_available": "本地附件可在导出时归档",
            "local_cache_key_missing": "本地缓存存在，但数据库缺少解密密钥和下载地址",
            "remote_url_missing": "本机未缓存，数据库也没有可下载地址",
            "private_cdn_unavailable": "微信私有图片标识无法直接下载；请先在微信中打开原图，再重新导出",
            "private_cdn_downloaded": "已通过腾讯 CDN token 恢复",
            "private_cdn_token_expired": "腾讯 CDN token 已失效",
            "private_cdn_token_invalid": "腾讯 CDN token 格式无法识别",
            "private_cdn_key_missing": "腾讯 CDN token 存在，但缺少解密密钥",
            "private_cdn_decrypt_failed": "腾讯 CDN 内容已下载，但无法用消息密钥解密或验证",
            "private_cdn_access_denied": "腾讯 CDN 拒绝访问，token 可能已失效",
            "network_disabled": "本地文件缺失；可在导出时勾选联网补全可安全下载的表情",
            "url_not_allowed": "媒体地址不在安全下载白名单内",
            "redirect_not_allowed": "下载地址跳转到非白名单域名，已阻止",
            "file_too_large": "媒体文件超过当前自动下载上限",
            "remote_too_large": "远端文件超过当前自动下载上限",
            "download_failed": "腾讯媒体下载失败或返回内容无法验证",
            "network_timeout": "连接腾讯媒体服务器超时",
            "network_unreachable": "当前网络无法连接腾讯媒体服务器",
            "remote_access_denied": "腾讯媒体服务器拒绝访问，地址可能已失效",
            "remote_not_found": "腾讯媒体已不存在或地址已失效",
            "remote_expired": "腾讯媒体地址已过期",
            "remote_server_error": "腾讯媒体服务器暂时不可用",
            "remote_http_error": "腾讯媒体服务器返回了无法处理的响应",
            "remote_content_invalid": "下载结果不是有效媒体文件",
            "video_container_invalid": "下载内容不是可验证的视频容器",
            "visual_decode_failed": "下载内容无法验证为图片或表情",
            "md5_mismatch": "媒体校验失败（MD5 不匹配）",
            "network_error": "联网补全失败，请稍后重试",
            "http_error": "媒体服务器返回错误",
            "legacy_http_not_authorized": "旧版腾讯表情地址仅支持 HTTP；当前已关闭兼容下载",
            "legacy_url_expired": "旧版腾讯表情地址已失效",
            "key_mismatch": "媒体密钥无法验证下载内容",
            "decode_failed": "本地媒体存在，但无法识别或解密",
            "wxgf_conversion_failed": "本地图片已解密，但 WXGF 转换失败",
            "source_locked": "本地媒体被其他程序占用，已跳过；聊天正文仍已导出",
            "local_media_missing": "本地文件缺失；工具不会联网下载",
        }
        if reason_code in {"local_media_missing", "private_cdn_unavailable"} and kind == "image":
            return "本机未缓存图片；请先在微信中打开后重新导出"
        if reason_code == "remote_url_missing" and kind == "image":
            return "本机未缓存图片；数据库也没有可下载地址"
        if reason_code == "private_cdn_unavailable" and kind in {"file", "video"}:
            return "只有腾讯 CDN token；导出时可尝试受限恢复"
        if reason_code == "local_media_missing" and kind == "emoji":
            return "表情包没有本地缓存，也没有可用的腾讯下载地址"
        if reason_code == "local_media_missing" and kind in {"file", "video", "audio"}:
            return "附件本机未缓存，聊天数据库只保留了消息记录，无法还原文件内容"
        if reason_code == "remote_url_missing" and kind in {"file", "video"}:
            return "本机未缓存，聊天数据库也没有标准腾讯下载地址"
        if reason_code == "remote_url_missing" and kind == "emoji":
            return "表情缓存不可用，数据库也没有可下载地址"
        if reason_code == "decode_failed" and kind == "emoji":
            return "本地表情包缓存存在但无法解密；可在导出时勾选联网补全"
        return texts.get(reason_code, "媒体不可用")

    @staticmethod
    def _attachment_aes_keys(attachment: Attachment) -> list[bytes]:
        keys: list[bytes] = []
        for field in (
            "xml:aeskey", "db:aes_key", "xml:cdnrawvideoaeskey",
            "xml:cdnthumbaeskey", "xml:filekey", "xml:encryptkey",
        ):
            value = str(attachment.metadata.get(field) or "").strip()
            if not value:
                continue
            encoded = value.encode("ascii", errors="ignore")
            if len(encoded) in {16, 24, 32}:
                keys.append(encoded)
            if re.fullmatch(r"[0-9a-fA-F]{32,64}", value):
                try:
                    decoded = bytes.fromhex(value)
                    if len(decoded) in {16, 24, 32}:
                        keys.append(decoded)
                except ValueError:
                    pass
            try:
                decoded = base64.b64decode(value, validate=True)
                if len(decoded) == 32 and re.fullmatch(rb"[0-9a-fA-F]{32}", decoded):
                    decoded = bytes.fromhex(decoded.decode("ascii"))
                if len(decoded) in {16, 24, 32}:
                    keys.append(decoded)
            except (ValueError, TypeError, UnicodeEncodeError):
                pass
        return list(dict.fromkeys(keys))

    @staticmethod
    def _attachment_aes_key(attachment: Attachment) -> bytes | None:
        keys = MediaExporter._attachment_aes_keys(attachment)
        return keys[0] if keys else None

    @staticmethod
    def _decrypt_aes_ecb(data: bytes, key: bytes | None) -> list[bytes]:
        if not key or not data or len(data) % 16:
            return []
        try:
            plain = Cipher(algorithms.AES(key), modes.ECB()).decryptor().update(data)
            candidates = [plain]
            unpadder = PKCS7(128).unpadder()
            unpadded = unpadder.update(plain) + unpadder.finalize()
            if unpadded != plain:
                candidates.insert(0, unpadded)
            return candidates
        except (ValueError, TypeError):
            return [plain] if "plain" in locals() else []

    def _decode_visual(self, data: bytes, attachment: Attachment) -> tuple[bytes, str] | None:
        extension = image_extension(data)
        if extension:
            return data, extension

        decoded = decrypt_dat(data)
        if decoded:
            return decoded[0], "." + decoded[1].lstrip(".")

        for key in self._attachment_aes_keys(attachment):
            for aes_plain in self._decrypt_aes_ecb(data, key):
                extension = image_extension(aes_plain)
                if extension:
                    return aes_plain, extension

        gcm_plain = self._decrypt_emoji_gcm(data, attachment)
        if gcm_plain:
            extension = image_extension(gcm_plain)
            if extension:
                return gcm_plain, extension
            if _looks_wxgf(gcm_plain):
                return gcm_plain, ".wxgf"

        if self.store:
            try:
                image_key = self.store.get_image_key(self.account_id, "aes")
            except Exception:
                image_key = None
            if image_key:
                try:
                    xor_value = self.store.get_image_key(self.account_id, "xor")
                except Exception:
                    xor_value = None
                decoded = decrypt_dat(
                    data,
                    xor_key=xor_value[0] if xor_value else None,
                    aes_key=image_key,
                )
                if decoded:
                    return decoded[0], "." + decoded[1].lstrip(".")
                for candidate in self._decode_v2_candidates(data, image_key):
                    extension = image_extension(candidate)
                    if extension:
                        return candidate, extension
        return None

    @staticmethod
    def _decrypt_emoji_gcm(data: bytes, attachment: Attachment) -> bytes | None:
        if attachment.category != "emoji" or len(data) <= 28:
            return None
        for raw_value in (
            attachment.metadata.get("xml:aeskey"), attachment.metadata.get("db:aes_key"),
        ):
            raw_key = str(raw_value or "").strip()
            if len(raw_key.encode("ascii", errors="ignore")) != 32:
                continue
            try:
                nonce = data[-28:-16]
                ciphertext_and_tag = data[:-28] + data[-16:]
                plain = AESGCM(raw_key.encode("ascii")).decrypt(nonce, ciphertext_and_tag, None)
            except (ValueError, TypeError, UnicodeEncodeError, InvalidTag):
                continue
            if image_extension(plain) or _looks_wxgf(plain):
                return plain
            try:
                inflated = zlib.decompress(plain)
            except zlib.error:
                continue
            if image_extension(inflated) or _looks_wxgf(inflated):
                return inflated
        return None

    @staticmethod
    def _decode_v2_candidates(data: bytes, image_key: bytes) -> Iterable[bytes]:
        if len(image_key) in {16, 24, 32} and len(data) >= 16:
            aligned = len(data) - len(data) % 16
            if aligned:
                try:
                    decryptor = Cipher(algorithms.AES(image_key), modes.ECB()).decryptor()
                    plain = decryptor.update(data[:aligned]) + decryptor.finalize() + data[aligned:]
                    yield plain
                except ValueError:
                    pass
        if image_key:
            yield bytes(value ^ image_key[index % len(image_key)] for index, value in enumerate(data))

    @staticmethod
    def _ffmpeg_path() -> str | None:
        return shutil.which("ffmpeg")

    @staticmethod
    def _wxgf_partitions(data: bytes) -> list[tuple[int, int]]:
        if len(data) < 15 or not _looks_wxgf(data):
            return []
        header_length = int(data[4])
        if header_length >= len(data):
            return []
        for pattern in (b"\x00\x00\x00\x01", b"\x00\x00\x01"):
            result: list[tuple[int, int]] = []
            position = header_length
            while position < len(data):
                index = data.find(pattern, position)
                if index < 0:
                    break
                size = int.from_bytes(data[index - 4:index], "big") if index >= 4 else 0
                if 0 < size <= len(data) - index:
                    result.append((index, size))
                    position = index + size
                else:
                    position = index + 1
            if result:
                return result
        return []

    def _convert_wxgf(self, data: bytes) -> tuple[bytes, str] | None:
        executable = self._ffmpeg_path()
        if not executable:
            return None
        partitions = self._wxgf_partitions(data)
        if not partitions:
            return None
        maximum = max(size for _, size in partitions)
        animated = len(partitions) > 1 and maximum / len(data) < 0.6
        if not animated:
            offset, size = max(partitions, key=lambda item: item[1])
            try:
                completed = subprocess.run(
                    [
                        executable, "-v", "error", "-i", "pipe:0", "-vframes", "1",
                        "-c:v", "mjpeg", "-q:v", "4", "-f", "image2", "pipe:1",
                    ],
                    input=data[offset : offset + size],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    creationflags=SUBPROCESS_FLAGS,
                    timeout=45,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                return None
            if completed.returncode == 0 and image_extension(completed.stdout):
                return completed.stdout, image_extension(completed.stdout) or ".jpg"

        anime_frames = [data[offset : offset + size] for index, (offset, size) in enumerate(partitions) if index % 2]
        mask_frames = [data[offset : offset + size] for index, (offset, size) in enumerate(partitions) if index % 2 == 0]
        if not anime_frames or len(anime_frames) != len(mask_frames):
            return None
        with tempfile.TemporaryDirectory(prefix="chatwechat-wxgf-") as folder:
            anime_path = Path(folder) / "anime.hevc"
            mask_path = Path(folder) / "mask.hevc"
            anime_path.write_bytes(b"".join(anime_frames))
            mask_path.write_bytes(b"".join(mask_frames))
            try:
                completed = subprocess.run(
                    [
                        executable, "-v", "error", "-i", str(anime_path), "-i", str(mask_path),
                        "-filter_complex", "[0:v][1:v]alphamerge,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
                        "-f", "gif", "pipe:1",
                    ],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    creationflags=SUBPROCESS_FLAGS, timeout=90, check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                return None
            if completed.returncode == 0 and image_extension(completed.stdout) == ".gif":
                return completed.stdout, ".gif"
        return None

    def _decode_voice(self, source: Path, target_folder: Path, stem: str) -> Path | None:
        node = shutil.which("node")
        script = Path(__file__).parent / "vendor" / "silk-wasm" / "decode_voice.mjs"
        if not node or not script.is_file():
            return None
        target = self._unique_target(target_folder, stem, ".wav")
        try:
            completed = subprocess.run(
                [node, str(script), str(source), str(target), "24000"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=SUBPROCESS_FLAGS,
                timeout=90,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            target.unlink(missing_ok=True)
            return None
        if completed.returncode == 0 and target.is_file():
            try:
                header = target.read_bytes()[:12]
                if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
                    return target
            except OSError:
                pass
        target.unlink(missing_ok=True)
        return None

    @staticmethod
    def _url_fields(attachment: Attachment) -> list[tuple[str, str]]:
        raw = attachment.metadata
        if attachment.category == "emoji":
            ordered = (
                ("xml:cdnurl", "original"),
                ("xml:externurl", "original"),
                ("xml:encrypturl", "original"),
                ("xml:thumburl", "thumbnail"),
            )
        elif attachment.category == "image":
            ordered = (
                ("xml:cdnbigimgurl", "original"),
                ("xml:cdnmidimgurl", "medium"),
                ("xml:cdnthumburl", "thumbnail"),
            )
        elif attachment.category == "video":
            ordered = (
                ("xml:cdnrawvideourl", "original"),
                ("xml:cdnvideourl", "medium"),
                ("xml:videourl", "medium"),
            )
        elif attachment.category == "file":
            ordered = (
                ("xml:cdnattachurl", "original"),
                ("xml:attachurl", "original"),
                ("xml:fileurl", "original"),
                ("xml:cdnurl", "original"),
            )
        else:
            ordered = ()
        return [(str(raw.get(key) or ""), quality) for key, quality in ordered if raw.get(key)]

    @staticmethod
    def _private_token_fields(attachment: Attachment) -> list[tuple[str, str]]:
        return [
            (value, quality) for value, quality in MediaExporter._url_fields(attachment)
            if value and not value.lower().startswith(("http://", "https://"))
        ]

    def _download_private_visual(self, attachment: Attachment) -> tuple[bytes, str, str, str] | tuple[None, None, str, str]:
        tokens = self._private_token_fields(attachment)
        if not tokens:
            return None, None, "private_cdn_unavailable", "none"
        keys = self._attachment_aes_keys(attachment)
        if not keys:
            return None, None, "private_cdn_key_missing", "none"
        if not self.client:
            return None, None, "network_disabled", "none"
        expected = self._expected_md5s(attachment)
        last_error = "private_cdn_token_invalid"
        for token, quality in tokens:
            encrypted, error = self.client.fetch_private_token(token, self.visual_limit_bytes + 16)
            if encrypted is None:
                last_error = error or last_error
                continue
            for key in keys:
                candidates = [encrypted, *self._decrypt_aes_ecb(encrypted, key)]
                for candidate in candidates:
                    decoded = self._decode_visual(candidate, attachment)
                    if not decoded:
                        continue
                    visual, extension = decoded
                    if extension == ".wxgf":
                        converted = self._convert_wxgf(visual)
                        if not converted:
                            continue
                        visual, extension = converted
                    if len(visual) > self.visual_limit_bytes or not validate_image(visual, extension):
                        continue
                    digests = {hashlib.md5(visual).hexdigest().lower(), hashlib.md5(encrypted).hexdigest().lower()}
                    if expected and not expected.intersection(digests):
                        continue
                    return visual, extension, quality, "private_cdn"
            last_error = "private_cdn_decrypt_failed"
        return None, None, last_error, "none"

    def _download_private_binary(self, attachment: Attachment) -> tuple[bytes, str, str, str] | tuple[None, None, str, str]:
        tokens = self._private_token_fields(attachment)
        if not tokens:
            return None, None, "private_cdn_unavailable", "none"
        keys = self._attachment_aes_keys(attachment)
        if not keys:
            return None, None, "private_cdn_key_missing", "none"
        if not self.client:
            return None, None, "network_disabled", "none"
        expected = self._expected_md5s(attachment)
        if not expected:
            return None, None, "private_cdn_decrypt_failed", "none"
        last_error = "private_cdn_token_invalid"
        for token, quality in tokens:
            encrypted, error = self.client.fetch_private_token(token, self.large_limit_bytes + 16)
            if encrypted is None:
                last_error = error or last_error
                continue
            encrypted_digest = hashlib.md5(encrypted).hexdigest().lower()
            for key in keys:
                for plain in [encrypted, *self._decrypt_aes_ecb(encrypted, key)]:
                    if not plain or len(plain) > self.large_limit_bytes:
                        continue
                    digest = hashlib.md5(plain).hexdigest().lower()
                    if not expected.intersection({digest, encrypted_digest}):
                        continue
                    extension = self._binary_extension(plain, attachment, "")
                    if not extension:
                        continue
                    return plain, extension, quality, "private_cdn"
            last_error = "private_cdn_decrypt_failed"
        return None, None, last_error, "none"

    @staticmethod
    def _attachment_md5(attachment: Attachment) -> str | None:
        for key, value in attachment.metadata.items():
            if "md5" in str(key).lower() and value and re.fullmatch(r"[0-9a-fA-F]{32}", str(value)):
                return str(value).lower()
        return None

    @staticmethod
    def _expected_md5s(attachment: Attachment) -> set[str]:
        values = {MediaExporter._attachment_md5(attachment) or ""}
        for key, value in attachment.metadata.items():
            if "md5" in str(key).lower() and value:
                values.add(str(value))
        return {value.lower() for value in values if re.fullmatch(r"[0-9a-fA-F]{32}", value)}

    def _download_visual(self, attachment: Attachment) -> tuple[bytes, str, str, str] | tuple[None, None, str, str]:
        urls = self._url_fields(attachment)
        if not urls:
            return None, None, "remote_url_missing", "none"
        has_private_identifier = any(value and not value.lower().startswith(("http://", "https://")) for value, _ in urls)
        if not self.client:
            return None, None, "private_cdn_unavailable" if has_private_identifier and attachment.category == "image" else "network_disabled", "none"

        last_error = "url_not_allowed"
        expected = self._expected_md5s(attachment)
        for value, quality in urls:
            is_legacy = value.lower().startswith("http://") and urllib.parse.urlsplit(value).hostname == "vweixinf.tc.qq.com"
            if is_legacy and not self.allow_legacy_http_media:
                last_error = "legacy_http_not_authorized"
                continue
            data, final_url, error = self.client.fetch(value, self.visual_limit_bytes)
            if data is None:
                last_error = error or last_error
                continue
            decoded = self._decode_visual(data, attachment)
            if not decoded:
                last_error = "visual_decode_failed"
                continue
            visual, extension = decoded
            if not validate_image(visual, extension):
                last_error = "visual_decode_failed"
                continue
            if expected and hashlib.md5(visual).hexdigest().lower() not in expected and hashlib.md5(data).hexdigest().lower() not in expected:
                last_error = "md5_mismatch"
                continue
            source_kind = "legacy_http" if str(final_url or "").lower().startswith("http://") else "network"
            return visual, extension, quality, source_kind
        if has_private_identifier:
            private_data, extension, quality, source_kind = self._download_private_visual(attachment)
            if private_data is not None and extension is not None:
                return private_data, extension, quality, source_kind
            last_error = quality
        if last_error in {"remote_not_found", "remote_expired"} and any(value.lower().startswith("http://") for value, _ in urls):
            last_error = "legacy_url_expired"
        return None, None, last_error, "none"

    @staticmethod
    def _binary_extension(data: bytes, attachment: Attachment, final_url: str) -> str | None:
        if attachment.category == "video":
            if len(data) >= 12 and data[4:8] == b"ftyp":
                return ".mp4"
            if data.startswith(b"\x1aE\xdf\xa3"):
                return ".webm"
            if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"AVI ":
                return ".avi"
            return None
        name = attachment.original_name or Path(urllib.parse.urlsplit(final_url).path).name
        extension = Path(name).suffix.lower()
        if extension and re.fullmatch(r"\.[a-z0-9]{1,10}", extension):
            return extension
        return ".bin"

    def _download_binary(self, attachment: Attachment) -> tuple[bytes, str, str, str] | tuple[None, None, str, str]:
        urls = self._url_fields(attachment)
        if not urls:
            return None, None, "remote_url_missing", "none"
        has_private_identifier = any(
            value and not value.lower().startswith(("http://", "https://")) for value, _ in urls
        )
        if not self.client:
            return None, None, "private_cdn_unavailable" if has_private_identifier else "network_disabled", "none"
        expected = self._expected_md5s(attachment)
        last_error = "private_cdn_unavailable" if has_private_identifier else "download_failed"
        for raw_url, quality in urls:
            # Files and videos never use the legacy HTTP exception. Standard
            # Tencent HTTP links are upgraded before the restricted client sees them.
            url = RestrictedMediaClient.normalize_url(raw_url, allow_legacy_http=False)
            if not url:
                continue
            data, final_url, error = self.client.fetch(url, self.large_limit_bytes)
            if data is None:
                last_error = "remote_too_large" if error == "file_too_large" else (error or "download_failed")
                continue
            if not data or data[:256].lstrip().lower().startswith((b"<!doctype html", b"<html")):
                last_error = "remote_content_invalid"
                continue
            digest = hashlib.md5(data).hexdigest().lower()
            if expected and digest not in expected:
                last_error = "md5_mismatch"
                continue
            extension = self._binary_extension(data, attachment, final_url or url)
            if not extension:
                last_error = "video_container_invalid" if attachment.category == "video" else "remote_content_invalid"
                continue
            return data, extension, quality, "network"
        if has_private_identifier:
            return self._download_private_binary(attachment)
        return None, None, last_error, "none"

    def _unique_target(self, folder: Path, stem: str, extension: str) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{safe_filename(stem)}{extension}"
        counter = 2
        while target.exists():
            target = folder / f"{safe_filename(stem)}_{counter}{extension}"
            counter += 1
        return target

    def _write_bytes(self, data: bytes, folder: Path, stem: str, extension: str) -> Path:
        digest = hashlib.sha256(data).hexdigest()
        with self._hash_lock:
            existing = self._hash_paths.get(digest)
            target = self._unique_target(folder, stem, extension)
            if existing and existing.exists():
                try:
                    os.link(existing, target)
                except OSError:
                    shutil.copy2(existing, target)
                return target
            def write_atomic() -> None:
                descriptor, temp_name = tempfile.mkstemp(prefix=f".{target.name}-", suffix=".tmp", dir=folder)
                try:
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temp_name, target)
                finally:
                    Path(temp_name).unlink(missing_ok=True)
            _retry_windows_file(write_atomic)
            self._hash_paths[digest] = target
            return target

    def _archive_file(self, source: Path, folder: Path, stem: str) -> Path:
        extension = source.suffix or mimetypes.guess_extension(mimetypes.guess_type(source.name)[0] or "") or ".bin"
        digest = sha256_file(source)
        with self._hash_lock:
            target = self._unique_target(folder, stem, extension)
            existing = self._hash_paths.get(digest)
            if existing and existing.exists():
                try:
                    os.link(existing, target)
                except OSError:
                    _retry_windows_file(lambda: shutil.copy2(existing, target))
                return target
            try:
                os.link(source, target)
            except OSError:
                _retry_windows_file(lambda: shutil.copy2(source, target))
            self._hash_paths[digest] = target
            return target

    @staticmethod
    def _fill_exported(attachment: Attachment, target: Path, source_kind: str, quality: str) -> Attachment:
        attachment.available = True
        attachment.exported_path = target.as_posix()
        attachment.size_bytes = target.stat().st_size
        attachment.sha256 = sha256_file(target)
        attachment.mime_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        attachment.status = "exported"
        attachment.source_kind = source_kind
        attachment.quality = quality
        attachment.reason_code = None
        attachment.reason = None
        attachment.recovery_method = "private_cdn_downloaded" if source_kind == "private_cdn" else source_kind
        return attachment

    def _mark_unavailable(self, attachment: Attachment, reason_code: str, failed: bool = False) -> Attachment:
        attachment.available = False
        attachment.status = "failed" if failed else "missing"
        attachment.source_kind = "none"
        attachment.reason_code = reason_code
        attachment.reason = self._reason_text(attachment.category, reason_code)
        return attachment

    def export(self, attachment: Attachment, target_folder: Path) -> Attachment:
        sources = self.resolver.candidates(attachment)
        source = sources[0] if sources else None
        stem = self._attachment_md5(attachment) or (source.stem if source else attachment.attachment_id[:16])

        if attachment.category in VISUAL_KINDS:
            for candidate_source in sources:
                try:
                    data = _retry_windows_file(candidate_source.read_bytes)
                    decoded = self._decode_visual(data, attachment)
                    if decoded:
                        visual, extension = decoded
                        if extension == ".wxgf":
                            converted = self._convert_wxgf(visual)
                            if converted:
                                visual, extension = converted
                            else:
                                target = self._write_bytes(visual, target_folder, stem, ".wxgf")
                                self._fill_exported(attachment, target, "local", "original")
                                attachment.available = False
                                attachment.status = "failed"
                                attachment.reason_code = "wxgf_conversion_failed"
                                attachment.reason = self._reason_text(attachment.category, attachment.reason_code)
                                return attachment
                        target = self._write_bytes(visual, target_folder, stem, extension)
                        return self._fill_exported(attachment, target, "local", "original")
                except (OSError, PermissionError):
                    continue

            network_reason = None
            if self.client:
                downloaded, extension, quality_or_error, source_kind = self._download_visual(attachment)
                if downloaded is not None and extension is not None:
                    target = self._write_bytes(downloaded, target_folder, stem, extension)
                    return self._fill_exported(attachment, target, source_kind, quality_or_error)
                network_reason = quality_or_error
            if source:
                try:
                    # Preserve one unsupported local candidate as evidence, without presenting it as an image.
                    target = self._archive_file(source, target_folder, stem)
                    self._fill_exported(attachment, target, "local", "unknown")
                    attachment.status = "raw_preserved"
                    attachment.available = False
                    # A cache file really exists here. A missing/absent network
                    # address must not overwrite that fact with "file missing".
                    if attachment.category == "emoji" and not self._attachment_aes_keys(attachment) and not self._url_fields(attachment):
                        attachment.reason_code = "local_cache_key_missing"
                    else:
                        attachment.reason_code = (
                            network_reason
                            if network_reason not in {None, "local_media_missing", "remote_url_missing", "network_disabled"}
                            else "decode_failed"
                        )
                    attachment.reason = self._reason_text(attachment.category, attachment.reason_code)
                    attachment.recovery_method = "raw_cache"
                    return attachment
                except (OSError, PermissionError):
                    pass

            data, extension, quality_or_error, source_kind = self._download_visual(attachment)
            if data is not None and extension is not None:
                target = self._write_bytes(data, target_folder, stem, extension)
                return self._fill_exported(attachment, target, source_kind, quality_or_error)
            reason = quality_or_error or "local_media_missing"
            return self._mark_unavailable(attachment, reason, failed=reason in {"md5_mismatch", "decode_failed", "visual_decode_failed"})

        if source and attachment.category == "audio":
            decoded = self._decode_voice(source, target_folder, stem)
            if decoded:
                return self._fill_exported(attachment, decoded, "local", "original")

        if source:
            try:
                target = self._archive_file(source, target_folder, stem)
                return self._fill_exported(attachment, target, "local", "original")
            except (OSError, PermissionError):
                return self._mark_unavailable(attachment, "source_locked")
        if attachment.category in {"file", "video"}:
            data, extension, quality_or_error, source_kind = self._download_binary(attachment)
            if data is not None and extension is not None:
                target = self._write_bytes(data, target_folder, stem, extension)
                return self._fill_exported(attachment, target, source_kind, quality_or_error)
            return self._mark_unavailable(
                attachment,
                quality_or_error or "remote_url_missing",
                failed=quality_or_error in {
                    "md5_mismatch", "download_failed", "remote_content_invalid",
                    "video_container_invalid", "private_cdn_decrypt_failed",
                },
            )
        return self._mark_unavailable(attachment, "remote_url_missing" if attachment.category != "audio" else "local_media_missing")

    def preview_diagnostic(self, attachment: Attachment) -> tuple[str, str, str]:
        """Describe recovery without network access or persistent writes."""
        sources = self.resolver.candidates(attachment)
        urls = self._url_fields(attachment)
        standard_urls = [
            value for value, _ in urls
            if RestrictedMediaClient.normalize_url(
                value,
                allow_legacy_http=self.allow_legacy_http_media and attachment.category == "emoji",
            )
        ]
        has_private_identifier = any(
            value and not value.lower().startswith(("http://", "https://")) for value, _ in urls
        )
        if standard_urls:
            code = "download_on_export"
            return code, code, self._reason_text(attachment.category, code)
        if sources:
            if attachment.category not in VISUAL_KINDS:
                code = "local_available"
                return "local_available", code, self._reason_text(attachment.category, code)
            if attachment.category == "emoji" and not self._attachment_aes_keys(attachment):
                code = "local_cache_key_missing"
            else:
                code = "decode_failed" if attachment.category in VISUAL_KINDS else "local_media_missing"
            return "missing", code, self._reason_text(attachment.category, code)
        if has_private_identifier:
            code = "download_on_export" if self._attachment_aes_keys(attachment) else "private_cdn_key_missing"
            status = "download_on_export" if code == "download_on_export" else "missing"
            return status, code, (
                "预览只读取本地缓存；导出时将尝试腾讯 CDN token 恢复"
                if code == "download_on_export" else self._reason_text(attachment.category, code)
            )
        code = "remote_url_missing" if attachment.category != "audio" else "local_media_missing"
        return "missing", code, self._reason_text(attachment.category, code)

    def preview_data_url(self, attachment: Attachment, max_bytes: int = 5 * 1024 * 1024) -> str | None:
        """Decode a local visual for on-demand preview without writing an export file."""
        if attachment.category not in VISUAL_KINDS:
            return None
        for source in self.resolver.candidates(attachment):
            try:
                data = _retry_windows_file(source.read_bytes)
            except (OSError, PermissionError):
                continue
            decoded = self._decode_visual(data, attachment)
            if not decoded:
                continue
            visual, extension = decoded
            if extension == ".wxgf":
                converted = self._convert_wxgf(visual)
                if not converted:
                    continue
                visual, extension = converted
            if len(visual) > max_bytes:
                continue
            mime = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
            }.get(extension.lower())
            if mime:
                return f"data:{mime};base64,{base64.b64encode(visual).decode('ascii')}"
        return None

    def inspect_local(self, attachment: Attachment) -> tuple[str, str | None]:
        """Return a privacy-safe local recovery status without writing output files."""
        sources = self.resolver.candidates(attachment)
        if not sources:
            return "missing", self.preview_diagnostic(attachment)[1]
        if attachment.category not in VISUAL_KINDS:
            return "recoverable", None
        for source in sources:
            try:
                decoded = self._decode_visual(_retry_windows_file(source.read_bytes), attachment)
            except (OSError, PermissionError):
                continue
            if decoded:
                if decoded[1] != ".wxgf" or self._convert_wxgf(decoded[0]):
                    return "recoverable", None
                return "unsupported", "wxgf_conversion_failed"
        return "unsupported", self.preview_diagnostic(attachment)[1]

    def export_many(self, items: list[tuple[Attachment, Path]]) -> list[Attachment]:
        if not items:
            return []
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="chatwechat-media") as pool:
            futures = [pool.submit(self.export, attachment, folder) for attachment, folder in items]
            return [future.result() for future in futures]

    def estimate(self, attachments: Iterable[Attachment]) -> tuple[int, int]:
        total = 0
        count = 0
        for attachment in attachments:
            source = self.resolver.resolve(attachment)
            if source:
                try:
                    total += source.stat().st_size
                    count += 1
                except OSError:
                    pass
        return count, total

    def estimate_details(self, attachments: Iterable[Attachment]) -> dict[str, object]:
        """Inspect local availability without network access or persistent writes."""
        known_bytes = 0
        local_recoverable = network_candidates = unavailable = referenced = 0
        by_category: dict[str, dict[str, int]] = {}
        for attachment in attachments:
            referenced += 1
            row = by_category.setdefault(attachment.category, {
                "referenced": 0,
                "local_recoverable": 0,
                "network_candidate": 0,
                "unavailable": 0,
            })
            row["referenced"] += 1
            source = self.resolver.resolve(attachment)
            if source:
                try:
                    known_bytes += source.stat().st_size
                except OSError:
                    pass
            status, _ = self.inspect_local(attachment)
            if status == "recoverable":
                local_recoverable += 1
                row["local_recoverable"] += 1
                continue
            diagnostic, _, _ = self.preview_diagnostic(attachment)
            if diagnostic == "download_on_export":
                network_candidates += 1
                row["network_candidate"] += 1
            else:
                unavailable += 1
                row["unavailable"] += 1
        return {
            "referenced": referenced,
            "known_bytes": known_bytes,
            "local_recoverable": local_recoverable,
            "network_candidates": network_candidates,
            "unavailable": unavailable,
            "by_category": by_category,
        }
