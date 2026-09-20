import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "../../bridge";
import { useWorkbench } from "../../store";
import { createExportDraft } from "../../state/exportDraft";
import type { ExportEstimate, ExportResult, Operation } from "../../types";
import {
  deferred,
  exampleAccount as account,
  exampleSettings as settings,
} from "../../test/fixtures";
import { createExportRequest, type ExportRequest } from "./model";
import { useExportEstimate } from "./useExportEstimate";
import { useExportWorkbench } from "./useExportWorkbench";

vi.mock("../../bridge", () => ({ invoke: vi.fn() }));
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
const mockedInvoke = vi.mocked(invoke);
const initialStore = useWorkbench.getState();
const request = createExportRequest(
  account.account_id,
  ["chat-a"],
  createExportDraft(settings),
);
const estimate = (count: number) =>
  ({ message_count: count, warnings: [] }) as unknown as ExportEstimate;
const operation: Operation<ExportResult> = {
  operation_id: "test-export",
  account_id: account.account_id,
  kind: "export",
  status: "running",
  progress: 0,
  message: "正在导出",
  created_at: "2026-09-20",
};
let root: Root;
let element: HTMLDivElement;
beforeEach(() => {
  vi.useFakeTimers();
  mockedInvoke.mockReset();
  useWorkbench.setState({
    ...initialStore,
    settings,
    account,
    selected: ["chat-a"],
    exportDraft: createExportDraft(settings),
    contextVersion: 1,
  });
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
});
afterEach(async () => {
  await act(async () => root.unmount());
  element.remove();
  vi.useRealTimers();
});

describe("live export estimates", () => {
  let value: ReturnType<typeof useExportEstimate>;
  function Harness({ payload }: { payload?: ExportRequest }) {
    value = useExportEstimate(payload);
    return null;
  }
  const render = (payload?: ExportRequest) =>
    act(async () => root.render(createElement(Harness, { payload })));
  const tick = () =>
    act(async () => {
      vi.advanceTimersByTime(500);
    });

  it("does not request an invalid or cleared configuration, and ignores its pending response", async () => {
    const pending = deferred<ExportEstimate>();
    mockedInvoke.mockReturnValue(pending.promise);
    await render(request);
    await tick();
    expect(mockedInvoke).toHaveBeenCalledTimes(1);
    await render(undefined);
    await act(async () => pending.resolve(estimate(12)));
    await tick();
    expect(mockedInvoke).toHaveBeenCalledTimes(1);
    expect(value.estimate).toBeUndefined();
    expect(value.estimating).toBe(false);
  });

  it("never replaces the newest estimate with an older configuration's response", async () => {
    const first = deferred<ExportEstimate>();
    const second = deferred<ExportEstimate>();
    mockedInvoke
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    await render(request);
    await tick();
    await render({ ...request, conversation_ids: ["chat-b"] });
    expect(value.estimate).toBeUndefined();
    await tick();
    await act(async () => second.resolve(estimate(20)));
    await act(async () => first.resolve(estimate(10)));
    expect(value.estimate?.message_count).toBe(20);
  });

  it("reports an estimate failure and retries with the current configuration", async () => {
    mockedInvoke
      .mockRejectedValueOnce(new Error("磁盘暂不可访问"))
      .mockResolvedValueOnce(estimate(30));
    await render(request);
    await tick();
    expect(value.estimateError).toBe("磁盘暂不可访问");
    await act(async () => value.retryEstimate());
    await tick();
    expect(value.estimate?.message_count).toBe(30);
    expect(value.estimateError).toBeUndefined();
  });
});

describe("export actions across account changes", () => {
  let value: ReturnType<typeof useExportWorkbench>;
  function Harness() {
    value = useExportWorkbench();
    return null;
  }
  const render = () => act(async () => root.render(createElement(Harness)));

  it("prevents duplicate submissions and discards a start response after an account round trip", async () => {
    const pending = deferred<Operation<ExportResult>>();
    mockedInvoke.mockReturnValue(pending.promise);
    const track = vi.fn();
    const poll = vi.fn();
    useWorkbench.setState({ trackOperation: track, pollOperation: poll });
    await render();
    let firstStart!: Promise<void>;
    await act(async () => {
      firstStart = value.start();
      await value.start();
    });
    expect(mockedInvoke).toHaveBeenCalledTimes(1);
    // Even an A -> B -> A switch must invalidate a request from the old session.
    await act(async () => useWorkbench.setState({ contextVersion: 3 }));
    await act(async () => {
      pending.resolve(operation);
      await firstStart;
    });
    expect(useWorkbench.getState().exportOperationId).toBeUndefined();
    expect(track).not.toHaveBeenCalled();
    expect(poll).not.toHaveBeenCalled();
  });

  it("surfaces a failed start and allows a deliberate retry", async () => {
    mockedInvoke.mockRejectedValue(new Error("导出目录不可写"));
    await render();
    await act(async () => value.start());
    expect(value.actionError).toBe("导出目录不可写");
    expect(value.starting).toBe(false);
    await act(async () => value.start());
    expect(mockedInvoke).toHaveBeenCalledTimes(2);
  });

  it("does not trigger a media scan for a new account after the old export finishes", async () => {
    const completion = deferred<Operation<ExportResult>>();
    const scan = vi.fn();
    const refresh = vi.fn();
    mockedInvoke.mockResolvedValue(operation);
    useWorkbench.setState({
      pollOperation: <T>() => completion.promise as Promise<Operation<T>>,
      startMediaScan: scan,
      refreshHistory: refresh,
    });
    await render();
    let start!: Promise<void>;
    await act(async () => {
      start = value.start();
    });
    await act(async () =>
      useWorkbench.setState({
        contextVersion: 2,
        account: { ...account, account_id: "account-b" },
      }),
    );
    await act(async () => {
      completion.resolve({
        ...operation,
        status: "completed",
        result: {
          warning_details: [
            { code: "missing", category: "image", count: 1, message: "缺失" },
          ],
        } as ExportResult,
      });
      await start;
    });
    expect(scan).not.toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
  });
});
