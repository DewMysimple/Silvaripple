"""Command dispatcher for the Tauri sidecar and source development entry."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from ..key_capture import authorization_helper
from ..redaction import RedactingFormatter
from ..sidecar import serve
from .diagnostics import self_test


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)


def _run_self_test(values: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    options = parser.parse_args(values)
    result = self_test()
    output = json.dumps(result, ensure_ascii=False, indent=None if options.json else 2)
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(output, encoding="utf-8")
    else:
        print(output)
    return 0 if result["ok"] else 1


def run_desktop() -> int:
    """Start the Tauri development shell from a source checkout."""
    if getattr(sys, "frozen", False):
        print("ChatWechat 后端只能由 Tauri 桌面应用启动。", file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parents[2]
    command = [
        "corepack",
        "pnpm@10.34.5",
        "--dir",
        str(root / "frontend"),
        "desktop:dev",
    ]
    return subprocess.call(command, cwd=root)


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    configure_logging()
    if values and values[0] == "--rpc":
        return serve()
    if values and values[0] == "--authorize-helper":
        return authorization_helper(values[1:])
    if values and values[0] == "--self-test":
        return _run_self_test(values[1:])
    if values:
        raise SystemExit(f"unknown ChatWechat argument: {values[0]}")
    return run_desktop()
