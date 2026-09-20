import { useEffect, useRef, useState } from "react";
import { invoke } from "../../bridge";
import { useWorkbench } from "../../store";
import { createExportDraft } from "../../state/exportDraft";
import type { ExportResult, MediaReport, Operation } from "../../types";
import { operationIsRunning } from "../../utils/labels";
import {
  createExportRequest,
  getExportBlockers,
  resolveSelectedConversations,
} from "./model";
import { useExportEstimate } from "./useExportEstimate";

const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

export function useExportWorkbench() {
  const workbench = useWorkbench();
  const {
    account,
    settings,
    selected,
    selectedDetails,
    contextVersion,
    exportDraft,
    operations,
    exportOperationId,
    mediaScanOperationId,
  } = workbench;
  const draft =
    exportDraft ?? (settings ? createExportDraft(settings) : undefined);
  const blockers = draft
    ? getExportBlockers(account, selected, draft)
    : ["正在载入导出设置"];
  const request =
    account && draft
      ? createExportRequest(
          account.account_id,
          selected,
          draft,
          settings?.export_folder_layout,
        )
      : undefined;
  const estimation = useExportEstimate(!blockers.length ? request : undefined);
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [starting, setStarting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const startingRef = useRef(false);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const operation = exportOperationId
    ? (operations[exportOperationId] as Operation<ExportResult> | undefined)
    : undefined;
  const mediaOperation = mediaScanOperationId
    ? (operations[mediaScanOperationId] as Operation<MediaReport> | undefined)
    : undefined;
  const running = operationIsRunning(operation?.status);

  const contextIsCurrent = () => {
    const current = useWorkbench.getState();
    return current.contextVersion === contextVersion;
  };
  const runAction = async (action: () => Promise<unknown>) => {
    setActionError("");
    setNotice("");
    try {
      await action();
    } catch (error) {
      if (mounted.current && contextIsCurrent())
        setActionError(errorMessage(error));
    }
  };
  const chooseOutput = () =>
    runAction(async () => {
      const data = await invoke<{ path?: string }>("choose_folder");
      if (data.path && contextIsCurrent())
        workbench.updateExportDraft({ output: data.path });
    });
  const openFolder = (path: string) =>
    runAction(() => invoke("open_result_folder", path));
  const copyPath = (path: string) =>
    runAction(async () => {
      await navigator.clipboard.writeText(path);
      if (mounted.current && contextIsCurrent()) setNotice("结果路径已复制");
    });
  const start = async () => {
    if (startingRef.current || running || blockers.length || !request) return;
    startingRef.current = true;
    setStarting(true);
    await runAction(async () => {
      const first = await invoke<Operation<ExportResult>>(
        "start_export",
        request,
      );
      if (!contextIsCurrent()) return;
      workbench.trackOperation(first);
      workbench.setExportOperationId(first.operation_id);
      const done = await workbench.pollOperation<ExportResult>(
        first.operation_id,
      );
      if (!contextIsCurrent()) return;
      await workbench.refreshHistory();
      if (!contextIsCurrent() || done.status !== "completed" || !done.result)
        return;
      if (done.result.warning_details.length)
        void workbench.startMediaScan(request.conversation_ids);
      if (settings?.open_result_folder_after_export && done.result.open_path) {
        try {
          await invoke("open_result_folder", done.result.open_path);
        } catch {
          if (mounted.current)
            setNotice("归档已完成，可使用“打开导出目录”查看结果。");
        }
      }
    });
    startingRef.current = false;
    if (mounted.current && contextIsCurrent()) setStarting(false);
  };
  const cancel = async () => {
    if (!operation || cancelling) return;
    setCancelling(true);
    await runAction(() => invoke("cancel_operation", operation.operation_id));
    if (mounted.current && contextIsCurrent()) setCancelling(false);
  };

  return {
    ...estimation,
    account,
    draft,
    settings,
    selected,
    blockers,
    operation,
    mediaOperation,
    running,
    starting,
    cancelling,
    actionError,
    notice,
    selectedRows: resolveSelectedConversations(selected, [
      ...workbench.conversations,
      ...Object.values(selectedDetails),
    ]),
    updateDraft: workbench.updateExportDraft,
    removeConversation: workbench.toggleSelected,
    clearSelected: workbench.clearSelected,
    addConversations: () => workbench.setView("conversations"),
    showMedia: () => workbench.setView("media"),
    resetResult: () => {
      workbench.setExportOperationId(undefined);
      setActionError("");
      setNotice("");
    },
    chooseOutput,
    openFolder,
    copyPath,
    start,
    cancel,
  };
}

export type ExportWorkbench = ReturnType<typeof useExportWorkbench>;
