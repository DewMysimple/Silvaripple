import type { Account, Settings } from "../types";

export const exampleSettings: Settings = {
  data_root: "test-data",
  data_root_mode: "manual",
  output_directory: "test-output",
  theme: "light",
  conversation_kind: "all",
  last_account_id: "account-a",
  font_scale: "standard",
  density: "comfortable",
  download_missing_media_default: true,
  allow_legacy_http_media_default: false,
  visual_download_limit_mib: 50,
  audio_download_limit_mib: 100,
  large_download_limit_mib: 500,
  open_result_folder_after_export: false,
  export_folder_layout: "by_type",
};

export const exampleAccount: Account = {
  account_id: "account-a",
  display_name: "示例账号",
  active: true,
  size_bytes: 0,
  database_count: 1,
  directory: "test-data/account-a",
  coverage: { covered: 1, total: 1, complete: true, missing_databases: [] },
};

export function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
