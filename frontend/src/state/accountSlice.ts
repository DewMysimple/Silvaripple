import { invoke } from "../bridge";
import type { Slice } from "./model";
import { reportError } from "./model";
import type { Bootstrap, DataRootCandidate } from "../types";
import { createExportDraft } from "./exportDraft";
import { resetAccountContext } from "./context";

export const createAccountSlice: Slice<
  | "initialize"
  | "selectAccount"
  | "refreshDataRoots"
  | "selectDataRoot"
  | "useAutoDataRoot"
> = (set, get) => {
  let rootRequest = 0;
  let bootstrapRequest = 0;
  return {
    initialize: async () => {
      const request = ++bootstrapRequest;
      const version = get().contextVersion;
      set({ loading: true, error: undefined });
      try {
        const data = await invoke<Bootstrap>("bootstrap");
        if (request !== bootstrapRequest || get().contextVersion !== version)
          return;
        const account =
          data.accounts.find(
            (item) => item.account_id === data.selected_account_id,
          ) ?? data.accounts[0];
        const previous = get();
        const contextChanged =
          previous.account?.account_id !== account?.account_id ||
          previous.settings?.data_root !== data.settings.data_root;
        set((state) => ({
          initialized: true,
          loading: false,
          settings: data.settings,
          accounts: data.accounts,
          dataRoots: data.data_roots || [],
          account,
          exportDraft: state.exportDraft ?? createExportDraft(data.settings),
          ...(contextChanged
            ? resetAccountContext(state.contextVersion + 1)
            : {}),
        }));
        if (account?.coverage.covered) await get().loadConversations();
        if (account) {
          await Promise.all([
            get().refreshHistory(),
            get().refreshAccountStatistics(),
          ]);
        }
      } catch (error) {
        if (request === bootstrapRequest && get().contextVersion === version)
          reportError(set, error);
      }
    },
    selectAccount: async (account) => {
      const version = get().contextVersion + 1;
      set({
        ...resetAccountContext(version),
        account,
        loading: true,
        error: undefined,
      });
      try {
        await invoke("save_settings", { last_account_id: account.account_id });
        if (get().contextVersion !== version) return;
        if (account.coverage.covered) await get().loadConversations();
        else set({ loading: false });
        await Promise.all([
          get().refreshHistory(),
          get().refreshAccountStatistics(),
        ]);
      } catch (error) {
        if (get().contextVersion === version) reportError(set, error);
      }
    },
    refreshDataRoots: async () => {
      const version = get().contextVersion;
      try {
        const data = await invoke<{ items: DataRootCandidate[] }>(
          "scan_data_roots",
        );
        if (get().contextVersion === version) set({ dataRoots: data.items });
      } catch (error) {
        if (get().contextVersion === version) reportError(set, error);
      }
    },
    selectDataRoot: async (path) => {
      const request = ++rootRequest;
      set({ loading: true, error: undefined });
      try {
        await invoke("set_data_root", path);
        if (request !== rootRequest) return;
        await get().initialize();
      } catch (error) {
        if (request === rootRequest) reportError(set, error);
      }
    },
    useAutoDataRoot: async () => {
      const request = ++rootRequest;
      set({ loading: true, error: undefined });
      try {
        await invoke("use_auto_data_root");
        if (request !== rootRequest) return;
        await get().initialize();
      } catch (error) {
        if (request === rootRequest) reportError(set, error);
      }
    },
  };
};
