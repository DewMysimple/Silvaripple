import { useEffect, useRef, useState } from "react";
import { useWorkbench } from "../../store";
import type { HistoryEntry } from "../../types";
import type { ConfirmRequest } from "../../ui/ConfirmDialog";
import {
  defaultFilters,
  filterHistory,
  isAbnormal,
  isRunning,
  selectableHistoryIds,
  type HistoryFilters,
} from "./historyModel";
import { taskApi } from "./taskApi";

export function useTaskHistory() {
  const history = useWorkbench((state) => state.history);
  const operations = useWorkbench((state) => state.operations);
  const account = useWorkbench((state) => state.account);
  const version = useWorkbench((state) => state.contextVersion);
  const [filters, setFilters] = useState(defaultFilters);
  const [selection, setSelection] = useState<string[]>([]);
  const [confirmation, setConfirmation] = useState<ConfirmRequest>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const locked = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const isCurrent = () =>
    mounted.current && useWorkbench.getState().contextVersion === version;
  const filtered = filterHistory(history, filters);
  const selected = selectableHistoryIds(filtered, selection);
  const active = Object.values(operations).filter(
    (item) =>
      isRunning(item.status) &&
      (!item.account_id || item.account_id === account?.account_id),
  );
  const terminal = history.filter((item) => !isRunning(item.status));
  const abnormal = terminal.filter(isAbnormal).length;

  async function reload() {
    if (!account || !isCurrent()) return;
    const data = await taskApi.list(account.account_id);
    if (isCurrent()) useWorkbench.setState({ history: data.items });
  }

  async function perform(action: () => Promise<unknown>, propagate = false) {
    if (locked.current || !isCurrent()) return;
    locked.current = true;
    setBusy(true);
    setError(undefined);
    try {
      await action();
    } catch (cause) {
      if (isCurrent()) {
        if (propagate) throw cause;
        setError(cause instanceof Error ? cause.message : String(cause));
      }
    } finally {
      locked.current = false;
      if (isCurrent()) setBusy(false);
    }
  }

  const confirmMutation = (action: () => Promise<unknown>) => () =>
    perform(async () => {
      await action();
      if (!isCurrent()) return;
      setSelection([]);
      try {
        await reload();
      } catch {
        if (isCurrent())
          setError(
            "操作已完成，但记录刷新失败。请点击“刷新状态”查看最新结果。",
          );
      }
    }, true);

  function askRemove(ids: string[]) {
    const safeIds = selectableHistoryIds(history, ids);
    if (!safeIds.length) return;
    setConfirmation({
      title: safeIds.length === 1 ? "删除这条任务记录？" : "删除所选任务记录？",
      description: "记录将从任务历史中移除，磁盘上的导出归档会保留。",
      count: safeIds.length,
      confirmLabel: "删除记录",
      onConfirm: confirmMutation(() => taskApi.remove(safeIds)),
    });
  }

  function askClear(mode: "all" | "abnormal") {
    const count = mode === "all" ? terminal.length : abnormal;
    if (!count || !account) return;
    setConfirmation({
      title: mode === "all" ? "清空全部任务记录？" : "清空异常任务记录？",
      description:
        mode === "all"
          ? "移除当前账号所有已结束的导出、统计和媒体扫描记录。"
          : "只移除失败、意外中断，以及目录缺失、不完整或无法访问的记录。",
      count,
      confirmLabel: mode === "all" ? "清空全部记录" : "清空异常记录",
      onConfirm: confirmMutation(() => taskApi.clear(mode, account.account_id)),
    });
  }

  function askTrash(item: HistoryEntry) {
    const shared = item.storage_mode === "shared";
    const count = item.conversation_archives?.length ?? item.conversation_count;
    setConfirmation({
      title: shared ? "将本次会话归档移入回收站？" : "将导出归档移入回收站？",
      description: shared
        ? `将检查本次涉及的 ${count} 个会话目录，只回收仍属于这次导出的版本。`
        : "移动经过验证的导出目录，保留任务记录并标记为已回收。",
      confirmLabel: "移入回收站",
      notes: [
        shared
          ? "被后续导出覆盖的会话会自动跳过，不会删除当前版本。"
          : "导出目录会进入 Windows 回收站，可从系统回收站恢复。",
        "输出根目录、微信源数据和其他会话不会受到影响。",
      ],
      onConfirm: confirmMutation(() => taskApi.trash(item.history_id)),
    });
  }

  return {
    history,
    active,
    terminalCount: terminal.length,
    abnormal,
    filtered,
    selected,
    filters,
    busy,
    error,
    confirmation,
    closeConfirmation: () => setConfirmation(undefined),
    clearError: () => setError(undefined),
    updateFilters: (next: Partial<HistoryFilters>) => {
      setFilters((value) => ({ ...value, ...next }));
      setSelection([]);
    },
    toggleSelected: (id: string) =>
      setSelection((rows) =>
        rows.includes(id)
          ? rows.filter((value) => value !== id)
          : [...rows, id],
      ),
    selectVisible: (checked: boolean) =>
      setSelection(
        checked
          ? filtered
              .filter((item) => !isRunning(item.status))
              .map((item) => item.history_id)
          : [],
      ),
    refresh: () => perform(reload),
    cancel: (id: string) =>
      perform(async () => {
        await taskApi.cancel(id);
        await reload();
      }),
    open: (item: HistoryEntry) =>
      perform(async () => {
        if (item.current_path) await taskApi.open(item.current_path);
      }),
    relink: (item: HistoryEntry) =>
      perform(async () => {
        const folder = await taskApi.chooseFolder();
        if (!folder.path || !isCurrent()) return;
        await taskApi.relink(item.history_id, folder.path);
        await reload();
      }),
    askRemove,
    askClear,
    askTrash,
  };
}
