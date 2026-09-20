import { invoke } from "../../bridge";
import type { HistoryEntry } from "../../types";

export const taskApi = {
  list: (accountId: string) =>
    invoke<{ items: HistoryEntry[] }>("list_operation_history", accountId),
  remove: (ids: string[]) => invoke("delete_operation_history_entries", ids),
  clear: (mode: "all" | "abnormal", accountId: string) =>
    invoke(
      mode === "all"
        ? "clear_operation_history"
        : "clear_abnormal_operation_history",
      accountId,
    ),
  chooseFolder: () => invoke<{ path?: string }>("choose_folder"),
  relink: (historyId: string, path: string) =>
    invoke("relink_operation_history_entry", historyId, path),
  trash: (historyId: string) => invoke("trash_export_result", historyId),
  open: (path: string) => invoke("open_result_folder", path),
  cancel: (operationId: string) => invoke("cancel_operation", operationId),
};
