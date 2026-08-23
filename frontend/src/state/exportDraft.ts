import type { ExportDraft, Settings } from "../types";

export const createExportDraft = (settings: Settings): ExportDraft => ({
  formats: ["html", "markdown", "json"],
  includeMedia: true,
  downloadMedia: settings.download_missing_media_default,
  legacyHttp: settings.allow_legacy_http_media_default,
  visualLimit: settings.visual_download_limit_mib,
  audioLimit: settings.audio_download_limit_mib,
  largeLimit: settings.large_download_limit_mib,
  allowPartial: false,
  output: settings.output_directory,
  startAt: "",
  endAt: "",
  messageTypes: [],
  mediaCategories: [],
});

export const mergeExportDraft = (
  current: ExportDraft | undefined,
  value: Partial<ExportDraft>,
): ExportDraft => ({ ...(current as ExportDraft), ...value });
