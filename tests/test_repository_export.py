import json
import os
import sqlite3
import threading
import hashlib
from datetime import datetime
from pathlib import Path

from chatwechat.exporters import export_archive
from chatwechat.models import Attachment, Conversation, ExportRequest, KeyCoverage, WechatAccount, WechatMessage
from chatwechat.repository import WechatRepository


class PlainRepository(WechatRepository):
    def _decrypt(self, source: Path) -> Path:
        return source


def make_db(path, statements):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    for sql, values in statements:
        db.execute(sql, values)
    db.commit(); db.close()


def test_schema_probe_lists_and_reads_messages(tmp_path):
    account_dir = tmp_path / "wxid_fixture_abcd"
    make_db(account_dir / "db_storage/contact/contact.db", [
        ("CREATE TABLE contact(username TEXT, remark TEXT, nickname TEXT)", ()),
        ("INSERT INTO contact VALUES(?,?,?)", ("friend", "朋友", "昵称")),
        ("INSERT INTO contact VALUES(?,?,?)", ("wxid_fixture", "", "测试昵称")),
    ])
    make_db(account_dir / "db_storage/session/session.db", [
        ("CREATE TABLE SessionTable(username TEXT, last_timestamp INTEGER, unread_count INTEGER)", ()),
        ("INSERT INTO SessionTable VALUES(?,?,?)", ("friend", 1700000000, 2)),
    ])
    make_db(account_dir / "db_storage/message/message_0.db", [
        ("CREATE TABLE messages(username TEXT, local_id INTEGER, local_type INTEGER, create_time INTEGER, message_content TEXT, is_sender INTEGER)", ()),
        ("INSERT INTO messages VALUES(?,?,?,?,?,?)", ("friend", 1, 1, 1700000000, "<script>你好", 1)),
    ])
    make_db(account_dir / "db_storage/message/media_0.db", [
        ("CREATE TABLE Name2Id(user_name TEXT)", ()),
        ("INSERT INTO Name2Id VALUES(?)", ("friend",)),
        ("CREATE TABLE VoiceInfo(chat_name_id INTEGER, create_time INTEGER, voice_data BLOB)", ()),
        ("INSERT INTO VoiceInfo VALUES(?,?,?)", (1, 1700000001, b"#!SILK_V3voice")),
    ])
    account = WechatAccount("a", account_dir, "测试账号", True, None, 0, 3, KeyCoverage(3, 3))
    repository = PlainRepository(account)
    assert [path.name for path in repository._message_sources()] == ["message_0.db"]
    conversations = repository.list_conversations()
    assert account.display_name == "测试昵称"
    assert conversations[0].display_name == "朋友"
    assert repository.contact_original_names()["friend"] == "昵称"
    messages = list(repository.iter_messages(conversations[0].conversation_id))
    assert messages[0].text == "<script>你好"
    db = sqlite3.connect(account_dir / "db_storage/message/message_0.db")
    db.execute("INSERT INTO messages VALUES(?,?,?,?,?,?)", ("friend", 2, 34, 1700000001, "", 0))
    db.commit(); db.close()
    messages = list(repository.iter_messages(conversations[0].conversation_id))
    voice = next(message for message in messages if message.message_type == "audio")
    voice_path = Path(voice.attachments[0].metadata["candidates"][0])
    assert voice_path.read_bytes() == b"#!SILK_V3voice"
    progress_rows = []
    report = repository.account_statistics("fingerprint", threading.Event(), lambda value, message, detail=None: progress_rows.append((value, message, detail)))
    assert report.conversation_count == 1 and report.message_count == 2
    assert report.by_message_type["text"] == 1 and report.by_message_type["audio"] == 1
    assert report.conversations[0].display_name == "朋友"
    assert progress_rows and "message_content" not in json.dumps(report.to_dict(), ensure_ascii=False)
    repository.close()


