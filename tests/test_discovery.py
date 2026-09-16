from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace


def _account(root: Path, name: str = "wxid_example") -> Path:
    account = root / name
    database = account / "db_storage" / "message" / "message_0.db"
    database.parent.mkdir(parents=True)
    database.write_bytes(b"x" * 4096)
    return account


def test_normalize_data_root_accepts_common_selection_levels(tmp_path):
    from chatwechat.discovery import normalize_data_root

    root = tmp_path / "Documents" / "xwechat_files"
    account = _account(root)

    assert normalize_data_root(account) == root.resolve()
    assert normalize_data_root(root) == root.resolve()
    assert normalize_data_root(root.parent) == root.resolve()
    assert normalize_data_root(tmp_path / "missing") is None


def test_discover_data_roots_deduplicates_and_reports_accounts(tmp_path, monkeypatch):
    from chatwechat import discovery

    root = tmp_path / "xwechat_files"
    _account(root, "wxid_first")
    _account(root, "wxid_second")
    monkeypatch.setattr(
        discovery,
        "_candidate_paths",
        lambda saved=None: [(root, "saved"), (root.parent, "documents")],
    )

    candidates = discovery.discover_data_roots(root)

    assert len(candidates) == 1
    assert candidates[0].path == root.resolve()
    assert candidates[0].account_count == 2
    assert candidates[0].to_dict(root)["selected"] is True


def test_registry_discovery_uses_only_path_like_values(tmp_path, monkeypatch):
    from chatwechat import discovery

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    values = [("FileSavePath", str(tmp_path), 1), ("Theme", "dark", 1)]

    def enum_value(_key, index):
        if index >= len(values):
            raise OSError
        return values[index]

    monkeypatch.setattr(
        discovery,
        "winreg",
        SimpleNamespace(
            HKEY_CURRENT_USER=object(),
            OpenKey=lambda *_args: Key(),
            EnumValue=enum_value,
        ),
    )

    assert discovery._registry_data_root_hints() == [tmp_path]


def test_sidecar_protocol_keeps_one_stateful_service(monkeypatch):
    import chatwechat.sidecar as sidecar

    class Service:
        def __init__(self):
            self.count = 0
            self.closed = False

        def scan_accounts(self):
            self.count += 1
            return {"count": self.count}

        def close(self):
            self.closed = True

    created: list[Service] = []

    def create_service():
        value = Service()
        created.append(value)
        return value

    monkeypatch.setattr(sidecar, "ChatWechatService", create_service)
    requests = b"".join(
        json.dumps(value).encode("utf-8") + b"\n"
        for value in (
            {"id": 1, "method": "scan_accounts", "args": []},
            {"id": 2, "method": "scan_accounts", "args": []},
            {"id": 3, "method": "shutdown", "args": []},
        )
    )
    output = io.BytesIO()

    assert sidecar.serve(io.BytesIO(requests), output) == 0
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert responses[0]["result"]["data"]["count"] == 1
    assert responses[1]["result"]["data"]["count"] == 2
    assert responses[2]["result"]["ok"] is True
    assert len(created) == 1 and created[0].closed is True


def test_auto_root_switch_closes_repositories(tmp_path, monkeypatch):
    from chatwechat.config import Settings
    from chatwechat.discovery import DataRootCandidate
    from chatwechat.service import ChatWechatService

    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    old_root.mkdir()
    _account(new_root)

    class Repository:
        closed = False

        def close(self):
            self.closed = True

    repository = Repository()
    service = object.__new__(ChatWechatService)
    service.settings = Settings(data_root=str(old_root), data_root_mode="auto")
    service.repositories = {"account": repository}
    service.settings_store = SimpleNamespace(save=lambda _settings: None)
    monkeypatch.setattr(
        "chatwechat.service.discover_data_roots",
        lambda _saved: [DataRootCandidate(new_root, "documents", 1)],
    )

    service._apply_auto_data_root()

    assert service.settings.data_root == str(new_root)
    assert repository.closed is True
    assert service.repositories == {}
