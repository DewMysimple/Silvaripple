from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_pyinstaller_spec_is_portable_and_windowed():
    source = (ROOT / "packaging" / "ChatWechat.spec").read_text(encoding="utf-8")

    assert "SPECPATH" in source
    assert "console=False" in source
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


def test_release_workflow_is_tag_only_and_version_source_is_unique():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert 'tags:' in workflow and '"v*.*.*"' in workflow
    assert "branches:" not in workflow
    assert "gh release create" in workflow
    assert project["project"]["version"] == "0.2.0"


def test_local_publish_uses_external_atomic_targets():
    source = (ROOT / "scripts" / "Publish-Local.ps1").read_text(encoding="utf-8")

    assert "GetFolderPath(\"Desktop\")" in source
    assert "Publish-CoreOutputsAtomically" in source
    assert "fileBackup" in source and "directoryBackup" in source
    assert "git -C $root archive" in source
    assert "status --porcelain" in source
    assert 'Join-Path $legacyBuildRoot "portable"' in source
