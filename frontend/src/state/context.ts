import type { WorkbenchState } from "./model";

// One reset boundary for every account-owned field. No messages or selections
// survive a different account or a successfully changed data root.
export const resetAccountContext = (contextVersion: number) =>
  ({
    contextVersion,
    conversations: [],
    totalConversations: 0,
    conversationResultTotal: 0,
    conversationsLoading: false,
    previewLoading: false,
    olderLoading: false,
    selected: [],
    selectedDetails: {},
    activeConversation: undefined,
    preview: [],
    previewTotal: 0,
    previewOffset: 0,
    operations: {},
    history: [],
    accountStatistics: undefined,
    accountStatisticsOperationId: undefined,
    exportOperationId: undefined,
    mediaScanOperationId: undefined,
    mediaScanConversationIds: [],
  }) satisfies Partial<WorkbenchState>;
