import type {
  Account,
  AccountStatisticsReport,
  Conversation,
  DataRootCandidate,
  ExportDraft,
  HistoryEntry,
  MediaReport,
  Message,
  Operation,
  Settings,
  ViewId,
} from "../types";
import type { StateCreator } from "zustand";

export interface WorkbenchState {
  initialized: boolean;
  contextVersion: number;
  loading: boolean;
  conversationsLoading: boolean;
  previewLoading: boolean;
  olderLoading: boolean;
  error?: string;
  view: ViewId;
  sidebarCollapsed: boolean;
  settings?: Settings;
  accounts: Account[];
  dataRoots: DataRootCandidate[];
  account?: Account;
  conversations: Conversation[];
  totalConversations: number;
  conversationResultTotal: number;
  selected: string[];
  selectedDetails: Record<string, Conversation>;
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
  refreshDataRoots(): Promise<void>;
  selectDataRoot(path: string): Promise<void>;
  useAutoDataRoot(): Promise<void>;
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

export type Slice<K extends keyof WorkbenchState> = StateCreator<
  WorkbenchState,
  [],
  [],
  Pick<WorkbenchState, K>
>;

export function reportError(
  set: (value: Partial<WorkbenchState>) => void,
  error: unknown,
) {
  set({
    loading: false,
    error: error instanceof Error ? error.message : String(error),
  });
}
