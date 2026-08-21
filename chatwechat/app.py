from __future__ import annotations

import logging
import winreg
from pathlib import Path

import webview

from .redaction import RedactingFormatter
from .service import Bridge, ChatWechatService


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


def main() -> None:
    configure_logging()
    service = ChatWechatService()
    bridge = Bridge(service)
    page = Path(__file__).parent / "web" / "index.html"
    window = webview.create_window(
        "ChatWechat 本地微信导出",
        page.as_uri(),
        js_api=bridge,
        width=1440,
        height=900,
        min_size=(1080, 700),
        background_color=system_background(),
    )
    window.events.closed += service.close
    webview.start(debug=False, private_mode=True)


if __name__ == "__main__":
    main()
