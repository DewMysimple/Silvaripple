import { invoke } from "../bridge";
import type { Slice } from "./model";
import { reportError } from "./model";
import type {
  AccountStatisticsReport,
  HistoryEntry,
  MediaReport,
  Operation,
} from "../types";

export const createOperationSlice: Slice<
  | "trackOperation"
  | "pollOperation"
  | "startMediaScan"
  | "refreshHistory"
  | "refreshAccountStatistics"
  | "startAccountStatisticsScan"
> = (set, get) => ({
  trackOperation: (operation) =>
    set((state) =>
      operation.account_id && operation.account_id !== state.account?.account_id
        ? state
        : {
            operations: {
              ...state.operations,
              [operation.operation_id]: operation,
            },
          },
    ),
  pollOperation: async <T>(operationId: string) => {
    const version = get().contextVersion;
    for (;;) {
      const operation = await invoke<Operation<T>>(
        "get_operation",
        operationId,
      );
      if (get().contextVersion !== version)
        return { ...operation, status: "cancelled", result: undefined };
      get().trackOperation(operation);
      if (["completed", "failed", "cancelled"].includes(operation.status))
        return operation;
      await new Promise((resolve) => setTimeout(resolve, 450));
    }
  },
  startMediaScan: async (conversationIds) => {
    const version = get().contextVersion;
    const account = get().account;
    if (!account) return undefined;
    try {
      const scope = Array.from(new Set(conversationIds ?? get().selected));
      const first = await invoke<Operation<MediaReport>>(
        "start_media_scan",
        account.account_id,
        { conversation_ids: scope, detailed: true, limit: 500 },
      );
      if (get().contextVersion !== version) return undefined;
      get().trackOperation(first);
      set({
        mediaScanOperationId: first.operation_id,
        mediaScanConversationIds: scope,
      });
      const done = await get().pollOperation<MediaReport>(first.operation_id);
      if (get().contextVersion === version) await get().refreshHistory();
      return done;
    } catch (error) {
      if (get().contextVersion === version) reportError(set, error);
      return undefined;
    }
  },
  refreshHistory: async () => {
    const version = get().contextVersion;
    const account = get().account;
    if (!account) {
      set({ history: [] });
      return;
    }
    try {
      const data = await invoke<{ items: HistoryEntry[] }>(
        "list_operation_history",
        account.account_id,
      );
      if (get().contextVersion === version) set({ history: data.items });
    } catch {
      /* optional */
    }
  },
  refreshAccountStatistics: async () => {
    const version = get().contextVersion;
    const account = get().account;
    if (!account) return;
    try {
      const data = await invoke<{ report?: AccountStatisticsReport }>(
        "get_account_statistics",
        account.account_id,
      );
      if (get().contextVersion === version)
        set({ accountStatistics: data.report });
    } catch {
      /* optional */
    }
  },
  startAccountStatisticsScan: async () => {
    const version = get().contextVersion;
    const account = get().account;
    if (!account) return undefined;
    try {
      const first = await invoke<Operation<AccountStatisticsReport>>(
        "start_account_statistics_scan",
        account.account_id,
      );
      if (get().contextVersion !== version) return undefined;
      get().trackOperation(first);
      set({ accountStatisticsOperationId: first.operation_id });
      const done = await get().pollOperation<AccountStatisticsReport>(
        first.operation_id,
      );
      if (
        done.status === "completed" &&
        done.result &&
        get().contextVersion === version
      )
        set({ accountStatistics: done.result });
      if (get().contextVersion === version) await get().refreshHistory();
      return done;
    } catch (error) {
      if (get().contextVersion === version) reportError(set, error);
      return undefined;
    }
  },
});
