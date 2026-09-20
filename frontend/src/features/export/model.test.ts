import { describe, expect, it } from "vitest";
import type { Account, ExportDraft } from "../../types";
import {
  createExportRequest,
  getExportBlockers,
  resolveSelectedConversations,
} from "./model";

const account = {
  account_id: "example",
  coverage: { complete: true },
} as Account;
const draft: ExportDraft = {
  formats: ["html"],
  includeMedia: true,
  downloadMedia: true,
  legacyHttp: true,
  visualLimit: 50,
  audioLimit: 100,
  largeLimit: 500,
  allowPartial: false,
  output: " output ",
  startAt: "",
  endAt: "",
  messageTypes: [],
  mediaCategories: [],
};

describe("export request validation", () => {
  it("blocks an inverted date range and missing required choices", () => {
    expect(
      getExportBlockers(account, ["chat"], {
        ...draft,
        startAt: "2026-09-20",
        endAt: "2026-09-01",
      }),
    ).toContain("结束日期不能早于开始日期");
    expect(
      getExportBlockers(account, [], { ...draft, formats: [], output: "  " }),
    ).toHaveLength(3);
    expect(getExportBlockers(account, ["chat"], draft)).toEqual([]);
  });
  it("requires explicit partial export consent when database coverage is incomplete", () => {
    const partialAccount = {
      ...account,
      coverage: { ...account.coverage, complete: false },
    };
    expect(getExportBlockers(partialAccount, ["chat"], draft)).toHaveLength(1);
    expect(
      getExportBlockers(partialAccount, ["chat"], {
        ...draft,
        allowPartial: true,
      }),
    ).toEqual([]);
  });
  it("snapshots selections and disables network recovery when media is excluded", () => {
    const selected = ["chat"];
    const request = createExportRequest("example", selected, {
      ...draft,
      includeMedia: false,
      startAt: "2026-09-01",
      endAt: "2026-09-20",
    });
    selected.push("later");
    expect(request.conversation_ids).toEqual(["chat"]);
    expect(request.output_directory).toBe("output");
    expect(request.start_at).toBe("2026-09-01T00:00:00");
    expect(request.end_at).toBe("2026-09-20T23:59:59");
    expect(request.download_missing_media).toBe(false);
    expect(request.allow_legacy_http_media).toBe(false);
  });
  it("keeps every selected conversation visible even after the browser is filtered", () => {
    const rows = resolveSelectedConversations(
      ["visible", "hidden"],
      [
        {
          conversation_id: "visible",
          display_name: "示例会话",
          kind: "private",
          unread_count: 0,
        },
      ],
    );
    expect(rows.map((row) => row.conversation_id)).toEqual([
      "visible",
      "hidden",
    ]);
    expect(rows[1].display_name).not.toContain("hidden");
  });
});
