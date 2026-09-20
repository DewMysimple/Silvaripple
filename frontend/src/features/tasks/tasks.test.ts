import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Archive } from "lucide-react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "../../bridge";
import { useWorkbench } from "../../store";
import { deferred, exampleAccount } from "../../test/fixtures";
import type { HistoryEntry } from "../../types";
import {
  filterHistory,
  historyActions,
  selectableHistoryIds,
} from "./historyModel";
import { TaskMenu } from "./TaskMenu";
import { HistoryRow } from "./HistoryRow";
import { useTaskHistory } from "./useTaskHistory";

vi.mock("../../bridge", () => ({ invoke: vi.fn() }));
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
const mockedInvoke = vi.mocked(invoke);
const initialStore = useWorkbench.getState();
const entry: HistoryEntry = {
  history_id: "history-a",
  account_id: exampleAccount.account_id,
  kind: "export",
  status: "completed",
  created_at: "2026-09-20T12:00:00",
  completed_at: "2026-09-20T12:00:03",
  directory_health: "healthy",
  current_path: "test-output/chat-a",
  conversation_count: 1,
  message_count: 20,
  media_count: 2,
  formats: ["html"],
  warnings: [],
  warning_details: [],
  result_summary: {},
};
let root: Root;
let container: HTMLDivElement;
let tasks: ReturnType<typeof useTaskHistory>;
function Harness() {
  tasks = useTaskHistory();
  return null;
}

beforeEach(() => {
  mockedInvoke.mockReset();
  useWorkbench.setState({
    ...initialStore,
    account: exampleAccount,
    contextVersion: 1,
    history: [entry],
  });
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});
const render = () => act(async () => root.render(createElement(Harness)));

describe("history action rules", () => {
  it("uses the shared Chinese media labels in archive warning details", async () => {
    await act(async () =>
      root.render(
        createElement(HistoryRow, {
          item: {
            ...entry,
            warning_details: [
              {
                code: "missing",
                category: "image",
                count: 2,
                message: "缺少图片缓存",
              },
              {
                code: "missing",
                category: "audio",
                count: 1,
                message: "缺少语音缓存",
              },
            ],
          },
          selected: false,
          busy: false,
          onSelect: vi.fn(),
          onOpen: vi.fn(),
          onRelink: vi.fn(),
          onTrash: vi.fn(),
          onRemove: vi.fn(),
        }),
      ),
    );
    const labels = [
      ...container.querySelectorAll(".history-detail-content li strong"),
    ].map((item) => item.textContent);
    expect(labels).toEqual(["图片 · 2", "语音 · 1"]);
  });

  it("never offers deletion or recycling for running tasks", () => {
    const running = { ...entry, status: "running" };
    expect(historyActions(running)).toMatchObject({
      canRemove: false,
      canTrash: false,
      canRelink: false,
    });
    expect(selectableHistoryIds([running], [running.history_id])).toEqual([]);
  });

  it("does not recycle an old shared archive when every conversation has a newer export", () => {
    expect(
      historyActions({
        ...entry,
        storage_mode: "shared",
        superseded_count: 1,
        conversation_archives: [
          {
            archive_id: "archive",
            conversation_id: "chat-a",
            export_id: "export",
            path: "output/chat-a",
          },
        ],
      }).canTrash,
    ).toBe(false);
    expect(
      historyActions({ ...entry, directory_health: "trashed" }).canRelink,
    ).toBe(false);
    expect(
      historyActions({ ...entry, directory_health: "missing" }),
    ).toMatchObject({ needsRelink: true, canOpen: false });
  });

  it("restricts bulk selection to visible records that still exist and are finished", () => {
    const scan = {
      ...entry,
      history_id: "scan",
      kind: "media_scan",
      directory_health: "not_applicable" as const,
    };
    const visible = filterHistory([entry, scan], {
      kind: "media_scan",
      health: "all",
      status: "all",
    });
    expect(
      selectableHistoryIds(visible, [entry.history_id, "scan", "removed"]),
    ).toEqual(["scan"]);
  });
});

