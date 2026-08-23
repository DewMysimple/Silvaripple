"""Locate application resources consistently in source and PyInstaller builds."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RuntimeLocator:
    """Resolve packaged resources without leaking builder-specific paths."""

    executable_dir: Path
    bundle_dir: Path
    package_dir: Path

    @classmethod
    def current(cls) -> "RuntimeLocator":
        package_dir = Path(__file__).resolve().parents[1]
        if getattr(sys, "frozen", False):
            executable_dir = Path(sys.executable).resolve().parent
            bundle_dir = Path(getattr(sys, "_MEIPASS", executable_dir)).resolve()
            packaged = bundle_dir / "chatwechat"
            if packaged.is_dir():
                package_dir = packaged
        else:
            executable_dir = package_dir.parent
            bundle_dir = executable_dir
        return cls(executable_dir, bundle_dir, package_dir)

    @property
    def frozen(self) -> bool:
        return bool(getattr(sys, "frozen", False))

    def web_index(self) -> Path:
        return self.package_dir / "web" / "index.html"

    def vendor_file(self, *parts: str) -> Path:
        return self.package_dir.joinpath("vendor", *parts)

    def bundled_tool(self, name: str) -> Path | None:
        executable = f"{name}.exe" if os.name == "nt" and not name.casefold().endswith(".exe") else name
        candidates = (
            self.executable_dir / "runtime" / name / executable,
            self.executable_dir / "runtime" / executable,
            self.bundle_dir / "runtime" / name / executable,
            self.bundle_dir / "runtime" / executable,
        )
        return next((path for path in candidates if path.is_file()), None)

    def tool(self, name: str) -> str | None:
        bundled = self.bundled_tool(name)
        return str(bundled) if bundled else shutil.which(name)

    def runtime_environment(self, name: str) -> dict[str, str]:
        """Return a minimal environment that makes bundled shared DLLs visible."""
        environment = os.environ.copy()
        bundled = self.bundled_tool(name)
        if bundled:
            current = environment.get("PATH", "")
            environment["PATH"] = f"{bundled.parent}{os.pathsep}{current}" if current else str(bundled.parent)
        return environment
