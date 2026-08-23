import { describe, expect, it } from "vitest";
import type { Settings } from "../types";
import { createExportDraft, mergeExportDraft } from "./exportDraft";
import { ensureId, mergeIds, toggleId } from "./selection";

const settings: Settings = {
  data_root: "data",
  output_directory: "output",
  theme: "system",
  conversation_kind: "all",
  last_account_id: "",
  font_scale: "standard",
  density: "comfortable",
  download_missing_media_default: true,
  allow_legacy_http_media_default: true,
  visual_download_limit_mib: 50,
  audio_download_limit_mib: 100,
  large_download_limit_mib: 500,
  open_result_folder_after_export: false,
  export_folder_layout: "by_type",
};

describe("export draft helpers", () => {
  it("creates a transient draft from persisted defaults", () => {
    const draft = createExportDraft(settings);
    expect(draft.output).toBe("output");
    expect(draft.formats).toEqual(["html", "markdown", "json"]);
    expect(draft.downloadMedia).toBe(true);
  });

  it("updates a draft without dropping unrelated choices", () => {
    const draft = mergeExportDraft(createExportDraft(settings), { visualLimit: 80 });
    expect(draft.visualLimit).toBe(80);
    expect(draft.audioLimit).toBe(100);
  });
});

describe("selection helpers", () => {
  it("keeps operations idempotent", () => {
    expect(ensureId(["a"], "a")).toEqual(["a"]);
    expect(toggleId(["a"], "a")).toEqual([]);
    expect(mergeIds(["a"], ["a", "b"])).toEqual(["a", "b"]);
  });
});
