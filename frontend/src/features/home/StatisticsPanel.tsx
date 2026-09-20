import { useState } from "react";
import { BarChart3, ChevronDown, RefreshCw } from "lucide-react";
import { invoke } from "../../bridge";
import { useWorkbench } from "../../store";
import { Panel, StatusBadge } from "../../ui/layout";
import { EmptyState, Progress } from "../../ui/primitives";
import { formatDate } from "../../utils/format";
import { messageTypeLabel, operationIsRunning } from "../../utils/labels";
import { StatisticsDetail } from "./StatisticsDetail";

export function StatisticsPanel() {
  const {
    account,
    accountStatistics: report,
    operations,
    accountStatisticsOperationId,
    startAccountStatisticsScan,
  } = useWorkbench();
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState("");
  const operation = accountStatisticsOperationId
    ? operations[accountStatisticsOperationId]
    : undefined;
  const running = operationIsRunning(operation?.status);
  const types = Object.entries(report?.by_message_type || {}).sort(
    (a, b) => b[1] - a[1],
  );
  const largest = Math.max(1, ...types.map(([, count]) => count));
  const cancel = async () => {
    try {
      await invoke("cancel_operation", operation?.operation_id);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  };
  return (
    <>
      <Panel
        title="聊天数据概览"
        description={
          report
            ? `更新于 ${formatDate(report.calculated_at, { year: "numeric" })}`
            : "扫描后了解聊天规模与消息分布。"
        }
        className="home-statistics-panel"
        action={
          <button
            className="secondary compact"
            disabled={!account || running}
            onClick={() => void startAccountStatisticsScan()}
          >
            <RefreshCw size={15} />
            {running ? "扫描中…" : report ? "更新统计" : "开始扫描"}
          </button>
        }
      >
        {report ? (
          <>
            <div className="home-statistics-summary">
              <div>
                <strong>{report.message_count.toLocaleString()}</strong>
                <span>条聊天消息</span>
              </div>
              <StatusBadge
                tone={report.stale || !report.complete ? "warning" : "success"}
              >
                {report.stale
                  ? "数据已变化"
                  : report.complete
                    ? "统计完整"
                    : "部分统计"}
              </StatusBadge>
            </div>
            <p className="home-statistics-range">
              {formatDate(report.earliest_at, { year: "numeric" })} —{" "}
              {formatDate(report.latest_at, { year: "numeric" })}
            </p>
            <div className="home-kind-summary">
              <span>
                <b>{report.by_conversation_kind.private || 0}</b> 个私聊
              </span>
              <span>
                <b>{report.by_conversation_kind.group || 0}</b> 个群聊
              </span>
              <span>
                <b>{report.conversation_count}</b> 个有效会话
              </span>
            </div>
            <div className="home-message-bars">
              {types.slice(0, 5).map(([type, count]) => (
                <div key={type}>
                  <span>{messageTypeLabel(type)}</span>
                  <div>
                    <i style={{ width: `${(count / largest) * 100}%` }} />
                  </div>
                  <b>{count.toLocaleString()}</b>
                </div>
              ))}
            </div>
            <button
              className="home-detail-toggle"
              aria-expanded={expanded}
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? "收起会话明细" : "查看逐会话统计"}
              <ChevronDown size={17} className={expanded ? "is-open" : ""} />
            </button>
          </>
        ) : (
          !running && (
            <EmptyState
              icon={BarChart3}
              title="还没有统计结果"
              text="按需扫描全部会话，只保存数量与时间范围，不保存聊天正文。"
            />
          )
        )}
        {running && operation && (
          <div className="home-scan-progress">
            <Progress operation={operation} />
            <div>
              <span>
                已处理{" "}
                {(
                  operation.progress_detail?.processed_messages || 0
                ).toLocaleString()}{" "}
                条消息
              </span>
              <button className="text-button" onClick={() => void cancel()}>
                取消扫描
              </button>
            </div>
          </div>
        )}
        {operation?.status === "failed" && (
          <p className="error-text" role="alert">
            {operation.error || "统计扫描失败，请重试。"}
          </p>
        )}
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
      </Panel>
      {expanded && report && <StatisticsDetail report={report} />}
    </>
  );
}
