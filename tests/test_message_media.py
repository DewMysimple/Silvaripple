import hashlib
import io
import base64
import struct
import urllib.error
import zlib
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from chatwechat.keystore import KeyStore
from chatwechat.media import MediaExporter, RestrictedMediaClient, decrypt_dat
from chatwechat.message_parser import decode_content, normalize_message
from chatwechat.models import Attachment


VALID_GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==")


def test_media_helpers_use_no_console_window_on_windows(tmp_path, monkeypatch):
    import chatwechat.media as media

    calls = []

    class Completed:
        returncode = 1

    monkeypatch.setattr(media.shutil, "which", lambda name: f"{name}.exe")
    monkeypatch.setattr(media.subprocess, "run", lambda *args, **kwargs: calls.append(kwargs) or Completed())
    MediaExporter("account", tmp_path)._decode_voice(tmp_path / "voice.silk", tmp_path / "out", "voice")
    assert calls
    expected = getattr(media.subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    assert calls[0]["creationflags"] == expected


def test_text_group_sender_and_unknown_preserved():
    message = normalize_message({"local_id": 1, "local_type": 1, "create_time": 1700000000, "message_content": "wxid_sender:\n你好"}, "conversation", 1)
    assert message.sender_id == "wxid_sender"
    assert message.text == "你好"
    unknown = normalize_message({"local_type": 98765, "content": "raw"}, "conversation", 2)
    assert unknown.message_type == "unknown"
    assert unknown.raw_type == 98765
    assert unknown.raw_fields["content"] == "raw"


def test_group_prefix_only_strips_matching_sender():
    matching = normalize_message({
        "local_type": 1, "sender": "wxid_member", "content": "wxid_member:\n正文",
    }, "c", 1)
    mismatched = normalize_message({
        "local_type": 1, "sender": "wxid_other", "content": "wxid_member:\n正文",
    }, "c", 2)
    assert matching.text == "正文"
    assert mismatched.text == "wxid_member:\n正文"


def test_revoke_and_quote_are_structured():
    revoke = normalize_message({
        "local_type": 10002,
        "content": '<?xml version="1.0"?><sysmsg type="revokemsg"><revokemsg><content>"甲" 撤回了一条消息</content></revokemsg></sysmsg>',
    }, "c", 1)
    quote = normalize_message({
        "local_type": 49,
        "content": "<msg><appmsg><type>57</type><title>回复</title><refermsg><chatusr>wxid_q</chatusr><displayname>成员甲</displayname><content>wxid_q:\n原文</content><type>1</type><svrid>88</svrid></refermsg></appmsg></msg>",
    }, "c", 2)
    assert revoke.message_type == "revoke"
    assert revoke.system_event and revoke.system_event.text == '"甲" 撤回了一条消息'
    assert quote.quote_preview and quote.quote_preview.text == "原文"
    assert quote.quote_preview.sender_name == "成员甲"

    image_quote = normalize_message({
        "local_type": 49,
        "content": "<msg><appmsg><type>57</type><title>回复</title><refermsg><displayname>成员乙</displayname><content>&lt;msg&gt;&lt;img aeskey='x'/&gt;&lt;/msg&gt;</content><type>3</type></refermsg></appmsg></msg>",
    }, "c", 3)
    assert image_quote.quote_preview and image_quote.quote_preview.text == "[图片]"


def test_pat_and_text_emoji_are_structured_for_display():
    pat = normalize_message({
        "local_type": (62 << 32) | 49,
        "message_content": (
            "<msg><appmsg><type>62</type><title>拍一拍</title><patinfo>"
            "<fromusername>wxid_actor</fromusername><pattedusername>wxid_target</pattedusername>"
            "<template>${fromusername} 拍了拍 ${pattedusername}</template>"
            "</patinfo></appmsg></msg>"
        ),
    }, "c", 1)
    text = normalize_message({"local_type": 1, "message_content": "你好[憨笑]"}, "c", 2)
    assert pat.message_type == "pat" and pat.system_event
    assert pat.system_event.actor_id == "wxid_actor" and pat.system_event.target_id == "wxid_target"
    assert text.text == "你好[憨笑]" and text.display_text == "你好😄"


def test_packed_info_media_token_becomes_local_candidate():
    token = "0123456789abcdef0123456789abcdef"
    inner = b"\x0a\x20" + token.encode("ascii")
    packed = b"\x12" + bytes([len(inner)]) + inner
    message = normalize_message({
        "local_type": 3,
        "message_content": "<msg><img /></msg>",
        "packed_info_data": packed,
    }, "c", 1)
    assert token in message.attachments[0].metadata["candidates"]


def test_app_types_and_malformed_xml():
    quote = normalize_message({"local_type": 49, "message_content": "<msg><appmsg><type>57</type><title>引用</title></appmsg></msg>"}, "c", 1)
    assert quote.message_type == "quote"
    malformed = normalize_message({"local_type": 49, "message_content": "<broken"}, "c", 2)
    assert malformed.message_type == "app_unknown"
    assert malformed.text == "<broken"


def test_legacy_xor_image():
    plain = b"\x89PNG\r\n\x1a\n" + b"x" * 40
    encrypted = bytes(value ^ 0x66 for value in plain)
    decoded, extension = decrypt_dat(encrypted)
    assert decoded == plain
    assert extension == "png"


def test_v2_aes_xor_image():
    plain = b"\xff\xd8\xff" + b"A" * 26
    pad = 16 - len(plain) % 16
    padded = plain + bytes([pad]) * pad
    key = b"0123456789abcdef"
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    header = b"\x07\x08V2\x08\x07" + struct.pack("<ii", len(plain), 0) + b"\x00"
    decoded, extension = decrypt_dat(header + encrypted, xor_key=0x55, aes_key=key)
    assert decoded == plain
    assert extension == "jpg"


def test_v2_wxgf_is_decrypted_and_partitioned():
    stream = b"\x00\x00\x00\x01" + b"hevc-frame"
    plain = b"wxgf\x05" + len(stream).to_bytes(4, "big") + stream
    pad = 16 - len(plain) % 16
    key = b"0123456789abcdef"
    encrypted = Cipher(algorithms.AES(key), modes.ECB()).encryptor().update(plain + bytes([pad]) * pad)
    header = b"\x07\x08V2\x08\x07" + struct.pack("<II", len(plain), 0) + b"\x00"
    decoded, extension = decrypt_dat(header + encrypted, xor_key=0x55, aes_key=key)
    assert decoded == plain and extension == "wxgf"
    assert MediaExporter._wxgf_partitions(decoded) == [(9, len(stream))]


def test_locked_media_is_skipped_without_aborting_export(tmp_path, monkeypatch):
    source = tmp_path / "source.bin"
    source.write_bytes(b"locked")
    attachment = Attachment("locked", "file", metadata={"candidates": [str(source)]})

    error = PermissionError("sharing violation")
    error.winerror = 32

    def locked(_path: Path) -> str:
        raise error

    monkeypatch.setattr("chatwechat.media.sha256_file", locked)
    exporter = MediaExporter("account", tmp_path, KeyStore(tmp_path / "keys"))
    result = exporter.export(attachment, tmp_path / "export")

    assert not result.available
    assert "已跳过" in (result.reason or "")


def test_extended_local_media_roots_and_real_header_detection(tmp_path):
    source = tmp_path / "business" / "emoticon" / "Persist" / "abc.bin"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"\x89PNG\r\n\x1a\n" + b"image")
    attachment = Attachment("emoji", "emoji", metadata={"candidates": ["abc"]})
    result = MediaExporter("account", tmp_path).export(attachment, tmp_path / "out")
    assert result.available and result.mime_type == "image/png"
    assert Path(result.exported_path).suffix == ".png"


