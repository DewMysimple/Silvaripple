import { invoke } from "../bridge";
import type { Slice } from "./model";
import { reportError } from "./model";
import type { Conversation, Message } from "../types";
import { ensureId, mergeIds, toggleId } from "./selection";

export const createConversationSlice: Slice<
  | "loadConversations"
  | "toggleSelected"
  | "ensureSelected"
  | "selectVisible"
  | "clearSelected"
  | "openConversation"
  | "loadOlder"
> = (set, get) => {
  let conversationRequest = 0;
  let previewRequest = 0;
  return {
    loadConversations: async (options = {}) => {
      const version = get().contextVersion;
      const account = get().account;
      if (!account) return;
      const request = ++conversationRequest;
      set({ conversationsLoading: true });
      try {
        const data = await invoke<{ items: Conversation[]; total: number }>(
          "list_conversations",
          account.account_id,
          { page: 1, page_size: 200, exclude_kinds: ["official"], ...options },
        );
        if (
          request !== conversationRequest ||
          get().contextVersion !== version ||
          get().account?.account_id !== account.account_id
        )
          return;
        set({
          conversations:
            Number(options.page || 1) > 1
              ? [
                  ...get().conversations,
                  ...data.items.filter(
                    (item) =>
                      !get().conversations.some(
                        (existing) =>
                          existing.conversation_id === item.conversation_id,
                      ),
                  ),
                ]
              : data.items,
          conversationResultTotal: data.total,
          ...(!options.query && (!options.kind || options.kind === "all")
            ? { totalConversations: data.total }
            : {}),
          conversationsLoading: false,
          loading: false,
        });
      } catch (error) {
        if (
          request === conversationRequest &&
          get().contextVersion === version
        ) {
          set({ conversationsLoading: false });
          reportError(set, error);
        }
      }
    },
    toggleSelected: (id) =>
      set((state) => {
        const selected = toggleId(state.selected, id);
        const selectedDetails = { ...state.selectedDetails };
        const item =
          state.conversations.find((row) => row.conversation_id === id) ??
          (state.activeConversation?.conversation_id === id
            ? state.activeConversation
            : undefined);
        if (!selected.includes(id)) delete selectedDetails[id];
        else if (item) selectedDetails[id] = item;
        return { selected, selectedDetails };
      }),
    ensureSelected: (id) =>
      set((state) => {
        const item =
          state.conversations.find((row) => row.conversation_id === id) ??
          (state.activeConversation?.conversation_id === id
            ? state.activeConversation
            : undefined);
        return {
          selected: ensureId(state.selected, id),
          selectedDetails: item
            ? { ...state.selectedDetails, [id]: item }
            : state.selectedDetails,
        };
      }),
    selectVisible: () =>
      set((state) => ({
        selected: mergeIds(
          state.selected,
          state.conversations.map((item) => item.conversation_id),
        ),
        selectedDetails: {
          ...state.selectedDetails,
          ...Object.fromEntries(
            state.conversations.map((item) => [item.conversation_id, item]),
          ),
        },
      })),
    clearSelected: () => set({ selected: [], selectedDetails: {} }),
    openConversation: async (conversation) => {
      const version = get().contextVersion;
      const account = get().account;
      if (!account) return;
      const request = ++previewRequest;
      set({
        activeConversation: conversation,
        preview: [],
        previewTotal: 0,
        previewOffset: 0,
        olderLoading: false,
        previewLoading: true,
      });
      try {
        const data = await invoke<{
          items: Message[];
          total: number;
          offset: number;
        }>(
          "preview_messages",
          account.account_id,
          conversation.conversation_id,
          {
            limit: 100,
            offset: 0,
          },
        );
        if (
          request !== previewRequest ||
          get().contextVersion !== version ||
          get().account?.account_id !== account.account_id ||
          get().activeConversation?.conversation_id !==
            conversation.conversation_id
        )
          return;
        set({
          preview: data.items,
          previewTotal: data.total,
          previewOffset: data.items.length,
          previewLoading: false,
          loading: false,
        });
      } catch (error) {
        if (request === previewRequest && get().contextVersion === version) {
          set({ previewLoading: false });
          reportError(set, error);
        }
      }
    },
    loadOlder: async () => {
      const version = get().contextVersion;
      const request = previewRequest;
      const { account, activeConversation, previewOffset, preview } = get();
      if (!account || !activeConversation || get().olderLoading) return;
      set({ olderLoading: true });
      try {
        const data = await invoke<{ items: Message[] }>(
          "preview_messages",
          account.account_id,
          activeConversation.conversation_id,
          { limit: 100, offset: previewOffset },
        );
        if (
          request !== previewRequest ||
          get().contextVersion !== version ||
          get().account?.account_id !== account.account_id ||
          get().activeConversation?.conversation_id !==
            activeConversation.conversation_id
        )
          return;
        set({
          preview: [...data.items, ...preview],
          previewOffset: previewOffset + data.items.length,
        });
      } catch (error) {
        if (request === previewRequest && get().contextVersion === version)
          reportError(set, error);
      } finally {
        if (request === previewRequest && get().contextVersion === version)
          set({ olderLoading: false });
      }
    },
  };
};
