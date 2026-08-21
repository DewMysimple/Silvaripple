from pathlib import Path


def test_old_settings_and_presets_migrate_media_defaults_on(tmp_path):
    import json
    from chatwechat.config import SettingsStore
    from chatwechat.service import ChatWechatService, JsonListStore

    (tmp_path / "settings.json").write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    settings = SettingsStore(tmp_path).load()
    assert settings.download_missing_media_default is True
    assert settings.allow_legacy_http_media_default is True
    assert settings.open_result_folder_after_export is False
    assert settings.export_folder_layout == "by_type"
    assert (settings.visual_download_limit_mib, settings.audio_download_limit_mib, settings.large_download_limit_mib) == (50, 100, 500)

    service = object.__new__(ChatWechatService)
    service.settings = settings
    service.preset_store = JsonListStore(tmp_path / "presets.json", maximum=5)
    service.preset_store.save([{"preset_id": "old", "name": "旧预设"}])
    preset = service.list_export_presets()["items"][0]
    assert preset["download_missing_media"] is True
    assert preset["allow_legacy_http_media"] is True
    assert (preset["visual_download_limit_mib"], preset["audio_download_limit_mib"], preset["large_download_limit_mib"]) == (50, 100, 500)


def test_download_limit_settings_are_clamped(tmp_path):
    from chatwechat.config import Settings
    from chatwechat.models import ExportRequest

    settings = Settings.from_dict({
        "visual_download_limit_mib": 0,
        "audio_download_limit_mib": "80",
        "large_download_limit_mib": 9999,
    })
    assert (settings.visual_download_limit_mib, settings.audio_download_limit_mib, settings.large_download_limit_mib) == (1, 80, 2048)
    request = ExportRequest.from_dict({
        "account_id": "account", "conversation_ids": [], "output_directory": str(tmp_path),
        "visual_download_limit_mib": 75, "audio_download_limit_mib": 125, "large_download_limit_mib": 640,
    })
    assert (request.visual_download_limit_mib, request.audio_download_limit_mib, request.large_download_limit_mib) == (75, 125, 640)
    assert request.folder_layout == "by_type"


def test_conversation_filter_excludes_only_requested_kind():
    from chatwechat.models import Conversation
    from chatwechat.service import ChatWechatService

    class Repository:
        account = type("Account", (), {"to_dict": lambda self: {}})()

        @staticmethod
        def list_conversations():
            return [
                Conversation("private", "friend", "朋友", "private"),
                Conversation("group", "room@chatroom", "群聊", "group"),
                Conversation("official", "official", "公众号", "official"),
                Conversation("brand", "brandsessionholder", "brandsessionholder", "private"),
                Conversation("brand-service", "brandservicesessionholder", "brandservicesessionholder", "private"),
                Conversation("placeholder", "@placeholder_foldgroup", "@placeholder_foldgroup", "private"),
                Conversation("service", "service-notify", "服务通知", "private"),
            ]

        @staticmethod
        def avatar_data_urls(_usernames):
            return {}

    service = object.__new__(ChatWechatService)
    service._repository = lambda _account_id: Repository()
    result = service.list_conversations("account", {"exclude_kinds": ["official"]})
    assert result["total"] == 2
    assert {row["kind"] for row in result["items"]} == {"private", "group"}


def test_metadata_stores_persist_media_defaults_but_not_conversations(tmp_path):
    from chatwechat.service import ChatWechatService, JsonListStore

    service = object.__new__(ChatWechatService)
    service.preset_store = JsonListStore(tmp_path / "presets.json", maximum=5)
    result = service.save_export_preset({
        "name": "完整归档",
        "formats": ["html", "json"],
        "download_missing_media": True,
        "allow_legacy_http_media": True,
        "visual_download_limit_mib": 80,
        "audio_download_limit_mib": 120,
        "large_download_limit_mib": 700,
        "conversation_ids": ["must-not-persist"],
    })
    preset = result["preset"]
    assert preset["allow_legacy_http_media"] is True
    assert preset["large_download_limit_mib"] == 700
    assert "conversation_ids" not in preset
    assert service.preset_store.load()[0]["name"] == "完整归档"


