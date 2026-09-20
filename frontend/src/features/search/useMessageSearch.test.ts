import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "../../bridge";
import { useWorkbench } from "../../store";
import type { Operation, SearchItem } from "../../types";
import { deferred, exampleAccount } from "../../test/fixtures";
import { useMessageSearch } from "./useMessageSearch";

vi.mock("../../bridge", () => ({ invoke: vi.fn() }));
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
const mockedInvoke = vi.mocked(invoke);
const initialStore = useWorkbench.getState();
const account = { ...exampleAccount, account_id: "test-account" };
const first: Operation = {
  operation_id: "test-search",
  kind: "search",
  account_id: account.account_id,
  status: "running",
  progress: 0,
  message: "正在搜索",
  created_at: "2026-09-20",
};
const item: SearchItem = {
  conversation_id: "chat",
  conversation_name: "示例会话",
  conversation_kind: "private",
  message_id: "message",
  sent_at: "2026-09-20T23:59:59",
  sender_name: "示例",
  message_type: "text",
  snippet: "合成搜索结果",
};
let root: Root;
let element: HTMLDivElement;
let search: ReturnType<typeof useMessageSearch>;
function Harness() {
  search = useMessageSearch();
  return null;
}
beforeEach(async () => {
  mockedInvoke.mockReset();
  useWorkbench.setState({ ...initialStore, account, contextVersion: 1 });
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
  await act(async () => root.render(createElement(Harness)));
  await act(async () => search.setQuery("  示例  "));
});
afterEach(async () => {
  await act(async () => root.unmount());
  element.remove();
});

describe("message search lifecycle", () => {
  it("searches an inclusive local date range with a snapshot of the selected conversations", async () => {
    const done = { ...first, status: "completed", result: { items: [item] } };
    await act(async () =>
      useWorkbench.setState({
        selected: ["chat"],
        pollOperation: async <T>() => {
          useWorkbench.getState().trackOperation(done);
          return done as Operation<T>;
        },
      }),
    );
    mockedInvoke.mockResolvedValue(first);
    await act(async () => {
      search.setStartAt("2026-09-01");
      search.setEndAt("2026-09-20");
      search.setMessageType("text");
      search.setSelectedOnly(true);
    });
    await act(async () => search.run());
    expect(mockedInvoke).toHaveBeenCalledWith("search_messages", {
      account_id: "test-account",
      query: "示例",
      limit: 300,
      start_at: "2026-09-01T00:00:00",
      end_at: "2026-09-20T23:59:59",
      message_types: ["text"],
      conversation_ids: ["chat"],
    });
    expect(search.items).toEqual([item]);
    expect(search.searchedQuery).toBe("示例");
    expect(search.running).toBe(false);
  });

  it("does not start a request with reversed dates", async () => {
    await act(async () => {
      search.setStartAt("2026-09-20");
      search.setEndAt("2026-09-01");
    });
    await act(async () => search.run());
    expect(mockedInvoke).not.toHaveBeenCalled();
    expect(search.dateError).toBe("结束日期不能早于开始日期");
  });

  it("prevents a duplicate submit and discards a start response from an older account context", async () => {
    const pending = deferred<Operation>();
    const track = vi.fn();
    await act(async () => useWorkbench.setState({ trackOperation: track }));
    mockedInvoke.mockReturnValue(pending.promise);
    let running!: Promise<void>;
    await act(async () => {
      running = search.run();
      await search.run();
    });
    expect(mockedInvoke).toHaveBeenCalledTimes(1);
    await act(async () => useWorkbench.setState({ contextVersion: 3 }));
    await act(async () => {
      pending.resolve(first);
      await running;
    });
    expect(track).not.toHaveBeenCalled();
    expect(search.items).toEqual([]);
  });

  it("does not publish completed search results after an account switch", async () => {
    const pending = deferred<Operation<{ items: SearchItem[] }>>();
    await act(async () =>
      useWorkbench.setState({
        pollOperation: <T>() => pending.promise as Promise<Operation<T>>,
      }),
    );
    mockedInvoke.mockResolvedValue(first);
    let running!: Promise<void>;
    await act(async () => {
      running = search.run();
    });
    await act(async () =>
      useWorkbench.setState({
        contextVersion: 2,
        account: { ...account, account_id: "other-account" },
      }),
    );
    await act(async () => {
      pending.resolve({
        ...first,
        status: "completed",
        result: { items: [item] },
      });
      await running;
    });
    expect(search.items).toEqual([]);
  });

  it("cancels an active search and leaves no stale search results", async () => {
    const pending = deferred<Operation<{ items: SearchItem[] }>>();
    await act(async () =>
      useWorkbench.setState({
        pollOperation: <T>() => pending.promise as Promise<Operation<T>>,
      }),
    );
    mockedInvoke.mockResolvedValue(first);
    let running!: Promise<void>;
    await act(async () => {
      running = search.run();
    });
    await act(async () => search.cancel());
    expect(mockedInvoke).toHaveBeenCalledWith(
      "cancel_operation",
      "test-search",
    );
    await act(async () => {
      const done = { ...first, status: "cancelled", result: undefined };
      useWorkbench.getState().trackOperation(done);
      pending.resolve(done);
      await running;
    });
    expect(search.items).toEqual([]);
    expect(search.running).toBe(false);
    expect(search.operation?.status).toBe("cancelled");
  });

  it("reports a search failure and allows retrying", async () => {
    mockedInvoke.mockRejectedValue(new Error("无法读取快照"));
    await act(async () => search.run());
    expect(search.error).toBe("无法读取快照");
    expect(search.running).toBe(false);
    await act(async () => search.run());
    expect(mockedInvoke).toHaveBeenCalledTimes(2);
  });

  it("removes the selected-only restriction when the selection is cleared", async () => {
    await act(async () => useWorkbench.setState({ selected: ["chat"] }));
    await act(async () => search.setSelectedOnly(true));
    expect(search.selectedOnly).toBe(true);
    await act(async () => useWorkbench.setState({ selected: [] }));
    expect(search.selectedOnly).toBe(false);
  });
});
