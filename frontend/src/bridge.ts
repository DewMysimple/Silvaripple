import type {
  AccountStatisticsReport,
  Bootstrap,
  Conversation,
  HistoryEntry,
  Message,
  Operation,
  Preset,
} from "./types";

type Envelope<T> =
  | { ok: true; data: T }
  | { ok: false; error: string; code?: string };

declare global {
  interface Window {
    pywebview?: {
      api: Record<string, (...args: unknown[]) => Promise<Envelope<unknown>>>;
    };
  }
}

const mockAccount = {
  account_id: "mock-account",
  display_name: "本地微信账号",
  active: true,
  size_bytes: 5583457484,
  database_count: 11,
  directory: "D:\\WeChat",
  coverage: { covered: 11, total: 11, complete: true, missing_databases: [] },
};
const mockConversations: Conversation[] = [
  {
    conversation_id: "c1",
    display_name: "设计讨论群",
    kind: "group",
    unread_count: 0,
    last_message_at: new Date().toISOString(),
  },
  {
    conversation_id: "c2",
    display_name: "文件传输助手",
    kind: "private",
    unread_count: 0,
    last_message_at: new Date(Date.now() - 86400000).toISOString(),
  },
  {
    conversation_id: "c3",
    display_name: "家人群",
    kind: "group",
    unread_count: 0,
    last_message_at: new Date(Date.now() - 172800000).toISOString(),
  },
];
const requestedMockTheme = new URLSearchParams(location.search).get("theme");
const mockSettings = {
  data_root: "D:\\WeChat\\xwechat_files",
  output_directory: "C:\\Users\\User\\Desktop",
  theme: (requestedMockTheme === "dark" || requestedMockTheme === "light"
    ? requestedMockTheme
    : "system") as "system" | "light" | "dark",
  conversation_kind: "all",
  last_account_id: "mock-account",
  font_scale: "standard" as const,
  density: "comfortable" as const,
  download_missing_media_default: true,
  allow_legacy_http_media_default: true,
  visual_download_limit_mib: 50,
  audio_download_limit_mib: 100,
  large_download_limit_mib: 500,
  open_result_folder_after_export: false,
  export_folder_layout: "by_type" as const,
};

const mockApi: Record<
  string,
  (...args: unknown[]) => Promise<Envelope<unknown>>
