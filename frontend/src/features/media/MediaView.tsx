import { useEffect, useState } from "react";
import { ArrowRight, Image, RefreshCw } from "lucide-react";
import { useWorkbench } from "../../store";
import { invoke } from "../../bridge";
import type { MediaReport, Operation } from "../../types";
import { EmptyState, Progress } from "../../ui/primitives";
import { PageIntro, Panel, StatusBadge } from "../../ui/layout";
import { operationIsRunning } from "../../utils/labels";
import { MediaReportView } from "./MediaReportView";

export function MediaView() {
  const {
    account,
    selected,
    operations,
    mediaScanOperationId,
    mediaScanConversationIds,
    startMediaScan,
    setView,
  } = useWorkbench();
  const [scope, setScope] = useState<"all" | "selected">(
    selected.length ? "selected" : "all",
  );
  const [starting, setStarting] = useState(false);
  const [actionError, setActionError] = useState("");
  useEffect(() => {
    if (!selected.length) setScope("all");
  }, [selected.length]);
  const operation = mediaScanOperationId
    ? (operations[mediaScanOperationId] as Operation<MediaReport> | undefined)
    : undefined;
  const running = starting || operationIsRunning(operation?.status);
  const report =
    operation?.status === "completed" ? operation.result : undefined;
  const scan = async () => {
    if (!account || running) return;
    setStarting(true);
    setActionError("");
    try {
      await startMediaScan(scope === "all" ? [] : [...selected]);
    } finally {
      setStarting(false);
    }
  };
  const cancel = async () => {
    if (!mediaScanOperationId) return;
    try {
      await invoke("cancel_operation", mediaScanOperationId);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  };
  return (
    <div className="page media-page">
      <PageIntro
        title="让归档里的图片和文件更完整"
        description="检查本机缓存，了解哪些媒体已可恢复、哪些需要在微信中重新打开。"
      />
      <Panel
        title="检查范围"
        description="检查只读取本地数据；联网补全可在导出时单独设置。"
        action={<StatusBadge tone="success">本地只读检查</StatusBadge>}
      >
        <div className="media-scan-controls">
          <div className="media-scope" role="group" aria-label="检查范围">
            <button
              aria-pressed={scope === "all"}
              className={scope === "all" ? "selected" : ""}
              disabled={running}
              onClick={() => setScope("all")}
            >
              <strong>整个账号</strong>
              <span>当前账号的全部会话</span>
            </button>
            <button
              aria-pressed={scope === "selected"}
              className={scope === "selected" ? "selected" : ""}
              disabled={!selected.length || running}
              onClick={() => setScope("selected")}
            >
              <strong>已选会话</strong>
              <span>
                {selected.length
                  ? `${selected.length} 个已选会话`
                  : "先在会话浏览中选择"}
              </span>
            </button>
          </div>
          <button
            className="primary"
            disabled={!account || running}
            onClick={() => void scan()}
          >
            <RefreshCw size={17} />
            {running ? "正在检查…" : report ? "重新检查" : "开始检查"}
          </button>
        </div>
        {operation && operationIsRunning(operation.status) && (
          <div className="media-progress">
            <Progress operation={operation} />
            <button className="text-button" onClick={() => void cancel()}>
              取消检查
            </button>
          </div>
        )}
        {actionError && (
          <p className="error-text" role="alert">
            {actionError}
          </p>
        )}
      </Panel>
      {report ? (
        <>
          <MediaReportView
            key={operation?.operation_id}
            report={report}
            scopeLabel={
              mediaScanConversationIds.length
                ? `${mediaScanConversationIds.length} 个会话`
                : "当前账号全部会话"
            }
          />
          {report.recoverable > 0 && (
            <div className="media-ready">
              <div>
                <strong>
                  {report.recoverable.toLocaleString()} 项媒体已可用于归档
                </strong>
                <p>回到导出工作台，确认范围后即可保存聊天和媒体。</p>
              </div>
              <button className="primary" onClick={() => setView("export")}>
                前往导出
                <ArrowRight size={16} />
              </button>
            </div>
          )}
        </>
      ) : (
        !running && (
          <Panel>
            <EmptyState
              icon={Image}
              title={
                !account
                  ? "先连接微信账号"
                  : operation?.status === "failed"
                    ? "检查未完成"
                    : operation?.status === "cancelled"
                      ? "检查已取消"
                      : "归档前，先了解媒体状态"
              }
              text={
                operation?.error ||
                (!account
                  ? "选择数据位置并授权后，即可检查媒体缓存。"
                  : "选择检查范围后开始。首次检查可能需要一些时间，可以切换页面，进度会继续保留。")
              }
              action={
                !account && (
                  <button
                    className="secondary"
                    onClick={() => setView("settings")}
                  >
                    连接账号
                  </button>
                )
              }
            />
          </Panel>
        )
      )}
    </div>
  );
}
