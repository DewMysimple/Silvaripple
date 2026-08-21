export type ViewId =
  | "home"
  | "conversations"
  | "search"
  | "export"
  | "media"
  | "tasks"
  | "settings";
export type Theme = "system" | "light" | "dark";

export interface Coverage {
  covered: number;
  total: number;
  complete: boolean;
  fingerprint?: string;
  missing_databases: string[];
}
export interface Account {
  account_id: string;
  display_name: string;
  active: boolean;
  size_bytes: number;
  database_count: number;
  coverage: Coverage;
  directory: string;
  avatar_data_url?: string;
}
export type ExportFolderLayout = "flat" | "by_type" | "account_by_type";
export interface Settings {
  data_root: string;
  output_directory: string;
  theme: Theme;
  conversation_kind: string;
  last_account_id: string;
  font_scale: "small" | "standard" | "large";
  density: "compact" | "comfortable";
  download_missing_media_default: boolean;
  allow_legacy_http_media_default: boolean;
  visual_download_limit_mib: number;
  audio_download_limit_mib: number;
  large_download_limit_mib: number;
  open_result_folder_after_export: boolean;
  export_folder_layout: ExportFolderLayout;
}
export interface Conversation {
  conversation_id: string;
  display_name: string;
  kind: string;
  last_message_at?: string;
  message_count?: number;
  unread_count: number;
  avatar_data_url?: string;
}
export interface Attachment {
  attachment_id: string;
  category: string;
  preview_data_url?: string;
  available: boolean;
  reason?: string;
  reason_code?: string;
  status: string;
  source_kind: string;
  recovery_method?: string;
}
export interface Message {
  message_id: string;
  sent_at: string;
  sender_name?: string;
  outgoing: boolean;
  message_type: string;
  text?: string;
  display_text?: string;
  attachments: Attachment[];
  sender_avatar_data_url?: string;
  system_event?: { kind: string; text: string };
  quote_preview?: {
    sender_name?: string;
    text?: string;
    message_type?: string;
  };
}
export interface OperationProgressDetail {
  phase?: string;
  database?: string;
  table?: string;
  processed_messages?: number;
  conversation_count?: number;
}
export interface Operation<T = unknown> {
  operation_id: string;
  kind: string;
  status: string;
  progress: number;
  message: string;
  result?: T;
  error?: string;
  created_at: string;
  progress_detail?: OperationProgressDetail;
}
export type DirectoryHealth =
  | "healthy"
  | "moved"
  | "missing"
  | "incomplete"
  | "inaccessible"
  | "trashed"
  | "not_applicable";
export interface ConversationArchive {
  archive_id: string;
  conversation_id: string;
  path: string;
  export_id: string;
}
export interface HistoryEntry {
  history_id: string;
  kind: string;
  status: string;
  created_at: string;
  completed_at: string;
  result_path?: string;
  original_path?: string;
  current_path?: string;
  output_root?: string;
  archive_id?: string;
  storage_mode?: "batch" | "shared";
  export_id?: string;
  conversation_archives?: ConversationArchive[];
  superseded_count?: number;
  directory_health: DirectoryHealth;
  deleted_at?: string;
  duration_seconds?: number;
  error_summary?: string;
  result_summary: Record<string, unknown>;
  conversation_count: number;
  message_count: number;
  media_count: number;
  formats: string[];
  warnings: string[];
  warning_details: Array<{
    code: string;
    category: string;
    count: number;
    message: string;
  }>;
}
export interface Preset {
  preset_id: string;
  name: string;
  formats: string[];
  message_types: string[];
  media_categories: string[];
  include_media: boolean;
  download_missing_media: boolean;
  allow_legacy_http_media: boolean;
  visual_download_limit_mib: number;
  audio_download_limit_mib: number;
  large_download_limit_mib: number;
  allow_partial: boolean;
  start_at?: string;
  end_at?: string;
}
export interface SearchItem {
  conversation_id: string;
  conversation_name: string;
  conversation_kind: string;
  message_id: string;
  sent_at: string;
  sender_name: string;
  message_type: string;
  snippet: string;
}
export interface MediaRecoveryItem {
  conversation_id: string;
  conversation_name: string;
  sent_at: string;
  category: string;
  status: string;
  reason_code?: string;
}
export interface MediaReport {
  referenced: number;
  recoverable: number;
  missing: number;
  unsupported: number;
  by_category: Record<string, Record<string, number>>;
  issues: Array<{
    category: string;
    status: string;
    reason_code?: string;
    count: number;
  }>;
  items: MediaRecoveryItem[];
  truncated: number;
}
export interface ExportEstimate {
  conversation_count: number;
  message_count: number;
  media_count: number;
  estimated_bytes: number;
  known_bytes: number;
  free_bytes: number;
  remote_size_unknown_count: number;
  local_recoverable_count: number;
  network_candidate_count: number;
  unavailable_count: number;
  by_category: Record<string, Record<string, number>>;
  calculated_at: string;
  warnings: string[];
}
export interface ExportResult {
  root: string;
  conversation_count: number;
  message_count: number;
  media_count: number;
  warnings: string[];
  media_summary: Record<string, any>;
  warning_details: Array<{
    code: string;
    category: string;
    count: number;
    message: string;
  }>;
  export_id: string;
  conversation_paths: string[];
  conversation_archives: ConversationArchive[];
  open_path: string;
  created_count: number;
  replaced_count: number;
}
export interface ExportDraft {
  formats: string[];
  includeMedia: boolean;
  downloadMedia: boolean;
  legacyHttp: boolean;
  visualLimit: number;
  audioLimit: number;
  largeLimit: number;
  allowPartial: boolean;
  output: string;
  startAt: string;
  endAt: string;
  messageTypes: string[];
  mediaCategories: string[];
}
export interface ConversationStatistics {
  conversation_id: string;
  display_name: string;
  kind: string;
  message_count: number;
  earliest_at?: string;
  latest_at?: string;
  by_message_type: Record<string, number>;
}
export interface AccountStatisticsReport {
  account_id: string;
  database_fingerprint: string;
  calculated_at: string;
  complete: boolean;
  stale: boolean;
  conversation_count: number;
  message_count: number;
  earliest_at?: string;
  latest_at?: string;
  by_conversation_kind: Record<string, number>;
  by_message_type: Record<string, number>;
  conversations: ConversationStatistics[];
}
export interface Bootstrap {
  version: string;
  settings: Settings;
  accounts: Account[];
  selected_account_id?: string;
  capabilities: Record<string, boolean>;
}