> = {
  bootstrap: async () => ({
    ok: true,
    data: {
      version: "0.2.0",
      settings: mockSettings,
      accounts: [mockAccount],
      selected_account_id: "mock-account",
      capabilities: { offline: true, dpapi: true },
    } satisfies Bootstrap,
  }),
  scan_accounts: async () => ({ ok: true, data: { accounts: [mockAccount] } }),
  list_conversations: async () => ({
    ok: true,
    data: {
      items: mockConversations,
      total: mockConversations.length,
      page: 1,
      page_size: 100,
      account: mockAccount,
    },
  }),
  preview_messages: async () => ({
    ok: true,
    data: {
      items: [
        {
          message_id: "m1",
          sent_at: new Date(Date.now() - 60000).toISOString(),
          sender_name: "群成员",
          outgoing: false,
          message_type: "text",
          display_text: "这是本地预览消息。",
          attachments: [],
        },
        {
          message_id: "m2",
          sent_at: new Date().toISOString(),
          sender_name: "当前账号",
          outgoing: true,
          message_type: "text",
          display_text: "导出前可以在这里检查排版与媒体。",
          attachments: [],
        },
      ] satisfies Message[],
      total: 2,
      offset: 0,
      returned: 2,
    },
  }),
  save_settings: async (value) => ({
    ok: true,
    data: { settings: { ...mockSettings, ...(value as object) } },
  }),
  list_operation_history: async () => ({
    ok: true,
    data: { items: [] satisfies HistoryEntry[] },
  }),
  list_export_presets: async () => ({
    ok: true,
    data: { items: [] satisfies Preset[] },
  }),
  estimate_export: async () => ({
    ok: true,
    data: {
      conversation_count: 1,
      message_count: 677,
      media_count: 52,
      estimated_bytes: 48234496,
      known_bytes: 48234496,
      free_bytes: 322122547200,
      remote_size_unknown_count: 6,
      local_recoverable_count: 41,
      network_candidate_count: 6,
      unavailable_count: 5,
      by_category: {},
      calculated_at: new Date().toISOString(),
      warnings: [],
    },
  }),
  start_export: async () => ({
    ok: true,
    data: {
      operation_id: "mock-export",
      kind: "export",
      status: "running",
      progress: 0.08,
      message: "正在读取消息",
      created_at: new Date().toISOString(),
    } satisfies Operation,
  }),
  search_messages: async () => ({
    ok: true,
    data: {
      operation_id: "mock-search",
      kind: "search",
      status: "running",
      progress: 0.2,
      message: "正在搜索聊天记录",
      created_at: new Date().toISOString(),
    } satisfies Operation,
  }),
  start_media_scan: async () => ({
    ok: true,
    data: {
      operation_id: "mock-media",
      kind: "media_scan",
      status: "running",
      progress: 0.15,
      message: "正在检查本地媒体",
      created_at: new Date().toISOString(),
    } satisfies Operation,
  }),
  get_account_statistics: async () => ({
    ok: true,
    data: { report: undefined },
  }),
  start_account_statistics_scan: async () => ({
    ok: true,
    data: {
      operation_id: "mock-statistics",
      kind: "account_statistics",
      status: "running",
      progress: 0.15,
      message: "正在统计全部会话",
      created_at: new Date().toISOString(),
      progress_detail: {
        phase: "messages",
        processed_messages: 320,
        conversation_count: 12,
      },
    } satisfies Operation,
  }),
  get_operation: async (id) => {
    const key = String(id);
    const statistics: AccountStatisticsReport = {
      account_id: "mock-account",
      database_fingerprint: "mock",
      calculated_at: new Date().toISOString(),
      complete: true,
      stale: false,
      conversation_count: 3,
      message_count: 12480,
      earliest_at: "2022-01-01T00:00:00+08:00",
      latest_at: new Date().toISOString(),
      by_conversation_kind: { private: 1, group: 2 },
      by_message_type: { text: 10600, image: 1400, emoji: 480 },
      conversations: mockConversations.map((item, index) => ({
        conversation_id: item.conversation_id,
        display_name: item.display_name,
        kind: item.kind,
        message_count: [7260, 3180, 2040][index],
        latest_at: item.last_message_at,
        by_message_type: { text: [6000, 2700, 1900][index] },
      })),
    };
    return {
      ok: true,
      data: {
        operation_id: key,
        kind: key.includes("search")
          ? "search"
          : key.includes("media")
            ? "media_scan"
            : key.includes("statistics")
              ? "account_statistics"
              : "export",
        status: "completed",
        progress: 1,
        message: "已完成",
        created_at: new Date().toISOString(),
        result: key.includes("search")
          ? {
              items: [
                {
                  conversation_id: "c1",
                  conversation_name: "设计讨论群",
                  conversation_kind: "group",
                  message_id: "m1",
                  sent_at: new Date().toISOString(),
                  sender_name: "群成员",
                  message_type: "text",
                  snippet: "这是包含关键词的本地搜索结果。",
                },
              ],
            }
          : key.includes("media")
            ? {
                referenced: 52,
                recoverable: 41,
                missing: 5,
                unsupported: 6,
                by_category: {
                  image: {
                    referenced: 37,
                    recoverable: 33,
                    missing: 4,
                    unsupported: 0,
                  },
                  emoji: {
                    referenced: 11,
                    recoverable: 5,
                    missing: 0,
                    unsupported: 6,
                  },
                },
                issues: [
                  {
                    category: "emoji",
                    status: "unsupported",
                    reason_code: "decode_failed",
                    count: 6,
                  },
                ],
                items: [],
                truncated: 0,
              }
            : key.includes("statistics")
              ? statistics
              : {
                  root: mockSettings.output_directory,
                  open_path: mockSettings.output_directory,
                  export_id: "mock-export-id",
                  conversation_paths: [
                    mockSettings.output_directory + "\\私聊\\文件传输助手",
                  ],
                  conversation_archives: [],
                  created_count: 1,
                  replaced_count: 0,
                  conversation_count: 1,
                  message_count: 677,
                  media_count: 52,
                  warnings: [],
                  warning_details: [],
                },
      },
    };
  },
  get_media_report: async (id) => mockApi.get_operation(id),
  cancel_operation: async (id) => ({
    ok: true,
    data: { operation_id: String(id), status: "cancelled" },
  }),
  choose_folder: async () => ({
    ok: true,
    data: { path: mockSettings.output_directory },
  }),
  clear_operation_history: async () => ({
    ok: true,
    data: { items: [], deleted_count: 0, preserved_running_count: 0 },
  }),
  clear_abnormal_operation_history: async () => ({
    ok: true,
    data: { items: [], deleted_count: 0, preserved_running_count: 0 },
  }),
  delete_operation_history_entry: async () => ({
    ok: true,
    data: { items: [] },
  }),
  delete_operation_history_entries: async () => ({
    ok: true,
    data: { items: [] },
  }),
  relink_operation_history_entry: async () => ({
    ok: true,
    data: { item: {} },
  }),
  trash_export_result: async () => ({ ok: true, data: { item: {} } }),
  save_export_preset: async (value) => ({
    ok: true,
    data: { preset: value, items: [value] },
  }),
  delete_export_preset: async () => ({ ok: true, data: { items: [] } }),
  open_result_folder: async (path) => ({ ok: true, data: { path } }),
  authorize_account: async () => ({ ok: true, data: { account: mockAccount } }),
};

