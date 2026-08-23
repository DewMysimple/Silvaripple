from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_pyinstaller_spec_is_internal_windowed_staging():
    source = (ROOT / "packaging" / "ChatWechat.spec").read_text(encoding="utf-8")

    assert "SPECPATH" in source
    assert "console=False" in source
    assert "ChatWechat.ico" in source
    assert "chatwechat" in source and "frozen_entry.py" in source
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


def test_installer_lock_and_nsis_script_are_pinned():
    lock = json.loads((ROOT / "packaging" / "installer.lock.json").read_text(encoding="utf-8"))
    script = (ROOT / "packaging" / "ChatWechat.nsi").read_text(encoding="utf-8")

    assert lock["schema_version"] == 1
    assert lock["nsis"]["version"] == "3.11"
    assert lock["nsis"]["source"].startswith("https://")
    assert re.fullmatch(r"[0-9a-f]{64}", lock["nsis"]["sha256"])
    assert "RequestExecutionLevel user" in script
    assert "ICON_FILE" in script
    assert "InstallDir \"$LOCALAPPDATA\\Programs\\ChatWechat\"" in script
    assert "ChatWechat-portable-backup-" in script
    assert "SKIP_LEGACY_MIGRATION" in script


def test_installer_build_uses_staging_and_isolated_install_test():
    source = (ROOT / "scripts" / "Build-Installer.ps1").read_text(encoding="utf-8")

    assert "Build-AppStaging.ps1" in source
    assert "Invoke-Nsis" in source
    assert "isolated-install" in source
    assert "Uninstall.exe" in source


def test_release_workflow_is_tag_only_and_version_source_is_unique():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert 'tags:' in workflow and '"v*.*.*"' in workflow
    assert "branches:" not in workflow
    assert "gh release create" in workflow
    assert "Build-Installer.ps1" in workflow
    assert "windows-x64-setup.exe" in workflow
    assert "windows-portable.zip" not in workflow
    assert project["project"]["version"] == "0.2.0"


def test_local_publish_uses_external_atomic_targets():
    source = (ROOT / "scripts" / "Publish-Local.ps1").read_text(encoding="utf-8")

    assert "artifacts\\发布版本" in source
    assert "GetFolderPath(\"Desktop\")" not in source
    assert "Replace-FileAtomically" in source
    assert "git -C $root archive" in source
    assert "status --porcelain" in source
    assert 'Join-Path $legacyBuildRoot "portable"' in source
    assert "ChatWechat-Setup.exe" in source
    assert "artifact_root" in source


def test_source_tree_has_no_root_pyw_launcher():
    assert not (ROOT / "启动ChatWechat.pyw").exists()
