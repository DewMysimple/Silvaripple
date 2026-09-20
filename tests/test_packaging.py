from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

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


def test_tauri_build_is_portable_with_shared_resource_mapping():
    config = json.loads((ROOT / "frontend" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    bundle = json.loads((ROOT / "frontend" / "src-tauri" / "tauri.bundle.conf.json").read_text(encoding="utf-8"))
    rust_host = (ROOT / "frontend" / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")

    package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))

    assert config["bundle"]["active"] is False
    assert "--no-bundle" in package["scripts"]["desktop:build"]
    assert bundle["bundle"]["externalBin"] == ["binaries/chatwechat-backend"]
    assert bundle["bundle"]["resources"]["resources/runtime/"] == "runtime/"
    assert config["mainBinaryName"] == "ChatWechat"
    assert "let working_directory = resource_dir.clone()" in rust_host
    assert ".current_dir(working_directory)" in rust_host


def test_portable_build_verifies_the_extracted_archive():
    source = (ROOT / "scripts" / "Build-Portable.ps1").read_text(encoding="utf-8")
    common = (ROOT / "scripts" / "Delivery.Common.ps1").read_text(encoding="utf-8")

    assert "Build-TauriSidecar.ps1" in source
    assert "desktop:build" in source
    assert "ZipFile]::ExtractToDirectory" in source
    assert "Invoke-PortableSelfTest $expandedApp" in source
    assert 'Environment["PATH"] = "$env:SystemRoot\\System32;$env:SystemRoot"' in common
    assert 'Environment["LOCALAPPDATA"]' in common
    assert '"CHATWECHAT_RESOURCE_DIR"' in common
    assert "$info.Environment.Remove($name)" in common


def test_release_workflow_is_tag_only_and_version_source_is_unique():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert 'tags:' in workflow and '"v*.*.*"' in workflow
    assert "branches:" not in workflow
    assert "gh release create" in workflow
    assert "Build-Portable.ps1" in workflow
    assert "windows-x64.zip" in workflow
    assert "setup.exe" not in workflow
    assert "git archive" not in workflow
    assert "source.zip" not in workflow
    assert project["project"]["version"] == "0.2.0"


def test_local_publish_delivers_one_archive_and_its_extraction():
    source = (ROOT / "scripts" / "Publish-Local.ps1").read_text(encoding="utf-8")

    assert 'Join-Path $root "dist"' in source
    assert "GetFolderPath(\"Desktop\")" not in source
    assert "Publish-DeliveryDirectory" in source
    assert "ZipFile]::ExtractToDirectory($archive, $candidate)" in source
    assert "status --porcelain" in source
    assert "ChatWechat.zip" in source
    assert "ChatWechat\\ChatWechat.exe" in source
    assert 'Join-Path $root "artifacts"' not in source
    assert "installer" not in source
    assert "source.zip" not in source


def test_powershell_release_scripts_are_windows_powershell_safe_ascii():
    for name in ("Build-Portable.ps1", "Delivery.Common.ps1", "Build-TauriSidecar.ps1", "Invoke-QualityGate.ps1", "Publish-Local.ps1"):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert source.isascii(), f"{name} must remain ASCII for Windows PowerShell 5"


def test_quality_gate_checks_python_react_and_tauri():
    source = (ROOT / "scripts" / "Invoke-QualityGate.ps1").read_text(encoding="utf-8")

    assert "python -m pytest" in source
    assert "pnpm@10.34.5 --dir frontend test" in source
    assert "cargo test --manifest-path frontend/src-tauri/Cargo.toml" in source


def test_source_tree_has_no_root_pyw_launcher():
    assert not (ROOT / "启动ChatWechat.pyw").exists()


def run_delivery_helper(tmp_path: Path, script: str) -> subprocess.CompletedProcess[str]:
    powershell = shutil.which("powershell.exe")
    if not powershell:
        pytest.skip("Windows PowerShell is required for delivery script checks")
    # Let Windows PowerShell locate its own modules when pytest runs under pwsh 7.
    environment = {key: value for key, value in os.environ.items() if key.upper() != "PSMODULEPATH"}
    environment["DELIVERY_TEST_ROOT"] = str(tmp_path)
    return subprocess.run(
        [powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
         "$ErrorActionPreference = 'Stop'; . ./scripts/Delivery.Common.ps1; " + script],
        cwd=ROOT,
        env=environment,
        capture_output=True, text=True, timeout=30,
    )


def test_package_manifest_survives_zip_roundtrip_and_detects_tampering(tmp_path):
    app = tmp_path / "ChatWechat"
    app.mkdir()
    (app / "ChatWechat.exe").write_bytes(b"synthetic desktop")
    runtime = app / "runtime" / "node"
    runtime.mkdir(parents=True)
    (runtime / "node.exe").write_bytes(b"synthetic runtime")
    result = run_delivery_helper(tmp_path, """
        $app = Join-Path $env:DELIVERY_TEST_ROOT 'ChatWechat'
        Write-PackageManifest $app 'test-version' 'test-commit'
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = Join-Path $env:DELIVERY_TEST_ROOT 'ChatWechat.zip'
        $expanded = Join-Path $env:DELIVERY_TEST_ROOT 'expanded'
        [IO.Compression.ZipFile]::CreateFromDirectory($app, $zip, [IO.Compression.CompressionLevel]::Optimal, $true)
        [IO.Compression.ZipFile]::ExtractToDirectory($zip, $expanded)
        Assert-PackageManifest (Join-Path $expanded 'ChatWechat')
    """)
    assert result.returncode == 0, result.stderr
    extracted = tmp_path / "expanded" / "ChatWechat"
    assert (extracted / "runtime" / "node" / "node.exe").read_bytes() == b"synthetic runtime"
    manifest = json.loads((extracted / "build-info.json").read_text(encoding="utf-8-sig"))
    assert manifest["version"] == "test-version"
    assert manifest["commit"] == "test-commit"
    assert {file["path"] for file in manifest["files"]} == {"ChatWechat.exe", "runtime/node/node.exe"}
    (extracted / "runtime" / "node" / "node.exe").write_bytes(b"tampered runtime")
    failed = run_delivery_helper(tmp_path, "Assert-PackageManifest (Join-Path $env:DELIVERY_TEST_ROOT 'expanded/ChatWechat')")
    assert failed.returncode != 0
    assert "Package integrity check failed" in failed.stderr


def test_tauri_resource_mapping_preserves_relative_runtime_layout(tmp_path):
    tauri = tmp_path / "source" / "frontend" / "src-tauri"
    runtime = tauri / "resources" / "runtime" / "node"
    runtime.mkdir(parents=True)
    (runtime / "node.exe").write_bytes(b"synthetic runtime")
    (tmp_path / "source" / "THIRD_PARTY_NOTICES.md").write_text("notices", encoding="utf-8")
    shutil.copyfile(ROOT / "frontend" / "src-tauri" / "tauri.bundle.conf.json", tauri / "tauri.bundle.conf.json")
    result = run_delivery_helper(tmp_path, "Copy-TauriResources (Join-Path $env:DELIVERY_TEST_ROOT 'source/frontend/src-tauri') (Join-Path $env:DELIVERY_TEST_ROOT 'ChatWechat')")
    assert result.returncode == 0, result.stderr
    app = tmp_path / "ChatWechat"
    assert (app / "runtime" / "node" / "node.exe").read_bytes() == b"synthetic runtime"
    assert (app / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8") == "notices"
    assert not (app / "runtime" / "runtime").exists()


@pytest.mark.parametrize("operation", ["missing", "extra", "traversal"])
def test_package_manifest_rejects_incomplete_or_unexpected_content(tmp_path, operation):
    app = tmp_path / "ChatWechat"
    app.mkdir()
    executable = app / "ChatWechat.exe"
    executable.write_bytes(b"synthetic desktop")
    initial = run_delivery_helper(tmp_path, "Write-PackageManifest (Join-Path $env:DELIVERY_TEST_ROOT 'ChatWechat') 'test' 'commit'")
    assert initial.returncode == 0, initial.stderr
    if operation == "missing":
        executable.unlink()
    elif operation == "extra":
        (app / "unexpected.exe").write_bytes(b"extra")
    else:
        manifest_path = app / "build-info.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        manifest["files"][0]["path"] = "../outside.exe"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = run_delivery_helper(tmp_path, "Assert-PackageManifest (Join-Path $env:DELIVERY_TEST_ROOT 'ChatWechat')")
    assert result.returncode != 0


@pytest.mark.parametrize("fail_verification", [False, True])
def test_delivery_replaces_archive_and_app_together_or_rolls_back(tmp_path, fail_verification):
    for name, contents in (("candidate", b"new"), ("dist", b"old")):
        directory = tmp_path / name
        (directory / "ChatWechat").mkdir(parents=True)
        (directory / "ChatWechat.zip").write_bytes(contents)
        (directory / "ChatWechat" / "ChatWechat.exe").write_bytes(contents)
    prepared = run_delivery_helper(tmp_path, "Write-PackageManifest (Join-Path $env:DELIVERY_TEST_ROOT 'dist/ChatWechat') 'old-version' 'old-commit'")
    assert prepared.returncode == 0, prepared.stderr
    # Known application files may be damaged; replacement must not require their old hash.
    (tmp_path / "dist" / "ChatWechat" / "ChatWechat.exe").write_bytes(b"repaired-old")
    verify = "throw 'synthetic verification failure'" if fail_verification else "param($published); if (-not (Test-Path (Join-Path $published 'ChatWechat/ChatWechat.exe'))) { throw 'missing app' }"
    result = run_delivery_helper(tmp_path, "Publish-DeliveryDirectory (Join-Path $env:DELIVERY_TEST_ROOT 'candidate') (Join-Path $env:DELIVERY_TEST_ROOT 'dist') { " + verify + " }")
    assert (result.returncode != 0) == fail_verification, result.stderr
    expected = b"old" if fail_verification else b"new"
    assert (tmp_path / "dist" / "ChatWechat.zip").read_bytes() == expected
    expected_app = b"repaired-old" if fail_verification else b"new"
    assert (tmp_path / "dist" / "ChatWechat" / "ChatWechat.exe").read_bytes() == expected_app
    assert not list(tmp_path.glob(".dist.backup-*"))


def test_delivery_refuses_to_overwrite_unrecognized_user_files(tmp_path):
    (tmp_path / "candidate").mkdir()
    destination = tmp_path / "dist"
    destination.mkdir()
    (destination / "user-notes.txt").write_text("preserve", encoding="utf-8")
    result = run_delivery_helper(tmp_path, "Publish-DeliveryDirectory (Join-Path $env:DELIVERY_TEST_ROOT 'candidate') (Join-Path $env:DELIVERY_TEST_ROOT 'dist') {}")
    assert result.returncode != 0
    assert (destination / "user-notes.txt").read_text(encoding="utf-8") == "preserve"


@pytest.mark.parametrize("extra", ["notes.txt", "exports/chat-a/chat.html", "runtime/node/empty-user-directory/"])
def test_delivery_preserves_extra_files_and_empty_directories_inside_old_application(tmp_path, extra):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    app = tmp_path / "dist" / "ChatWechat"
    runtime = app / "runtime" / "node"
    runtime.mkdir(parents=True)
    (app / "ChatWechat.exe").write_bytes(b"old")
    (runtime / "node.exe").write_bytes(b"runtime")
    (tmp_path / "dist" / "ChatWechat.zip").write_bytes(b"old-zip")
    prepared = run_delivery_helper(tmp_path, "Write-PackageManifest (Join-Path $env:DELIVERY_TEST_ROOT 'dist/ChatWechat') 'old-version' 'old-commit'")
    assert prepared.returncode == 0, prepared.stderr
    extra_path = app / extra
    if extra.endswith("/"):
        extra_path.mkdir(parents=True)
    else:
        extra_path.parent.mkdir(parents=True, exist_ok=True)
        extra_path.write_bytes(b"user data")
    result = run_delivery_helper(tmp_path, "Publish-DeliveryDirectory (Join-Path $env:DELIVERY_TEST_ROOT 'candidate') (Join-Path $env:DELIVERY_TEST_ROOT 'dist') {}")
    assert result.returncode != 0
    assert "unrecognized file or directory" in result.stderr
    assert extra_path.exists()
    if extra_path.is_file():
        assert extra_path.read_bytes() == b"user data"
    assert (app / "ChatWechat.exe").read_bytes() == b"old"
    assert (tmp_path / "dist" / "ChatWechat.zip").read_bytes() == b"old-zip"
    assert candidate.exists()
    assert not list(tmp_path.glob(".dist.backup-*"))


@pytest.mark.parametrize("manifest", [None, "not JSON", '{"files": []}'])
def test_delivery_preserves_old_application_without_recognizable_manifest(tmp_path, manifest):
    (tmp_path / "candidate").mkdir()
    app = tmp_path / "dist" / "ChatWechat"
    app.mkdir(parents=True)
    (app / "ChatWechat.exe").write_bytes(b"old")
    if manifest is not None:
        (app / "build-info.json").write_text(manifest, encoding="utf-8")
    result = run_delivery_helper(tmp_path, "Publish-DeliveryDirectory (Join-Path $env:DELIVERY_TEST_ROOT 'candidate') (Join-Path $env:DELIVERY_TEST_ROOT 'dist') {}")
    assert result.returncode != 0
    assert (app / "ChatWechat.exe").read_bytes() == b"old"
    assert (tmp_path / "candidate").exists()
    assert not list(tmp_path.glob(".dist.backup-*"))


def test_isolated_process_strips_development_environment_and_drains_both_pipes(tmp_path):
    result = run_delivery_helper(tmp_path, r'''
        $env:PYTHONPATH = 'development-only'
        $env:CHATWECHAT_RESOURCE_DIR = 'development-only'
        $executable = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $arguments = '-NoLogo -NoProfile -NonInteractive -Command "[Console]::Write($env:PATH + ''|'' + $env:PYTHONPATH + ''|'' + $env:CHATWECHAT_RESOURCE_DIR); [Console]::Error.Write(''x'' * 131072)"'
        $result = Invoke-IsolatedProcess $executable $arguments $env:DELIVERY_TEST_ROOT 5000
        @{ output = $result.stdout; error_length = $result.stderr.Length } | ConvertTo-Json
    ''')
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    system_root = os.environ["SystemRoot"]
    assert report["output"] == f"{system_root}\\System32;{system_root}||"
    assert report["error_length"] == 131072


def test_isolated_process_reports_nonzero_exit_instead_of_accepting_existing_file(tmp_path):
    result = run_delivery_helper(tmp_path, r'''
        Invoke-IsolatedProcess (Join-Path $env:SystemRoot 'System32\cmd.exe') '/D /C exit 17' $env:DELIVERY_TEST_ROOT 5000
    ''')
    assert result.returncode != 0
    assert "exit code 17" in result.stderr


def test_isolated_process_times_out_and_stops_the_owned_process(tmp_path):
    result = run_delivery_helper(tmp_path, r'''
        $executable = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        Invoke-IsolatedProcess $executable '-NoLogo -NoProfile -NonInteractive -Command "Start-Sleep -Seconds 30"' $env:DELIVERY_TEST_ROOT 200
    ''')
    assert result.returncode != 0
    assert "Portable component timed out" in result.stderr
