import { create } from "zustand";
import { invoke } from "./bridge";
import type { Settings } from "./types";
import type { WorkbenchState } from "./state/model";
import { mergeExportDraft } from "./state/exportDraft";
import { createAccountSlice } from "./state/accountSlice";
import { createConversationSlice } from "./state/conversationSlice";
import { createOperationSlice } from "./state/operationSlice";

export const useWorkbench = create<WorkbenchState>((set, get, api) => ({
  initialized: false,
  contextVersion: 0,
  loading: true,
  conversationsLoading: false,
  previewLoading: false,
  olderLoading: false,
  view: "home",
  sidebarCollapsed:
    localStorage.getItem("chatwechat.sidebar-collapsed") === "true",
  accounts: [],
  dataRoots: [],
  conversations: [],
  totalConversations: 0,
  conversationResultTotal: 0,
  selected: [],
  selectedDetails: {},
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
  saveSettings: async (value) => {
    const version = get().contextVersion;
    const data = await invoke<{ settings: Settings }>("save_settings", value);
    if (get().contextVersion === version) set({ settings: data.settings });
  },
  ...createAccountSlice(set, get, api),
  ...createConversationSlice(set, get, api),
  ...createOperationSlice(set, get, api),
}));
