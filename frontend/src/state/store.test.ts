import { beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "../bridge";
import { useWorkbench } from "../store";
import type {
  AccountStatisticsReport,
  Bootstrap,
  Conversation,
  HistoryEntry,
  Message,
  Operation,
} from "../types";
import {
  deferred,
  exampleAccount as account,
  exampleSettings as settings,
} from "../test/fixtures";

vi.mock("../bridge", () => ({ invoke: vi.fn() }));
const mockedInvoke = vi.mocked(invoke);
const initial = useWorkbench.getState();
const conversation = (id: string): Conversation => ({
  conversation_id: id,
  display_name: `示例会话 ${id}`,
  kind: "private",
  unread_count: 0,
});
const message = (id: string): Message => ({
  message_id: id,
  sent_at: "2026-09-20T12:00:00",
  outgoing: false,
  message_type: "text",
  attachments: [],
});
const operation: Operation = {
  operation_id: "test-operation",
  account_id: account.account_id,
  kind: "media_scan",
  status: "completed",
  progress: 1,
  message: "完成",
  created_at: "2026-09-20",
};
beforeEach(() => {
  mockedInvoke.mockReset();
  useWorkbench.setState({
    ...initial,
    initialized: true,
    loading: false,
    settings,
    account,
    contextVersion: 1,
  });
});

describe("selected conversation identity", () => {
  it("retains display details when filtering replaces the browser list", async () => {
    useWorkbench.setState({
      conversations: [conversation("a"), conversation("b")],
    });
    useWorkbench.getState().toggleSelected("a");
    mockedInvoke.mockResolvedValue({ items: [conversation("b")], total: 1 });
    await useWorkbench.getState().loadConversations({ query: "b" });
    expect(useWorkbench.getState().selectedDetails.a.display_name).toBe(
      "示例会话 a",
    );
    useWorkbench.getState().toggleSelected("a");
    expect(useWorkbench.getState().selectedDetails).toEqual({});
  });
  it("can select a preview after filtering, and clears all cached details with the selection", () => {
    useWorkbench.setState({
      activeConversation: conversation("a"),
      conversations: [conversation("b")],
    });
    useWorkbench.getState().ensureSelected("a");
    useWorkbench.getState().selectVisible();
    expect(Object.keys(useWorkbench.getState().selectedDetails)).toEqual([
      "a",
      "b",
    ]);
    useWorkbench.getState().clearSelected();
    expect(useWorkbench.getState().selected).toEqual([]);
    expect(useWorkbench.getState().selectedDetails).toEqual({});
  });
});

describe("conversation lists and previews", () => {
  it("keeps account totals independent from filters and appends pages without duplicates", async () => {
    useWorkbench.setState({ totalConversations: 8 });
    mockedInvoke.mockResolvedValueOnce({
      items: [conversation("a"), conversation("b")],
      total: 3,
    });
    await useWorkbench.getState().loadConversations({ query: "示例" });
    mockedInvoke.mockResolvedValueOnce({
      items: [conversation("b"), conversation("c")],
      total: 3,
    });
    await useWorkbench.getState().loadConversations({ query: "示例", page: 2 });
    expect(
      useWorkbench.getState().conversations.map((item) => item.conversation_id),
    ).toEqual(["a", "b", "c"]);
    expect(useWorkbench.getState().conversationResultTotal).toBe(3);
    expect(useWorkbench.getState().totalConversations).toBe(8);
  });
  it("ignores a slow filter response after the newer filter has completed", async () => {
    const first = deferred<{ items: Conversation[]; total: number }>();
    mockedInvoke
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce({ items: [conversation("new")], total: 1 });
    const oldRequest = useWorkbench
      .getState()
      .loadConversations({ query: "old" });
    await useWorkbench.getState().loadConversations({ query: "new" });
    first.resolve({ items: [conversation("old")], total: 1 });
    await oldRequest;
    expect(useWorkbench.getState().conversations[0].conversation_id).toBe(
      "new",
    );
    expect(useWorkbench.getState().conversationsLoading).toBe(false);
  });
  it("does not let an older preview replace a more recently opened conversation", async () => {
    const first = deferred<{ items: Message[]; total: number }>();
    mockedInvoke
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce({ items: [message("new")], total: 1 });
    const oldRequest = useWorkbench
      .getState()
      .openConversation(conversation("a"));
    await useWorkbench.getState().openConversation(conversation("b"));
    first.resolve({ items: [message("old")], total: 1 });
    await oldRequest;
    expect(useWorkbench.getState().preview[0].message_id).toBe("new");
    expect(useWorkbench.getState().activeConversation?.conversation_id).toBe(
      "b",
    );
  });
  it("requests an older page only once and prepends it without losing the visible messages", async () => {
    useWorkbench.setState({
      activeConversation: conversation("a"),
      preview: [message("recent")],
      previewOffset: 1,
      previewTotal: 2,
    });
    const pending = deferred<{ items: Message[] }>();
    mockedInvoke.mockReturnValue(pending.promise);
    const first = useWorkbench.getState().loadOlder();
    await useWorkbench.getState().loadOlder();
    expect(mockedInvoke).toHaveBeenCalledTimes(1);
    expect(mockedInvoke).toHaveBeenCalledWith(
      "preview_messages",
      "account-a",
      "a",
      { limit: 100, offset: 1 },
    );
    pending.resolve({ items: [message("older")] });
    await first;
    expect(
      useWorkbench.getState().preview.map((item) => item.message_id),
    ).toEqual(["older", "recent"]);
    expect(useWorkbench.getState().previewOffset).toBe(2);
    expect(useWorkbench.getState().olderLoading).toBe(false);
  });
  it("releases the old-page loading lock when the user opens another conversation", async () => {
    useWorkbench.setState({
      activeConversation: conversation("a"),
      preview: [message("a-recent")],
      previewOffset: 1,
      previewTotal: 2,
    });
    const pending = deferred<{ items: Message[] }>();
    mockedInvoke
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValueOnce({ items: [message("b-recent")], total: 2 });
    const oldRequest = useWorkbench.getState().loadOlder();
    await useWorkbench.getState().openConversation(conversation("b"));
    expect(useWorkbench.getState().olderLoading).toBe(false);
    pending.resolve({ items: [message("a-old")] });
    await oldRequest;
    mockedInvoke.mockResolvedValueOnce({ items: [message("b-old")] });
    await useWorkbench.getState().loadOlder();
    expect(
      useWorkbench.getState().preview.map((item) => item.message_id),
    ).toEqual(["b-old", "b-recent"]);
  });
});

describe("account context isolation", () => {
  it("resets transient data and increments the context on every account switch, including an A-B-A round trip", async () => {
    useWorkbench.setState({
      selected: ["a"],
      selectedDetails: { a: conversation("a") },
      preview: [message("private")],
      operations: { old: operation },
      totalConversations: 50,
    });
    mockedInvoke.mockImplementation(async (name) =>
      name === "list_conversations"
        ? { items: [], total: 0 }
        : name === "list_operation_history"
          ? { items: [] }
          : {},
    );
    await useWorkbench
      .getState()
      .selectAccount({ ...account, account_id: "account-b" });
    await useWorkbench.getState().selectAccount(account);
    expect(useWorkbench.getState().contextVersion).toBe(3);
    expect(useWorkbench.getState().selectedDetails).toEqual({});
    expect(useWorkbench.getState().preview).toEqual([]);
    expect(useWorkbench.getState().operations).toEqual({});
    expect(useWorkbench.getState().totalConversations).toBe(0);
  });
  it("does not apply an old list response when the account ID matches but its context has changed", async () => {
    const pending = deferred<{ items: Conversation[]; total: number }>();
    mockedInvoke.mockReturnValue(pending.promise);
    const request = useWorkbench.getState().loadConversations();
    useWorkbench.setState({
      contextVersion: 3,
      conversations: [conversation("current")],
      conversationsLoading: false,
    });
    pending.resolve({ items: [conversation("stale")], total: 1 });
    await request;
    expect(useWorkbench.getState().conversations[0].conversation_id).toBe(
      "current",
    );
  });
  it("does not register an old media scan when its start response arrives in a new context", async () => {
    const pending = deferred<Operation>();
    mockedInvoke.mockReturnValue(pending.promise);
    const request = useWorkbench.getState().startMediaScan(["a", "a"]);
    expect(mockedInvoke).toHaveBeenCalledWith("start_media_scan", "account-a", {
      conversation_ids: ["a"],
      detailed: true,
      limit: 500,
    });
    useWorkbench.setState({ contextVersion: 2 });
    pending.resolve(operation);
    await request;
    expect(useWorkbench.getState().mediaScanOperationId).toBeUndefined();
    expect(useWorkbench.getState().operations).toEqual({});
  });
  it("discards old history and statistics responses after a data-root or account change", async () => {
    const history = deferred<{ items: HistoryEntry[] }>();
    const stats = deferred<{ report: AccountStatisticsReport }>();
    mockedInvoke
      .mockReturnValueOnce(history.promise)
      .mockReturnValueOnce(stats.promise);
    const historyRequest = useWorkbench.getState().refreshHistory();
    const statsRequest = useWorkbench.getState().refreshAccountStatistics();
    useWorkbench.setState({ contextVersion: 2 });
    history.resolve({ items: [{ history_id: "old-history" } as HistoryEntry] });
    stats.resolve({
      report: {
        account_id: "account-a",
        message_count: 99,
      } as AccountStatisticsReport,
    });
    await Promise.all([historyRequest, statsRequest]);
    expect(useWorkbench.getState().history).toEqual([]);
    expect(useWorkbench.getState().accountStatistics).toBeUndefined();
  });
  it("stops polling without publishing the old operation's result into the new context", async () => {
    const pending = deferred<Operation>();
    mockedInvoke.mockReturnValue(pending.promise);
    const polling = useWorkbench
      .getState()
      .pollOperation(operation.operation_id);
    useWorkbench.setState({ contextVersion: 2 });
    pending.resolve({ ...operation, result: { private: "synthetic" } });
    expect(await polling).toMatchObject({
      status: "cancelled",
      result: undefined,
    });
    expect(useWorkbench.getState().operations).toEqual({});
  });
  it("discards a bootstrap response that belongs to an earlier context", async () => {
    const pending = deferred<Bootstrap>();
    mockedInvoke.mockReturnValue(pending.promise);
    const startup = useWorkbench.getState().initialize();
    useWorkbench.setState({
      contextVersion: 2,
      settings: { ...settings, data_root: "current-data" },
    });
    pending.resolve({
      version: "test",
      accounts: [account],
      settings,
      data_roots: [],
      capabilities: {},
    });
    await startup;
    expect(useWorkbench.getState().settings?.data_root).toBe("current-data");
  });
  it("keeps tracking a running export when a manually chosen data directory fails validation", async () => {
    const completion = deferred<Operation>();
    useWorkbench.setState({
      operations: {
        [operation.operation_id]: { ...operation, status: "running" },
      },
      exportOperationId: operation.operation_id,
    });
    mockedInvoke.mockImplementation(async (name) => {
      if (name === "get_operation") return completion.promise;
      if (name === "set_data_root") throw new Error("目录中没有微信数据");
      throw new Error(`Unexpected method: ${name}`);
    });
    const polling = useWorkbench
      .getState()
      .pollOperation(operation.operation_id);
    await useWorkbench.getState().selectDataRoot("not-a-wechat-directory");
    completion.resolve(operation);
    expect((await polling).status).toBe("completed");
    expect(useWorkbench.getState().contextVersion).toBe(1);
    expect(
      useWorkbench.getState().operations[operation.operation_id].status,
    ).toBe("completed");
    expect(useWorkbench.getState().error).toBe("目录中没有微信数据");
  });
  it("keeps tracking a running export when automatic discovery selects the same data root", async () => {
    const completion = deferred<Operation>();
    const discovery = deferred<unknown>();
    useWorkbench.setState({
      selected: ["a"],
      operations: {
        [operation.operation_id]: { ...operation, status: "running" },
      },
      exportOperationId: operation.operation_id,
    });
    mockedInvoke.mockImplementation(async (name) => {
      if (name === "get_operation") return completion.promise;
      if (name === "use_auto_data_root") return discovery.promise;
      if (name === "bootstrap")
        return {
          version: "test",
          accounts: [account],
          selected_account_id: account.account_id,
          settings: { ...settings, data_root_mode: "auto" },
          data_roots: [],
          capabilities: {},
        } satisfies Bootstrap;
      if (name === "list_conversations") return { items: [], total: 0 };
      if (name === "list_operation_history") return { items: [] };
      if (name === "get_account_statistics") return {};
      throw new Error(`Unexpected method: ${name}`);
    });
    const polling = useWorkbench
      .getState()
      .pollOperation(operation.operation_id);
    const findingRoot = useWorkbench.getState().useAutoDataRoot();
    discovery.resolve({});
    await findingRoot;
    completion.resolve(operation);
    expect((await polling).status).toBe("completed");
    expect(useWorkbench.getState().contextVersion).toBe(1);
    expect(useWorkbench.getState().selected).toEqual(["a"]);
    expect(
      useWorkbench.getState().operations[operation.operation_id].status,
    ).toBe("completed");
  });
});
