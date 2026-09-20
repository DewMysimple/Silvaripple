import { useState } from "react";
import {
  Check,
  Download,
  FolderOpen,
  Monitor,
  ShieldCheck,
  Wifi,
} from "lucide-react";
import { useWorkbench } from "../../store";
import type { Settings } from "../../types";
import { PageIntro } from "../../ui/layout";
import { AccountsSettings } from "./AccountsSettings";
import { AppearanceSettings, PrivacySettings } from "./PreferencesSettings";
import { ArchiveSettings, MediaSettings } from "./ExportSettings";
import "./settings.css";

const SECTIONS = [
  {
    id: "accounts",
    label: "账号与数据",
    hint: "数据位置 · 读取授权",
    icon: FolderOpen,
  },
  {
    id: "appearance",
    label: "外观与显示",
    hint: "主题 · 字体 · 密度",
    icon: Monitor,
  },
  {
    id: "archive",
    label: "归档与存储",
    hint: "保存位置 · 目录结构",
    icon: Download,
  },
  { id: "media", label: "媒体恢复", hint: "联网补全 · 下载上限", icon: Wifi },
  {
    id: "privacy",
    label: "隐私与行为",
    hint: "本地数据边界",
    icon: ShieldCheck,
  },
] as const;
type SectionId = (typeof SECTIONS)[number]["id"];

export function SettingsView() {
  const { settings, saveSettings } = useWorkbench();
  const [section, setSection] = useState<SectionId>("accounts");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  if (!settings) return null;
  const save = async (value: Partial<Settings>) => {
    setSaving(true);
    setError("");
    try {
      await saveSettings(value);
      setSaved(true);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setSaving(false);
    }
  };
  const props = {
    settings,
    saving,
    onChange: (value: Partial<Settings>) => {
      void save(value);
    },
  };
  return (
    <div className="page settings-workspace">
      <PageIntro
        title="让工作台适合你的习惯"
        description="管理本机账号、显示偏好与新导出的默认设置。"
        action={
          <span
            className={`settings-save-status ${error ? "has-error" : ""}`}
            role="status"
          >
            {saving ? (
              "正在保存…"
            ) : error ? (
              "未能保存，请重试"
            ) : (
              <>
                <Check size={16} />
                {saved ? "更改已保存" : "更改后自动保存"}
              </>
            )}
          </span>
        }
      />
      <div className="settings-layout">
        <nav className="settings-navigation" aria-label="设置分类">
          {SECTIONS.map(({ id, label, hint, icon: Icon }) => (
            <button
              key={id}
              type="button"
              aria-current={section === id ? "page" : undefined}
              className={section === id ? "selected" : ""}
              onClick={() => setSection(id)}
            >
              <Icon size={19} />
              <span>
                <strong>{label}</strong>
                <small>{hint}</small>
              </span>
            </button>
          ))}
        </nav>
        <div className="settings-panels" key={section}>
          {error && (
            <p className="error-text settings-error" role="alert">
              {error}
            </p>
          )}
          {section === "accounts" && <AccountsSettings />}
          {section === "appearance" && <AppearanceSettings {...props} />}
          {section === "archive" && <ArchiveSettings {...props} />}
          {section === "media" && <MediaSettings {...props} />}
          {section === "privacy" && <PrivacySettings />}
        </div>
      </div>
    </div>
  );
}