def test_wechat4_md5_message_shard_and_packed_type(tmp_path):
    account_dir = tmp_path / "wxid_self_abcd"
    talker = "room@chatroom"
    table = "Msg_" + hashlib.md5(talker.encode("utf-8")).hexdigest()
    make_db(account_dir / "db_storage/contact/contact.db", [
        ("CREATE TABLE contact(id INTEGER, username TEXT, remark TEXT, nick_name TEXT)", ()),
        ("INSERT INTO contact VALUES(?,?,?,?)", (1, "wxid_self", "", "我")),
        ("INSERT INTO contact VALUES(?,?,?,?)", (2, talker, "测试群", "")),
    ])
    make_db(account_dir / "db_storage/session/session.db", [
        ("CREATE TABLE Name2Id(user_name TEXT)", ()),
        ("INSERT INTO Name2Id VALUES(?)", (talker,)),
        ("CREATE TABLE SessionTable(username TEXT, last_timestamp INTEGER)", ()),
        ("INSERT INTO SessionTable VALUES(?,?)", (talker, 1700000000)),
    ])
    make_db(account_dir / "db_storage/message/message_0.db", [
        ("CREATE TABLE Name2Id(user_name TEXT, is_session INTEGER)", ()),
        ("INSERT INTO Name2Id VALUES(?,?)", ("wxid_self", 1)),
        ("INSERT INTO Name2Id VALUES(?,?)", (talker, 1)),
        (f"CREATE TABLE {table}(local_id INTEGER, server_id INTEGER, local_type INTEGER, real_sender_id INTEGER, create_time INTEGER, message_content BLOB, compress_content BLOB)", ()),
        (f"INSERT INTO {table} VALUES(?,?,?,?,?,?,?)", (1, 2, (57 << 32) | 49, 1, 1700000000, b"<msg><appmsg><title>quoted</title></appmsg></msg>", b"")),
    ])
    account = WechatAccount("a", account_dir, "测试账号", True, None, 0, 3, KeyCoverage(3, 3))
    repository = PlainRepository(account)
    conversation = repository.list_conversations()[0]
    assert conversation.last_message_at is not None
    messages = list(repository.iter_messages(conversation.conversation_id, limit=30))
    assert len(messages) == 1
    assert messages[0].message_type == "quote"
    assert messages[0].sender_name == "我" and messages[0].outgoing
    repository.close()


def test_message_preview_pages_from_latest_and_reports_full_range(tmp_path):
    account_dir = tmp_path / "wxid_self_abcd"
    talker = "friend"
    table = "Msg_" + hashlib.md5(talker.encode("utf-8")).hexdigest()
    make_db(account_dir / "db_storage/contact/contact.db", [
        ("CREATE TABLE contact(username TEXT, nick_name TEXT)", ()),
        ("INSERT INTO contact VALUES(?,?)", (talker, "朋友")),
    ])
    make_db(account_dir / "db_storage/session/session.db", [
        ("CREATE TABLE Name2Id(user_name TEXT)", ()),
        ("INSERT INTO Name2Id VALUES(?)", (talker,)),
        ("CREATE TABLE SessionTable(username TEXT, last_timestamp INTEGER, sort_timestamp INTEGER)", ()),
        ("INSERT INTO SessionTable VALUES(?,?,?)", (talker, 0, 1700000005)),
    ])
    statements = [
        ("CREATE TABLE Name2Id(user_name TEXT)", ()),
        ("INSERT INTO Name2Id VALUES(?)", (talker,)),
        (f"CREATE TABLE {table}(local_id INTEGER, local_type INTEGER, create_time INTEGER, message_content TEXT)", ()),
    ]
    statements.extend(
        (f"INSERT INTO {table} VALUES(?,?,?,?)", (index, 1, 1700000000 + index, f"message-{index}"))
        for index in range(1, 6)
    )
    make_db(account_dir / "db_storage/message/message_0.db", statements)
    account = WechatAccount("a", account_dir, "测试账号", True, None, 0, 3, KeyCoverage(3, 3))
    repository = PlainRepository(account)
    conversation = repository.list_conversations()[0]

    latest = list(repository.iter_messages(conversation.conversation_id, limit=2))
    older = list(repository.iter_messages(conversation.conversation_id, limit=2, offset=2))
    summary = repository.message_summary(conversation.conversation_id)

    assert [message.text for message in latest] == ["message-4", "message-5"]
    assert [message.text for message in older] == ["message-2", "message-3"]
    assert summary["total"] == 5
    assert summary["earliest_at"] < summary["latest_at"]
    repository.close()