def test_bridge_contract_and_ui_assets():
    from chatwechat.service import Bridge

    expected = {
        "bootstrap", "scan_accounts", "authorize_account", "list_conversations", "preview_messages",
        "estimate_export", "start_export", "cancel_operation", "get_operation", "choose_folder", "save_settings",
        "search_messages", "start_media_scan", "get_media_report", "list_operation_history",
        "clear_operation_history", "clear_abnormal_operation_history", "list_export_presets", "save_export_preset", "delete_export_preset",
        "open_result_folder", "start_account_statistics_scan", "get_account_statistics",
        "delete_operation_history_entry", "delete_operation_history_entries",
        "relink_operation_history_entry", "trash_export_result",
    }
    assert expected <= set(dir(Bridge))
    root = Path(__file__).parents[1] / "chatwechat" / "web"
    html = (root / "index.html").read_text(encoding="utf-8")
    assets = list((root / "assets").glob("index-*.js"))
    assert assets
    javascript = assets[0].read_text(encoding="utf-8")
    frontend = Path(__file__).parents[1] / "frontend" / "src"
    source = (frontend / "App.tsx").read_text(encoding="utf-8")
    assert "pywebview" in javascript
    assert "开始导出" in source and "允许数据库覆盖不完整" in source
    assert "allow_legacy_http_media" in source
    assert "download_missing_media_default" in source
    assert "私聊与群聊" in source and '<option value="official">' not in source
    assert "ResizeObserver" in source and "olderAnchor" in source
    assert "ensureSelected(activeConversation.conversation_id)" in source
    assert "加入导出" in source
    assert "visual_download_limit_mib" in source
    assert "实时导出检查" in source and "导出会话列表" in source
    assert "扫描全部私聊与群聊" in source and "逐会话统计" in source
    assert "应用导出预设" not in source and "预计生成" not in source
    assert "高级选项" in source and "目录已移动" in source
    assert "window.setTimeout(() => void pumpEstimate(), 600)" in source
    assert "计算导出规模" not in source
    assert "打开导出目录" in source and "我已在微信中打开，重新检测" in source
    store_source = (frontend / "store.ts").read_text(encoding="utf-8")
    assert "exportDraft" in store_source and "exportOperationId" in store_source
    assert "mediaScanOperationId" in store_source and "startMediaScan" in store_source
    assert "last_account_id" in store_source
    assert "正在刷新本地媒体状态" in source
    assert "account.avatar_data_url" in source
    assert "浏览并选择聊天" in source and "整理导出范围" in source and "检查媒体可用性" in source
    assert "workbench-launches" in source and "account-overview" in source
    assert "clear_abnormal_operation_history" in source
    assert "ConfirmDialog" in source and "window.confirm" not in source
    assert "清空异常记录" in source and "清空全部记录" in source
    assert "secondary-workbenches" not in source
    assert "类媒体告警" not in source
    assert "http://" not in html and "https://" not in html
    styles = (frontend / "styles.css").read_text(encoding="utf-8")
    assert ".conversation-list { min-height: 0" in styles
    assert ".messages { min-height: 0" in styles
    assert "grid-template-columns: minmax(0,1fr) 18px" in styles
    assert ".global-search .primary" in styles and "white-space: nowrap" in styles
    assert ".bubble { width: fit-content" in styles
    assert ".home-page { max-width: 1440px" in styles
    assert ".workbench-launches { display: grid" in styles
    assert "grid-template-columns: repeat(3,minmax(0,1fr))" in styles
    assert ".action-menu" in styles and ".confirm-dialog" in styles
    assert "button:active { scale: .96; }" in styles
    assert ".account-statistics-panel" in styles and ".rich-history" in styles


def test_history_health_relink_and_metadata_delete(tmp_path):
    from types import SimpleNamespace
    from chatwechat.service import ChatWechatService, JsonListStore

    output = tmp_path / "output"; output.mkdir()
    archive = output / "微信导出_1"; archive.mkdir()
    (archive / "_chatwechat_export.json").write_text(
        '{"version":1,"archive_id":"archive-1"}', encoding="utf-8"
    )
    service = object.__new__(ChatWechatService)
    service.settings = SimpleNamespace(output_directory=str(output), data_root=str(tmp_path / "wechat"))
    service.history_store = JsonListStore(tmp_path / "history.json")
    service.approved_output_dirs = set()
    service.history_store.save([{
        "history_id":"h1","kind":"export","status":"completed","created_at":"2026-01-01T00:00:00+08:00",
        "completed_at":"2026-01-01T00:00:01+08:00","result_path":str(archive),"original_path":str(archive),
        "current_path":str(archive),"archive_id":"archive-1","directory_health":"missing","formats":[],
        "warnings":[],"warning_details":[],"conversation_count":1,"message_count":2,"media_count":0,
    }])
    item = service.list_operation_history()["items"][0]
    assert item["directory_health"] == "healthy"
    service.delete_operation_history_entry("h1")
    assert archive.is_dir() and service.history_store.load() == []