def test_local_emoji_aes256_gcm_and_zlib(tmp_path):
    plain = b"GIF89a" + b"g" * 80
    key = "0123456789abcdef0123456789abcdef"
    nonce = b"123456789012"
    encrypted_and_tag = AESGCM(key.encode("ascii")).encrypt(nonce, zlib.compress(plain), None)
    stored = encrypted_and_tag[:-16] + nonce + encrypted_and_tag[-16:]
    source = tmp_path / "cache" / "Emoticon" / "sample"
    source.parent.mkdir(parents=True)
    source.write_bytes(stored)
    attachment = Attachment("emoji", "emoji", metadata={
        "candidates": [str(source)], "xml:aeskey": key,
    })
    result = MediaExporter("account", tmp_path).export(attachment, tmp_path / "out")
    assert result.available and result.mime_type == "image/gif"


def test_network_is_opt_in_and_host_restricted(tmp_path, monkeypatch):
    attachment = Attachment("emoji", "emoji", metadata={"xml:cdnurl": "http://vweixinf.tc.qq.com/a.gif"})
    offline = MediaExporter("account", tmp_path, download_missing_media=False)
    assert offline.client is None
    result = offline.export(attachment, tmp_path / "offline")
    assert not result.available and result.reason_code == "network_disabled"
    assert RestrictedMediaClient.normalize_url("http://vweixinf.tc.qq.com/a") == "https://vweixinf.tc.qq.com/a"
    assert RestrictedMediaClient.normalize_url("https://evil.example/a") is None
    assert RestrictedMediaClient.normalize_url("https://mmbiz.qpic.cn.evil.example/a") is None
    assert RestrictedMediaClient.normalize_url("http://vweixinf.tc.qq.com/a", True) == "http://vweixinf.tc.qq.com/a"
    assert RestrictedMediaClient.normalize_url("http://wxapp.tc.qq.com/a", True) == "https://wxapp.tc.qq.com/a"