const BRIDGE_TIMEOUT_MS = 15_000;

/**
 * pywebview dispatches `pywebviewready` on `window`.  Older builds listened on
 * `document`, so a fast host could fire the event before React subscribed and
 * leave the splash screen waiting forever.  Polling also covers WebView2
 * versions which install `window.pywebview` immediately before/after the event.
 */
async function ready(method: string): Promise<void> {
  if (typeof window.pywebview?.api?.[method] === "function") return;
  if (import.meta.env.DEV) return;

  await new Promise<void>((resolve, reject) => {
    let settled = false;
    const finish = (error?: Error) => {
      if (settled) return;
      settled = true;
      window.removeEventListener("pywebviewready", onReady);
      document.removeEventListener("pywebviewready", onReady);
      clearInterval(poll);
      clearTimeout(timeout);
      error ? reject(error) : resolve();
    };
    const onReady = () => {
      if (typeof window.pywebview?.api?.[method] === "function") finish();
    };
    const poll = window.setInterval(() => {
      if (typeof window.pywebview?.api?.[method] === "function") finish();
    }, 50);
    const timeout = window.setTimeout(
      () =>
        finish(
          new Error("桌面服务连接超时。请关闭旧窗口后重新启动 ChatWechat。"),
        ),
      BRIDGE_TIMEOUT_MS,
    );

    window.addEventListener("pywebviewready", onReady);
    // Retain document support for older pywebview releases.
    document.addEventListener("pywebviewready", onReady);
    onReady();
  });
}

export async function invoke<T>(
  method: string,
  ...args: unknown[]
): Promise<T> {
  await ready(method);
  const api = import.meta.env.DEV
    ? (window.pywebview?.api ?? mockApi)
    : window.pywebview?.api;
  if (!api)
    throw new Error("桌面服务尚未就绪。请关闭旧窗口后重新启动 ChatWechat。");
  const fn = api[method];
  if (!fn) throw new Error(`桌面接口不可用：${method}`);
  const envelope = (await fn(...args)) as Envelope<T>;
  if (!envelope.ok) throw new Error(envelope.error || "操作失败");
  return envelope.data;
}

export const isMockBridge = () => !window.pywebview?.api;