def test_history_cleanup_preserves_running_and_only_removes_true_abnormal(tmp_path):
    from chatwechat.service import ChatWechatService, JsonListStore

    service = object.__new__(ChatWechatService)
    service.history_store = JsonListStore(tmp_path / "history.json")
    rows = [
        {"history_id": "running", "status": "running", "directory_health": "not_applicable"},
        {"history_id": "healthy", "status": "completed", "directory_health": "healthy"},
        {"history_id": "cancelled", "status": "cancelled", "directory_health": "not_applicable"},
        {"history_id": "moved", "status": "completed", "directory_health": "moved"},
        {"history_id": "trashed", "status": "completed", "directory_health": "trashed"},
        {"history_id": "failed", "status": "failed", "directory_health": "not_applicable"},
        {"history_id": "interrupted", "status": "interrupted", "directory_health": "not_applicable"},
        {"history_id": "missing", "status": "completed", "directory_health": "missing"},
        {"history_id": "incomplete", "status": "completed", "directory_health": "incomplete"},
        {"history_id": "inaccessible", "status": "completed", "directory_health": "inaccessible"},
    ]
    service.history_store.save(rows)

    result = service.clear_abnormal_operation_history()
    assert result["deleted_count"] == 5
    assert result["preserved_running_count"] == 1
    assert {row["history_id"] for row in service.history_store.load()} == {
        "running", "healthy", "cancelled", "moved", "trashed",
    }

    result = service.clear_operation_history()
    assert result["deleted_count"] == 4
    assert result["preserved_running_count"] == 1
    assert service.history_store.load() == [rows[0]]


def test_shared_history_detects_superseded_export_and_will_not_trash_current(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    from chatwechat.errors import ChatWechatError
    from chatwechat.service import ChatWechatService, JsonListStore

    output = tmp_path / "output"; folder = output / "私聊" / "好友"; folder.mkdir(parents=True)
    archive_id = "conversation-archive"
    (folder / "_export_manifest.json").write_text(json.dumps({
        "version": 4, "storage_mode": "shared", "conversation_archive_id": archive_id,
        "export_id": "new-export", "account_id": "account",
    }), encoding="utf-8")
    service = object.__new__(ChatWechatService)
    service.settings = SimpleNamespace(output_directory=str(output), data_root=str(tmp_path / "wechat"))
    service.history_store = JsonListStore(tmp_path / "history.json")
    service.approved_output_dirs = set()
    service.history_store.save([{
        "history_id": "old", "kind": "export", "status": "completed", "storage_mode": "shared",
        "created_at": "2026-01-01T00:00:00+08:00", "completed_at": "2026-01-01T00:00:01+08:00",
        "result_path": str(folder), "current_path": str(folder), "original_path": str(folder),
        "output_root": str(output), "export_id": "old-export", "directory_health": "healthy",
        "conversation_archives": [{"archive_id": archive_id, "conversation_id": "cid", "path": str(folder), "export_id": "old-export"}],
        "formats": ["html"], "warnings": [], "warning_details": [],
        "conversation_count": 1, "message_count": 2, "media_count": 0,
    }])
    item = service.list_operation_history()["items"][0]
    assert item["directory_health"] == "healthy" and item["superseded_count"] == 1
    monkeypatch.setattr(service, "_move_to_recycle_bin", lambda _path: (_ for _ in ()).throw(AssertionError("must not delete")))
    try:
        service.trash_export_result("old")
    except ChatWechatError as error:
        assert "后续导出更新" in str(error)
    else:
        raise AssertionError("superseded archive should not be trashed")
    assert folder.is_dir()


def test_raw_media_is_hidden_behind_diagnostics():
    from chatwechat.exporters import _attachment_html, _attachment_markdown
    from chatwechat.models import Attachment

    attachment = Attachment(
        attachment_id="raw-cache",
        category="emoji",
        exported_path="media/raw/cache.bin",
        status="unavailable",
        reason="本地缓存无法识别",
        reason_code="local_cache_unrecognized",
    )
    html = _attachment_html(attachment)
    markdown = "\n".join(_attachment_markdown(attachment))
    assert "查看保留的原始数据" not in html + markdown
    assert "诊断详情" in html + markdown
    assert "打开原始缓存文件" in html + markdown
