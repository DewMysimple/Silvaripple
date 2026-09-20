import {
  Archive,
  ArrowRight,
  Clock3,
  Download,
  FolderSearch,
  HardDrive,
  MessageCircle,
  ShieldCheck,
} from "lucide-react";
import { useWorkbench } from "../../store";
import type { MediaReport } from "../../types";
import { Panel, StatusBadge } from "../../ui/layout";
import { Stat } from "../../ui/primitives";
import { formatBytes, formatDate } from "../../utils/format";
import { operationIsRunning } from "../../utils/labels";
import { DataSourcePicker } from "../accounts/DataSourcePicker";
import { AccountOverview } from "./AccountOverview";
import { StatisticsPanel } from "./StatisticsPanel";
import "./home.css";

export function HomeView() {
  const {
    account,
    totalConversations,
    history,
    selected,
    operations,
    mediaScanOperationId,
    setView,
  } = useWorkbench();
  const exports = history
    .filter((item) => item.kind === "export" && item.status === "completed")
    .slice(0, 3);
  const mediaOperation = mediaScanOperationId
    ? operations[mediaScanOperationId]
    : undefined;
  const report =
    mediaOperation?.status === "completed"
      ? (mediaOperation.result as MediaReport | undefined)
      : undefined;
  const mediaStatus = operationIsRunning(mediaOperation?.status)
    ? "正在检查"
    : report
      ? `${report.recoverable} 项可恢复`
      : "按需检查";
  if (!account)
    return (
      <div className="page home-page home-setup-page">
        <div className="home-setup-heading">
          <span className="home-setup-icon">
            <FolderSearch size={29} />
          </span>
          <span className="eyebrow green">开始使用 ChatWechat</span>
          <h2>连接这台电脑上的微信数据</h2>
          <p>找到数据位置，选择你的账号，即可浏览和归档聊天。</p>
        </div>
        <ol className="home-setup-steps">
          <li className="active">
            <b>1</b>
            <span>
              定位数据<small>自动发现或选择目录</small>
            </span>
          </li>
          <li>
            <b>2</b>
            <span>
              选择账号<small>账号信息独立切换</small>
            </span>
          </li>
          <li>
            <b>3</b>
            <span>
              授权读取<small>本地只读解析</small>
            </span>
          </li>
        </ol>
        <Panel
          title="微信数据位置"
          description="检测常见文档与存储位置，也支持迁移后的数据目录。"
        >
          <DataSourcePicker showCurrent={false} />
        </Panel>
        <p className="home-privacy-note">
          <ShieldCheck size={17} />
          微信源数据始终只读，聊天内容只保留在本机。
        </p>
      </div>
    );
  return (
    <div className="page home-page">
      <AccountOverview />
      <section className="home-metrics" aria-label="当前账号概况">
        <Stat
          icon={MessageCircle}
          label="可用会话"
          value={totalConversations.toLocaleString()}
          detail="私聊与群聊"
        />
        <Stat
          icon={Archive}
          label="本次待导出"
          value={selected.length}
          detail="已选择的会话"
        />
        <Stat
          icon={HardDrive}
          label="本地数据"
          value={formatBytes(account.size_bytes)}
          detail={`${account.database_count} 个数据库`}
        />
        <Stat
          icon={Clock3}
          label="最近归档"
          value={
            exports.length ? formatDate(exports[0].completed_at) : "尚无归档"
          }
          detail={
            exports.length
              ? `${exports[0].conversation_count} 个会话 · ${exports[0].message_count.toLocaleString()} 条消息`
              : "从选择第一个会话开始"
          }
        />
      </section>
      <section className="home-shortcuts" aria-label="快捷工作台">
        <button onClick={() => setView("export")}>
          <span className="home-shortcut-icon">
            <Download size={22} />
          </span>
          <div>
            <strong>导出工作台</strong>
            <p>
              {selected.length
                ? `继续整理 ${selected.length} 个已选会话`
                : "设置时间、格式与保存位置"}
            </p>
          </div>
          <ArrowRight size={19} />
        </button>
        <button onClick={() => setView("media")}>
          <span className="home-shortcut-icon">
            <HardDrive size={22} />
          </span>
          <div>
            <strong>媒体完整性</strong>
            <p>检查图片、语音和文件 · {mediaStatus}</p>
          </div>
          <ArrowRight size={19} />
        </button>
      </section>
      <div className="home-insights-grid">
        <div className="home-insights-main">
          <StatisticsPanel />
        </div>
        <Panel
          title="近期归档"
          description="当前账号最近完成的导出。"
          className="home-recent-panel"
          action={
            <button className="text-button" onClick={() => setView("tasks")}>
              全部记录 <ArrowRight size={15} />
            </button>
          }
        >
          {exports.length ? (
            <div className="home-recent-list">
              {exports.map((item) => (
                <button key={item.history_id} onClick={() => setView("tasks")}>
                  <span className="home-recent-icon">
                    <Archive size={19} />
                  </span>
                  <div>
                    <strong>{item.conversation_count} 个会话已归档</strong>
                    <span>
                      {item.message_count.toLocaleString()} 条消息 ·{" "}
                      {formatDate(item.completed_at)}
                    </span>
                    <small>
                      {item.formats
                        .map((format) =>
                          format === "markdown"
                            ? "Markdown"
                            : format.toUpperCase(),
                        )
                        .join(" · ")}
                    </small>
                  </div>
                  <StatusBadge
                    tone={item.warnings.length ? "warning" : "success"}
                  >
                    {item.warnings.length ? "有提醒" : "已完成"}
                  </StatusBadge>
                </button>
              ))}
            </div>
          ) : (
            <div className="home-recent-empty">
              <span>
                <Archive size={26} />
              </span>
              <strong>第一份归档，从这里开始</strong>
              <p>完成导出后，可在这里查看结果，再到任务记录中打开归档目录。</p>
              <button
                className="secondary"
                onClick={() => setView("conversations")}
              >
                选择要保留的会话 <ArrowRight size={16} />
              </button>
            </div>
          )}
          <div className="home-archive-tip">
            <ShieldCheck size={18} />
            <p>同一会话保存到固定位置。再次导出会更新归档，避免重复副本。</p>
          </div>
        </Panel>
      </div>
    </div>
  );
}
