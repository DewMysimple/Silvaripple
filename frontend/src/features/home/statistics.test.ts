import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { AccountStatisticsReport } from "../../types";
import { useWorkbench } from "../../store";
import { StatisticsDetail } from "./StatisticsDetail";
import { StatisticsPanel } from "./StatisticsPanel";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
const initialStore = useWorkbench.getState();
const report: AccountStatisticsReport = {
  account_id: "example",
  database_fingerprint: "example",
  calculated_at: "2026-09-20",
  complete: true,
  stale: false,
  conversation_count: 25,
  message_count: 250,
  earliest_at: "2020-01-01T12:00:00",
  latest_at: "2026-09-20T13:00:00",
  by_conversation_kind: { private: 25 },
  by_message_type: { text: 250 },
  conversations: Array.from({ length: 25 }, (_, index) => ({
    conversation_id: String(index),
    display_name: `会话 ${index + 1}`,
    kind: "private",
    message_count: 25 - index,
    earliest_at: "2020-01-01T12:00:00",
    latest_at: "2026-09-20T13:00:00",
    by_message_type: {},
  })),
};
let root: Root;
let element: HTMLDivElement;
beforeEach(() => {
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
});
afterEach(async () => {
  await act(async () => root.unmount());
  element.remove();
  useWorkbench.setState(initialStore, true);
});

describe("conversation statistics details", () => {
  it("keeps both years visible in account and conversation date ranges", async () => {
    useWorkbench.setState({ accountStatistics: report });
    await act(async () => root.render(createElement(StatisticsPanel)));
    const summary = element.querySelector(
      ".home-statistics-range",
    )?.textContent;
    expect(summary).toContain("2020");
    expect(summary).toContain("2026");
    await act(async () =>
      element.querySelector<HTMLButtonElement>(".home-detail-toggle")!.click(),
    );
    const range = element.querySelector("tbody tr td:last-child")?.textContent;
    expect(range).toContain("2020");
    expect(range).toContain("2026");
  });

  it("paginates large account reports and resets the page when filtering", async () => {
    await act(async () =>
      root.render(createElement(StatisticsDetail, { report })),
    );
    expect(element.querySelectorAll("tbody tr")).toHaveLength(12);
    expect(element.querySelector("tbody tr")?.textContent).toContain("会话 1");
    await act(async () =>
      element
        .querySelector<HTMLButtonElement>('[aria-label="统计下一页"]')!
        .click(),
    );
    expect(element.querySelector("tbody tr")?.textContent).toContain("会话 13");
    const input = element.querySelector<HTMLInputElement>(
      '[aria-label="搜索统计会话"]',
    )!;
    const setValue = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )!.set!;
    await act(async () => {
      setValue.call(input, "会话 25");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(element.querySelectorAll("tbody tr")).toHaveLength(1);
    expect(element.querySelector("tbody tr")?.textContent).toContain("会话 25");
    expect(
      element.querySelector<HTMLButtonElement>('[aria-label="统计上一页"]')!
        .disabled,
    ).toBe(true);
    expect(
      element.querySelector<HTMLButtonElement>('[aria-label="统计下一页"]')!
        .disabled,
    ).toBe(true);
  });
});
