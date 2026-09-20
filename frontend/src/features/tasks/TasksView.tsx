import { useEffect, useRef } from "react";
import {
  AlertTriangle,
  CheckCheck,
  ChevronDown,
  Clock3,
  History,
  ListChecks,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";
import { ConfirmDialog } from "../../ui/ConfirmDialog";
import { PageIntro, Panel, StatusBadge } from "../../ui/layout";
import { EmptyState, Progress, Stat } from "../../ui/primitives";
import {
  defaultFilters,
  directoryStatuses,
  isRunning,
  taskKindLabel,
  taskKinds,
  taskStatuses,
} from "./historyModel";
import { HistoryRow } from "./HistoryRow";
import { TaskMenu } from "./TaskMenu";
import { useTaskHistory } from "./useTaskHistory";

export function TasksView() {
  const tasks = useTaskHistory();
  const selectAll = useRef<HTMLInputElement>(null);
  const selectableCount = tasks.filtered.filter(
    (item) => !isRunning(item.status),
  ).length;
  const hasFilters = Object.values(tasks.filters).some(
    (value) => value !== "all",
  );
  useEffect(() => {
    if (selectAll.current)
      selectAll.current.indeterminate =
        tasks.selected.length > 0 && tasks.selected.length < selectableCount;
  }, [tasks.selected.length, selectableCount]);

  return (
    <>
      <div className="page tasks-page">
        <PageIntro
          eyebrow="任务中心"
          title="每一次归档，都有记录"
          description="查看当前账号的任务进度、导出结果与归档状态。"
          action={
            <button
              className="secondary"
              disabled={tasks.busy}
              onClick={() => void tasks.refresh()}
            >
              <RefreshCw size={16} />
              {tasks.busy ? "处理中…" : "刷新状态"}
            </button>
          }
        />
        {tasks.error && (
          <div className="tasks-feedback" role="alert">
            <AlertTriangle size={18} />
            <span>{tasks.error}</span>
            <button
              className="icon-button"
              aria-label="关闭任务错误提示"
              onClick={tasks.clearError}
            >
              <X size={16} />
            </button>
          </div>
        )}
        <div className="stats-grid tasks-metrics">
          <Stat
            label="正在运行"
            value={tasks.active.length}
            detail="当前账号的后台任务"
            icon={Clock3}
          />
          <Stat
            label="已完成"
            value={
              tasks.history.filter((item) => item.status === "completed").length
            }
            detail="已完成处理的任务"
            icon={CheckCheck}
          />
          <Stat
            label="需要关注"
            value={tasks.abnormal}
            detail="失败任务或归档目录异常"
            icon={AlertTriangle}
          />
          <Stat
            label="全部记录"
            value={tasks.history.length}
            detail="仅保存结果，不保存正文"
            icon={History}
          />
        </div>
        <div className="section-stack">
          <Panel
            title="当前任务"
            action={
              <StatusBadge tone={tasks.active.length ? "success" : "neutral"}>
                {tasks.active.length
                  ? `${tasks.active.length} 个任务运行中`
                  : "空闲"}
              </StatusBadge>
            }
          >
            {tasks.active.length ? (
              <div className="active-task-grid">
                {tasks.active.map((item) => (
                  <article className="active-task" key={item.operation_id}>
                    <div className="active-task-heading">
                      <strong>{taskKindLabel(item.kind)}</strong>
                      <button
                        className="text-button muted"
                        disabled={tasks.busy}
                        onClick={() => void tasks.cancel(item.operation_id)}
                      >
                        取消任务
                      </button>
                    </div>
                    <Progress operation={item} />
                  </article>
                ))}
              </div>
            ) : (
              <div className="tasks-idle">
                <CheckCheck size={21} />
                <div>
                  <strong>当前没有正在运行的任务</strong>
                  <p>开始导出、媒体检查或会话统计后，可在这里查看进度。</p>
                </div>
              </div>
            )}
          </Panel>
          <Panel
            title="任务历史"
            description="结果摘要优先展示，路径与媒体提醒可按需展开。"
            className="task-history-panel"
            action={
              <TaskMenu
                label="清理任务记录"
                disabled={tasks.busy}
                actions={[
                  {
                    label: "清空异常记录",
                    description: tasks.abnormal
                      ? `${tasks.abnormal} 条需要关注的记录`
                      : "没有异常记录",
                    icon: AlertTriangle,
                    disabled: !tasks.abnormal,
                    onSelect: () => tasks.askClear("abnormal"),
                  },
                  {
                    label: "清空全部记录",
                    description: tasks.terminalCount
                      ? `${tasks.terminalCount} 条已结束记录`
                      : "没有可清理记录",
                    icon: Trash2,
                    disabled: !tasks.terminalCount,
                    danger: true,
                    onSelect: () => tasks.askClear("all"),
                  },
                ]}
              >
                清理记录
                <ChevronDown size={14} />
              </TaskMenu>
            }
          >
            <div className="history-filters">
              <label className="field">
                任务类型
                <select
                  value={tasks.filters.kind}
                  onChange={(event) =>
                    tasks.updateFilters({ kind: event.target.value })
                  }
                >
                  <option value="all">全部任务</option>
                  {taskKinds.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                执行状态
                <select
                  value={tasks.filters.status}
                  onChange={(event) =>
                    tasks.updateFilters({ status: event.target.value })
                  }
                >
                  <option value="all">全部状态</option>
                  {taskStatuses.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                归档状态
                <select
                  value={tasks.filters.health}
                  onChange={(event) =>
                    tasks.updateFilters({ health: event.target.value })
                  }
                >
                  <option value="all">全部归档状态</option>
                  {directoryStatuses.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              {hasFilters && (
                <button
                  className="text-button muted"
                  onClick={() => tasks.updateFilters(defaultFilters)}
                >
                  重置筛选
                </button>
              )}
            </div>
            <div className="history-selection-bar">
              <label>
                <input
                  ref={selectAll}
                  type="checkbox"
                  className="green-check"
                  checked={
                    selectableCount > 0 &&
                    tasks.selected.length === selectableCount
                  }
                  disabled={!selectableCount || tasks.busy}
                  onChange={(event) =>
                    tasks.selectVisible(event.target.checked)
                  }
                />
                选择当前列表
              </label>
              <span role="status">
                {tasks.selected.length
                  ? `已选择 ${tasks.selected.length} 条`
                  : `${tasks.filtered.length} 条记录`}
              </span>
              {tasks.selected.length > 0 && (
                <button
                  className="secondary compact danger"
                  disabled={tasks.busy}
                  onClick={() => tasks.askRemove(tasks.selected)}
                >
                  <Trash2 size={15} />
                  删除所选记录
                </button>
              )}
            </div>
            {tasks.filtered.length ? (
              <div className="history-list">
                {tasks.filtered.map((item) => (
                  <HistoryRow
                    key={item.history_id}
                    item={item}
                    selected={tasks.selected.includes(item.history_id)}
                    busy={tasks.busy}
                    onSelect={() => tasks.toggleSelected(item.history_id)}
                    onOpen={() => void tasks.open(item)}
                    onRelink={() => void tasks.relink(item)}
                    onTrash={() => tasks.askTrash(item)}
                    onRemove={() => tasks.askRemove([item.history_id])}
                  />
                ))}
              </div>
            ) : (
              <EmptyState
                icon={ListChecks}
                title={hasFilters ? "没有符合筛选条件的记录" : "还没有任务记录"}
                text={
                  hasFilters
                    ? "试试其他筛选条件，或查看全部任务。"
                    : "完成一次导出、媒体检查或会话统计后，结果会保存在这里。"
                }
                action={
                  hasFilters && (
                    <button
                      className="secondary"
                      onClick={() => tasks.updateFilters(defaultFilters)}
                    >
                      查看全部记录
                    </button>
                  )
                }
              />
            )}
          </Panel>
        </div>
      </div>
      <ConfirmDialog
        request={tasks.confirmation}
        onClose={tasks.closeConfirmation}
      />
    </>
  );
}
