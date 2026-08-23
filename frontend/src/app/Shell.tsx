import {
  ChevronLeft,
  Download,
  HardDrive,
  Home,
  Image,
  ListChecks,
  MessageCircle,
  Moon,
  Search,
  Settings2,
  ShieldCheck,
  Sun,
} from "lucide-react";
import { isMockBridge } from "../bridge";
import { useWorkbench } from "../store";
import type { ViewId } from "../types";
import { BrandMark } from "../ui/primitives";

const views: Array<{ id: ViewId; label: string; icon: typeof Home }> = [
  { id: "home", label: "首页", icon: Home },
  { id: "conversations", label: "会话浏览", icon: MessageCircle },
  { id: "search", label: "全局搜索", icon: Search },
  { id: "export", label: "导出工作台", icon: Download },
  { id: "media", label: "媒体完整性", icon: Image },
  { id: "tasks", label: "任务与记录", icon: ListChecks },
  { id: "settings", label: "设置", icon: Settings2 },
];

const pageCopy: Record<ViewId, [string, string]> = {
  home: ["本地概览", "账号、数据库覆盖和最近导出状态"],
  conversations: ["会话浏览", "选择会话并在右侧按需预览"],
  search: ["全局搜索", "直接查询只读快照，不建立正文索引"],
  export: ["导出工作台", "集中确认范围、媒体、格式和保存位置"],
  media: ["媒体完整性", "手动检查当前账号全部本地媒体"],
  tasks: ["任务与记录", "只保存导出数量、告警与结果路径"],
  settings: ["设置", "账号、目录与界面显示偏好"],
};

export function Sidebar() {
  const { view, setView, sidebarCollapsed, toggleSidebar, account, operations } =
    useWorkbench();
  const running = Object.values(operations).filter((item) =>
    ["pending", "running"].includes(item.status),
  ).length;
  return (
    <aside className={`sidebar ${sidebarCollapsed ? "is-collapsed" : ""}`}>
      <div className="brand-row">
        <BrandMark />
        <div className="brand-copy">
          <strong>ChatWechat</strong>
          <span>LOCAL ARCHIVE DESK</span>
        </div>
        <button
          className="icon-button sidebar-toggle"
          onClick={toggleSidebar}
          aria-label={sidebarCollapsed ? "展开侧栏" : "收起侧栏"}
        >
          <ChevronLeft size={17} />
        </button>
      </div>
      <nav aria-label="主导航">
        <p className="nav-caption">本地工作台</p>
        {views.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={`nav-item ${view === id ? "is-active" : ""}`}
            onClick={() => setView(id)}
            aria-current={view === id ? "page" : undefined}
          >
            <Icon size={18} />
            <span>{label}</span>
            {id === "tasks" && running > 0 && <b>{running}</b>}
          </button>
        ))}
      </nav>
      <div className="sidebar-spacer" />
      <section className="account-status">
        <div className="status-line">
          <i className={account?.coverage.complete ? "ok" : ""} />
          <span>{account?.coverage.complete ? "本地数据库就绪" : "等待账号授权"}</span>
        </div>
        <strong>{account?.display_name || "尚未选择账号"}</strong>
        <span>
          {account
            ? `${account.coverage.covered}/${account.coverage.total} 个数据库 · 离线`
            : "只读 · 手动触发"}
        </span>
      </section>
      <p className="build-label">
        DESKTOP BRIDGE · {isMockBridge() ? "MOCK" : "OFFLINE"}
      </p>
    </aside>
  );
}

export function Topbar() {
  const { view, settings, setView } = useWorkbench();
  const [title, subtitle] = pageCopy[view];
  const ThemeIcon =
    settings?.theme === "dark"
      ? Moon
      : settings?.theme === "light"
        ? Sun
        : Settings2;
  return (
    <header className="topbar">
      <div>
        <span className="eyebrow">{subtitle}</span>
        <h1>{title}</h1>
      </div>
      <div className="topbar-actions">
        <span className="privacy-chip">
          <ShieldCheck size={15} />
          只读快照
        </span>
        <button className="icon-button" onClick={() => setView("search")} aria-label="打开全局搜索">
          <Search size={18} />
        </button>
        <button className="icon-button" onClick={() => setView("settings")} aria-label="打开显示设置">
          <ThemeIcon size={18} />
        </button>
      </div>
    </header>
  );
}
