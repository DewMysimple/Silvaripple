import {
  Check,
  FileCode2,
  FileJson2,
  FileText,
  FolderOpen,
} from "lucide-react";
import type { ExportDraft, ExportFolderLayout } from "../../types";
import { ChipGroup, Panel, SettingRow } from "../../ui/layout";
import { GreenSwitch } from "../../ui/primitives";
import { clampDownloadLimit } from "../../utils/format";
import { MEDIA_TYPES } from "../../utils/labels";
import { EXPORT_FORMATS, folderLayoutDescription } from "./model";

type DraftProps = {
  draft: ExportDraft;
  onChange(value: Partial<ExportDraft>): void;
};
const formatIcons = { html: FileCode2, markdown: FileText, json: FileJson2 };

export function ExportFormats({ draft, onChange }: DraftProps) {
  return (
    <Panel
      title="02 · 保存哪些内容"
      description="可同时生成多种格式，内容与消息范围保持一致。"
    >
      <fieldset className="export-format-field">
        <legend className="sr-only">输出格式（可多选）</legend>
        <div className="export-format-grid">
          {EXPORT_FORMATS.map((format) => {
            const checked = draft.formats.includes(format.value);
            const Icon = formatIcons[format.value];
            return (
              <label
                className={`export-format-option ${checked ? "selected" : ""}`}
                key={format.value}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() =>
                    onChange({
                      formats: checked
                        ? draft.formats.filter(
                            (value) => value !== format.value,
                          )
                        : [...draft.formats, format.value],
                    })
                  }
                />
                <div className="export-format-top">
                  <Icon size={23} />
                  <span aria-hidden="true" className="export-format-check">
                    {checked && <Check size={13} />}
                  </span>
                </div>
                <strong>{format.label}</strong>
                <span>{format.extension}</span>
                <small>{format.description}</small>
              </label>
            );
          })}
        </div>
      </fieldset>
      <div className="export-media-options">
        <SettingRow
          title="包含聊天中的媒体"
          description="一同保存图片、表情、语音、视频和文件。"
        >
          <GreenSwitch
            label="包含聊天中的媒体"
            checked={draft.includeMedia}
            onChange={(includeMedia) => onChange({ includeMedia })}
          />
        </SettingRow>
        <SettingRow
          title="补全本地缺失的媒体"
          description={
            draft.includeMedia
              ? "需要联网，仅尝试恢复微信提供的媒体资源。"
              : "开启“包含聊天中的媒体”后可用。"
          }
        >
          <GreenSwitch
            label="补全本地缺失的媒体"
            checked={draft.includeMedia && draft.downloadMedia}
            disabled={!draft.includeMedia}
            onChange={(downloadMedia) => onChange({ downloadMedia })}
          />
        </SettingRow>
      </div>
    </Panel>
  );
}

export function ExportAdvanced({ draft, onChange }: DraftProps) {
  const downloading = draft.includeMedia && draft.downloadMedia;
  return (
    <details className="export-disclosure export-advanced">
      <summary>
        <span>
          高级选项<small>媒体类别、单文件上限与兼容设置</small>
        </span>
      </summary>
      <div className="export-disclosure-body">
        <fieldset
          className="export-dependent-options"
          disabled={!draft.includeMedia}
        >
          <ChipGroup
            label="归档的媒体类别"
            options={MEDIA_TYPES}
            value={draft.mediaCategories}
            onChange={(mediaCategories) => onChange({ mediaCategories })}
          />
        </fieldset>
        <fieldset className="export-download-limits" disabled={!downloading}>
          <legend>单个媒体的下载上限</legend>
          <p>本地已有文件不受此限制。每项可设置为 1–2048 MiB。</p>
          <div>
            {(
              [
                { key: "visualLimit", label: "图片 / 表情" },
                { key: "audioLimit", label: "语音" },
                { key: "largeLimit", label: "视频 / 文件" },
              ] as const
            ).map((item) => (
              <label key={item.key}>
                <span>{item.label}</span>
                <div>
                  <input
                    type="number"
                    min={1}
                    max={2048}
                    value={draft[item.key]}
                    onChange={(event) =>
                      onChange({
                        [item.key]: clampDownloadLimit(
                          Number(event.target.value),
                        ),
                      })
                    }
                  />
                  <span>MiB</span>
                </div>
              </label>
            ))}
          </div>
        </fieldset>
        <SettingRow
          title="兼容旧版微信表情"
          description="允许通过经过校验的腾讯旧版 HTTP 地址恢复表情。"
          warning
        >
          <GreenSwitch
            label="兼容旧版微信表情"
            checked={downloading && draft.legacyHttp}
            disabled={!downloading}
            onChange={(legacyHttp) => onChange({ legacyHttp })}
          />
        </SettingRow>
        <SettingRow
          title="允许部分导出"
          description="数据库覆盖不完整时仍继续，归档可能缺少部分聊天记录。"
          warning
        >
          <GreenSwitch
            label="允许部分导出"
            checked={draft.allowPartial}
            onChange={(allowPartial) => onChange({ allowPartial })}
          />
        </SettingRow>
      </div>
    </details>
  );
}

export function ExportDestination({
  draft,
  layout,
  onChoose,
  onOpen,
}: {
  draft: ExportDraft;
  layout?: ExportFolderLayout;
  onChoose(): void;
  onOpen(path: string): void;
}) {
  return (
    <Panel
      title="03 · 保存位置"
      description={folderLayoutDescription(layout)}
      action={
        <button className="secondary" onClick={onChoose}>
          <FolderOpen size={16} />
          {draft.output ? "更改位置" : "选择文件夹"}
        </button>
      }
    >
      <div className="export-output-path">
        <FolderOpen size={21} />
        <span>{draft.output || "尚未设置保存位置"}</span>
        {draft.output && (
          <button className="text-button" onClick={() => onOpen(draft.output)}>
            打开
          </button>
        )}
      </div>
      <p className="export-destination-note">
        再次导出同一会话时，将更新该会话的已有归档。
      </p>
    </Panel>
  );
}
