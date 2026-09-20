import { useState } from "react";
import { Check, FolderOpen } from "lucide-react";
import { invoke } from "../../bridge";
import type { ExportFolderLayout } from "../../types";
import { Panel, SettingRow } from "../../ui/layout";
import { GreenSwitch } from "../../ui/primitives";
import { clampDownloadLimit } from "../../utils/format";
import type { SettingsSectionProps } from "./settingsTypes";

const LAYOUTS: Array<{
  value: ExportFolderLayout;
  title: string;
  example: string;
}> = [
  { value: "by_type", title: "按会话类型", example: "私聊 / 好友名称" },
  { value: "flat", title: "扁平存放", example: "好友名称" },
  {
    value: "account_by_type",
    title: "按账号与类型",
    example: "账号 / 私聊 / 好友名称",
  },
];

export function ArchiveSettings({
  settings,
  saving,
  onChange,
}: SettingsSectionProps) {
  const [error, setError] = useState("");
  const chooseOutput = async () => {
    setError("");
    try {
      const result = await invoke<{ path?: string }>("choose_folder");
      if (result.path) onChange({ output_directory: result.path });
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  };
  return (
    <>
      <Panel
        title="保存位置"
        description="设置新导出草稿的默认目录；当前草稿可在导出工作台中单独调整。"
      >
        <div className="settings-output-path">
          <div>
            <span>默认输出目录</span>
            <code>{settings.output_directory || "尚未设置"}</code>
          </div>
          <button
            className="secondary"
            disabled={saving}
            onClick={() => void chooseOutput()}
          >
            <FolderOpen size={16} />
            更改目录
          </button>
        </div>
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
        <SettingRow
          title="导出完成后打开目录"
          description="关闭后，仍可从结果或任务记录中打开。"
        >
          <GreenSwitch
            label="导出完成后自动打开目录"
            disabled={saving}
            checked={settings.open_result_folder_after_export}
            onChange={(value) =>
              onChange({ open_result_folder_after_export: value })
            }
          />
        </SettingRow>
      </Panel>
      <Panel
        title="归档目录结构"
        description="同一会话更新到固定目录。更换结构后，下次导出会迁移对应归档。"
      >
        <div
          className="settings-layout-options"
          role="group"
          aria-label="导出目录结构"
        >
          {LAYOUTS.map((layout) => (
            <button
              key={layout.value}
              type="button"
              aria-pressed={settings.export_folder_layout === layout.value}
              disabled={saving}
              className={
                settings.export_folder_layout === layout.value ? "selected" : ""
              }
              onClick={() => onChange({ export_folder_layout: layout.value })}
            >
              <span className="settings-layout-option-icon">
                <FolderOpen size={21} />
              </span>
              <strong>{layout.title}</strong>
              <code>{layout.example}</code>
              <span className="settings-layout-check">
                {settings.export_folder_layout === layout.value && (
                  <Check size={15} />
                )}
              </span>
            </button>
          ))}
        </div>
      </Panel>
    </>
  );
}

function DownloadLimit({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: number;
  disabled: boolean;
  onChange(value: number): void;
}) {
  const [draft, setDraft] = useState(String(value));
  const commit = () => {
    const next = clampDownloadLimit(Number(draft));
    setDraft(String(next));
    if (next !== value) onChange(next);
  };
  return (
    <label className="settings-download-limit">
      <span>{label}</span>
      <div>
        <input
          aria-label={`${label}下载上限`}
          type="number"
          min="1"
          max="2048"
          disabled={disabled}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") event.currentTarget.blur();
          }}
        />
        <em>MiB</em>
      </div>
    </label>
  );
}

export function MediaSettings({
  settings,
  saving,
  onChange,
}: SettingsSectionProps) {
  return (
    <>
      <Panel
        title="联网恢复默认值"
        description="应用于新建导出；可以在每次导出前调整。"
      >
        <SettingRow
          title="联网补全腾讯媒体"
          description="本地缺失时，尝试从消息引用的腾讯媒体地址恢复。"
        >
          <GreenSwitch
            label="默认联网补全腾讯媒体"
            disabled={saving}
            checked={settings.download_missing_media_default}
            onChange={(value) =>
              onChange({ download_missing_media_default: value })
            }
          />
        </SettingRow>
        <SettingRow
          title="兼容旧版表情下载"
          description="允许指定腾讯域名的旧 HTTP 表情地址，下载后校验内容。"
        >
          <GreenSwitch
            label="默认允许旧腾讯 HTTP 表情地址"
            disabled={saving}
            checked={settings.allow_legacy_http_media_default}
            onChange={(value) =>
              onChange({ allow_legacy_http_media_default: value })
            }
          />
        </SettingRow>
      </Panel>
      <Panel
        title="单个文件下载上限"
        description="限制每个联网下载文件的大小，可设置 1–2048 MiB。"
      >
        <div className="settings-download-limits">
          <DownloadLimit
            key={`visual-${settings.visual_download_limit_mib}`}
            label="图片 / 表情"
            value={settings.visual_download_limit_mib}
            disabled={saving}
            onChange={(value) => onChange({ visual_download_limit_mib: value })}
          />
          <DownloadLimit
            key={`audio-${settings.audio_download_limit_mib}`}
            label="语音"
            value={settings.audio_download_limit_mib}
            disabled={saving}
            onChange={(value) => onChange({ audio_download_limit_mib: value })}
          />
          <DownloadLimit
            key={`large-${settings.large_download_limit_mib}`}
            label="视频 / 文件"
            value={settings.large_download_limit_mib}
            disabled={saving}
            onChange={(value) => onChange({ large_download_limit_mib: value })}
          />
        </div>
        <p className="settings-footnote">
          超过上限的文件会在导出结果中说明，不会静默跳过。
        </p>
      </Panel>
    </>
  );
}
