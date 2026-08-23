"""Compatibility entry point for existing source launchers."""

from .desktop.entrypoint import configure_logging, main, run_desktop, system_background

__all__ = ["configure_logging", "main", "run_desktop", "system_background"]


if __name__ == "__main__":
    raise SystemExit(main())