def test_legacy_mode_still_upgrades_wxapp_http_to_https(monkeypatch):
    data = VALID_GIF
    requested = []

    class Response(io.BytesIO):
        headers = {"Content-Length": str(len(data))}
        fp = None

    client = RestrictedMediaClient(allow_legacy_http=True)

    def open_url(request, **_kwargs):
        requested.append(request.full_url)
        return Response(data)

    monkeypatch.setattr(client._opener, "open", open_url)
    downloaded, final_url, error = client.fetch("http://wxapp.tc.qq.com/a.gif")
    assert downloaded == data and error is None
    assert requested == ["https://wxapp.tc.qq.com/a.gif"]
    assert final_url == "https://wxapp.tc.qq.com/a.gif"


def test_unpadded_aes_ecb_emoji_is_validated_by_image_header(tmp_path):
    key = bytes.fromhex("00112233445566778899aabbccddeeff")
    plain = b"GIF89a" + b"x" * 26
    encrypted = Cipher(algorithms.AES(key), modes.ECB()).encryptor().update(plain)
    source = tmp_path / "cache" / "Emoticon" / "sample.bin"
    source.parent.mkdir(parents=True)
    source.write_bytes(encrypted)
    attachment = Attachment("emoji", "emoji", metadata={"candidates": [str(source)], "xml:aeskey": key.hex()})
    result = MediaExporter("account", tmp_path).export(attachment, tmp_path / "out")
    assert result.available and result.mime_type == "image/gif"


def test_visual_resolver_tries_all_local_candidates(tmp_path):
    wrong = tmp_path / "cache" / "bad.bin"
    right = tmp_path / "business" / "emoticon" / "good.bin"
    wrong.parent.mkdir(parents=True)
    right.parent.mkdir(parents=True)
    wrong.write_bytes(b"encrypted-but-unknown")
    right.write_bytes(b"GIF89a" + b"g" * 40)
    attachment = Attachment("emoji", "emoji", metadata={"candidates": [str(wrong), str(right)]})
    result = MediaExporter("account", tmp_path).export(attachment, tmp_path / "out")
    assert result.available and result.mime_type == "image/gif"


