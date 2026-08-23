import { useMemo, useState } from "react";
import {
  Archive,
  ArrowRight,
  BarChart3,
  Clock3,
  Database,
  Download,
  HardDrive,
  MessageCircle,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";
import { invoke } from "../bridge";
import { useWorkbench } from "../store";
import type { AccountStatisticsReport, MediaReport, Operation } from "../types";
import { Progress, Stat } from "../ui/primitives";
import { formatBytes, formatDate, kindLabel, publicText } from "../utils/format";

export function HomeView() {
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
  const [statisticsSort, setStatisticsSort] = useState<"count" | "name" | "latest">("count");
  const last = history.find((item) => item.kind === "export" && item.status === "completed");
  const mediaOperation = mediaScanOperationId ? operations[mediaScanOperationId] : undefined;
  const statisticsOperation = accountStatisticsOperationId
    ? (operations[accountStatisticsOperationId] as Operation<AccountStatisticsReport> | undefined)
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
  const scanning = statisticsOperation && ["pending", "running"].includes(statisticsOperation.status);
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
              <img src={account.avatar_data_url} alt={`${displayName}的账号头像`} />
            ) : (
              <span>{account ? displayName.slice(0, 1) : "微"}</span>
            )}
          </div>
          <div className="account-copy">
            <div className="account-labels">
              <span className="eyebrow green">当前本地账号</span>
              <em className={account?.coverage.complete ? "is-ready" : ""}>
                {account?.coverage.complete ? "数据库已就绪" : account ? "需要补充授权" : "等待选择"}
              </em>
            </div>
            <h2>{displayName}</h2>
            <p>
              {account
                ? "所有内容均从本机临时只读快照读取；搜索、预览和会话选择不会写入微信数据。"
                : "选择一个已授权的本机微信账号后，即可浏览、检查和导出聊天记录。"}
            </p>
            {!account && (
              <button className="secondary compact" onClick={() => setView("settings")}>
                前往账号设置
              </button>
            )}
          </div>
        </div>
        <aside className="account-readiness" aria-label="账号读取状态">
          <div className="readiness-heading">
            <span>数据库密钥覆盖</span>
            <strong>{account ? `${account.coverage.covered}/${account.coverage.total}` : "—"}</strong>
          </div>
          <div className="coverage-track" aria-label={`数据库密钥覆盖 ${coverage}%`}>
            <i style={{ width: `${coverage}%` }} />
          </div>
          <dl>
            <div><dt>读取方式</dt><dd>本地只读</dd></div>
            <div><dt>账号数据</dt><dd>{account ? formatBytes(account.size_bytes) : "—"}</dd></div>
          </dl>
          <p><ShieldCheck size={15} />不保存头像副本或内部账号标识</p>
        </aside>
      </section>
      <section className="stats-grid home-stats">
        <Stat icon={Database} label="数据库" value={account?.database_count || 0} detail={account?.coverage.complete ? "密钥覆盖完整" : "等待完整授权"} />
        <Stat icon={MessageCircle} label="可用会话" value={totalConversations} detail="私聊与群聊" />
        <Stat icon={Archive} label="已选择" value={selected.length} detail="保留到本次退出" />
        <Stat icon={Clock3} label="最近导出" value={last ? formatDate(last.completed_at) : "暂无"} detail={last ? `${last.message_count} 条消息` : "尚无导出记录"} />
      </section>
      <section className="account-statistics-panel">
        <div className="statistics-intro">
          <span className="statistics-icon"><BarChart3 size={22} /></span>
          <div>
            <span className="eyebrow green">只读全量统计</span>
            <h3>{accountStatistics ? `${accountStatistics.message_count.toLocaleString()} 条聊天消息` : "扫描全部私聊与群聊"}</h3>
            <p>
              {accountStatistics
                ? `${accountStatistics.conversation_count} 个有效会话 · ${formatDate(accountStatistics.earliest_at)} 至 ${formatDate(accountStatistics.latest_at)}${accountStatistics.stale ? " · 数据已变化，建议重新扫描" : ""}`
                : "逐个读取全部消息分片，只保存会话名称和数量，不保存聊天正文。"}
            </p>
          </div>
        </div>
        <div className="statistics-actions">
          {accountStatistics && <button className="secondary compact" onClick={() => setStatisticsOpen(!statisticsOpen)}>{statisticsOpen ? "收起完整统计" : "查看完整统计"}</button>}
          <button className="primary compact" disabled={!account || Boolean(scanning)} onClick={() => void startAccountStatisticsScan()}>
            <RefreshCw size={15} />{accountStatistics ? "重新扫描" : "开始扫描"}
          </button>
        </div>
        {scanning && (
          <div className="statistics-progress">
            <Progress operation={statisticsOperation as Operation} />
            <div className="statistics-live">
              <span>阶段：{detail?.phase === "inventory" ? "清点数据库" : detail?.phase === "saving" ? "保存汇总" : "遍历消息"}</span>
              <span>已处理 {(detail?.processed_messages || 0).toLocaleString()} 条</span>
              <span>已识别 {detail?.conversation_count || 0} 个会话</span>
              {detail?.database && <span>{detail.database}</span>}
              <button className="text-button muted" onClick={() => void invoke("cancel_operation", statisticsOperation?.operation_id)}>取消</button>
            </div>
          </div>
        )}
        {accountStatistics && (
          <div className="statistics-snapshot">
            <span><b>{accountStatistics.by_conversation_kind.private || 0}</b> 私聊</span>
            <span><b>{accountStatistics.by_conversation_kind.group || 0}</b> 群聊</span>
            {Object.entries(accountStatistics.by_message_type).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([key, value]) => (
              <span key={key}><b>{value.toLocaleString()}</b> {key}</span>
            ))}
            <em>{accountStatistics.stale ? "统计已过期" : `更新于 ${formatDate(accountStatistics.calculated_at)}`}</em>
          </div>
        )}
      </section>
      {statisticsOpen && accountStatistics && (
        <section className="statistics-detail">
          <div className="section-toolbar">
            <div><h3>逐会话统计</h3><p>统计结果不包含消息正文、发送者和内部账号标识。</p></div>
            <div className="statistics-controls">
              <label className="search-box"><Search size={15} /><input value={statisticsQuery} onChange={(event) => setStatisticsQuery(event.target.value)} placeholder="搜索会话名称" /></label>
              <select value={statisticsSort} onChange={(event) => setStatisticsSort(event.target.value as typeof statisticsSort)}>
                <option value="count">消息最多</option><option value="latest">最近活跃</option><option value="name">名称排序</option>
              </select>
            </div>
          </div>
          <div className="statistics-table">
            <div className="statistics-table-head"><span>会话</span><span>类型</span><span>消息数量</span><span>时间范围</span></div>
            {statisticRows.map((item) => (
              <article key={item.conversation_id}>
                <strong>{publicText(item.display_name)}</strong><span>{kindLabel(item.kind)}</span><b>{item.message_count.toLocaleString()}</b>
                <small>{formatDate(item.earliest_at)} — {formatDate(item.latest_at)}</small>
              </article>
            ))}
          </div>
        </section>
      )}
      <section className="workbench-launches" aria-label="工作台快捷入口">
        <button className="workbench-card workbench-primary" onClick={() => setView(account ? "conversations" : "settings")}>
          <span className="workbench-icon"><MessageCircle size={22} /></span><span className="workbench-kicker">会话浏览</span>
          <strong>{account ? "浏览并选择聊天" : "先选择本地账号"}</strong>
          <p>{account ? "查看私聊和群聊，在固定预览区确认内容并加入导出。" : "完成账号授权后，聊天会话会显示在这里。"}</p>
          <span className="workbench-meta">{account ? `${totalConversations} 个可用会话` : "前往账号设置"}<ArrowRight size={16} /></span>
        </button>
        <button className="workbench-card" onClick={() => setView("export")}>
          <span className="workbench-icon"><Download size={22} /></span><span className="workbench-kicker">导出工作台</span>
          <strong>{selected.length ? `继续整理 ${selected.length} 个会话` : "整理导出范围"}</strong><p>设置时间、格式、媒体和保存位置。</p>
          <span className="workbench-meta">{selected.length ? "继续当前导出" : "开始准备导出"}<ArrowRight size={16} /></span>
        </button>
        <button className="workbench-card" onClick={() => setView("media")}>
          <span className="workbench-icon"><HardDrive size={22} /></span><span className="workbench-kicker">媒体完整性</span><strong>检查媒体可用性</strong>
          <p>扫描图片、表情、视频和文件的本地恢复状态。</p><span className="workbench-meta">{mediaStatus}<ArrowRight size={16} /></span>
        </button>
      </section>
    </div>
  );
}
