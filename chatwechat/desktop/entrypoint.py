"""Single command dispatcher for source and frozen desktop execution."""

from __future__ import annotations

import argparse
import ctypes
import json
import logging
import sys
import winreg
from pathlib import Path
from typing import Sequence

import webview

from ..application import ChatWechatService
from ..key_capture import authorization_helper
from ..redaction import RedactingFormatter
from ..infrastructure.runtime import RuntimeLocator
from .bridge import Bridge
from .diagnostics import self_test, webview2_available


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)


def system_background() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "#FFFFFF" if int(value) else "#191919"
    except (OSError, ValueError, TypeError):
        return "#FFFFFF"


def _attach_parent_console() -> None:
    """Make JSON diagnostics visible when the windowed EXE is called by a shell."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    try:
        if ctypes.windll.kernel32.AttachConsole(-1):
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
            sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
    except OSError:
        pass


def _show_startup_error(message: str) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, "ChatWechat 无法启动", 0x10)
    else:
        print(message, file=sys.stderr)


def run_desktop() -> int:
    configure_logging()
    if not webview2_available():
        _show_startup_error(
            "未检测到 Microsoft Edge WebView2 Runtime。\n\n"
            "请先安装 WebView2 Runtime，再重新启动 ChatWechat。"
        )
        return 2
    service = ChatWechatService()
    locator = RuntimeLocator.current()
    page = locator.web_index()
    if not page.is_file():
        raise FileNotFoundError(f"ChatWechat web assets are missing: {page}")
    window = webview.create_window(
        "ChatWechat 本地微信导出",
        page.as_uri(),
        js_api=Bridge(service),
        width=1440,
        height=900,
        min_size=(1080, 700),
        background_color=system_background(),
    )
    window.events.closed += service.close
    webview.start(debug=False, private_mode=True)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if values and values[0] == "--authorize-helper":
        return authorization_helper(values[1:])
    if values and values[0] == "--self-test":
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--output", type=Path)
        options = parser.parse_args(values[1:])
        if not options.output:
            _attach_parent_console()
        result = self_test()
        output = json.dumps(result, ensure_ascii=False, indent=None if options.json else 2)
        if options.output:
            options.output.parent.mkdir(parents=True, exist_ok=True)
            options.output.write_text(output, encoding="utf-8")
        else:
            print(output)
        return 0 if result["ok"] else 1
    if values:
        raise SystemExit(f"unknown ChatWechat argument: {values[0]}")
    return run_desktop()