def test_avatar_uses_existing_offline_url_cache(tmp_path):
    account_dir = tmp_path / "wxid_fixture_abcd"
    avatar_url = "https://example.invalid/avatar"
    make_db(account_dir / "db_storage/contact/contact.db", [
        ("CREATE TABLE contact(username TEXT, remark TEXT, nick_name TEXT, small_head_url TEXT)", ()),
        ("INSERT INTO contact VALUES(?,?,?,?)", ("friend", "朋友", "", avatar_url)),
        ("INSERT INTO contact VALUES(?,?,?,?)", ("wxid_fixture", "当前账号", "", avatar_url)),
    ])
    cached = account_dir / "temp/head_image" / hashlib.md5(avatar_url.encode("utf-8")).hexdigest()
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"\x89PNG\r\n\x1a\n" + b"avatar")
    account = WechatAccount("a", account_dir, "测试账号", True, None, 0, 1, KeyCoverage(1, 1))
    repository = PlainRepository(account)
    assert repository.avatar_data_urls(["friend"])["friend"].startswith("data:image/png;base64,")
    assert repository.resolve_account_avatar_data_url().startswith("data:image/png;base64,")
    assert account.avatar_data_url == repository.resolve_account_avatar_data_url()
    repository.close()


class FakeRepository:
    def __init__(self, conversation, message, store):
        self._conversation = conversation; self._message = message; self.store = store
    def conversation(self, _): return self._conversation
    def iter_messages(self, *_): yield self._message
    def message_summary(self, *_): return {"total": 1}


class OriginalNameRepository(FakeRepository):
    def __init__(self, conversation, message, store, original_names):
        super().__init__(conversation, message, store)
        self._original_names = original_names
    def contact_original_names(self): return dict(self._original_names)


class MultiConversationRepository(OriginalNameRepository):
    def __init__(self, conversations, messages, store, original_names):
        super().__init__(conversations[0], messages[conversations[0].conversation_id], store, original_names)
        self._conversations = {item.conversation_id: item for item in conversations}
        self._messages = messages
    def conversation(self, conversation_id): return self._conversations[conversation_id]
    def iter_messages(self, conversation_id, *_): yield self._messages[conversation_id]
    def message_summary(self, *_): return {"total": 1}


