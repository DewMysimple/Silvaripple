from __future__ import annotations

from pathlib import Path


def test_version_comes_from_project_metadata():
    from chatwechat import __version__

    assert __version__ == "0.2.0"


def test_runtime_locator_prefers_bundled_tools(tmp_path):
    from chatwechat.infrastructure.runtime import RuntimeLocator

    package = tmp_path / "bundle" / "chatwechat"
    (package / "web").mkdir(parents=True)
    (package / "vendor" / "silk-wasm").mkdir(parents=True)
    (tmp_path / "runtime" / "node").mkdir(parents=True)
    (tmp_path / "runtime" / "ffmpeg").mkdir(parents=True)
    (tmp_path / "runtime" / "node" / "node.exe").write_bytes(b"node")
    (tmp_path / "runtime" / "ffmpeg" / "ffmpeg.exe").write_bytes(b"ffmpeg")
    locator = RuntimeLocator(tmp_path, tmp_path / "bundle", package)

    assert Path(locator.tool("node") or "").name == "node.exe"
    assert Path(locator.tool("ffmpeg") or "").name == "ffmpeg.exe"
    assert locator.runtime_environment("ffmpeg")["PATH"].split(";")[0].endswith("runtime\\ffmpeg")


def test_desktop_entrypoint_dispatches_authorization_helper(monkeypatch):
    import chatwechat.desktop.entrypoint as entrypoint

    captured: list[str] = []
    monkeypatch.setattr(entrypoint, "authorization_helper", lambda values: captured.extend(values) or 7)

    code = entrypoint.main(["--authorize-helper", "--account", "account", "--result", "result.json"])

    assert code == 7
    assert captured == ["--account", "account", "--result", "result.json"]


def test_elevated_command_uses_frozen_executable_arguments(monkeypatch, tmp_path):
    import chatwechat.key_capture as capture

    executable = tmp_path / "ChatWechat.exe"
    monkeypatch.setattr(capture.sys, "executable", str(executable))
    monkeypatch.setattr(capture.sys, "frozen", True, raising=False)

    command, arguments, working = capture.elevated_command(tmp_path / "account", tmp_path / "result.json")

    assert command == str(executable)
    assert arguments[0] == "--authorize-helper"
    assert "-m" not in arguments
    assert working == tmp_path


def test_service_bridge_compatibility_alias():
    from chatwechat.desktop.bridge import Bridge as DesktopBridge
    from chatwechat.service import Bridge

    assert Bridge is DesktopBridge
