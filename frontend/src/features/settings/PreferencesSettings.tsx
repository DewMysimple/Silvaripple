import { HardDrive, Search, ShieldCheck } from "lucide-react";
import type { Settings, Theme } from "../../types";
import { Panel, SettingRow } from "../../ui/layout";
import type { SettingsSectionProps } from "./settingsTypes";

export function AppearanceSettings({
  settings,
  saving,
  onChange,
}: SettingsSectionProps) {
  return (
    <Panel
      title="外观与显示"
      description="改变界面呈现方式，不影响聊天和导出内容。"
    >
      <SettingRow
        title="主题"
        description="自动跟随 Windows，或固定你习惯的明暗模式。"
      >
        <select
          aria-label="主题"
          disabled={saving}
          value={settings.theme}
          onChange={(event) => onChange({ theme: event.target.value as Theme })}
        >
          <option value="system">跟随系统</option>
          <option value="light">浅色模式</option>
          <option value="dark">深色模式</option>
        </select>
      </SettingRow>
      <SettingRow title="字体大小" description="统一调整会话、表单与数据文字。">
        <select
          aria-label="字体大小"
          disabled={saving}
          value={settings.font_scale}
          onChange={(event) =>
            onChange({
              font_scale: event.target.value as Settings["font_scale"],
            })
          }
        >
          <option value="small">较小</option>
          <option value="standard">标准</option>
          <option value="large">较大</option>
        </select>
      </SettingRow>
      <SettingRow
        title="界面密度"
        description="舒适模式留出更多间距；紧凑模式显示更多会话。"
      >
        <select
          aria-label="界面密度"
          disabled={saving}
          value={settings.density}
          onChange={(event) =>
            onChange({ density: event.target.value as Settings["density"] })
          }
        >
          <option value="comfortable">舒适</option>
          <option value="compact">紧凑</option>
        </select>
      </SettingRow>
      <div className="settings-display-preview" aria-label="当前显示效果预览">
        <span className="settings-preview-icon">聊</span>
        <div>
          <strong>聊天记录的阅读体验</strong>
          <p>文字、间距与主题会立即应用到整个工作台。</p>
        </div>
        <span className="settings-preview-tag">预览</span>
      </div>
    </Panel>
  );
}

const PRIVACY_ITEMS = [
  {
    icon: ShieldCheck,
    title: "微信源数据始终只读",
    text: "解析使用临时数据库快照。浏览、搜索与选择会话不会修改微信源文件。",
  },
  {
    icon: Search,
    title: "搜索与预览随退出清除",
    text: "不建立聊天全文搜索索引。搜索词、结果、预览与导出选择只保留在本次运行期间。",
  },
  {
    icon: HardDrive,
    title: "归档由你主动保存",
    text: "联网补全的媒体仅写入你选择的导出目录。任务记录只保存结果信息，不保存聊天正文。",
  },
];

export function PrivacySettings() {
  return (
    <Panel title="本地数据边界" description="以下行为始终生效，无需额外开启。">
      <div className="settings-privacy-list">
        {PRIVACY_ITEMS.map(({ icon: Icon, title, text }) => (
          <article key={title}>
            <span>
              <Icon size={22} />
            </span>
            <div>
              <strong>{title}</strong>
              <p>{text}</p>
            </div>
          </article>
        ))}
      </div>
    </Panel>
  );
}
