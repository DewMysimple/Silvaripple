from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_pyinstaller_spec_builds_console_sidecar_without_webview():
    source = (ROOT / "packaging" / "ChatWechat.spec").read_text(encoding="utf-8")

    assert "SPECPATH" in source
    assert "console=True" in source
    assert "chatwechat-backend" in source
    assert "chatwechat" in source and "frozen_entry.py" in source
    assert 'excludes=["webview"]' in source
    assert "启动ChatWechat.pyw" not in source
    assert "runtime.lock.json" not in source
    assert not re.search(r"[A-Za-z]:[/\\]Users[/\\]", source)


def test_runtime_lock_has_versioned_sha256_files():
    lock = json.loads((ROOT / "packaging" / "runtime.lock.json").read_text(encoding="utf-8"))

    assert lock["schema_version"] == 1
    assert lock["node"]["version"] == "24.16.0"
    assert lock["ffmpeg"]["version_prefix"].startswith("ffmpeg version ")
    for component in (lock["node"], lock["ffmpeg"]):
        assert component["source"].startswith("https://")
        assert component["files"]
        for item in component["files"]:
            assert item["size"] > 0
            assert re.fullmatch(r"[0-9a-f]{64}", item["sha256"])


def test_tauri_bundle_uses_current_user_nsis_and_external_backend():
    config = json.loads((ROOT / "frontend" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    bundle = json.loads((ROOT / "frontend" / "src-tauri" / "tauri.bundle.conf.json").read_text(encoding="utf-8"))
    rust_host = (ROOT / "frontend" / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")

    assert config["bundle"]["targets"] == ["nsis"]
    assert config["bundle"]["windows"]["nsis"]["installMode"] == "currentUser"
    assert bundle["bundle"]["externalBin"] == ["binaries/chatwechat-backend"]
    assert bundle["bundle"]["resources"]["resources/runtime/"] == "runtime/"
    assert config["mainBinaryName"] == "ChatWechat"
    assert "let working_directory = resource_dir.clone()" in rust_host
    assert ".current_dir(working_directory)" in rust_host


def test_installer_build_uses_tauri_and_verified_sidecar():
    source = (ROOT / "scripts" / "Build-Installer.ps1").read_text(encoding="utf-8")

    assert "Build-TauriSidecar.ps1" in source
    assert "desktop:build" in source
    assert "backend-self-test.json" in source
    assert "isolated-install" in source and "installed-backend-self-test.json" in source
    assert "CHATWECHAT_RESOURCE_DIR" in source


def test_release_workflow_is_tag_only_and_version_source_is_unique():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert 'tags:' in workflow and '"v*.*.*"' in workflow
    assert "branches:" not in workflow
    assert "gh release create" in workflow
    assert "Build-Installer.ps1" in workflow
    assert "windows-x64-setup.exe" in workflow
    assert "windows-portable.zip" not in workflow
    assert "git archive" not in workflow
    assert "source.zip" not in workflow
    assert project["project"]["version"] == "0.2.0"


def test_local_publish_uses_in_repo_atomic_targets_without_source_archive():
    source = (ROOT / "scripts" / "Publish-Local.ps1").read_text(encoding="utf-8")

    assert "artifacts\\发布版本" in source
    assert "artifacts\\安装版\\ChatWechat" in source
    assert "GetFolderPath(\"Desktop\")" not in source
    assert "Replace-FileAtomically" in source
    assert "test_installer" in source
    assert "chatwechat-backend.exe" in source
    assert "status --porcelain" in source
    assert 'Join-Path $legacyBuildRoot "portable"' in source
    assert "ChatWechat-Setup.exe" in source
    assert "artifact_root" in source
    assert "ChatWechat-source.zip" in source
    assert "Source archive" not in source
    assert "source_zip" not in source


def test_quality_gate_checks_python_react_and_tauri():
    source = (ROOT / "scripts" / "Invoke-QualityGate.ps1").read_text(encoding="utf-8")

    assert "python -m pytest" in source
    assert "pnpm@10.34.5 --dir frontend test" in source
    assert "cargo test --manifest-path frontend/src-tauri/Cargo.toml" in source


def test_source_tree_has_no_root_pyw_launcher():
    assert not (ROOT / "启动ChatWechat.pyw").exists()
