import type {
  Account,
  Conversation,
  ExportDraft,
  ExportFolderLayout,
} from "../../types";
import { clampDownloadLimit } from "../../utils/format";

export const EXPORT_FORMATS = [
  {
    value: "html",
    label: "网页归档",
    extension: "HTML",
    description: "双击阅读，保留聊天排版",
  },
  {
    value: "markdown",
    label: "文档归档",
    extension: "Markdown",
    description: "便于整理、编辑和做笔记",
  },
  {
    value: "json",
    label: "完整数据",
    extension: "JSON",
    description: "适合程序处理与长期保存",
  },
] as const;

/** The estimate and export must always use the same snapshot of the draft. */
export function createExportRequest(
  accountId: string,
  selected: string[],
  draft: ExportDraft,
  layout: ExportFolderLayout = "by_type",
) {
  return {
    account_id: accountId,
    conversation_ids: [...selected],
    output_directory: draft.output.trim(),
    folder_layout: layout,
    start_at: draft.startAt ? `${draft.startAt}T00:00:00` : null,
    end_at: draft.endAt ? `${draft.endAt}T23:59:59` : null,
    formats: [...draft.formats],
    include_media: draft.includeMedia,
    download_missing_media: draft.includeMedia && draft.downloadMedia,
    allow_legacy_http_media:
      draft.includeMedia && draft.downloadMedia && draft.legacyHttp,
    visual_download_limit_mib: clampDownloadLimit(draft.visualLimit),
    audio_download_limit_mib: clampDownloadLimit(draft.audioLimit),
    large_download_limit_mib: clampDownloadLimit(draft.largeLimit),
    allow_partial: draft.allowPartial,
    message_types: [...draft.messageTypes],
    media_categories: [...draft.mediaCategories],
  };
}
export type ExportRequest = ReturnType<typeof createExportRequest>;

export function getExportBlockers(
  account: Account | undefined,
  selected: string[],
  draft: ExportDraft,
) {
  return [
    !account ? "请选择账号" : "",
    !selected.length ? "请添加至少一个会话" : "",
    !draft.formats.length ? "请选择至少一种格式" : "",
    !draft.output.trim() ? "请选择保存位置" : "",
    draft.startAt && draft.endAt && draft.startAt > draft.endAt
      ? "结束日期不能早于开始日期"
      : "",
    account && !account.coverage.complete && !draft.allowPartial
      ? "数据库覆盖不完整，请重新授权或在高级选项中允许部分导出"
      : "",
  ].filter(Boolean);
}

/** A filtered browser list must not silently hide selected conversations. */
export function resolveSelectedConversations(
  selected: string[],
  conversations: Conversation[],
): Conversation[] {
  const byId = new Map(
    conversations.map((item) => [item.conversation_id, item]),
  );
  return selected.map(
    (id) =>
      byId.get(id) ?? {
        conversation_id: id,
        display_name: "已选会话（不在当前列表）",
        kind: "unknown",
        unread_count: 0,
      },
  );
}

export function folderLayoutDescription(layout?: ExportFolderLayout) {
  if (layout === "flat") return "每个会话单独一个文件夹";
  if (layout === "account_by_type") return "按账号、私聊与群聊分组保存";
  return "按私聊与群聊分组保存";
}
