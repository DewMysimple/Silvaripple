import {
  AlertCircle,
  Check,
  CheckCircle2,
  Download,
  FolderOpen,
  RefreshCw,
} from "lucide-react";
import { Panel, StatusBadge } from "../../ui/layout";
import { Progress } from "../../ui/primitives";
import { formatBytes } from "../../utils/format";
import { operationIsRunning } from "../../utils/labels";
import type { ExportWorkbench } from "./useExportWorkbench";

export function ExportReview({ model }: { model: ExportWorkbench }) {
  const {
    draft,
    account,
    selected,
    estimate,
    estimating,
    estimateError,
    retryEstimate,
    operation,
    running,
    starting,
    cancelling,
    blockers,
    actionError,
    notice,
  } = model;
  if (!draft) return null;
  const checks = [
    {
      label: "会话范围",
      ready: selected.length > 0,
      value: selected.length ? `${selected.length} 个会话` : "待选择",
    },
    {
      label: "输出格式",
      ready: draft.formats.length > 0,
      value: draft.formats.length ? `${draft.formats.length} 种格式` : "待选择",
    },
    {
      label: "数据库",
      ready: Boolean(account?.coverage.complete || draft.allowPartial),
      value: account?.coverage.complete
        ? "覆盖完整"
        : draft.allowPartial
          ? "部分导出"
          : "待授权",
    },
    {
      label: "保存位置",
      ready: Boolean(draft.output.trim()),
      value: draft.output.trim() ? "已设置" : "待设置",
    },
  ];
  return (
    <Panel
      title="确认并导出"
      description="检查范围和空间后，即可生成归档。"
      className="export-review"
      action={
        <StatusBadge tone={blockers.length ? "warning" : "success"}>
          {blockers.length ? "待完善" : "已就绪"}
        </StatusBadge>
      }
    >
      <div className="export-review-count">
        <strong>{selected.length}</strong>
        <span>个会话待归档</span>
      </div>
      <ul className="export-checks">
        {checks.map((check) => (
          <li key={check.label}>
            {check.ready ? (
              <CheckCircle2 size={16} />
            ) : (
              <AlertCircle size={16} className="export-check-warning" />
            )}
            <span>{check.label}</span>
            <strong>{check.value}</strong>
          </li>
        ))}
      </ul>
      <div className="export-estimate" aria-busy={estimating}>
        <div className="export-estimate-heading">
          <span>预计内容</span>
          {estimating ? (
            <small>
              <RefreshCw size={12} className="export-spin" />
              正在计算
            </small>
          ) : estimate ? (
            <small>已更新</small>
          ) : (
            <small>配置完成后计算</small>
          )}
        </div>
        <dl>
          <div>
            <dt>消息数量</dt>
            <dd>{estimate ? estimate.message_count.toLocaleString() : "—"}</dd>
          </div>
          <div>
            <dt>媒体文件</dt>
            <dd>{estimate ? estimate.media_count.toLocaleString() : "—"}</dd>
          </div>
          <div>
            <dt>已知体积</dt>
            <dd>{estimate ? formatBytes(estimate.known_bytes) : "—"}</dd>
          </div>
          <div>
            <dt>可用空间</dt>
            <dd>
              {estimate?.free_bytes ? formatBytes(estimate.free_bytes) : "—"}
            </dd>
          </div>
        </dl>
      </div>
      {estimate && draft.includeMedia && (
        <details className="export-disclosure export-recovery">
          <summary>
            <span>
              媒体可用性
              <small>
                {estimate.unavailable_count
                  ? `${estimate.unavailable_count} 项暂不可恢复`
                  : "查看恢复方式"}
              </small>
            </span>
          </summary>
          <div className="export-disclosure-body">
            <dl>
              <div>
                <dt>本地可恢复</dt>
                <dd>{estimate.local_recoverable_count}</dd>
              </div>
              <div>
                <dt>联网恢复候选</dt>
                <dd>{estimate.network_candidate_count}</dd>
              </div>
              <div>
                <dt>暂不可恢复</dt>
                <dd>{estimate.unavailable_count}</dd>
              </div>
            </dl>
            {estimate.remote_size_unknown_count > 0 && (
              <p className="export-muted">
                {estimate.remote_size_unknown_count}{" "}
                项联网媒体的大小将在下载时确认。
              </p>
            )}
          </div>
        </details>
      )}
      {estimateError && (
        <div className="export-notice warning" role="alert">
          <p>暂时无法估算：{estimateError}</p>
          <button className="text-button" onClick={retryEstimate}>
            重新计算
          </button>
        </div>
      )}
      {estimate?.warnings.map((warning) => (
        <p className="export-notice warning" key={warning}>
          {warning}
        </p>
      ))}
      {running && operation && (
        <div className="export-live-progress" role="status">
          <Progress operation={operation} />
          <button
            className="secondary wide"
            disabled={cancelling}
            onClick={() => void model.cancel()}
          >
            {cancelling ? "正在取消…" : "取消导出"}
          </button>
        </div>
      )}
      {!running && (
        <button
          className="primary wide export-start"
          disabled={Boolean(blockers.length) || starting}
          onClick={() => void model.start()}
        >
          <Download size={18} />
          {starting
            ? "正在准备…"
            : operation?.status === "completed"
              ? "再次导出"
              : "开始导出"}
        </button>
      )}
      {blockers.length > 0 && !running && (
        <ul className="export-blockers">
          {blockers.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      {operation?.status === "failed" && (
        <p className="export-notice danger" role="alert">
          {operation.error || "导出未完成，请检查配置后重试。"}
        </p>
      )}
      {operation?.status === "cancelled" && (
        <p className="export-notice" role="status">
          导出已取消，未完成的归档已清理。
        </p>
      )}
      {actionError && (
        <p className="export-notice danger" role="alert">
          {actionError}
        </p>
      )}
      {notice && (
        <p className="export-notice" role="status">
          {notice}
        </p>
      )}
      <p className="export-local-note">只读取本机数据，聊天内容不会上传。</p>
    </Panel>
  );
}

export function ExportOutcome({ model }: { model: ExportWorkbench }) {
  const result =
    model.operation?.status === "completed"
      ? model.operation.result
      : undefined;
  if (!result) return null;
  const path = result.open_path || result.root;
  const report = model.mediaOperation?.result;
  return (
    <section className="export-outcome" aria-label="导出结果" role="status">
      <span className="export-outcome-icon">
        <Check size={23} />
      </span>
      <div>
        <h3>归档已完成</h3>
        <p>
          新建 {result.created_count} 个 · 更新 {result.replaced_count} 个 · 共{" "}
          {result.message_count.toLocaleString()} 条消息
        </p>
        <span className="export-result-path">{path}</span>
        {result.warning_details.length > 0 && (
          <div className="export-result-warnings">
            <p>
              {operationIsRunning(model.mediaOperation?.status)
                ? `正在刷新媒体状态 · ${Math.round((model.mediaOperation?.progress ?? 0) * 100)}%`
                : report
                  ? `本地媒体状态已刷新，${report.missing + report.unsupported} 项仍需处理`
                  : "部分媒体尚不可用，可前往媒体检查查看详情。"}
            </p>
            <button className="text-button" onClick={model.showMedia}>
              查看媒体告警
            </button>
          </div>
        )}
        <div className="export-result-actions">
          <button
            className="primary"
            onClick={() => void model.openFolder(path)}
          >
            <FolderOpen size={16} />
            打开导出目录
          </button>
          <button
            className="secondary"
            onClick={() => void model.copyPath(path)}
          >
            复制路径
          </button>
          <button className="text-button" onClick={model.resetResult}>
            收起结果
          </button>
        </div>
      </div>
    </section>
  );
}
