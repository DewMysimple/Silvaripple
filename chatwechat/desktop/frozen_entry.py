"""PyInstaller entry point for the windowed ChatWechat executable."""

from chatwechat.desktop.entrypoint import main


if __name__ == "__main__":
    raise SystemExit(main())
