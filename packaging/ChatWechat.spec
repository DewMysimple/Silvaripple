# -*- mode: python ; coding: utf-8 -*-
"""One-file Python backend sidecar embedded by the Tauri desktop bundle."""

import os
from pathlib import Path


ROOT = Path(SPECPATH).resolve().parent
datas = [
    (str(ROOT / "chatwechat" / "vendor"), "chatwechat/vendor"),
    (str(ROOT / "pyproject.toml"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
]

analysis = Analysis(
    [str(ROOT / "chatwechat" / "desktop" / "frozen_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["webview"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name=os.environ.get("CHATWECHAT_BACKEND_NAME", "chatwechat-backend"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=os.environ.get("CHATWECHAT_VERSION_FILE") or None,
)
