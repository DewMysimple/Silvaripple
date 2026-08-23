# -*- mode: python ; coding: utf-8 -*-
"""Relative-path PyInstaller definition for the internal installer staging tree."""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


ROOT = Path(SPECPATH).resolve().parent
datas = [
    (str(ROOT / "chatwechat" / "web"), "chatwechat/web"),
    (str(ROOT / "chatwechat" / "vendor"), "chatwechat/vendor"),
    (str(ROOT / "pyproject.toml"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
]
binaries = []
hiddenimports = ["webview.platforms.edgechromium", "webview.platforms.winforms"]
webview_datas, webview_binaries, webview_hidden = collect_all("webview")
datas += webview_datas
binaries += webview_binaries
hiddenimports += webview_hidden

analysis = Analysis(
    [str(ROOT / "启动ChatWechat.pyw")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="ChatWechat",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "packaging" / "ChatWechat.ico"),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=os.environ.get("CHATWECHAT_VERSION_FILE") or None,
)

collect = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ChatWechat",
)