def test_unique_original_filename_recovers_local_file(tmp_path):
    source = tmp_path / "msg" / "attach" / "archive.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.4\nlocal attachment")
    attachment = Attachment("file", "file", original_name="archive.pdf")
    result = MediaExporter("account", tmp_path).export(attachment, tmp_path / "out")
    assert result.available
    assert result.source_kind == "local"
    assert Path(result.exported_path).suffix == ".pdf"


def test_legacy_http_requires_one_time_authorization(tmp_path, monkeypatch):
    data = VALID_GIF

    class Response(io.BytesIO):
        headers = {"Content-Length": str(len(data))}
        fp = None

    metadata = {
        "xml:cdnurl": "http://vweixinf.tc.qq.com/a.gif",
        "xml:md5": hashlib.md5(data).hexdigest(),
    }
    blocked = MediaExporter("account", tmp_path, download_missing_media=True)
    result = blocked.export(Attachment("emoji", "emoji", metadata=dict(metadata)), tmp_path / "blocked")
    assert result.reason_code == "legacy_http_not_authorized"

    allowed = MediaExporter("account", tmp_path, download_missing_media=True, allow_legacy_http_media=True)
    monkeypatch.setattr(allowed.client._opener, "open", lambda *_args, **_kwargs: Response(data))
    result = allowed.export(Attachment("emoji2", "emoji", metadata=dict(metadata)), tmp_path / "allowed")
    assert result.available and result.source_kind == "legacy_http"


def test_network_download_validates_image_and_md5(tmp_path, monkeypatch):
    data = VALID_GIF

    class Response(io.BytesIO):
        headers = {"Content-Length": str(len(data))}
        fp = None

    attachment = Attachment("emoji", "emoji", metadata={
        "xml:cdnurl": "https://vweixinf.tc.qq.com/a.gif",
        "xml:md5": hashlib.md5(data).hexdigest(),
    })
    exporter = MediaExporter("account", tmp_path, download_missing_media=True)
    monkeypatch.setattr(exporter.client._opener, "open", lambda *_args, **_kwargs: Response(data))
    result = exporter.export(attachment, tmp_path / "network")
    assert result.available and result.source_kind == "network" and result.mime_type == "image/gif"


def test_network_rejects_header_only_fake_image(tmp_path, monkeypatch):
    data = b"GIF89a" + b"not-a-complete-image"

    class Response(io.BytesIO):
        headers = {"Content-Length": str(len(data))}
        fp = None

    attachment = Attachment("emoji", "emoji", metadata={
        "xml:cdnurl": "https://wxapp.tc.qq.com/a.gif",
        "xml:md5": hashlib.md5(data).hexdigest(),
    })
    exporter = MediaExporter("account", tmp_path, download_missing_media=True)
    monkeypatch.setattr(exporter.client._opener, "open", lambda *_args, **_kwargs: Response(data))
    result = exporter.export(attachment, tmp_path / "network")
    assert not result.available and result.reason_code == "visual_decode_failed"


def test_network_can_replace_undecodable_local_emoji(tmp_path, monkeypatch):
    local = tmp_path / "msg" / "encrypted.bin"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"not-an-image")
    data = VALID_GIF

    class Response(io.BytesIO):
        headers = {"Content-Length": str(len(data))}
        fp = None

    attachment = Attachment("emoji", "emoji", metadata={
        "candidates": [str(local)],
        "xml:cdnurl": "https://vweixinf.tc.qq.com/a.gif",
        "xml:md5": hashlib.md5(data).hexdigest(),
    })
    exporter = MediaExporter("account", tmp_path, download_missing_media=True)
    monkeypatch.setattr(exporter.client._opener, "open", lambda *_args, **_kwargs: Response(data))
    result = exporter.export(attachment, tmp_path / "network")
    assert result.status == "exported" and result.source_kind == "network"


