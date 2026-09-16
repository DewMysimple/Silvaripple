"""PyInstaller entry point for the ChatWechat backend sidecar."""

from chatwechat.desktop.entrypoint import main


if __name__ == "__main__":
    raise SystemExit(main())
