"""Resolve the application version from the single project source of truth."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _source_version() -> str:
    try:
        import tomllib

        project = Path(__file__).resolve().parents[1] / "pyproject.toml"
        if project.is_file():
            value = tomllib.loads(project.read_text(encoding="utf-8"))
            return str(value["project"]["version"])
    except (KeyError, OSError, ValueError):
        pass
    return "0.0.0"


try:
    __version__ = version("chatwechat")
except PackageNotFoundError:
    __version__ = _source_version()