def test_network_redirect_to_non_allowlisted_host_is_rejected(monkeypatch):
    client = RestrictedMediaClient()

    def redirect(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 302, "redirect", {"Location": "https://evil.example/file"}, None
        )

    monkeypatch.setattr(client._opener, "open", redirect)
    data, _, reason = client.fetch("https://mmbiz.qpic.cn/file")
    assert data is None and reason == "redirect_not_allowed"


def test_file_and_video_use_safe_https_and_large_limit(tmp_path, monkeypatch):
    video = b"\x00\x00\x00\x18ftypisom" + b"v" * 64

    class Response(io.BytesIO):
        headers = {"Content-Length": str(len(video))}
        fp = None

    requested = []
    attachment = Attachment("video", "video", metadata={
        "xml:cdnvideourl": "http://wxapp.tc.qq.com/media/video",
        "xml:md5": hashlib.md5(video).hexdigest(),
    })
    exporter = MediaExporter(
        "account", tmp_path, download_missing_media=True, allow_legacy_http_media=True,
    )

    def open_url(request, **_kwargs):
        requested.append(request.full_url)
        return Response(video)

    monkeypatch.setattr(exporter.client._opener, "open", open_url)
    result = exporter.export(attachment, tmp_path / "out")
    assert result.available and Path(result.exported_path).suffix == ".mp4"
    assert requested == ["https://wxapp.tc.qq.com/media/video"]


def test_large_file_limit_and_unavailable_media_do_not_make_unsafe_requests(tmp_path, monkeypatch):
    class TooLarge(io.BytesIO):
        headers = {"Content-Length": str(500 * 1024 * 1024 + 1)}
        fp = None

    exporter = MediaExporter("account", tmp_path, download_missing_media=True)
    monkeypatch.setattr(exporter.client._opener, "open", lambda *_args, **_kwargs: TooLarge(b""))
    oversized = exporter.export(Attachment(
        "file", "file", original_name="archive.zip",
        metadata={"xml:cdnattachurl": "https://wxapp.tc.qq.com/archive.zip"},
    ), tmp_path / "large")
    assert oversized.reason_code == "remote_too_large"

    calls = []
    monkeypatch.setattr(exporter.client._opener, "open", lambda *_args, **_kwargs: calls.append(1))
    missing = exporter.export(Attachment("missing", "file"), tmp_path / "missing")
    private = exporter.export(Attachment(
        "private", "video", metadata={"xml:cdnvideourl": "00112233"},
    ), tmp_path / "private")
    assert missing.reason_code == "remote_url_missing"
    assert private.reason_code == "private_cdn_key_missing"
    assert calls == []


def test_private_cdn_token_is_allowlisted_decrypted_and_validated(tmp_path, monkeypatch):
    key = bytes.fromhex("00112233445566778899aabbccddeeff")
    plain = b"\x00\x00\x00\x18ftypisom" + b"v" * 64
    pad = 16 - len(plain) % 16
    padded = plain + bytes([pad]) * pad
    encrypted = Cipher(algorithms.AES(key), modes.ECB()).encryptor().update(padded)

    class Response(io.BytesIO):
        headers = {"Content-Length": str(len(encrypted))}
        fp = None

    requested = []
    exporter = MediaExporter("account", tmp_path, download_missing_media=True)

    def open_url(request, **_kwargs):
        requested.append(request.full_url)
        assert not request.has_header("Authorization")
        assert not request.has_header("Cookie")
        return Response(encrypted)

    monkeypatch.setattr(exporter.client._opener, "open", open_url)
    result = exporter.export(Attachment(
        "private-video", "video",
        metadata={
            "xml:cdnvideourl": "a1b2c3d4",
            "xml:aeskey": key.hex(),
            "xml:md5": hashlib.md5(plain).hexdigest(),
        },
    ), tmp_path / "private-cdn")
    assert result.available and result.source_kind == "private_cdn"
    assert result.recovery_method == "private_cdn_downloaded"
    assert requested and requested[0].startswith(
        "https://novac2c.cdn.weixin.qq.com/c2c/download?encrypted_query_param="
    )


