"""Compatibility entry point for the Tauri development launcher."""

from .desktop.entrypoint import configure_logging, main, run_desktop

__all__ = ["configure_logging", "main", "run_desktop"]


if __name__ == "__main__":
    raise SystemExit(main())