describe("history actions across account contexts", () => {
  it("clears hidden selections when a filter changes", async () => {
    await render();
    await act(async () => tasks.selectVisible(true));
    expect(tasks.selected).toEqual([entry.history_id]);
    await act(async () => tasks.updateFilters({ kind: "media_scan" }));
    expect(tasks.selected).toEqual([]);
    await act(async () => tasks.updateFilters({ kind: "all" }));
    expect(tasks.selected).toEqual([]);
  });

  it("reports a refresh failure and prevents duplicate requests", async () => {
    const pending = deferred<{ items: HistoryEntry[] }>();
    mockedInvoke.mockReturnValueOnce(pending.promise);
    await render();
    let first!: Promise<void>;
    await act(async () => {
      first = tasks.refresh();
      await tasks.refresh();
    });
    expect(mockedInvoke).toHaveBeenCalledTimes(1);
    await act(async () => {
      pending.resolve({ items: [] });
      await first;
    });
    expect(tasks.history).toEqual([]);
    mockedInvoke.mockRejectedValueOnce(new Error("目录暂时不可访问"));
    await act(async () => tasks.refresh());
    expect(tasks.error).toBe("目录暂时不可访问");
    expect(tasks.busy).toBe(false);
  });

  it("does not write an old account history response into the new account", async () => {
    const pending = deferred<{ items: HistoryEntry[] }>();
    mockedInvoke.mockReturnValueOnce(pending.promise);
    await render();
    let request!: Promise<void>;
    await act(async () => {
      request = tasks.refresh();
    });
    await act(async () =>
      useWorkbench.setState({ contextVersion: 3, history: [] }),
    );
    await act(async () => {
      pending.resolve({ items: [entry] });
      await request;
    });
    expect(useWorkbench.getState().history).toEqual([]);
  });

  it("abandons a folder selection after the account changes before relinking", async () => {
    const pending = deferred<{ path: string }>();
    mockedInvoke.mockReturnValueOnce(pending.promise);
    await render();
    let request!: Promise<void>;
    await act(async () => {
      request = tasks.relink(entry);
    });
    await act(async () => useWorkbench.setState({ contextVersion: 2 }));
    await act(async () => {
      pending.resolve({ path: "new-output" });
      await request;
    });
    expect(mockedInvoke).toHaveBeenCalledTimes(1);
    expect(mockedInvoke).not.toHaveBeenCalledWith(
      "relink_operation_history_entry",
      expect.anything(),
      expect.anything(),
    );
  });

  it("propagates a failed confirmed mutation so the shared dialog stays open", async () => {
    mockedInvoke.mockRejectedValueOnce(new Error("记录正在使用"));
    await render();
    await act(async () => tasks.askRemove([entry.history_id]));
    await act(async () => {
      await expect(tasks.confirmation?.onConfirm()).rejects.toThrow(
        "记录正在使用",
      );
    });
    expect(tasks.confirmation).toBeDefined();
    expect(tasks.busy).toBe(false);
    expect(mockedInvoke).toHaveBeenCalledWith(
      "delete_operation_history_entries",
      [entry.history_id],
    );
  });

  it("does not repeat a successful destructive action because the following refresh failed", async () => {
    mockedInvoke
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce(new Error("刷新失败"));
    await render();
    await act(async () => tasks.askClear("all"));
    await act(async () => {
      await expect(tasks.confirmation?.onConfirm()).resolves.toBeUndefined();
    });
    expect(mockedInvoke).toHaveBeenCalledWith(
      "clear_operation_history",
      exampleAccount.account_id,
    );
    expect(tasks.error).toContain("操作已完成");
  });
});

describe("task action menu keyboard support", () => {
  it("focuses enabled actions, supports arrows and returns focus on Escape", async () => {
    await act(async () =>
      root.render(
        createElement(TaskMenu, {
          label: "更多操作",
          children: "更多",
          actions: [
            {
              label: "禁用动作",
              icon: Archive,
              disabled: true,
              onSelect: vi.fn(),
            },
            { label: "第一项", icon: Archive, onSelect: vi.fn() },
            { label: "第二项", icon: Archive, onSelect: vi.fn() },
          ],
        }),
      ),
    );
    const trigger = container.querySelector<HTMLButtonElement>("button")!;
    await act(async () => trigger.click());
    expect(document.activeElement?.textContent).toBe("第一项");
    await act(async () => {
      document.activeElement?.dispatchEvent(
        new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }),
      );
    });
    expect(document.activeElement?.textContent).toBe("第二项");
    await act(async () => {
      document.activeElement?.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Escape", bubbles: true }),
      );
    });
    expect(container.querySelector('[role="menu"]')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});
