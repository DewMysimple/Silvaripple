import { create } from "zustand";
import { invoke } from "./bridge";
import type {
  Account,
  AccountStatisticsReport,
  Bootstrap,
  Conversation,
  ExportDraft,
  HistoryEntry,
  MediaReport,
  Message,
  Operation,
  Settings,
  ViewId,
} from "./types";
import { createExportDraft, mergeExportDraft } from "./state/exportDraft";
import { ensureId, mergeIds, toggleId } from "./state/selection";

interface WorkbenchState {
  initialized: boolean;
  loading: boolean;
  error?: string;
  view: ViewId;
  sidebarCollapsed: boolean;
  settings?: Settings;
  accounts: Account[];
  account?: Account;
  conversations: Conversation[];
  totalConversations: number;
  selected: string[];
  activeConversation?: Conversation;
  preview: Message[];
  previewTotal: number;
  previewOffset: number;
  operations: Record<string, Operation>;
  history: HistoryEntry[];
  accountStatistics?: AccountStatisticsReport;
  accountStatisticsOperationId?: string;
  exportDraft?: ExportDraft;
  exportOperationId?: string;
  mediaScanOperationId?: string;
  mediaScanConversationIds: string[];
  setView(view: ViewId): void;
  toggleSidebar(): void;
  clearError(): void;
  initialize(): Promise<void>;
  selectAccount(account: Account): Promise<void>;
  loadConversations(options?: Record<string, unknown>): Promise<void>;
  toggleSelected(id: string): void;
  ensureSelected(id: string): void;
  selectVisible(): void;
  clearSelected(): void;
  openConversation(conversation: Conversation): Promise<void>;
  loadOlder(): Promise<void>;
  trackOperation(operation: Operation): void;
  pollOperation<T>(operationId: string): Promise<Operation<T>>;
  refreshHistory(): Promise<void>;
  refreshAccountStatistics(): Promise<void>;
  startAccountStatisticsScan(): Promise<
    Operation<AccountStatisticsReport> | undefined
  >;
  saveSettings(value: Partial<Settings>): Promise<void>;
  updateExportDraft(value: Partial<ExportDraft>): void;
  resetExportDraft(): void;
  setExportOperationId(operationId?: string): void;
  startMediaScan(
    conversationIds?: string[],
  ): Promise<Operation<MediaReport> | undefined>;
}

const fail = (set: (value: Partial<WorkbenchState>) => void, error: unknown) =>
  set({
    loading: false,
    error: error instanceof Error ? error.message : String(error),
  });
let conversationRequest = 0;
let previewRequest = 0;

