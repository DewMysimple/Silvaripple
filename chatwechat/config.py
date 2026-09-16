from __future__ import annotations

import json
import os
import tempfile
import ctypes
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "ChatWechat"


def windows_documents_directory() -> Path:
    """Resolve the real Windows Documents known folder without assuming C:\\Users."""
    if os.name == "nt":
        # FOLDERID_Documents.  SHGetKnownFolderPath follows OneDrive and other
        # shell-folder redirections, unlike ``Path.home() / 'Documents'``.
        class GUID(ctypes.Structure):
            _fields_ = [
                ("data1", ctypes.c_uint32),
                ("data2", ctypes.c_uint16),
                ("data3", ctypes.c_uint16),
                ("data4", ctypes.c_ubyte * 8),
            ]

        folder_id = uuid.UUID("fdd39ad0-238f-46af-adb4-6c85480369c7")
        guid = GUID.from_buffer_copy(folder_id.bytes_le)
        value = ctypes.c_wchar_p()
        try:
            function = ctypes.windll.shell32.SHGetKnownFolderPath  # type: ignore[attr-defined]
            function.argtypes = [
                ctypes.POINTER(GUID),
                ctypes.c_uint32,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_wchar_p),
            ]
            function.restype = ctypes.c_long
            result = function(
                ctypes.byref(guid), 0, None, ctypes.byref(value)
            )
            if result == 0 and value.value:
                return Path(value.value)
        except (AttributeError, OSError, ValueError):
            pass
        finally:
            if value.value:
                try:
                    free = ctypes.windll.ole32.CoTaskMemFree  # type: ignore[attr-defined]
                    free.argtypes = [ctypes.c_void_p]
                    free(value)
                except (AttributeError, OSError):
                    pass
    return Path.home() / "Documents"


def default_data_root() -> str:
    """Return a conventional per-user WeChat 4.x data location.

    The actual data folder can be moved in WeChat, so this is deliberately a
    runtime hint only.  It keeps a portable build free of the builder's local
    drive and username while still providing a sensible first location on a
    new computer.
    """
    documents = windows_documents_directory()
    candidates = (
        documents / "xwechat_files",
        documents / "WeChat Files" / "xwechat_files",
        documents / "WeChat Files",
    )
    return str(next((item for item in candidates if item.is_dir()), candidates[0]))


@dataclass(slots=True)
class Settings:
    data_root: str = field(default_factory=default_data_root)
    data_root_mode: str = "auto"
    output_directory: str = str(Path.home() / "Desktop")
    theme: str = "system"
    conversation_kind: str = "all"
    last_account_id: str = ""
    font_scale: str = "standard"
    density: str = "comfortable"
    download_missing_media_default: bool = True
    allow_legacy_http_media_default: bool = True
    visual_download_limit_mib: int = 50
    audio_download_limit_mib: int = 100
    large_download_limit_mib: int = 500
    open_result_folder_after_export: bool = False
    export_folder_layout: str = "by_type"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Settings":
        allowed = {field for field in cls.__dataclass_fields__}
        cleaned = {key: val for key, val in value.items() if key in allowed}
        if cleaned.get("theme") not in {"system", "light", "dark"}:
            cleaned["theme"] = "system"
        if cleaned.get("font_scale") not in {"small", "standard", "large"}:
            cleaned["font_scale"] = "standard"
        if cleaned.get("density") not in {"compact", "comfortable"}:
            cleaned["density"] = "comfortable"
        if cleaned.get("export_folder_layout") not in {"flat", "by_type", "account_by_type"}:
            cleaned["export_folder_layout"] = "by_type"
        if cleaned.get("data_root_mode") not in {"auto", "manual"}:
            cleaned["data_root_mode"] = "auto"
        for key, default in (
            ("download_missing_media_default", True),
            ("allow_legacy_http_media_default", True),
            ("open_result_folder_after_export", False),
        ):
            value = cleaned.get(key, default)
            if isinstance(value, str):
                cleaned[key] = value.strip().casefold() not in {"", "0", "false", "no", "off"}
            else:
                cleaned[key] = bool(value)
        for key, default in (
            ("visual_download_limit_mib", 50),
            ("audio_download_limit_mib", 100),
            ("large_download_limit_mib", 500),
        ):
            try:
                cleaned[key] = min(2048, max(1, int(cleaned.get(key, default))))
            except (TypeError, ValueError):
                cleaned[key] = default
        return cls(**cleaned)


class SettingsStore:
    def __init__(self, app_dir: Path = APP_DIR):
        self.app_dir = app_dir
        self.path = app_dir / "settings.json"

    def load(self) -> Settings:
        try:
            return Settings.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
        except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
            return Settings()

    def save(self, settings: Settings) -> None:
        self.app_dir.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix="settings-", suffix=".tmp", dir=self.app_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(asdict(settings), stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.path)
        finally:
            Path(temp_name).unlink(missing_ok=True)


def temp_root(app_dir: Path = APP_DIR) -> Path:
    return app_dir / "temp"
