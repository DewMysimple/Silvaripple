"""Typed pywebview adapter around the application service facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..redaction import redact


class Bridge:
    def __init__(self, service: Any):
        self.service = service

    @staticmethod
    def _safe(call: Any) -> dict[str, Any]:
        try:
            return {"ok": True, "data": call()}
        except Exception as error:
            return {"ok": False, "error": redact(error), "code": type(error).__name__}

    def bootstrap(self) -> dict[str, Any]:
        return self._safe(self.service.bootstrap)

    def scan_accounts(self) -> dict[str, Any]:
        return self._safe(self.service.scan_accounts)

    def authorize_account(self, account_id: str) -> dict[str, Any]:
        return self._safe(lambda: self.service.authorize_account(account_id))

    def list_conversations(self, account_id: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._safe(lambda: self.service.list_conversations(account_id, options))

    def preview_messages(self, account_id: str, conversation_id: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._safe(lambda: self.service.preview_messages(account_id, conversation_id, options))

    def estimate_export(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._safe(lambda: self.service.estimate_export(payload))

    def start_export(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._safe(lambda: self.service.start_export(payload))

    def cancel_operation(self, operation_id: str) -> dict[str, Any]:
        return self._safe(lambda: self.service.cancel_operation(operation_id))

    def get_operation(self, operation_id: str) -> dict[str, Any]:
        return self._safe(lambda: self.service.get_operation(operation_id))

    def search_messages(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._safe(lambda: self.service.search_messages(payload))

    def start_media_scan(self, account_id: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._safe(lambda: self.service.start_media_scan(account_id, options))

    def get_media_report(self, operation_id: str) -> dict[str, Any]:
        return self._safe(lambda: self.service.get_media_report(operation_id))

    def start_account_statistics_scan(self, account_id: str) -> dict[str, Any]:
        return self._safe(lambda: self.service.start_account_statistics_scan(account_id))

    def get_account_statistics(self, account_id: str) -> dict[str, Any]:
        return self._safe(lambda: self.service.get_account_statistics(account_id))

    def list_operation_history(self) -> dict[str, Any]:
        return self._safe(self.service.list_operation_history)

    def clear_operation_history(self) -> dict[str, Any]:
        return self._safe(self.service.clear_operation_history)

    def clear_abnormal_operation_history(self) -> dict[str, Any]:
        return self._safe(self.service.clear_abnormal_operation_history)

    def delete_operation_history_entry(self, history_id: str) -> dict[str, Any]:
        return self._safe(lambda: self.service.delete_operation_history_entry(history_id))

    def delete_operation_history_entries(self, history_ids: list[str]) -> dict[str, Any]:
        return self._safe(lambda: self.service.delete_operation_history_entries(history_ids))

    def relink_operation_history_entry(self, history_id: str, path: str) -> dict[str, Any]:
        return self._safe(lambda: self.service.relink_operation_history_entry(history_id, path))

    def trash_export_result(self, history_id: str) -> dict[str, Any]:
        return self._safe(lambda: self.service.trash_export_result(history_id))

    def list_export_presets(self) -> dict[str, Any]:
        return self._safe(self.service.list_export_presets)

    def save_export_preset(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._safe(lambda: self.service.save_export_preset(payload))

    def delete_export_preset(self, preset_id: str) -> dict[str, Any]:
        return self._safe(lambda: self.service.delete_export_preset(preset_id))

    def open_result_folder(self, value: str) -> dict[str, Any]:
        return self._safe(lambda: self.service.open_result_folder(value))

    def choose_folder(self) -> dict[str, Any]:
        def choose() -> dict[str, Any]:
            import webview

            result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
            path = str(result[0]) if result else None
            if path:
                self.service.approved_output_dirs.add(str(Path(path).resolve()))
            return {"path": path}

        return self._safe(choose)

    def save_settings(self, value: dict[str, Any]) -> dict[str, Any]:
        return self._safe(lambda: self.service.save_settings(value))