export const useWorkbench = create<WorkbenchState>((set, get) => ({
  initialized: false,
  loading: true,
  view: "home",
  sidebarCollapsed:
    localStorage.getItem("chatwechat.sidebar-collapsed") === "true",
  accounts: [],
  conversations: [],
  totalConversations: 0,
  selected: [],
  preview: [],
  previewTotal: 0,
  previewOffset: 0,
  operations: {},
  history: [],
  mediaScanConversationIds: [],
  setView: (view) => set({ view }),
  toggleSidebar: () =>
    set((state) => {
      const sidebarCollapsed = !state.sidebarCollapsed;
      localStorage.setItem(
        "chatwechat.sidebar-collapsed",
        String(sidebarCollapsed),
      );
      return { sidebarCollapsed };
    }),
  clearError: () => set({ error: undefined }),
  updateExportDraft: (value) =>
    set((state) => ({
      exportDraft: mergeExportDraft(state.exportDraft, value),
    })),
  resetExportDraft: () => set({ exportDraft: undefined }),
  setExportOperationId: (exportOperationId) => set({ exportOperationId }),
  initialize: async () => {
    set({ loading: true, error: undefined });
    try {
      const data = await invoke<Bootstrap>("bootstrap");
      const account =
        data.accounts.find(
          (item) => item.account_id === data.selected_account_id,
        ) ?? data.accounts[0];
      set((state) => ({
        initialized: true,
        loading: false,
        settings: data.settings,
        accounts: data.accounts,
        account,
        exportDraft: state.exportDraft ?? createExportDraft(data.settings),
      }));
      if (account?.coverage.covered) await get().loadConversations();
      await Promise.all([
        get().refreshHistory(),
        get().refreshAccountStatistics(),
      ]);
    } catch (error) {
      fail(set, error);
    }
  },
  selectAccount: async (account) => {
    set({
      account,
      conversations: [],
      activeConversation: undefined,
      preview: [],
      selected: [],
      loading: true,
      exportOperationId: undefined,
      mediaScanOperationId: undefined,
      mediaScanConversationIds: [],
      accountStatistics: undefined,
      accountStatisticsOperationId: undefined,
    });
    try {
      await invoke("save_settings", { last_account_id: account.account_id });
      await get().loadConversations();
      await get().refreshAccountStatistics();
    } catch (error) {
      fail(set, error);
    }
  },
  loadConversations: async (options = {}) => {
    const account = get().account;
    if (!account) return;
    const request = ++conversationRequest;
    set({ loading: true });
    try {
      const data = await invoke<{ items: Conversation[]; total: number }>(
        "list_conversations",
        account.account_id,
        { page: 1, page_size: 200, exclude_kinds: ["official"], ...options },
      );
      if (
        request !== conversationRequest ||
        get().account?.account_id !== account.account_id
      )
        return;
      set({
        conversations: data.items,
        totalConversations: data.total,
        loading: false,
      });
    } catch (error) {
      if (request === conversationRequest) fail(set, error);
    }
  },
  toggleSelected: (id) =>
    set((state) => ({
      selected: toggleId(state.selected, id),
    })),
  ensureSelected: (id) =>
    set((state) => ({
      selected: ensureId(state.selected, id),
    })),
  selectVisible: () =>
    set((state) => ({
      selected: mergeIds(
        state.selected,
        state.conversations.map((item) => item.conversation_id),
      ),
    })),
  clearSelected: () => set({ selected: [] }),
  openConversation: async (conversation) => {
    const account = get().account;
    if (!account) return;
    const request = ++previewRequest;
    set({
      activeConversation: conversation,
      preview: [],
      previewOffset: 0,
      loading: true,
    });
    try {
      const data = await invoke<{
        items: Message[];
        total: number;
        offset: number;
      }>("preview_messages", account.account_id, conversation.conversation_id, {
        limit: 100,
        offset: 0,
      });
      if (
        request !== previewRequest ||
        get().activeConversation?.conversation_id !==
          conversation.conversation_id
      )
        return;
      set({
        preview: data.items,
        previewTotal: data.total,
        previewOffset: data.items.length,
        loading: false,
      });
    } catch (error) {
      if (request === previewRequest) fail(set, error);
    }
  },
  loadOlder: async () => {
    const { account, activeConversation, previewOffset, preview } = get();
    if (!account || !activeConversation) return;
    try {
      const data = await invoke<{ items: Message[] }>(
        "preview_messages",
        account.account_id,
        activeConversation.conversation_id,
        { limit: 100, offset: previewOffset },
      );
      if (
        get().activeConversation?.conversation_id !==
        activeConversation.conversation_id
      )
        return;
      set({
        preview: [...data.items, ...preview],
        previewOffset: previewOffset + data.items.length,
      });
    } catch (error) {
      fail(set, error);
    }
  },
  trackOperation: (operation) =>
    set((state) => ({
      operations: { ...state.operations, [operation.operation_id]: operation },
    })),
  pollOperation: async <T>(operationId: string) => {
    for (;;) {
      const operation = await invoke<Operation<T>>(
        "get_operation",
        operationId,
      );
      get().trackOperation(operation);
      if (["completed", "failed", "cancelled"].includes(operation.status))
        return operation;
      await new Promise((resolve) => setTimeout(resolve, 450));
    }
  },
  startMediaScan: async (conversationIds) => {
    const account = get().account;
    if (!account) return undefined;
    try {
      const scope = Array.from(new Set(conversationIds ?? get().selected));
      const first = await invoke<Operation<MediaReport>>(
        "start_media_scan",
        account.account_id,
        { conversation_ids: scope, detailed: true, limit: 500 },
      );
      get().trackOperation(first);
      set({
        mediaScanOperationId: first.operation_id,
        mediaScanConversationIds: scope,
      });
      return get().pollOperation<MediaReport>(first.operation_id);
    } catch (error) {
      fail(set, error);
      return undefined;
    }
  },
  refreshHistory: async () => {
    try {
      const data = await invoke<{ items: HistoryEntry[] }>(
        "list_operation_history",
      );
      set({ history: data.items });
    } catch {
      /* optional */
    }
  },
  refreshAccountStatistics: async () => {
    const account = get().account;
    if (!account) return;
    try {
      const data = await invoke<{ report?: AccountStatisticsReport }>(
        "get_account_statistics",
        account.account_id,
      );
      set({ accountStatistics: data.report });
    } catch {
      /* optional */
    }
  },
  startAccountStatisticsScan: async () => {
    const account = get().account;
    if (!account) return undefined;
    try {
      const first = await invoke<Operation<AccountStatisticsReport>>(
        "start_account_statistics_scan",
        account.account_id,
      );
      get().trackOperation(first);
      set({ accountStatisticsOperationId: first.operation_id });
      const done = await get().pollOperation<AccountStatisticsReport>(
        first.operation_id,
      );
      if (done.status === "completed" && done.result)
        set({ accountStatistics: done.result });
      await get().refreshHistory();
      return done;
    } catch (error) {
      fail(set, error);
      return undefined;
    }
  },
  saveSettings: async (value) => {
    const data = await invoke<{ settings: Settings }>("save_settings", value);
    set({ settings: data.settings });
  },
}));
