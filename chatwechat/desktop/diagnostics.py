"""Non-interactive checks used by source and packaged builds."""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any

from .. import __version__
from ..crypto import WindowsCngAes
from ..infrastructure.runtime import RuntimeLocator
from ..keystore import protect, unprotect


def _webview2_available() -> bool:
    if os.name != "nt":
        return False
    roots = [
        Path(os.environ.get("PROGRAMFILES(X86)", "")),
        Path(os.environ.get("PROGRAMFILES", "")),
        Path(os.environ.get("LOCALAPPDATA", "")),
    ]
    candidates = [
        root / "Microsoft" / "EdgeWebView" / "Application"
        for root in roots
        if str(root)
    ]
    return any(path.is_dir() and any(path.iterdir()) for path in candidates)


def self_test(locator: RuntimeLocator | None = None) -> dict[str, Any]:
    locator = locator or RuntimeLocator.current()
    node = locator.tool("node")
    ffmpeg = locator.tool("ffmpeg")
    try:
        WindowsCngAes()
        cng = True
    except (OSError, RuntimeError):
        cng = False
    try:
        probe = b"ChatWechat self-test"
        dpapi = unprotect(protect(probe)) == probe
    except (OSError, RuntimeError):
        dpapi = False
    checks = {
        "web_assets": locator.web_index().is_file(),
        "silk_wasm": locator.vendor_file("silk-wasm", "silk.wasm").is_file(),
        "node": bool(node),
        "ffmpeg": bool(ffmpeg),
        "windows": os.name == "nt",
        "webview2": _webview2_available(),
        "cng": cng,
        "dpapi": dpapi,
    }
    required = ("web_assets", "silk_wasm", "node", "ffmpeg", "windows", "webview2", "cng", "dpapi")
    return {
        "ok": all(checks[name] for name in required),
        "version": __version__,
        "frozen": locator.frozen,
        "platform": platform.platform(),
        "checks": checks,
    }
