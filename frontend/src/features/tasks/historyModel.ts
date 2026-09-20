import type { HistoryEntry } from "../../types";

export const taskKinds = [
  { value: "export", label: "聊天导出" },
  { value: "media_scan", label: "媒体扫描" },
  { value: "account_statistics", label: "会话统计" },
];
export const taskStatuses = [
  { value: "completed", label: "已完成" },
  { value: "failed", label: "失败" },
  { value: "cancelled", label: "已取消" },
  { value: "interrupted", label: "意外中断" },
];
export const directoryStatuses = [
  { value: "healthy", label: "目录正常" },
  { value: "moved", label: "目录已移动" },
  { value: "missing", label: "目录缺失" },
  { value: "incomplete", label: "归档不完整" },
  { value: "inaccessible", label: "无法访问" },
  { value: "trashed", label: "已移入回收站" },
  { value: "not_applicable", label: "无需目录" },
];
export type HistoryFilters = { kind: string; status: string; health: string };
export const defaultFilters: HistoryFilters = {
  kind: "all",
  status: "all",
  health: "all",
};

export const isRunning = (status: string) =>
  status === "pending" || status === "running";
export const isAbnormal = (item: HistoryEntry) =>
  ["failed", "interrupted"].includes(item.status) ||
  ["missing", "incomplete", "inaccessible"].includes(item.directory_health);
export const taskKindLabel = (kind: string) =>
  taskKinds.find((item) => item.value === kind)?.label ||
  (kind === "search" ? "聊天搜索" : kind);
export const taskStatusLabel = (status: string) =>
  taskStatuses.find((item) => item.value === status)?.label ||
  (status === "pending" ? "等待中" : status === "running" ? "运行中" : status);
export const directoryLabel = (item: HistoryEntry) =>
  item.superseded_count
    ? "已有更新版本"
    : directoryStatuses.find((status) => status.value === item.directory_health)
        ?.label || item.directory_health;
export const statusTone = (
  status: string,
): "success" | "warning" | "neutral" =>
  status === "completed"
    ? "success"
    : ["failed", "interrupted"].includes(status)
      ? "warning"
      : "neutral";

export function filterHistory(
  history: HistoryEntry[],
  filters: HistoryFilters,
) {
  return history.filter(
    (item) =>
      (filters.kind === "all" || item.kind === filters.kind) &&
      (filters.status === "all" || item.status === filters.status) &&
      (filters.health === "all" || item.directory_health === filters.health),
  );
}

export function selectableHistoryIds(
  history: HistoryEntry[],
  selected: string[],
) {
  const available = new Set(
    history
      .filter((item) => !isRunning(item.status))
      .map((item) => item.history_id),
  );
  return selected.filter((id) => available.has(id));
}

export function historyActions(item: HistoryEntry) {
  const isExport = item.kind === "export";
  const directoryAvailable = ["healthy", "moved"].includes(
    item.directory_health,
  );
  const archiveCount = item.conversation_archives?.length ?? 0;
  const allSuperseded =
    item.storage_mode === "shared" &&
    archiveCount > 0 &&
    item.superseded_count === archiveCount;
  return {
    canOpen: isExport && directoryAvailable && Boolean(item.current_path),
    canRelink:
      isExport &&
      item.directory_health !== "trashed" &&
      !isRunning(item.status),
    needsRelink:
      isExport &&
      ["missing", "incomplete", "inaccessible"].includes(item.directory_health),
    canTrash:
      isExport &&
      directoryAvailable &&
      !allSuperseded &&
      !isRunning(item.status),
    canRemove: !isRunning(item.status),
  };
}

export function historySummary(item: HistoryEntry) {
  if (item.kind === "media_scan")
    return `${item.media_count.toLocaleString()} 个媒体引用 · 可恢复 ${String(item.result_summary?.recoverable ?? 0)}`;
  const summary = `${item.conversation_count.toLocaleString()} 个会话 · ${item.message_count.toLocaleString()} 条消息`;
  return item.kind === "export"
    ? `${summary} · ${item.media_count.toLocaleString()} 个媒体`
    : summary;
}