def test_private_cdn_expired_token_has_specific_reason(tmp_path, monkeypatch):
    exporter = MediaExporter("account", tmp_path, download_missing_media=True)

    def expired(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 410, "expired", {}, None)

    monkeypatch.setattr(exporter.client._opener, "open", expired)
    result = exporter.export(Attachment(
        "expired", "video",
        metadata={
            "xml:cdnvideourl": "a1b2c3d4",
            "xml:aeskey": "00112233445566778899aabbccddeeff",
            "xml:md5": "0" * 32,
        },
    ), tmp_path / "expired")
    assert result.reason_code == "private_cdn_token_expired"


def test_download_limits_are_category_specific(tmp_path, monkeypatch):
    exporter = MediaExporter(
        "account", tmp_path, download_missing_media=True,
        visual_download_limit_mib=1, audio_download_limit_mib=2, large_download_limit_mib=3,
    )
    assert exporter.visual_limit_bytes == 1 * 1024 * 1024
    assert exporter.audio_limit_bytes == 2 * 1024 * 1024
    assert exporter.large_limit_bytes == 3 * 1024 * 1024


def test_preview_diagnostic_is_local_only_and_specific(tmp_path):
    cached = tmp_path / "cache" / "Emoticon" / "encrypted.bin"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"encrypted")
    exporter = MediaExporter("account", tmp_path, download_missing_media=True, allow_legacy_http_media=True)

    downloadable = Attachment(
        "remote", "emoji", metadata={"xml:cdnurl": "http://vweixinf.tc.qq.com/a.gif"},
    )
    cache_without_key = Attachment(
        "cached", "emoji", metadata={"candidates": [str(cached)]},
    )
    absent = Attachment("absent", "file")
    assert exporter.preview_diagnostic(downloadable)[1] == "download_on_export"
    assert exporter.preview_diagnostic(cache_without_key)[1] == "local_cache_key_missing"
    assert exporter.preview_diagnostic(absent)[1] == "remote_url_missing"


def test_estimate_details_is_local_only_and_reports_remote_candidates(tmp_path, monkeypatch):
    cached = tmp_path / "msg" / "local.mp4"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"v" * 20)
    exporter = MediaExporter("account", tmp_path, download_missing_media=True)
    calls = []
    monkeypatch.setattr(exporter.client._opener, "open", lambda *_a, **_k: calls.append(1))
    result = exporter.estimate_details([
        Attachment("local", "video", source_path=str(cached)),
        Attachment("remote", "video", metadata={"xml:cdnvideourl": "https://wxapp.tc.qq.com/v.mp4"}),
        Attachment("missing", "file"),
    ])
    assert result["referenced"] == 3
    assert result["local_recoverable"] == 1
    assert result["network_candidates"] == 1
    assert result["unavailable"] == 1
    assert result["known_bytes"] == cached.stat().st_size
    assert calls == []


def test_video_network_failures_have_specific_reasons(tmp_path, monkeypatch):
    exporter = MediaExporter("account", tmp_path, download_missing_media=True)
    attachment = Attachment("video", "video", metadata={"xml:cdnvideourl": "https://wxapp.tc.qq.com/v.mp4"})

    def missing(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "missing", {}, None)

    monkeypatch.setattr(exporter.client._opener, "open", missing)
    assert exporter.export(attachment, tmp_path / "missing-video").reason_code == "remote_not_found"


def test_xml_element_text_media_urls_are_parsed():
    message = normalize_message({
        "local_type": 43,
        "content": "<msg><videomsg><cdnvideourl>https://wxapp.tc.qq.com/video</cdnvideourl></videomsg></msg>",
    }, "conversation", 1)
    assert message.attachments[0].metadata["xml:cdnvideourl"] == "https://wxapp.tc.qq.com/video"
