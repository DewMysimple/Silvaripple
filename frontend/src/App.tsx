import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  AlertTriangle,
  Archive,
  ArrowRight,
  BarChart3,
  Check,
  ChevronDown,
  ChevronLeft,
  Clock3,
  Database,
  Download,
  FileSearch,
  FolderOpen,
  HardDrive,
  Home,
  Image,
  ListChecks,
  Menu,
  MessageCircle,
  Moon,
  MoreHorizontal,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Sun,
  Trash2,
  X,
} from "lucide-react";
import { invoke, isMockBridge } from "./bridge";
import { useWorkbench } from "./store";
import type {
  Account,
  AccountStatisticsReport,
  Conversation,
  ExportEstimate,
  ExportFolderLayout,
  ExportResult,
  HistoryEntry,
  MediaReport,
  Message,
  Operation,
  SearchItem,
  Settings,
  Theme,
  ViewId,
} from "./types";

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

const formatBytes = (value = 0) => {
  if (!value) return "0 B";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  const index = Math.min(
    units.length - 1,
    Math.floor(Math.log(value) / Math.log(1024)),
  );
  return `${(value / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
};
const formatDate = (value?: string) =>
  value
    ? new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value))
    : "无时间记录";
const publicText = (value?: string) =>
  (value || "").replace(/wxid_[A-Za-z0-9_-]+/g, "未知成员");
const kindLabel = (value: string) =>
  ({ group: "群聊", private: "私聊", official: "公众号", business: "业务" })[
    value
  ] || "其他";
const clampDownloadLimit = (value: number) =>
  Math.min(2048, Math.max(1, Math.round(Number(value) || 1)));

function GreenSwitch({
  checked,
  disabled = false,
  onChange,
  label,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange(value: boolean): void;
  label: string;
}) {
  return (
    <input
      className="green-switch"
      type="checkbox"
      checked={checked}
      disabled={disabled}
      onChange={(event) => onChange(event.target.checked)}
      aria-label={label}
    />
  );
}

function BrandMark() {
  return (
    <div className="brand-mark" aria-hidden="true">
      <span />
      <span />
    </div>
  );
}

function Sidebar() {
  const {
    view,
    setView,
    sidebarCollapsed,
    toggleSidebar,
    account,
    operations,
  } = useWorkbench();
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
          <span>
            {account?.coverage.complete ? "本地数据库就绪" : "等待账号授权"}
          </span>
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

function Topbar() {
  const { view, settings, setView } = useWorkbench();
  const [title, subtitle] = pageCopy[view];
  const themeIcon =
    settings?.theme === "dark"
      ? Moon
      : settings?.theme === "light"
        ? Sun
        : Settings2;
  const ThemeIcon = themeIcon;
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
        <button
          className="icon-button"
          onClick={() => setView("search")}
          aria-label="打开全局搜索"
        >
          <Search size={18} />
        </button>
        <button
          className="icon-button"
          onClick={() => setView("settings")}
          aria-label="打开显示设置"
        >
          <ThemeIcon size={18} />
        </button>
      </div>
    </header>
  );
}

function EmptyState({
  icon: Icon,
  title,
  text,
  action,
}: {
  icon: typeof Search;
  title: string;
  text: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <Icon size={26} />
      </div>
      <strong>{title}</strong>
      <p>{text}</p>
      {action}
    </div>
  );
}

function Stat({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: ReactNode;
  detail: string;
  icon: typeof Home;
}) {
  return (
    <article className="stat">
      <div className="stat-icon">
        <Icon size={18} />
      </div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function HomeView() {
  const {
    account,
    totalConversations,
    history,
    selected,
    operations,
    mediaScanOperationId,
    accountStatistics,
    accountStatisticsOperationId,
    startAccountStatisticsScan,
    setView,
  } = useWorkbench();
  const [statisticsOpen, setStatisticsOpen] = useState(false);
  const [statisticsQuery, setStatisticsQuery] = useState("");
  const [statisticsSort, setStatisticsSort] = useState<
    "count" | "name" | "latest"
  >("count");
  const last = history.find(
    (item) => item.kind === "export" && item.status === "completed",
  );
  const mediaOperation = mediaScanOperationId
    ? operations[mediaScanOperationId]
    : undefined;
  const statisticsOperation = accountStatisticsOperationId
    ? (operations[accountStatisticsOperationId] as
        | Operation<AccountStatisticsReport>
        | undefined)
    : undefined;
  const mediaReport =
    mediaOperation?.status === "completed"
      ? (mediaOperation.result as MediaReport | undefined)
      : undefined;
  const coverage = account?.coverage.total
    ? Math.round((account.coverage.covered / account.coverage.total) * 100)
    : 0;
  const displayName = account?.display_name || "尚未选择本地账号";
  const mediaStatus =
    mediaOperation && ["pending", "running"].includes(mediaOperation.status)
      ? `正在检查 · ${Math.round(mediaOperation.progress * 100)}%`
      : mediaReport
        ? `可恢复 ${mediaReport.recoverable} 项 · 待处理 ${mediaReport.missing + mediaReport.unsupported} 项`
        : "尚未检查";
  const scanning =
    statisticsOperation &&
    ["pending", "running"].includes(statisticsOperation.status);
  const detail = statisticsOperation?.progress_detail;
  const statisticRows = useMemo(() => {
    const query = statisticsQuery.trim().toLocaleLowerCase();
    const rows = (accountStatistics?.conversations || []).filter(
      (item) => !query || item.display_name.toLocaleLowerCase().includes(query),
    );
    return [...rows].sort((a, b) =>
      statisticsSort === "name"
        ? a.display_name.localeCompare(b.display_name, "zh-CN")
        : statisticsSort === "latest"
          ? String(b.latest_at || "").localeCompare(String(a.latest_at || ""))
          : b.message_count - a.message_count,
    );
  }, [accountStatistics, statisticsQuery, statisticsSort]);
  return (
    <div className="page home-page">
      <section className={`account-overview ${account ? "" : "is-empty"}`}>
        <div className="account-identity">
          <div className="home-account-avatar">
            {account?.avatar_data_url ? (
              <img
                src={account.avatar_data_url}
                alt={`${displayName}的账号头像`}
              />
            ) : (
              <span>{account ? displayName.slice(0, 1) : "微"}</span>
            )}
          </div>
          <div className="account-copy">
            <div className="account-labels">
              <span className="eyebrow green">当前本地账号</span>
              <em className={account?.coverage.complete ? "is-ready" : ""}>
                {account?.coverage.complete
                  ? "数据库已就绪"
                  : account
                    ? "需要补充授权"
                    : "等待选择"}
              </em>
            </div>
            <h2>{displayName}</h2>
            <p>
              {account
                ? "所有内容均从本机临时只读快照读取；搜索、预览和会话选择不会写入微信数据。"
                : "选择一个已授权的本机微信账号后，即可浏览、检查和导出聊天记录。"}
            </p>
            {!account && (
              <button
                className="secondary compact"
                onClick={() => setView("settings")}
              >
                前往账号设置
              </button>
            )}
          </div>
        </div>
        <aside className="account-readiness" aria-label="账号读取状态">
          <div className="readiness-heading">
            <span>数据库密钥覆盖</span>
            <strong>
              {account
                ? `${account.coverage.covered}/${account.coverage.total}`
                : "—"}
            </strong>
          </div>
          <div
            className="coverage-track"
            aria-label={`数据库密钥覆盖 ${coverage}%`}
          >
            <i style={{ width: `${coverage}%` }} />
          </div>
          <dl>
            <div>
              <dt>读取方式</dt>
              <dd>本地只读</dd>
            </div>
            <div>
              <dt>账号数据</dt>
              <dd>{account ? formatBytes(account.size_bytes) : "—"}</dd>
            </div>
          </dl>
          <p>
            <ShieldCheck size={15} />
            不保存头像副本或内部账号标识
          </p>
        </aside>
      </section>
      <section className="stats-grid home-stats">
        <Stat
          icon={Database}
          label="数据库"
          value={account?.database_count || 0}
          detail={account?.coverage.complete ? "密钥覆盖完整" : "等待完整授权"}
        />
        <Stat
          icon={MessageCircle}
          label="可用会话"
          value={totalConversations}
          detail="私聊与群聊"
        />
        <Stat
          icon={Archive}
          label="已选择"
          value={selected.length}
          detail="保留到本次退出"
        />
        <Stat
          icon={Clock3}
          label="最近导出"
          value={last ? formatDate(last.completed_at) : "暂无"}
          detail={last ? `${last.message_count} 条消息` : "尚无导出记录"}
        />
      </section>
      <section className="account-statistics-panel">
        <div className="statistics-intro">
          <span className="statistics-icon">
            <BarChart3 size={22} />
          </span>
          <div>
            <span className="eyebrow green">只读全量统计</span>
            <h3>
              {accountStatistics
                ? `${accountStatistics.message_count.toLocaleString()} 条聊天消息`
                : "扫描全部私聊与群聊"}
            </h3>
            <p>
              {accountStatistics
                ? `${accountStatistics.conversation_count} 个有效会话 · ${formatDate(accountStatistics.earliest_at)} 至 ${formatDate(accountStatistics.latest_at)}${accountStatistics.stale ? " · 数据已变化，建议重新扫描" : ""}`
                : "逐个读取全部消息分片，只保存会话名称和数量，不保存聊天正文。"}
            </p>
          </div>
        </div>
        <div className="statistics-actions">
          {accountStatistics && (
            <button
              className="secondary compact"
              onClick={() => setStatisticsOpen(!statisticsOpen)}
            >
              {statisticsOpen ? "收起完整统计" : "查看完整统计"}
            </button>
          )}
          <button
            className="primary compact"
            disabled={!account || Boolean(scanning)}
            onClick={() => void startAccountStatisticsScan()}
          >
            <RefreshCw size={15} />
            {accountStatistics ? "重新扫描" : "开始扫描"}
          </button>
        </div>
        {scanning && (
          <div className="statistics-progress">
            <Progress operation={statisticsOperation as Operation} />
            <div className="statistics-live">
              <span>
                阶段：
                {detail?.phase === "inventory"
                  ? "清点数据库"
                  : detail?.phase === "saving"
                    ? "保存汇总"
                    : "遍历消息"}
              </span>
              <span>
                已处理 {(detail?.processed_messages || 0).toLocaleString()} 条
              </span>
              <span>已识别 {detail?.conversation_count || 0} 个会话</span>
              {detail?.database && <span>{detail.database}</span>}
              <button
                className="text-button muted"
                onClick={() =>
                  void invoke(
                    "cancel_operation",
                    statisticsOperation?.operation_id,
                  )
                }
              >
                取消
              </button>
            </div>
          </div>
        )}
        {accountStatistics && (
          <div className="statistics-snapshot">
            <span>
              <b>{accountStatistics.by_conversation_kind.private || 0}</b> 私聊
            </span>
            <span>
              <b>{accountStatistics.by_conversation_kind.group || 0}</b> 群聊
            </span>
            {Object.entries(accountStatistics.by_message_type)
              .sort((a, b) => b[1] - a[1])
              .slice(0, 5)
              .map(([key, value]) => (
                <span key={key}>
                  <b>{value.toLocaleString()}</b> {key}
                </span>
              ))}
            <em>
              {accountStatistics.stale
                ? "统计已过期"
                : `更新于 ${formatDate(accountStatistics.calculated_at)}`}
            </em>
          </div>
        )}
      </section>
      {statisticsOpen && accountStatistics && (
        <section className="statistics-detail">
          <div className="section-toolbar">
            <div>
              <h3>逐会话统计</h3>
              <p>统计结果不包含消息正文、发送者和内部账号标识。</p>
            </div>
            <div className="statistics-controls">
              <label className="search-box">
                <Search size={15} />
                <input
                  value={statisticsQuery}
                  onChange={(event) => setStatisticsQuery(event.target.value)}
                  placeholder="搜索会话名称"
                />
              </label>
              <select
                value={statisticsSort}
                onChange={(event) =>
                  setStatisticsSort(event.target.value as typeof statisticsSort)
                }
              >
                <option value="count">消息最多</option>
                <option value="latest">最近活跃</option>
                <option value="name">名称排序</option>
              </select>
            </div>
          </div>
          <div className="statistics-table">
            <div className="statistics-table-head">
              <span>会话</span>
              <span>类型</span>
              <span>消息数量</span>
              <span>时间范围</span>
            </div>
            {statisticRows.map((item) => (
              <article key={item.conversation_id}>
                <strong>{publicText(item.display_name)}</strong>
                <span>{kindLabel(item.kind)}</span>
                <b>{item.message_count.toLocaleString()}</b>
                <small>
                  {formatDate(item.earliest_at)} — {formatDate(item.latest_at)}
                </small>
              </article>
            ))}
          </div>
        </section>
      )}
      <section className="workbench-launches" aria-label="工作台快捷入口">
        <button
          className="workbench-card workbench-primary"
          onClick={() => setView(account ? "conversations" : "settings")}
        >
          <span className="workbench-icon">
            <MessageCircle size={22} />
          </span>
          <span className="workbench-kicker">会话浏览</span>
          <strong>{account ? "浏览并选择聊天" : "先选择本地账号"}</strong>
          <p>
            {account
              ? "查看私聊和群聊，在固定预览区确认内容并加入导出。"
              : "完成账号授权后，聊天会话会显示在这里。"}
          </p>
          <span className="workbench-meta">
            {account ? `${totalConversations} 个可用会话` : "前往账号设置"}
            <ArrowRight size={16} />
          </span>
        </button>
        <button className="workbench-card" onClick={() => setView("export")}>
          <span className="workbench-icon">
            <Download size={22} />
          </span>
          <span className="workbench-kicker">导出工作台</span>
          <strong>
            {selected.length
              ? `继续整理 ${selected.length} 个会话`
              : "整理导出范围"}
          </strong>
          <p>设置时间、格式、媒体和保存位置。</p>
          <span className="workbench-meta">
            {selected.length ? "继续当前导出" : "开始准备导出"}
            <ArrowRight size={16} />
          </span>
        </button>
        <button className="workbench-card" onClick={() => setView("media")}>
          <span className="workbench-icon">
            <HardDrive size={22} />
          </span>
          <span className="workbench-kicker">媒体完整性</span>
          <strong>检查媒体可用性</strong>
          <p>扫描图片、表情、视频和文件的本地恢复状态。</p>
          <span className="workbench-meta">
            {mediaStatus}
            <ArrowRight size={16} />
          </span>
        </button>
      </section>
    </div>
  );
}

function ConversationRow({ item }: { item: Conversation }) {
  const { selected, toggleSelected, activeConversation, openConversation } =
    useWorkbench();
  const checked = selected.includes(item.conversation_id);
  return (
    <article
      className={`conversation-row ${activeConversation?.conversation_id === item.conversation_id ? "is-active" : ""}`}
      onClick={() => void openConversation(item)}
    >
      <button
        className={`check ${checked ? "checked" : ""}`}
        onClick={(event) => {
          event.stopPropagation();
          toggleSelected(item.conversation_id);
        }}
        aria-label={checked ? "取消选择" : "选择会话"}
      >
        {checked && <Check size={13} />}
      </button>
      {item.avatar_data_url ? (
        <img src={item.avatar_data_url} alt={`${item.display_name}头像`} />
      ) : (
        <div className="avatar-fallback">{item.display_name.slice(0, 1)}</div>
      )}
      <div className="conversation-copy">
        <strong>{publicText(item.display_name)}</strong>
        <span>最近 {formatDate(item.last_message_at)}</span>
      </div>
      <small>{kindLabel(item.kind)}</small>
    </article>
  );
}

function MessageBubble({ message }: { message: Message }) {
  if (message.system_event)
    return (
      <div className="system-message">
        {publicText(message.system_event.text)}
      </div>
    );
  const text =
    publicText(message.display_text || message.text) ||
    (message.attachments.length ? "" : `[${message.message_type}]`);
  const mediaOnly =
    !text && !message.quote_preview && message.attachments.length > 0;
  return (
    <article className={`message ${message.outgoing ? "outgoing" : ""}`}>
      <div className="message-avatar">
        {message.sender_avatar_data_url ? (
          <img src={message.sender_avatar_data_url} alt="发送者头像" />
        ) : (
          publicText(message.sender_name).slice(0, 1) || "未"
        )}
      </div>
      <div className="message-stack">
        <span className="message-sender">
          {publicText(message.sender_name) || "未知成员"}
        </span>
        <div className={`bubble ${mediaOnly ? "media-only" : ""}`}>
          {message.quote_preview && (
            <blockquote>
              <strong>
                {publicText(message.quote_preview.sender_name) || "未知成员"}
              </strong>
              <span>
                {publicText(message.quote_preview.text) ||
                  `[${message.quote_preview.message_type || "消息"}]`}
              </span>
            </blockquote>
          )}
          {text && <p>{text}</p>}
          {message.attachments.map((attachment) =>
            attachment.preview_data_url ? (
              <img
                className={
                  attachment.category === "emoji"
                    ? "emoji-media"
                    : "message-media"
                }
                src={attachment.preview_data_url}
                alt={attachment.category === "emoji" ? "表情包" : "聊天图片"}
                key={attachment.attachment_id}
              />
            ) : (
              <div className="media-placeholder" key={attachment.attachment_id}>
                <Image size={16} />
                <div>
                  <strong>
                    {attachment.category === "emoji"
                      ? "表情缓存不完整"
                      : attachment.category === "video"
                        ? "视频暂不可预览"
                        : attachment.category === "file"
                          ? "文件暂不可用"
                          : "媒体暂不可用"}
                  </strong>
                  <span>{attachment.reason || "导出时将继续尝试恢复"}</span>
                  {attachment.reason_code && (
                    <details>
                      <summary>诊断详情</summary>
                      <code>{attachment.reason_code}</code>
                    </details>
                  )}
                </div>
              </div>
            ),
          )}
        </div>
        <time>{formatDate(message.sent_at)}</time>
      </div>
    </article>
  );
}

function ConversationsView() {
  const {
    conversations,
    totalConversations,
    selected,
    selectVisible,
    clearSelected,
    ensureSelected,
    activeConversation,
    preview,
    previewTotal,
    previewOffset,
    loadOlder,
    loadConversations,
    loading,
    setView,
  } = useWorkbench();
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("all");
  const messagesRef = useRef<HTMLDivElement>(null);
  const streamRef = useRef<HTMLDivElement>(null);
  const pinLatest = useRef(true);
  const pinTimer = useRef<number | undefined>(undefined);
  const olderAnchor = useRef<
    { height: number; top: number; offset: number } | undefined
  >(undefined);
  useEffect(() => {
    const id = setTimeout(() => void loadConversations({ query, kind }), 240);
    return () => clearTimeout(id);
  }, [query, kind, loadConversations]);
  useLayoutEffect(() => {
    pinLatest.current = true;
    olderAnchor.current = undefined;
    if (pinTimer.current) window.clearTimeout(pinTimer.current);
  }, [activeConversation?.conversation_id]);
  useLayoutEffect(() => {
    const container = messagesRef.current;
    if (!container) return;
    const anchor = olderAnchor.current;
    if (anchor && previewOffset > anchor.offset) {
      container.scrollTop =
        anchor.top + (container.scrollHeight - anchor.height);
      olderAnchor.current = undefined;
      pinLatest.current = false;
      return;
    }
    if (!preview.length || !pinLatest.current) return;
    const frame = window.requestAnimationFrame(() => {
      container.scrollTop = container.scrollHeight;
    });
    if (pinTimer.current) window.clearTimeout(pinTimer.current);
    pinTimer.current = window.setTimeout(() => {
      pinLatest.current = false;
    }, 1800);
    return () => window.cancelAnimationFrame(frame);
  }, [activeConversation?.conversation_id, preview.length, previewOffset]);
  useEffect(() => {
    const container = messagesRef.current;
    const stream = streamRef.current;
    if (!container || !stream || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (pinLatest.current) container.scrollTop = container.scrollHeight;
    });
    observer.observe(stream);
    return () => observer.disconnect();
  }, [activeConversation?.conversation_id]);
  useEffect(
    () => () => {
      if (pinTimer.current) window.clearTimeout(pinTimer.current);
    },
    [],
  );
  const stopPinning = () => {
    pinLatest.current = false;
    if (pinTimer.current) window.clearTimeout(pinTimer.current);
  };
  const loadEarlier = async () => {
    const container = messagesRef.current;
    if (!container) return;
    stopPinning();
    olderAnchor.current = {
      height: container.scrollHeight,
      top: container.scrollTop,
      offset: previewOffset,
    };
    await loadOlder();
  };
  return (
    <div className="page conversation-page">
      <section className="conversation-browser">
        <div className="conversation-toolbar">
          <label className="search-box">
            <Search size={17} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索会话名称"
            />
          </label>
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value)}
          >
            <option value="all">私聊与群聊</option>
            <option value="private">私聊</option>
            <option value="group">群聊</option>
          </select>
        </div>
        <div className="selection-bar">
          <span>
            {totalConversations} 个会话 · 已选择 {selected.length}
          </span>
          <div>
            <button className="text-button" onClick={selectVisible}>
              选择当前列表
            </button>
            {selected.length > 0 && (
              <button className="text-button muted" onClick={clearSelected}>
                清空
              </button>
            )}
          </div>
        </div>
        <div className="conversation-list">
          {loading && !conversations.length
            ? Array.from({ length: 7 }, (_, index) => (
                <div className="skeleton-row" key={index} />
              ))
            : conversations.map((item) => (
                <ConversationRow item={item} key={item.conversation_id} />
              ))}
        </div>
      </section>
      <section className="preview-panel">
        {activeConversation ? (
          <>
            <header className="preview-header">
              <div>
                <strong>{publicText(activeConversation.display_name)}</strong>
                <span>{previewTotal} 条消息 · 本地按需读取</span>
              </div>
              <button
                className="secondary compact"
                title="保留已选择的其他会话"
                onClick={() => {
                  ensureSelected(activeConversation.conversation_id);
                  setView("export");
                }}
              >
                加入导出
              </button>
            </header>
            <div
              className="messages"
              ref={messagesRef}
              onWheel={stopPinning}
              onPointerDown={stopPinning}
              onTouchStart={stopPinning}
            >
              <div className="message-stream" ref={streamRef}>
                {previewOffset < previewTotal && (
                  <button
                    className="load-older"
                    onClick={() => void loadEarlier()}
                  >
                    加载更早的100条
                  </button>
                )}
                {preview.map((message) => (
                  <MessageBubble message={message} key={message.message_id} />
                ))}
              </div>
            </div>
          </>
        ) : (
          <EmptyState
            icon={MessageCircle}
            title="选择一个会话"
            text="聊天预览会固定显示在这里，不再打开遮挡界面的弹窗。"
          />
        )}
      </section>
    </div>
  );
}

function SearchView() {
  const {
    account,
    selected,
    trackOperation,
    pollOperation,
    openConversation,
    conversations,
    setView,
  } = useWorkbench();
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<SearchItem[]>([]);
  const [operation, setOperation] =
    useState<Operation<{ items: SearchItem[] }>>();
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  const [messageType, setMessageType] = useState("all");
  const [selectedOnly, setSelectedOnly] = useState(false);
  useEffect(() => {
    if (!selected.length) setSelectedOnly(false);
  }, [selected.length]);
  const running = operation
    ? ["pending", "running"].includes(operation.status)
    : false;
  const run = async () => {
    if (!account || !query.trim()) return;
    setItems([]);
    try {
      const start = await invoke<Operation>("search_messages", {
        account_id: account.account_id,
        query,
        limit: 300,
        start_at: startAt || null,
        end_at: endAt || null,
        message_types: messageType === "all" ? [] : [messageType],
        conversation_ids: selectedOnly ? selected : [],
      });
      trackOperation(start);
      setOperation(start as Operation<{ items: SearchItem[] }>);
      const done = await pollOperation<{ items: SearchItem[] }>(
        start.operation_id,
      );
      setOperation(done);
      setItems(done.result?.items || []);
    } catch (error) {
      setOperation({
        operation_id: "",
        kind: "search",
        status: "failed",
        progress: 0,
        message: "搜索失败",
        error: String(error),
        created_at: new Date().toISOString(),
      });
    }
  };
  return (
    <div className="page constrained search-page">
      <section className="search-hero">
        <FileSearch size={31} />
        <h2>搜索全部聊天记录</h2>
        <p>每次搜索都重新读取临时快照。关键词和结果不会写入磁盘。</p>
        <div className="global-search">
          <Search size={20} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && void run()}
            placeholder="输入消息正文关键词"
          />
          <button
            className="primary"
            disabled={!query.trim() || running}
            onClick={() => void run()}
          >
            {running ? "正在搜索" : "开始搜索"}
          </button>
        </div>
        <div className="search-filters">
          <label>
            <span>开始日期</span>
            <input
              type="date"
              value={startAt}
              onChange={(event) => setStartAt(event.target.value)}
            />
          </label>
          <label>
            <span>结束日期</span>
            <input
              type="date"
              value={endAt}
              onChange={(event) => setEndAt(event.target.value)}
            />
          </label>
          <label>
            <span>消息类型</span>
            <select
              value={messageType}
              onChange={(event) => setMessageType(event.target.value)}
            >
              <option value="all">全部类型</option>
              <option value="text">文本</option>
              <option value="image">图片</option>
              <option value="emoji">表情包</option>
              <option value="file">文件</option>
              <option value="audio">语音</option>
            </select>
          </label>
          <label
            className={`inline-check ${!selected.length ? "disabled" : ""}`}
          >
            <input
              className="green-check"
              type="checkbox"
              checked={selectedOnly}
              disabled={!selected.length}
              onChange={(event) => setSelectedOnly(event.target.checked)}
            />
            <span>仅搜索已选择的 {selected.length} 个会话</span>
          </label>
        </div>
      </section>
      {running && (
        <>
          <Progress operation={operation as Operation} />
          <section className="search-skeleton" aria-label="正在加载搜索结果">
            {Array.from({ length: 4 }, (_, index) => (
              <div key={index}>
                <i />
                <span />
              </div>
            ))}
          </section>
        </>
      )}
      {operation?.status === "failed" && (
        <section className="search-error" role="alert">
          <strong>搜索未完成</strong>
          <p>{operation.error || "读取临时快照时发生错误，请稍后重试。"}</p>
          <button className="secondary compact" onClick={() => void run()}>
            重新搜索
          </button>
        </section>
      )}
      {items.length ? (
        <section className="result-list">
          {items.map((item) => (
            <button
              key={item.message_id}
              className="search-result"
              onClick={() => {
                const conversation = conversations.find(
                  (row) => row.conversation_id === item.conversation_id,
                ) ?? {
                  conversation_id: item.conversation_id,
                  display_name: item.conversation_name,
                  kind: item.conversation_kind,
                  unread_count: 0,
                };
                void openConversation(conversation);
                setView("conversations");
              }}
            >
              <div>
                <strong>{item.conversation_name}</strong>
                <span>
                  {item.sender_name} · {formatDate(item.sent_at)}
                </span>
              </div>
              <p>{item.snippet}</p>
            </button>
          ))}
        </section>
      ) : operation?.status === "completed" ? (
        <EmptyState
          icon={Search}
          title="没有匹配结果"
          text="换一个关键词，或先确认相应数据库已经授权。"
        />
      ) : !operation ? (
        <div className="search-idle">
          <Search size={20} />
          <span>输入关键词后开始搜索，最多显示 300 条结果。</span>
        </div>
      ) : null}
    </div>
  );
}

function Progress({ operation }: { operation: Operation }) {
  return (
    <div className="progress-card">
      <div>
        <strong>{operation.message}</strong>
        <span>{Math.round(operation.progress * 100)}%</span>
      </div>
      <div className="progress-track">
        <i style={{ width: `${Math.max(2, operation.progress * 100)}%` }} />
      </div>
      {operation.error && <p className="error-text">{operation.error}</p>}
    </div>
  );
}

function ExportView() {
  const workbench = useWorkbench();
  const {
    account,
    selected,
    settings,
    conversations,
    operations,
    exportOperationId,
    setExportOperationId,
    mediaScanOperationId,
    startMediaScan,
    trackOperation,
    pollOperation,
    refreshHistory,
    exportDraft,
    updateExportDraft,
    toggleSelected,
    clearSelected,
    setView,
  } = workbench;
  const draft = exportDraft ?? {
    formats: ["html", "markdown", "json"],
    includeMedia: true,
    downloadMedia: true,
    legacyHttp: true,
    visualLimit: 50,
    audioLimit: 100,
    largeLimit: 500,
    allowPartial: false,
    output: settings?.output_directory || "",
    startAt: "",
    endAt: "",
    messageTypes: [],
    mediaCategories: [],
  };
  const {
    formats,
    includeMedia,
    downloadMedia,
    legacyHttp,
    visualLimit,
    audioLimit,
    largeLimit,
    allowPartial,
    output,
    startAt,
    endAt,
    messageTypes,
    mediaCategories,
  } = draft;
  const setFormats = (value: string[]) => updateExportDraft({ formats: value });
  const setIncludeMedia = (value: boolean) =>
    updateExportDraft({ includeMedia: value });
  const setDownloadMedia = (value: boolean) =>
    updateExportDraft({ downloadMedia: value });
  const setLegacyHttp = (value: boolean) =>
    updateExportDraft({ legacyHttp: value });
  const setVisualLimit = (value: number) =>
    updateExportDraft({ visualLimit: value });
  const setAudioLimit = (value: number) =>
    updateExportDraft({ audioLimit: value });
  const setLargeLimit = (value: number) =>
    updateExportDraft({ largeLimit: value });
  const setAllowPartial = (value: boolean) =>
    updateExportDraft({ allowPartial: value });
  const setOutput = (value: string) => updateExportDraft({ output: value });
  const setStartAt = (value: string) => updateExportDraft({ startAt: value });
  const setEndAt = (value: string) => updateExportDraft({ endAt: value });
  const setMessageTypes = (value: string[]) =>
    updateExportDraft({ messageTypes: value });
  const setMediaCategories = (value: string[]) =>
    updateExportDraft({ mediaCategories: value });
  const [estimate, setEstimate] = useState<ExportEstimate>();
  const [estimating, setEstimating] = useState(false);
  const [estimateError, setEstimateError] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [listQuery, setListQuery] = useState("");
  const operation = exportOperationId
    ? (operations[exportOperationId] as Operation<ExportResult> | undefined)
    : undefined;
  const mediaOperation = mediaScanOperationId
    ? (operations[mediaScanOperationId] as Operation<MediaReport> | undefined)
    : undefined;
  const estimateVersion = useRef(0);
  const estimateCompleted = useRef(0);
  const estimateRunning = useRef(false);
  const latestPayload = useRef<Record<string, unknown>>({});
  const payload = useMemo(
    () => ({
      account_id: account?.account_id,
      conversation_ids: selected,
      output_directory: output,
      folder_layout: settings?.export_folder_layout ?? "by_type",
      start_at: startAt ? `${startAt}T00:00:00` : null,
      end_at: endAt ? `${endAt}T23:59:59` : null,
      formats,
      include_media: includeMedia,
      download_missing_media: includeMedia && downloadMedia,
      allow_legacy_http_media: includeMedia && downloadMedia && legacyHttp,
      visual_download_limit_mib: clampDownloadLimit(visualLimit),
      audio_download_limit_mib: clampDownloadLimit(audioLimit),
      large_download_limit_mib: clampDownloadLimit(largeLimit),
      allow_partial: allowPartial,
      message_types: messageTypes,
      media_categories: mediaCategories,
    }),
    [
      account?.account_id,
      settings?.export_folder_layout,
      selected,
      output,
      startAt,
      endAt,
      formats,
      includeMedia,
      downloadMedia,
      legacyHttp,
      visualLimit,
      audioLimit,
      largeLimit,
      allowPartial,
      messageTypes,
      mediaCategories,
    ],
  );
  const pumpEstimate = async () => {
    if (estimateRunning.current) return;
    estimateRunning.current = true;
    setEstimating(true);
    try {
      while (estimateCompleted.current < estimateVersion.current) {
        const version = estimateVersion.current;
        const current = { ...latestPayload.current };
        try {
          const result = await invoke<ExportEstimate>(
            "estimate_export",
            current,
          );
          if (version === estimateVersion.current) {
            setEstimate(result);
            setEstimateError("");
          }
        } catch (error) {
          if (version === estimateVersion.current)
            setEstimateError(
              error instanceof Error ? error.message : String(error),
            );
        }
        estimateCompleted.current = version;
      }
    } finally {
      estimateRunning.current = false;
      setEstimating(false);
    }
  };
  useEffect(() => {
    latestPayload.current = payload;
    estimateVersion.current += 1;
    if (!account || !selected.length || !formats.length || !output) {
      setEstimate(undefined);
      setEstimateError("");
      return;
    }
    const timer = window.setTimeout(() => void pumpEstimate(), 600);
    return () => window.clearTimeout(timer);
  }, [payload]);
  const request = () => payload;
  const choose = async () => {
    const data = await invoke<{ path?: string }>("choose_folder");
    if (data.path) setOutput(data.path);
  };
  const start = async () => {
    const first = await invoke<Operation<ExportResult>>(
      "start_export",
      request(),
    );
    trackOperation(first);
    setExportOperationId(first.operation_id);
    const done = await pollOperation<ExportResult>(first.operation_id);
    await refreshHistory();
    if (done.status === "completed" && done.result) {
      if (done.result.warning_details.length > 0)
        void startMediaScan([...selected]);
      if (done.result.open_path && settings?.open_result_folder_after_export) {
        try {
          await invoke("open_result_folder", done.result.open_path);
        } catch {
          /* export remains successful */
        }
      }
    }
  };
  const toggleFormat = (value: string) =>
    setFormats(
      formats.includes(value)
        ? formats.filter((item) => item !== value)
        : [...formats, value],
    );
  const toggleChoice = (
    value: string,
    current: string[],
    setter: (value: string[]) => void,
  ) =>
    setter(
      current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value],
    );
  const selectedRows = conversations.filter((item) =>
    selected.includes(item.conversation_id),
  );
  const filteredRows = selectedRows.filter((item) =>
    item.display_name
      .toLocaleLowerCase()
      .includes(listQuery.toLocaleLowerCase()),
  );
  const visibleRows = expanded ? filteredRows : filteredRows.slice(0, 5);
  const result = operation?.result;
  const mediaReport = mediaOperation?.result;
  const running = ["pending", "running"].includes(operation?.status || "");
  const blockers = [
    !account ? "未选择账号" : "",
    !selected.length ? "未选择会话" : "",
    !formats.length ? "未选择格式" : "",
    !output ? "未选择导出目录" : "",
    account && !account.coverage.complete && !allowPartial
      ? "数据库密钥覆盖不完整"
      : "",
  ].filter(Boolean);
  return (
    <div className="page export-layout">
      <section className="export-form">
        <div className="form-section">
          <div className="section-number">01</div>
          <div className="form-content">
            <div className="export-list-heading">
              <div>
                <h3>导出会话列表</h3>
                <p>
                  已选择 {selected.length} 个会话，列表仅保留到本次应用退出。
                </p>
              </div>
              <button
                className="text-button"
                onClick={() => setView("conversations")}
              >
                继续添加
              </button>
            </div>
            {selected.length > 10 && (
              <label className="export-list-search">
                <Search size={15} />
                <input
                  value={listQuery}
                  onChange={(event) => setListQuery(event.target.value)}
                  placeholder="筛选已选会话"
                />
              </label>
            )}
            <div className="export-conversation-list">
              {visibleRows.map((item) => (
                <article key={item.conversation_id}>
                  {item.avatar_data_url ? (
                    <img src={item.avatar_data_url} alt="" />
                  ) : (
                    <span className="avatar-fallback">
                      {item.display_name.slice(0, 1)}
                    </span>
                  )}
                  <div>
                    <strong>{item.display_name}</strong>
                    <small>
                      {item.kind === "group" ? "群聊" : "私聊"} ·{" "}
                      {formatDate(item.last_message_at)}
                    </small>
                  </div>
                  <button
                    aria-label={`移除 ${item.display_name}`}
                    onClick={() => toggleSelected(item.conversation_id)}
                  >
                    <X size={15} />
                  </button>
                </article>
              ))}
              {!selected.length && (
                <p className="quiet-line">尚未选择会话，请返回会话浏览添加。</p>
              )}
            </div>
            {filteredRows.length > 5 && (
              <div className="export-list-actions">
                <button
                  className="text-button"
                  onClick={() => setExpanded(!expanded)}
                >
                  {expanded
                    ? "收起列表"
                    : `展开其余 ${filteredRows.length - 5} 项`}
                </button>
                <button className="text-button muted" onClick={clearSelected}>
                  清空全部
                </button>
              </div>
            )}
            <div className="range-grid">
              <label>
                <span>开始日期</span>
                <input
                  type="date"
                  value={startAt}
                  onChange={(event) => setStartAt(event.target.value)}
                />
              </label>
              <label>
                <span>结束日期</span>
                <input
                  type="date"
                  value={endAt}
                  onChange={(event) => setEndAt(event.target.value)}
                />
              </label>
            </div>
            <div className="choice-block">
              <span>消息类型</span>
              <div className="choice-chips">
                <button
                  className={!messageTypes.length ? "active" : ""}
                  onClick={() => setMessageTypes([])}
                >
                  全部
                </button>
                {["text", "image", "emoji", "audio", "video", "file"].map(
                  (value) => (
                    <button
                      key={value}
                      className={messageTypes.includes(value) ? "active" : ""}
                      onClick={() =>
                        toggleChoice(value, messageTypes, setMessageTypes)
                      }
                    >
                      {value}
                    </button>
                  ),
                )}
              </div>
            </div>
          </div>
        </div>
        <div className="form-section">
          <div className="section-number">02</div>
          <div className="form-content">
            <h3>输出格式</h3>
            <div className="option-grid">
              {[
                ["html", "离线 HTML"],
                ["markdown", "Markdown"],
                ["json", "完整 JSON"],
              ].map(([value, label]) => (
                <label
                  className={`option-card ${formats.includes(value) ? "selected" : ""}`}
                  key={value}
                >
                  <input
                    type="checkbox"
                    checked={formats.includes(value)}
                    onChange={() => toggleFormat(value)}
                  />
                  <span>
                    <strong>{label}</strong>
                    <small>
                      {value === "html"
                        ? "适合直接阅读"
                        : value === "markdown"
                          ? "保留相对媒体链接"
                          : "版本2结构化归档"}
                    </small>
                  </span>
                  <Check size={16} />
                </label>
              ))}
            </div>
          </div>
        </div>
        <div className="form-section">
          <div className="section-number">03</div>
          <div className="form-content">
            <h3>媒体与完整性</h3>
            <div className="choice-block">
              <span>媒体类别</span>
              <div className="choice-chips">
                <button
                  className={!mediaCategories.length ? "active" : ""}
                  onClick={() => setMediaCategories([])}
                >
                  全部
                </button>
                {["image", "emoji", "audio", "video", "file"].map((value) => (
                  <button
                    key={value}
                    className={mediaCategories.includes(value) ? "active" : ""}
                    onClick={() =>
                      toggleChoice(value, mediaCategories, setMediaCategories)
                    }
                  >
                    {value}
                  </button>
                ))}
              </div>
            </div>
            <label className="switch-row">
              <span>
                <strong>归档所选消息引用的媒体</strong>
                <small>只处理消息实际引用的文件</small>
              </span>
              <GreenSwitch
                label="归档所选消息引用的媒体"
                checked={includeMedia}
                onChange={setIncludeMedia}
              />
            </label>
            <label className="switch-row">
              <span>
                <strong>联网补全腾讯媒体</strong>
                <small>标准地址失败后会尝试受限腾讯 CDN token</small>
              </span>
              <GreenSwitch
                label="联网补全腾讯媒体"
                checked={downloadMedia}
                disabled={!includeMedia}
                onChange={(value) => {
                  setDownloadMedia(value);
                  if (!value) setLegacyHttp(false);
                }}
              />
            </label>
            <label className="switch-row warning">
              <span>
                <strong>允许旧腾讯 HTTP 表情地址</strong>
                <small>仅限 vweixinf.tc.qq.com 并严格校验</small>
              </span>
              <GreenSwitch
                label="允许旧腾讯 HTTP 表情地址"
                checked={legacyHttp}
                disabled={!downloadMedia}
                onChange={setLegacyHttp}
              />
            </label>
            <details className="advanced-options">
              <summary>
                高级选项 <span>下载上限与部分导出</span>
              </summary>
              <div
                className={`download-limit-grid ${!downloadMedia ? "disabled" : ""}`}
              >
                <label>
                  <span>图片 / 表情</span>
                  <div>
                    <input
                      type="number"
                      min="1"
                      max="2048"
                      value={visualLimit}
                      disabled={!downloadMedia}
                      onChange={(event) =>
                        setVisualLimit(
                          clampDownloadLimit(Number(event.target.value)),
                        )
                      }
                    />
                    <em>MiB</em>
                  </div>
                </label>
                <label>
                  <span>语音</span>
                  <div>
                    <input
                      type="number"
                      min="1"
                      max="2048"
                      value={audioLimit}
                      disabled={!downloadMedia}
                      onChange={(event) =>
                        setAudioLimit(
                          clampDownloadLimit(Number(event.target.value)),
                        )
                      }
                    />
                    <em>MiB</em>
                  </div>
                </label>
                <label>
                  <span>视频 / 文件</span>
                  <div>
                    <input
                      type="number"
                      min="1"
                      max="2048"
                      value={largeLimit}
                      disabled={!downloadMedia}
                      onChange={(event) =>
                        setLargeLimit(
                          clampDownloadLimit(Number(event.target.value)),
                        )
                      }
                    />
                    <em>MiB</em>
                  </div>
                </label>
              </div>
              <label className="switch-row">
                <span>
                  <strong>允许数据库覆盖不完整时部分导出</strong>
                  <small>可能缺少部分历史记录</small>
                </span>
                <GreenSwitch
                  label="允许数据库覆盖不完整时部分导出"
                  checked={allowPartial}
                  onChange={setAllowPartial}
                />
              </label>
            </details>
          </div>
        </div>
      </section>
      <aside className="export-summary">
        <div className="estimate-heading">
          <span className="eyebrow">实时导出检查</span>
          {estimating && <em>正在更新</em>}
        </div>
        <div className="export-destination">
          <span>固定归档目录</span>
          <strong>{output || "尚未选择"}</strong>
          <small>
            {settings?.export_folder_layout === "flat"
              ? "会话直接存放在此目录"
              : settings?.export_folder_layout === "account_by_type"
                ? "按账号与会话类型分组"
                : "按私聊与群聊分组"}
          </small>
          <div>
            <button
              className="text-button"
              disabled={!output}
              onClick={() => void invoke("open_result_folder", output)}
            >
              打开
            </button>
            <button className="text-button" onClick={() => void choose()}>
              更改
            </button>
          </div>
        </div>
        <h3>{selected.length} 个会话</h3>
        <div className="readiness-list">
          <span className={selected.length ? "ready" : "blocked"}>
            {selected.length ? "会话范围已就绪" : "尚未选择会话"}
          </span>
          <span className={formats.length ? "ready" : "blocked"}>
            {formats.length ? `${formats.length} 种输出格式` : "尚未选择格式"}
          </span>
          <span
            className={
              account?.coverage.complete || allowPartial ? "ready" : "blocked"
            }
          >
            {account?.coverage.complete
              ? "数据库覆盖完整"
              : allowPartial
                ? "允许部分导出"
                : "密钥覆盖不完整"}
          </span>
          <span className={output ? "ready" : "blocked"}>
            {output ? "输出目录已设置" : "尚未设置目录"}
          </span>
        </div>
        <dl>
          <div>
            <dt>消息</dt>
            <dd>{estimate?.message_count ?? "—"}</dd>
          </div>
          <div>
            <dt>媒体引用</dt>
            <dd>{estimate?.media_count ?? "—"}</dd>
          </div>
          <div>
            <dt>已知体积</dt>
            <dd>{estimate ? formatBytes(estimate.known_bytes) : "—"}</dd>
          </div>
          <div>
            <dt>可用空间</dt>
            <dd>{estimate ? formatBytes(estimate.free_bytes) : "—"}</dd>
          </div>
        </dl>
        {estimate && (
          <div className="recovery-preview">
            <span>
              <i className="good" />
              本地可恢复 <b>{estimate.local_recoverable_count}</b>
            </span>
            <span>
              <i className="pending" />
              联网候选 <b>{estimate.network_candidate_count}</b>
            </span>
            <span>
              <i className="bad" />
              不可恢复 <b>{estimate.unavailable_count}</b>
            </span>
            {estimate.remote_size_unknown_count > 0 && (
              <p>
                另有 {estimate.remote_size_unknown_count}{" "}
                项联网媒体大小待下载时确认。
              </p>
            )}
          </div>
        )}
        {estimateError && (
          <div className="estimate-error">
            <span>{estimateError}</span>
            <button
              className="text-button"
              onClick={() => {
                estimateCompleted.current = 0;
                void pumpEstimate();
              }}
            >
              重新计算
            </button>
          </div>
        )}
        {estimate?.warnings.map((warning) => (
          <p className="inline-warning" key={warning}>
            {warning}
          </p>
        ))}
        {operation && running && (
          <>
            <Progress operation={operation} />
            <button
              className="secondary wide"
              onClick={() =>
                void invoke("cancel_operation", operation.operation_id)
              }
            >
              取消导出
            </button>
          </>
        )}
        <button
          className="primary wide"
          disabled={Boolean(blockers.length) || running}
          onClick={() => void start()}
        >
          开始导出
        </button>
        {blockers.length > 0 && !running && (
          <p className="export-blocker">{blockers.join(" · ")}</p>
        )}
        {operation?.status === "failed" && (
          <p className="error-text">{operation.error || "导出未完成"}</p>
        )}
        {result && (
          <section className="export-result-card">
            <Check size={19} />
            <div>
              <strong>导出完成</strong>
              <span>
                新建 {result.created_count} 个 · 覆盖 {result.replaced_count} 个
                · {result.message_count} 条消息
              </span>
              <code>{result.open_path || result.root}</code>
            </div>
            {result.warning_details.length > 0 && (
              <div className="warning-refresh-status">
                {mediaOperation &&
                ["pending", "running"].includes(mediaOperation.status) ? (
                  <>
                    <RefreshCw size={14} />
                    <span>
                      正在刷新本地媒体状态 ·{" "}
                      {Math.round(mediaOperation.progress * 100)}%
                    </span>
                  </>
                ) : mediaReport ? (
                  <>
                    <Check size={14} />
                    <span>
                      本地状态已刷新：
                      {mediaReport.missing + mediaReport.unsupported} 项仍需处理
                    </span>
                  </>
                ) : (
                  <span>等待刷新媒体状态</span>
                )}
              </div>
            )}
            <button
              className="primary wide"
              onClick={() =>
                void invoke(
                  "open_result_folder",
                  result.open_path || result.root,
                )
              }
            >
              打开导出目录
            </button>
            <button
              className="text-button"
              onClick={() =>
                void navigator.clipboard.writeText(
                  result.open_path || result.root,
                )
              }
            >
              复制结果路径
            </button>
            {result.warning_details.length > 0 && (
              <button
                className="secondary wide"
                onClick={() => setView("media")}
              >
                查看媒体告警
              </button>
            )}
            <button
              className="text-button"
              onClick={() => setExportOperationId(undefined)}
            >
              使用相同配置再次导出
            </button>
          </section>
        )}
      </aside>
    </div>
  );
}

function MediaView() {
  const {
    account,
    selected,
    operations,
    mediaScanOperationId,
    mediaScanConversationIds,
    startMediaScan,
    setView,
  } = useWorkbench();
  const [filter, setFilter] = useState("all");
  const [reasonFilter, setReasonFilter] = useState("all");
  const operation = mediaScanOperationId
    ? (operations[mediaScanOperationId] as Operation<MediaReport> | undefined)
    : undefined;
  const scan = async () => {
    if (!account) return;
    await startMediaScan([...selected]);
  };
  const report = operation?.result;
  const categories = report
    ? Object.entries(report.by_category).filter(
        ([key]) => filter === "all" || key === filter,
      )
    : [];
  const reasons = Array.from(
    new Set((report?.items || []).map((item) => item.reason_code || "unknown")),
  );
  const detailItems = (report?.items || []).filter(
    (item) =>
      (filter === "all" || item.category === filter) &&
      (reasonFilter === "all" ||
        (item.reason_code || "unknown") === reasonFilter),
  );
  const reasonText = (code?: string) =>
    (
      ({
        decode_failed: "缓存存在，但无法用现有密钥或容器算法验证",
        local_media_missing: "本机没有对应媒体缓存",
        remote_url_missing: "数据库没有可下载地址",
        private_cdn_key_missing: "存在 CDN token，但缺少解密密钥",
        wxgf_conversion_failed: "WXGF 已解密，但本机转换失败",
      }) as Record<string, string>
    )[code || ""] || "本地暂时无法恢复";
  return (
    <div className="page constrained">
      <section className="media-intro">
        <div>
          <span className="eyebrow green">本地重新检测</span>
          <h2>
            {mediaScanConversationIds.length
              ? `检查已选的 ${mediaScanConversationIds.length} 个会话`
              : "检查整个当前账号"}
          </h2>
          <p>
            请先在微信中打开缺失视频或文件，再点击重新检测。检测结果会在工作台之间持续保留并实时更新。
          </p>
        </div>
        <button
          className="primary"
          disabled={
            !account || ["pending", "running"].includes(operation?.status || "")
          }
          onClick={() => void scan()}
        >
          <RefreshCw size={17} />
          {report ? "我已在微信中打开，重新检测" : "开始检测"}
        </button>
      </section>
      {operation && ["pending", "running"].includes(operation.status) && (
        <Progress operation={operation} />
      )}{" "}
      {report ? (
        <>
          <section className="stats-grid media-stats">
            <Stat
              icon={Image}
              label="媒体引用"
              value={report.referenced}
              detail={mediaScanConversationIds.length ? "所选会话" : "全部会话"}
            />
            <Stat
              icon={Check}
              label="现在可恢复"
              value={report.recoverable}
              detail="可重新导出"
            />
            <Stat
              icon={FolderOpen}
              label="本机未缓存"
              value={report.missing}
              detail="请在微信中打开"
            />
            <Stat
              icon={FileSearch}
              label="无法识别"
              value={report.unsupported}
              detail="查看具体原因"
            />
          </section>
          <div className="media-actions">
            <div className="filter-row">
              <button
                className={filter === "all" ? "active" : ""}
                onClick={() => setFilter("all")}
              >
                全部
              </button>
              {Object.keys(report.by_category).map((key) => (
                <button
                  key={key}
                  className={filter === key ? "active" : ""}
                  onClick={() => setFilter(key)}
                >
                  {key}
                </button>
              ))}
            </div>
            {reasons.length > 1 && (
              <select
                value={reasonFilter}
                onChange={(event) => setReasonFilter(event.target.value)}
              >
                <option value="all">全部原因</option>
                {reasons.map((reason) => (
                  <option value={reason} key={reason}>
                    {reasonText(reason)}
                  </option>
                ))}
              </select>
            )}
          </div>
          <section className="media-table">
            <div className="media-table-head">
              <span>类别</span>
              <span>引用</span>
              <span>可恢复</span>
              <span>缺失</span>
              <span>无法识别</span>
            </div>
            {categories.map(([category, value]) => (
              <div className="media-table-row" key={category}>
                <strong>{category}</strong>
                <span>{value.referenced || 0}</span>
                <span className="green-text">{value.recoverable || 0}</span>
                <span>{value.missing || 0}</span>
                <span>{value.unsupported || 0}</span>
              </div>
            ))}
          </section>
          {detailItems.length > 0 && (
            <section className="recovery-item-list">
              <div className="section-toolbar">
                <div>
                  <h3>缺失媒体清单</h3>
                  <p>仅显示会话、时间和恢复状态，不保存消息正文或下载凭据。</p>
                </div>
                <button
                  className="secondary compact"
                  onClick={() => setView("export")}
                >
                  返回导出工作台
                </button>
              </div>
              {detailItems.map((item, index) => (
                <article
                  key={`${item.conversation_id}-${item.sent_at}-${index}`}
                >
                  <span className="media-kind">{item.category}</span>
                  <div>
                    <strong>{item.conversation_name}</strong>
                    <small>{formatDate(item.sent_at)}</small>
                  </div>
                  <p>{reasonText(item.reason_code)}</p>
                </article>
              ))}
              {report.truncated > 0 && (
                <p className="quiet-line">
                  另有 {report.truncated} 项仅在上方分类汇总中显示。
                </p>
              )}
            </section>
          )}
          {report.recoverable > 0 && (
            <div className="media-ready">
              <Check size={18} />
              <span>
                本地已有 {report.recoverable}{" "}
                项可恢复媒体。返回导出工作台会保留上一次导出完成状态。
              </span>
              <button
                className="primary compact"
                onClick={() => setView("export")}
              >
                返回导出工作台
              </button>
            </div>
          )}
        </>
      ) : (
        <EmptyState
          icon={BarChart3}
          title={operation?.status === "failed" ? "检测未完成" : "尚未检测"}
          text={
            operation?.error ||
            "首次检测可能需要较长时间；切换工作台不会再清空进度和结果。"
          }
        />
      )}
    </div>
  );
}

type ConfirmRequest = {
  title: string;
  description: string;
  count?: number;
  confirmLabel: string;
  notes?: string[];
  onConfirm(): Promise<void>;
};

function ConfirmDialog({
  request,
  onClose,
}: {
  request?: ConfirmRequest;
  onClose(): void;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (request) cancelRef.current?.focus();
  }, [request]);
  useEffect(() => {
    if (!request) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [request, onClose]);
  const notes = request?.notes || [
    "只删除任务历史元数据，导出文件仍会保留。",
    "正在运行的任务和记录不会被清除。",
  ];
  return (
    <AnimatePresence initial={false}>
      {request && (
        <motion.div
          className="dialog-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) onClose();
          }}
        >
          <motion.section
            className="confirm-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-dialog-title"
            initial={{ opacity: 0, scale: 0.98, y: 6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 4 }}
            transition={{ type: "spring", duration: 0.3, bounce: 0 }}
          >
            <span className="confirm-dialog-icon">
              <AlertTriangle size={22} />
            </span>
            <div>
              <span className="eyebrow">谨慎操作</span>
              <h3 id="confirm-dialog-title">{request.title}</h3>
              {request.count != null && (
                <strong className="confirm-count">
                  {request.count.toLocaleString()} 条记录
                </strong>
              )}
              <p>{request.description}</p>
              <ul>
                {notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </div>
            <footer>
              <button ref={cancelRef} className="secondary" onClick={onClose}>
                取消
              </button>
              <button
                className="primary danger-solid"
                onClick={async () => {
                  await request.onConfirm();
                  onClose();
                }}
              >
                {request.confirmLabel}
              </button>
            </footer>
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function TasksView() {
  const { history, operations, refreshHistory } = useWorkbench();
  const active = Object.values(operations).filter((item) =>
    ["pending", "running"].includes(item.status),
  );
  const [selectedHistory, setSelectedHistory] = useState<string[]>([]);
  const [kindFilter, setKindFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [healthFilter, setHealthFilter] = useState("all");
  const [openMenu, setOpenMenu] = useState<string>();
  const [confirmation, setConfirmation] = useState<ConfirmRequest>();
  const menuRef = useRef<HTMLDivElement>(null);
  const menuTrigger = useRef<HTMLButtonElement | null>(null);
  const kindText = (kind: string) =>
    (
      ({
        export: "聊天导出",
        media_scan: "媒体完整性",
        account_statistics: "全会话统计",
      }) as Record<string, string>
    )[kind] || kind;
  const statusText = (status: string) =>
    (
      ({
        completed: "已完成",
        failed: "失败",
        cancelled: "已取消",
        interrupted: "意外中断",
        running: "运行中",
      }) as Record<string, string>
    )[status] || status;
  const healthText = (health: string) =>
    (
      ({
        healthy: "目录正常",
        moved: "目录已移动",
        missing: "目录缺失",
        incomplete: "归档不完整",
        inaccessible: "无法访问",
        trashed: "已移入回收站",
        not_applicable: "无需目录",
      }) as Record<string, string>
    )[health] || health;
  const filtered = history.filter(
    (item) =>
      (kindFilter === "all" || item.kind === kindFilter) &&
      (statusFilter === "all" || item.status === statusFilter) &&
      (healthFilter === "all" || item.directory_health === healthFilter),
  );
  const isAbnormal = (item: HistoryEntry) =>
    ["failed", "interrupted"].includes(item.status) ||
    ["missing", "incomplete", "inaccessible"].includes(item.directory_health);
  const abnormal = history.filter(isAbnormal).length;
  const terminalCount = history.filter(
    (item) => !["pending", "running"].includes(item.status),
  ).length;
  useEffect(() => {
    if (!openMenu) return;
    const close = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setOpenMenu(undefined);
        menuTrigger.current?.focus();
      }
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpenMenu(undefined);
        menuTrigger.current?.focus();
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", escape);
    };
  }, [openMenu]);
  const toggleMenu = (
    id: string,
    event: React.MouseEvent<HTMLButtonElement>,
  ) => {
    menuTrigger.current = event.currentTarget;
    setOpenMenu((value) => (value === id ? undefined : id));
  };
  const removeNow = async (ids: string[]) => {
    await invoke("delete_operation_history_entries", ids);
    setSelectedHistory([]);
    await refreshHistory();
  };
  const askRemove = (ids: string[]) => {
    if (!ids.length) return;
    setConfirmation({
      title: ids.length === 1 ? "删除这条任务记录？" : "删除所选任务记录？",
      description:
        "记录删除后不会再出现在任务历史中，但磁盘上的导出归档不会受到影响。",
      count: ids.length,
      confirmLabel: "删除记录",
      onConfirm: () => removeNow(ids),
    });
  };
  const askClear = (mode: "all" | "abnormal") => {
    const count = mode === "all" ? terminalCount : abnormal;
    if (!count) return;
    setOpenMenu(undefined);
    setConfirmation({
      title: mode === "all" ? "清空全部任务记录？" : "清空异常任务记录？",
      description:
        mode === "all"
          ? "所有已经结束的导出、统计和媒体扫描记录都会从历史中移除。"
          : "只移除失败、意外中断，以及目录缺失、不完整或无法访问的记录。",
      count,
      confirmLabel: mode === "all" ? "清空全部记录" : "清空异常记录",
      onConfirm: async () => {
        await invoke(
          mode === "all"
            ? "clear_operation_history"
            : "clear_abnormal_operation_history",
        );
        setSelectedHistory([]);
        await refreshHistory();
      },
    });
  };
  const relink = async (item: HistoryEntry) => {
    const folder = await invoke<{ path?: string }>("choose_folder");
    if (!folder.path) return;
    await invoke(
      "relink_operation_history_entry",
      item.history_id,
      folder.path,
    );
    await refreshHistory();
  };
  const askTrash = (item: HistoryEntry) => {
    const shared = item.storage_mode === "shared";
    const count = item.conversation_archives?.length ?? item.conversation_count;
    setConfirmation({
      title: shared ? "将本次会话归档移入回收站？" : "将导出归档移入回收站？",
      description: shared
        ? `将检查本次涉及的 ${count} 个会话目录，只回收仍属于这次导出的版本。`
        : "此操作会移动经过验证的单个导出目录；任务记录会保留并标记为已回收。",
      confirmLabel: "移入回收站",
      notes: [
        shared
          ? "被后续导出覆盖的会话会自动跳过，不会删除当前版本。"
          : "导出目录会进入 Windows 回收站，可由系统回收站恢复。",
        "输出根目录、微信源数据和其他会话不会受到影响。",
      ],
      onConfirm: async () => {
        await invoke("trash_export_result", item.history_id);
        await refreshHistory();
      },
    });
  };
  const exportHealthLabel = (item: HistoryEntry) =>
    item.superseded_count
      ? "已由后续导出更新"
      : healthText(item.directory_health);
  const supersededNote = (item: HistoryEntry) =>
    item.superseded_count ? (
      <small className="history-note">
        其中 {item.superseded_count}{" "}
        个会话已有更新版本；旧记录不会删除当前归档。
      </small>
    ) : null;
  return (
    <>
      <div className="page constrained tasks-page">
        <div className="section-toolbar">
          <div>
            <span className="eyebrow green">运行状态</span>
            <h2>任务与记录</h2>
            <p>
              长期保存导出、媒体扫描和全会话统计的结果元数据，不保存聊天正文。
            </p>
          </div>
          <button
            className="secondary compact"
            onClick={() => void refreshHistory()}
          >
            <RefreshCw size={15} />
            刷新状态
          </button>
        </div>
        <section className="history-overview">
          <span>
            <b>{active.length}</b> 正在运行
          </span>
          <span>
            <b>
              {history.filter((item) => item.status === "completed").length}
            </b>{" "}
            已完成
          </span>
          <span className={abnormal ? "warning" : ""}>
            <b>{abnormal}</b> 需要关注
          </span>
          <span>
            <b>{history.length}</b> 全部记录
          </span>
        </section>
        {active.length ? (
          <section className="task-grid">
            {active.map((item) => (
              <article className="task-card" key={item.operation_id}>
                <span>{kindText(item.kind)}</span>
                <Progress operation={item} />
                <button
                  className="text-button muted"
                  onClick={() =>
                    void invoke("cancel_operation", item.operation_id)
                  }
                >
                  取消任务
                </button>
              </article>
            ))}
          </section>
        ) : (
          <p className="quiet-line">当前没有正在运行的任务。</p>
        )}
        <div className="history-toolbar">
          <div className="history-filters">
            <select
              value={kindFilter}
              onChange={(event) => setKindFilter(event.target.value)}
            >
              <option value="all">全部任务</option>
              <option value="export">聊天导出</option>
              <option value="account_statistics">全会话统计</option>
              <option value="media_scan">媒体扫描</option>
            </select>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="all">全部状态</option>
              <option value="completed">已完成</option>
              <option value="failed">失败</option>
              <option value="cancelled">已取消</option>
              <option value="interrupted">意外中断</option>
            </select>
            <select
              value={healthFilter}
              onChange={(event) => setHealthFilter(event.target.value)}
            >
              <option value="all">全部目录状态</option>
              <option value="healthy">目录正常</option>
              <option value="moved">已移动</option>
              <option value="missing">目录缺失</option>
              <option value="incomplete">归档不完整</option>
              <option value="inaccessible">无法访问</option>
              <option value="trashed">已回收</option>
            </select>
          </div>
          <div className="history-toolbar-actions">
            {selectedHistory.length > 0 && (
              <button
                className="secondary compact danger"
                onClick={() => askRemove(selectedHistory)}
              >
                <Trash2 size={15} />
                删除 {selectedHistory.length} 条
              </button>
            )}
            <div
              className="menu-anchor"
              ref={openMenu === "cleanup" ? menuRef : undefined}
            >
              <button
                className="secondary compact"
                aria-haspopup="menu"
                aria-expanded={openMenu === "cleanup"}
                onClick={(event) => toggleMenu("cleanup", event)}
              >
                清理记录
                <ChevronDown size={14} />
              </button>
              {openMenu === "cleanup" && (
                <div className="action-menu cleanup-menu" role="menu">
                  <button
                    role="menuitem"
                    disabled={!abnormal}
                    onClick={() => askClear("abnormal")}
                  >
                    <AlertTriangle size={15} />
                    <span>
                      <strong>清空异常记录</strong>
                      <small>
                        {abnormal
                          ? `${abnormal} 条需要关注的记录`
                          : "没有异常记录"}
                      </small>
                    </span>
                  </button>
                  <button
                    className="danger"
                    role="menuitem"
                    disabled={!terminalCount}
                    onClick={() => askClear("all")}
                  >
                    <Trash2 size={15} />
                    <span>
                      <strong>清空全部记录</strong>
                      <small>
                        {terminalCount
                          ? `${terminalCount} 条已结束记录`
                          : "没有可清理记录"}
                      </small>
                    </span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
        {filtered.length ? (
          <section className="history-list rich-history">
            {filtered.map((item) => {
              const primaryOpen =
                item.kind === "export" &&
                ["healthy", "moved"].includes(item.directory_health) &&
                item.current_path;
              const primaryRelink =
                item.kind === "export" &&
                ["missing", "incomplete", "inaccessible"].includes(
                  item.directory_health,
                );
              const allSuperseded =
                item.storage_mode === "shared" &&
                (item.conversation_archives?.length ?? 0) > 0 &&
                item.superseded_count === item.conversation_archives?.length;
              return (
                <article
                  key={item.history_id}
                  className={isAbnormal(item) ? "has-issue" : ""}
                >
                  <button
                    className={`check ${selectedHistory.includes(item.history_id) ? "checked" : ""}`}
                    onClick={() =>
                      setSelectedHistory((rows) =>
                        rows.includes(item.history_id)
                          ? rows.filter((id) => id !== item.history_id)
                          : [...rows, item.history_id],
                      )
                    }
                    aria-label="选择历史记录"
                  >
                    {selectedHistory.includes(item.history_id) && (
                      <Check size={13} />
                    )}
                  </button>
                  <div className="history-icon">
                    {item.kind === "export" ? (
                      <Archive size={19} />
                    ) : item.kind === "media_scan" ? (
                      <Image size={19} />
                    ) : (
                      <BarChart3 size={19} />
                    )}
                  </div>
                  <div className="history-content">
                    <div>
                      <strong>{kindText(item.kind)}</strong>
                      <em className={`history-status ${item.status}`}>
                        {statusText(item.status)}
                      </em>
                      {item.kind === "export" && (
                        <em
                          className={`health-status ${item.directory_health}`}
                        >
                          {exportHealthLabel(item)}
                        </em>
                      )}
                    </div>
                    <span>
                      {formatDate(item.completed_at || item.created_at)}
                      {item.duration_seconds != null
                        ? ` · ${Math.round(item.duration_seconds)} 秒`
                        : ""}
                    </span>
                    <p>
                      {item.kind === "export"
                        ? `${item.conversation_count} 个会话 · ${item.message_count.toLocaleString()} 条消息 · ${item.media_count} 个媒体${item.formats.length ? ` · ${item.formats.join(" / ")}` : ""}`
                        : item.kind === "media_scan"
                          ? `${item.media_count} 个媒体引用 · 可恢复 ${String(item.result_summary?.recoverable ?? 0)}`
                          : `${item.conversation_count} 个会话 · ${item.message_count.toLocaleString()} 条消息`}
                    </p>
                    {supersededNote(item)}
                    {item.error_summary && (
                      <small className="history-error">
                        {item.error_summary}
                      </small>
                    )}
                    {item.warning_details.length > 0 && (
                      <details>
                        <summary>
                          {item.warning_details.reduce(
                            (sum, row) => sum + row.count,
                            0,
                          )}{" "}
                          项媒体告警
                        </summary>
                        {item.warning_details.map((row, index) => (
                          <span key={`${row.code}-${index}`}>
                            {row.category} · {row.count}：{row.message}
                          </span>
                        ))}
                      </details>
                    )}
                    {item.current_path && <code>{item.current_path}</code>}
                  </div>
                  <div className="history-actions">
                    {primaryOpen && (
                      <button
                        className="secondary compact"
                        onClick={() =>
                          void invoke("open_result_folder", item.current_path)
                        }
                      >
                        <FolderOpen size={14} />
                        打开
                      </button>
                    )}
                    {primaryRelink && (
                      <button
                        className="secondary compact"
                        onClick={() => void relink(item)}
                      >
                        重新定位
                      </button>
                    )}
                    <div
                      className="menu-anchor"
                      ref={openMenu === item.history_id ? menuRef : undefined}
                    >
                      <button
                        className="icon-button more-button"
                        aria-label={`更多${kindText(item.kind)}操作`}
                        aria-haspopup="menu"
                        aria-expanded={openMenu === item.history_id}
                        onClick={(event) => toggleMenu(item.history_id, event)}
                      >
                        <MoreHorizontal size={18} />
                      </button>
                      {openMenu === item.history_id && (
                        <div className="action-menu row-menu" role="menu">
                          {item.kind === "export" &&
                            item.directory_health !== "trashed" &&
                            !primaryRelink && (
                              <button
                                role="menuitem"
                                onClick={() => {
                                  setOpenMenu(undefined);
                                  void relink(item);
                                }}
                              >
                                <RefreshCw size={15} />
                                重新定位
                              </button>
                            )}
                          {item.kind === "export" &&
                            ["healthy", "moved"].includes(
                              item.directory_health,
                            ) &&
                            !allSuperseded && (
                              <button
                                className="danger"
                                role="menuitem"
                                onClick={() => {
                                  setOpenMenu(undefined);
                                  askTrash(item);
                                }}
                              >
                                <Trash2 size={15} />
                                移入回收站
                              </button>
                            )}
                          <button
                            role="menuitem"
                            onClick={() => {
                              setOpenMenu(undefined);
                              askRemove([item.history_id]);
                            }}
                          >
                            <X size={15} />
                            仅删除记录
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </section>
        ) : (
          <EmptyState
            icon={Clock3}
            title="没有匹配的任务记录"
            text="调整筛选条件，或完成一次导出、媒体扫描或全会话统计。"
          />
        )}
      </div>
      <ConfirmDialog
        request={confirmation}
        onClose={() => setConfirmation(undefined)}
      />
    </>
  );
}

function AccountCard({ item }: { item: Account }) {
  const { account, selectAccount, initialize } = useWorkbench();
  const current = account?.account_id === item.account_id;
  const authorize = async () => {
    await invoke("authorize_account", item.account_id);
    await initialize();
  };
  return (
    <article className={`settings-account ${current ? "current" : ""}`}>
      <div className="avatar-fallback">{item.display_name.slice(0, 1)}</div>
      <div>
        <strong>{item.display_name}</strong>
        <span>
          {formatBytes(item.size_bytes)} · 密钥 {item.coverage.covered}/
          {item.coverage.total}
        </span>
      </div>
      {current ? (
        <em>当前</em>
      ) : (
        <button
          className="text-button"
          onClick={() => void selectAccount(item)}
        >
          切换
        </button>
      )}
      <button className="secondary compact" onClick={() => void authorize()}>
        {item.coverage.complete ? "重新授权" : "授权读取"}
      </button>
    </article>
  );
}

function SettingsView() {
  const { settings, accounts, saveSettings, initialize } = useWorkbench();
  if (!settings) return null;
  const set = (value: Partial<Settings>) => void saveSettings(value);
  const chooseDataRoot = async () => {
    const data = await invoke<{ path?: string }>("choose_folder");
    if (!data.path) return;
    await saveSettings({ data_root: data.path, last_account_id: "" });
    await initialize();
  };
  const layouts: Array<{
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
  return (
    <div className="page settings-page">
      <aside className="settings-index">
        <strong>设置</strong>
        <a href="#appearance">界面与显示</a>
        <a href="#accounts">账号与存储</a>
        <a href="#export-layout">归档目录结构</a>
        <a href="#media-defaults">媒体导出默认值</a>
        <a href="#privacy">隐私与行为</a>
      </aside>
      <div className="settings-content">
        <section id="appearance">
          <span className="eyebrow">界面与显示</span>
          <h2>外观</h2>
          <div className="setting-row">
            <div>
              <strong>主题</strong>
              <span>默认跟随 Windows，也可以固定浅色或深色</span>
            </div>
            <select
              value={settings.theme}
              onChange={(event) => set({ theme: event.target.value as Theme })}
            >
              <option value="system">跟随系统</option>
              <option value="light">浅色模式</option>
              <option value="dark">深色模式</option>
            </select>
          </div>
          <div className="setting-row">
            <div>
              <strong>字体大小</strong>
              <span>同时调整会话、表单和数据字体</span>
            </div>
            <select
              value={settings.font_scale}
              onChange={(event) =>
                set({
                  font_scale: event.target.value as Settings["font_scale"],
                })
              }
            >
              <option value="small">小</option>
              <option value="standard">标准</option>
              <option value="large">大</option>
            </select>
          </div>
          <div className="setting-row">
            <div>
              <strong>界面密度</strong>
              <span>紧凑模式可在会话列表显示更多内容</span>
            </div>
            <select
              value={settings.density}
              onChange={(event) =>
                set({ density: event.target.value as Settings["density"] })
              }
            >
              <option value="comfortable">舒适</option>
              <option value="compact">紧凑</option>
            </select>
          </div>
        </section>
        <section id="accounts">
          <span className="eyebrow">账号与存储</span>
          <h2>本机账号</h2>
          <div className="settings-accounts">
            {accounts.map((item) => (
              <AccountCard item={item} key={item.account_id} />
            ))}
          </div>
          <div className="setting-row path-row">
            <div>
              <strong>微信数据根目录</strong>
              <span>{settings.data_root}</span>
            </div>
            <button
              className="secondary compact"
              onClick={() => void chooseDataRoot()}
            >
              更改
            </button>
          </div>
          <div className="setting-row path-row">
            <div>
              <strong>默认输出目录</strong>
              <span>{settings.output_directory}</span>
            </div>
            <button
              className="secondary compact"
              onClick={async () => {
                const data = await invoke<{ path?: string }>("choose_folder");
                if (data.path) set({ output_directory: data.path });
              }}
            >
              更改
            </button>
          </div>
          <div className="setting-row">
            <div>
              <strong>导出完成后自动打开目录</strong>
              <span>默认关闭；关闭时仍可在结果卡直接打开</span>
            </div>
            <GreenSwitch
              label="导出完成后自动打开目录"
              checked={settings.open_result_folder_after_export}
              onChange={(value) =>
                set({ open_result_folder_after_export: value })
              }
            />
          </div>
        </section>
        <section id="export-layout">
          <span className="eyebrow">固定会话归档</span>
          <h2>目录结构</h2>
          <p className="settings-section-copy">
            同一会话始终覆盖固定目录。切换结构后，下次导出会自动迁移该会话，不产生重复副本。
          </p>
          <div
            className="layout-choice-grid"
            role="radiogroup"
            aria-label="导出目录结构"
          >
            {layouts.map((layout) => (
              <button
                type="button"
                role="radio"
                aria-checked={settings.export_folder_layout === layout.value}
                className={
                  settings.export_folder_layout === layout.value
                    ? "selected"
                    : ""
                }
                key={layout.value}
                onClick={() => set({ export_folder_layout: layout.value })}
              >
                <span>
                  <strong>{layout.title}</strong>
                  <small>{layout.example}</small>
                </span>
                <i>
                  {settings.export_folder_layout === layout.value && (
                    <Check size={15} />
                  )}
                </i>
              </button>
            ))}
          </div>
        </section>
        <section id="media-defaults">
          <span className="eyebrow">媒体导出默认值</span>
          <h2>联网恢复</h2>
          <div className="setting-row">
            <div>
              <strong>联网补全腾讯媒体</strong>
              <span>新导出默认开启，包含受限腾讯 CDN token 恢复</span>
            </div>
            <GreenSwitch
              label="默认联网补全腾讯媒体"
              checked={settings.download_missing_media_default}
              onChange={(value) =>
                set({ download_missing_media_default: value })
              }
            />
          </div>
          <div className="setting-row">
            <div>
              <strong>允许旧腾讯 HTTP 表情地址</strong>
              <span>仅允许 vweixinf.tc.qq.com，下载后仍执行完整校验</span>
            </div>
            <GreenSwitch
              label="默认允许旧腾讯 HTTP 表情地址"
              checked={settings.allow_legacy_http_media_default}
              onChange={(value) =>
                set({ allow_legacy_http_media_default: value })
              }
            />
          </div>
          <div className="settings-limit-grid">
            <label>
              <span>图片 / 表情</span>
              <div>
                <input
                  type="number"
                  min="1"
                  max="2048"
                  value={settings.visual_download_limit_mib}
                  onChange={(event) =>
                    set({
                      visual_download_limit_mib: clampDownloadLimit(
                        Number(event.target.value),
                      ),
                    })
                  }
                />
                <em>MiB</em>
              </div>
            </label>
            <label>
              <span>语音</span>
              <div>
                <input
                  type="number"
                  min="1"
                  max="2048"
                  value={settings.audio_download_limit_mib}
                  onChange={(event) =>
                    set({
                      audio_download_limit_mib: clampDownloadLimit(
                        Number(event.target.value),
                      ),
                    })
                  }
                />
                <em>MiB</em>
              </div>
            </label>
            <label>
              <span>视频 / 文件</span>
              <div>
                <input
                  type="number"
                  min="1"
                  max="2048"
                  value={settings.large_download_limit_mib}
                  onChange={(event) =>
                    set({
                      large_download_limit_mib: clampDownloadLimit(
                        Number(event.target.value),
                      ),
                    })
                  }
                />
                <em>MiB</em>
              </div>
            </label>
          </div>
        </section>
        <section id="privacy">
          <span className="eyebrow">隐私与行为</span>
          <h2>本地数据边界</h2>
          <ul className="privacy-list">
            <li>
              <ShieldCheck size={17} />
              <span>
                <strong>只读微信源数据</strong>所有解析都使用临时数据库快照。
              </span>
            </li>
            <li>
              <Search size={17} />
              <span>
                <strong>不建立搜索索引</strong>搜索词和结果在退出时清除。
              </span>
            </li>
            <li>
              <HardDrive size={17} />
              <span>
                <strong>不缓存联网媒体</strong>
                补全内容只进入用户主动创建的导出目录。
              </span>
            </li>
          </ul>
        </section>
      </div>
    </div>
  );
}

function ErrorBanner() {
  const { error, clearError } = useWorkbench();
  return (
    <AnimatePresence>
      {error && (
        <motion.div
          className="error-banner"
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          role="alert"
        >
          <span>{error}</span>
          <button onClick={clearError} aria-label="关闭错误">
            <X size={16} />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function applyTheme(settings?: Settings) {
  if (!settings) return () => undefined;
  const media = matchMedia("(prefers-color-scheme: dark)");
  const update = () => {
    const dark =
      settings.theme === "dark" ||
      (settings.theme === "system" && media.matches);
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    document.documentElement.dataset.fontScale = settings.font_scale;
    document.documentElement.dataset.density = settings.density;
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", dark ? "#191919" : "#ffffff");
  };
  update();
  media.addEventListener("change", update);
  return () => media.removeEventListener("change", update);
}

export default function App() {
  const {
    initialize,
    initialized,
    loading,
    error,
    view,
    settings,
    sidebarCollapsed,
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
        <div className="view-content" key={view}>
          {content}
        </div>
      </main>
    </div>
  );
}