def test_export_is_atomic_and_escapes_html(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"; source.write_text("attachment", encoding="utf-8")
    account_dir = tmp_path / "wxid"; (account_dir / "msg").mkdir(parents=True)
    media = account_dir / "msg" / "source.txt"; media.write_bytes(source.read_bytes())
    attachment = Attachment("att", "file", original_name='坏:name?.txt', metadata={"candidates": [str(media)]})
    conversation = Conversation("cid", "friend", '会话<名字>', "private")
    message = WechatMessage("m", "cid", 1, datetime.now().astimezone(), None, None, True, "text", "<script>alert(1)</script>", [attachment])
    account = WechatAccount("a", account_dir, "测试账号", True, None, 0, 0, KeyCoverage(1, 1))
    from chatwechat.keystore import KeyStore
    repository = FakeRepository(conversation, message, KeyStore(tmp_path / "keys"))
    request = ExportRequest("a", ["cid"], tmp_path / "out")
    original_replace = os.replace
    replace_attempts = 0

    def flaky_replace(source, destination):
        nonlocal replace_attempts
        replace_attempts += 1
        if replace_attempts < 3:
            error = PermissionError("sharing violation")
            error.winerror = 32
            raise error
        return original_replace(source, destination)

    monkeypatch.setattr("chatwechat.exporters.os.replace", flaky_replace)
    monkeypatch.setattr("chatwechat.exporters.time.sleep", lambda _seconds: None)
    result = export_archive(account, repository, request, threading.Event(), lambda *_: None)
    folder = result.root / "私聊" / "会话_名字_"
    assert (folder / "chat.json").is_file() and (folder / "chat.md").is_file() and (folder / "chat.html").is_file()
    html = (folder / "chat.html").read_text(encoding="utf-8")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    manifest = json.loads((folder / "_export_manifest.json").read_text(encoding="utf-8"))
    assert any(row["path"].startswith("media/") for row in manifest["files"])
    assert manifest["storage_mode"] == "shared" and manifest["conversation_archive_id"]
    assert not (result.root / "_chatwechat_export.json").exists()
    assert result.created_count == 1 and result.replaced_count == 0
    assert not list((tmp_path / "out").glob(".chatwechat-*"))
    assert replace_attempts == 3


def test_export_layout_and_people_use_profile_nicknames_not_local_remarks(tmp_path):
    account_dir = tmp_path / "wxid_self_abcd"; account_dir.mkdir()
    conversation = Conversation("cid", "friend", "我设置的好友备注", "private")
    message = WechatMessage(
        "m", "cid", 1, datetime.now().astimezone(), "friend", "我设置的好友备注", False,
        "text", "你好", [], raw_fields={"sender": "friend"},
    )
    account = WechatAccount("a", account_dir, "本地账号显示名", True, None, 0, 0, KeyCoverage(1, 1))
    from chatwechat.keystore import KeyStore
    repository = OriginalNameRepository(
        conversation, message, KeyStore(tmp_path / "keys"),
        {"wxid_self": "账号原昵称", "friend": "好友原昵称"},
    )
    result = export_archive(
        account, repository, ExportRequest("a", ["cid"], tmp_path / "out"),
        threading.Event(), lambda *_: None,
    )

    folder = result.root / "私聊" / "好友原昵称"
    assert folder.is_dir()
    html_text = (folder / "chat.html").read_text(encoding="utf-8")
    markdown = (folder / "chat.md").read_text(encoding="utf-8")
    data = json.loads((folder / "chat.json").read_text(encoding="utf-8"))
    assert "好友原昵称" in html_text and "我设置的好友备注" not in html_text
    assert "好友原昵称" in markdown and "我设置的好友备注" not in markdown
    assert data["conversation"]["display_name"] == "好友原昵称"
    assert data["messages"][0]["sender_display_name"] == "好友原昵称"
    assert data["messages"][0]["raw_fields"]["sender"] == "friend"


def test_export_v2_hides_internal_ids_from_display_layers(tmp_path):
    account_dir = tmp_path / "wxid_account"; account_dir.mkdir()
    conversation = Conversation("cid", "room@chatroom", "测试群", "group")
    message = WechatMessage(
        "m", "cid", 1, datetime.now().astimezone(), "wxid_member", None, False,
        "text", "wxid_member: 你好", [], raw_fields={"sender": "wxid_member"}, raw_xml="<x>wxid_member</x>",
    )
    account = WechatAccount("a", account_dir, "小宇快跑", True, None, 0, 0, KeyCoverage(1, 1))
    from chatwechat.keystore import KeyStore
    repository = FakeRepository(conversation, message, KeyStore(tmp_path / "keys"))
    result = export_archive(account, repository, ExportRequest("a", ["cid"], tmp_path / "out"), threading.Event(), lambda *_: None)
    folder = result.root / "群聊" / "测试群"
    html_text = (folder / "chat.html").read_text(encoding="utf-8")
    markdown = (folder / "chat.md").read_text(encoding="utf-8")
    data = json.loads((folder / "chat.json").read_text(encoding="utf-8"))
    manifest = json.loads((folder / "_export_manifest.json").read_text(encoding="utf-8"))
    assert "wxid_" not in html_text and "wxid_" not in markdown
    assert data["version"] == 2 and data["messages"][0]["sender_id"] == "wxid_member"
    assert data["messages"][0]["raw_xml"] == "<x>wxid_member</x>"
    assert manifest["version"] == 4 and "media_summary" in manifest and "warning_details" in manifest


def test_export_uses_display_emoji_and_does_not_duplicate_image_placeholder(tmp_path):
    account_dir = tmp_path / "wxid_account"; account_dir.mkdir()
    conversation = Conversation("cid", "friend", "测试", "private")
    attachment = Attachment("missing", "image", reason="本机未缓存图片；请先在微信中打开后重新导出")
    message = WechatMessage(
        "m", "cid", 1, datetime.now().astimezone(), "friend", "朋友", False,
        "image", None, [attachment], display_text=None,
    )
    account = WechatAccount("a", account_dir, "我", True, None, 0, 0, KeyCoverage(1, 1))
    from chatwechat.keystore import KeyStore
    repository = FakeRepository(conversation, message, KeyStore(tmp_path / "keys"))
    result = export_archive(account, repository, ExportRequest("a", ["cid"], tmp_path / "out"), threading.Event(), lambda *_: None)
    folder = result.root / "私聊" / "测试"
    html_text = (folder / "chat.html").read_text(encoding="utf-8")
    assert "[image]" not in html_text
    assert html_text.count("本机未缓存图片") == 1

    repository._message = WechatMessage(
        "m2", "cid", 2, datetime.now().astimezone(), "friend", "朋友", False,
        "text", "你好[憨笑]", [], display_text="你好😄",
    )
    result2 = export_archive(account, repository, ExportRequest("a", ["cid"], tmp_path / "out2"), threading.Event(), lambda *_: None)
    folder2 = result2.root / "私聊" / "测试"
    assert "你好😄" in (folder2 / "chat.html").read_text(encoding="utf-8")
    assert json.loads((folder2 / "chat.json").read_text(encoding="utf-8"))["messages"][0]["text"] == "你好[憨笑]"


def test_fixed_archive_replaces_same_conversation_and_removes_old_formats(tmp_path):
    account_dir = tmp_path / "wxid_self_abcd"; account_dir.mkdir()
    conversation = Conversation("cid", "friend", "好友", "private")
    first = WechatMessage("m1", "cid", 1, datetime.now().astimezone(), "friend", "好友", False, "text", "旧内容")
    from chatwechat.keystore import KeyStore
    repository = OriginalNameRepository(conversation, first, KeyStore(tmp_path / "keys"), {"friend": "好友"})
    request = ExportRequest("a", ["cid"], tmp_path / "out")
    account = WechatAccount("a", account_dir, "账号", True, None, 0, 0, KeyCoverage(1, 1))

    first_result = export_archive(account, repository, request, threading.Event(), lambda *_: None)
    folder = first_result.root / "私聊" / "好友"
    first_export_id = json.loads((folder / "_export_manifest.json").read_text(encoding="utf-8"))["export_id"]
    repository._message = WechatMessage("m2", "cid", 2, datetime.now().astimezone(), "friend", "好友", False, "text", "新内容")
    request.formats = ["html"]
    second_result = export_archive(account, repository, request, threading.Event(), lambda *_: None)

    assert second_result.root == first_result.root
    assert second_result.created_count == 0 and second_result.replaced_count == 1
    assert "新内容" in (folder / "chat.html").read_text(encoding="utf-8")
    assert "旧内容" not in (folder / "chat.html").read_text(encoding="utf-8")
    assert not (folder / "chat.md").exists() and not (folder / "chat.json").exists()
    assert json.loads((folder / "_export_manifest.json").read_text(encoding="utf-8"))["export_id"] != first_export_id
    assert len(list((tmp_path / "out").glob("微信导出_*"))) == 0


def test_fixed_archive_moves_when_profile_name_or_layout_changes(tmp_path):
    account_dir = tmp_path / "wxid_self_abcd"; account_dir.mkdir()
    conversation = Conversation("cid", "friend", "备注", "private")
    message = WechatMessage("m", "cid", 1, datetime.now().astimezone(), "friend", "备注", False, "text", "内容")
    from chatwechat.keystore import KeyStore
    repository = OriginalNameRepository(conversation, message, KeyStore(tmp_path / "keys"), {"friend": "旧昵称"})
    account = WechatAccount("a", account_dir, "账号", True, None, 0, 0, KeyCoverage(1, 1))
    export_archive(account, repository, ExportRequest("a", ["cid"], tmp_path / "out"), threading.Event(), lambda *_: None)
    old = tmp_path / "out" / "私聊" / "旧昵称"
    assert old.is_dir()

    repository._original_names = {"friend": "新昵称"}
    request = ExportRequest("a", ["cid"], tmp_path / "out", folder_layout="flat")
    result = export_archive(account, repository, request, threading.Event(), lambda *_: None)
    assert not old.exists()
    assert (tmp_path / "out" / "新昵称").is_dir()
    assert result.replaced_count == 1


def test_same_account_same_name_uses_readable_numeric_suffix(tmp_path):
    account_dir = tmp_path / "wxid_self_abcd"; account_dir.mkdir()
    rows = [Conversation("c1", "friend1", "备注1", "private"), Conversation("c2", "friend2", "备注2", "private")]
    messages = {
        item.conversation_id: WechatMessage(item.conversation_id, item.conversation_id, 1, datetime.now().astimezone(), item.username, "备注", False, "text", "内容")
        for item in rows
    }
    from chatwechat.keystore import KeyStore
    repository = MultiConversationRepository(rows, messages, KeyStore(tmp_path / "keys"), {"friend1": "同名", "friend2": "同名"})
    account = WechatAccount("a", account_dir, "账号", True, None, 0, 0, KeyCoverage(1, 1))
    export_archive(account, repository, ExportRequest("a", ["c1", "c2"], tmp_path / "out"), threading.Event(), lambda *_: None)
    assert (tmp_path / "out" / "私聊" / "同名").is_dir()
    assert (tmp_path / "out" / "私聊" / "同名（2）").is_dir()


def test_unverified_name_collision_is_never_overwritten(tmp_path):
    account_dir = tmp_path / "wxid_self_abcd"; account_dir.mkdir()
    occupied = tmp_path / "out" / "私聊" / "好友"; occupied.mkdir(parents=True)
    (occupied / "用户文件.txt").write_text("保留", encoding="utf-8")
    conversation = Conversation("cid", "friend", "备注", "private")
    message = WechatMessage("m", "cid", 1, datetime.now().astimezone(), "friend", "备注", False, "text", "内容")
    from chatwechat.keystore import KeyStore
    repository = OriginalNameRepository(conversation, message, KeyStore(tmp_path / "keys"), {"friend": "好友"})
    account = WechatAccount("a", account_dir, "账号", True, None, 0, 0, KeyCoverage(1, 1))
    export_archive(account, repository, ExportRequest("a", ["cid"], tmp_path / "out"), threading.Event(), lambda *_: None)
    assert (occupied / "用户文件.txt").read_text(encoding="utf-8") == "保留"
    assert (tmp_path / "out" / "私聊" / "好友（2）" / "chat.html").is_file()


def test_multi_conversation_commit_failure_restores_every_previous_archive(tmp_path, monkeypatch):
    account_dir = tmp_path / "wxid_self_abcd"; account_dir.mkdir()
    rows = [Conversation("c1", "friend1", "甲", "private"), Conversation("c2", "friend2", "乙", "private")]
    from chatwechat.keystore import KeyStore
    old_messages = {
        item.conversation_id: WechatMessage(item.conversation_id, item.conversation_id, 1, datetime.now().astimezone(), item.username, item.display_name, False, "text", f"旧{item.display_name}")
        for item in rows
    }
    repository = MultiConversationRepository(rows, old_messages, KeyStore(tmp_path / "keys"), {"friend1": "甲", "friend2": "乙"})
    account = WechatAccount("a", account_dir, "账号", True, None, 0, 0, KeyCoverage(1, 1))
    request = ExportRequest("a", ["c1", "c2"], tmp_path / "out")
    export_archive(account, repository, request, threading.Event(), lambda *_: None)
    repository._messages = {
        item.conversation_id: WechatMessage("new" + item.conversation_id, item.conversation_id, 2, datetime.now().astimezone(), item.username, item.display_name, False, "text", f"新{item.display_name}")
        for item in rows
    }
    real_replace = os.replace

    def fail_second_staged_commit(source, destination):
        if ".chatwechat-" in str(source) and Path(source).parent.name == "new" and Path(destination).name == "乙":
            error = PermissionError("sharing violation")
            error.winerror = 32
            raise error
        return real_replace(source, destination)

    monkeypatch.setattr("chatwechat.exporters.os.replace", fail_second_staged_commit)
    monkeypatch.setattr("chatwechat.exporters.time.sleep", lambda _seconds: None)
    try:
        export_archive(account, repository, request, threading.Event(), lambda *_: None)
    except PermissionError:
        pass
    else:
        raise AssertionError("second commit should fail")
    for name in ("甲", "乙"):
        html = (tmp_path / "out" / "私聊" / name / "chat.html").read_text(encoding="utf-8")
        assert f"旧{name}" in html and f"新{name}" not in html
    assert not list((tmp_path / "out").glob(".chatwechat-*"))
