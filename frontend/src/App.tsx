import { useEffect, useMemo } from "react";
import { useWorkbench } from "./store";
import { Sidebar, Topbar } from "./app/Shell";
import { ErrorBanner } from "./app/Feedback";
import { applyTheme } from "./app/appearance";
import { BrandMark } from "./ui/primitives";
import { HomeView } from "./features/home/HomeView";
import { ConversationsView } from "./features/conversations/ConversationsView";
import { SearchView } from "./features/search/SearchView";
import { ExportView } from "./features/export/ExportView";
import { MediaView } from "./features/media/MediaView";
import { TasksView } from "./features/tasks/TasksView";
import { SettingsView } from "./features/settings/SettingsView";

export default function App() {
  const {
    initialize,
    initialized,
    loading,
    error,
    view,
    settings,
    sidebarCollapsed,
    account,
    contextVersion,
  } = useWorkbench();
  useEffect(() => {
    void initialize();
  }, [initialize]);
  useEffect(() => applyTheme(settings), [settings]);
  const content = useMemo(
    () =>
      ({
        home: <HomeView />,
        conversations: <ConversationsView />,
        search: <SearchView />,
        export: <ExportView />,
        media: <MediaView />,
        tasks: <TasksView />,
        settings: <SettingsView />,
      })[view],
    [view],
  );
  if (!initialized && loading)
    return (
      <div className="boot-screen">
        <BrandMark />
        <strong>ChatWechat</strong>
        <span>正在核对本地账号与数据库密钥</span>
        <div className="boot-line">
          <i />
        </div>
      </div>
    );
  if (!initialized)
    return (
      <div className="boot-screen boot-failed">
        <BrandMark />
        <strong>无法连接桌面服务</strong>
        <span>{error || "启动没有完成，请重试。"}</span>
        <button className="primary" onClick={() => void initialize()}>
          重新连接
        </button>
        <small>若仍无法进入，请关闭所有 ChatWechat 窗口后重新启动。</small>
      </div>
    );
  return (
    <div className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <Sidebar />
      <main id="main-content" className="main-canvas">
        <Topbar />
        <ErrorBanner />
        <div
          className="view-content"
          key={`${view}:${account?.account_id || "none"}:${contextVersion}`}
        >
          {content}
        </div>
      </main>
    </div>
  );
}
