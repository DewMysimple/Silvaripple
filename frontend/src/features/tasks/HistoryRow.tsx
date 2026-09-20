import {
  Archive,
  BarChart3,
  FolderOpen,
  Image,
  MoreHorizontal,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";
import type { HistoryEntry } from "../../types";
import { StatusBadge } from "../../ui/layout";
import { formatDate } from "../../utils/format";
import { messageTypeLabel } from "../../utils/labels";
import {
  directoryLabel,
  historyActions,
  historySummary,
  isAbnormal,
  statusTone,
  taskKindLabel,
  taskStatusLabel,
} from "./historyModel";
import { TaskMenu } from "./TaskMenu";

export function HistoryRow({
  item,
  selected,
  busy,
  onSelect,
  onOpen,
  onRelink,
  onTrash,
  onRemove,
}: {
  item: HistoryEntry;
  selected: boolean;
  busy: boolean;
  onSelect(): void;
  onOpen(): void;
  onRelink(): void;
  onTrash(): void;
  onRemove(): void;
}) {
  const actions = historyActions(item);
  const Icon =
    item.kind === "export"
      ? Archive
      : item.kind === "media_scan"
        ? Image
        : BarChart3;
  const date = formatDate(item.completed_at || item.created_at);
  const warnings = item.warning_details.reduce(
    (sum, detail) => sum + detail.count,
    0,
  );
  const hasDetails = Boolean(
    item.current_path ||
    item.formats.length ||
    warnings ||
    item.superseded_count,
  );
  const menuActions = [
    ...(actions.canRelink && !actions.needsRelink
      ? [{ label: "重新定位归档", icon: RefreshCw, onSelect: onRelink }]
      : []),
    ...(actions.canTrash
      ? [{ label: "移入回收站", icon: Trash2, danger: true, onSelect: onTrash }]
      : []),
    {
      label: "仅删除记录",
      icon: X,
      disabled: !actions.canRemove,
      onSelect: onRemove,
    },
  ];
  return (
    <article
      className={`history-row ${isAbnormal(item) ? "has-issue" : ""} ${selected ? "is-selected" : ""}`}
    >
      <label className="history-checkbox">
        <input
          type="checkbox"
          className="green-check"
          checked={selected}
          disabled={busy || !actions.canRemove}
          onChange={onSelect}
          aria-label={`选择${date}的${taskKindLabel(item.kind)}记录`}
        />
      </label>
      <div className="history-icon" aria-hidden="true">
        <Icon size={20} />
      </div>
      <div className="history-content">
        <div className="history-title">
          <h4>{taskKindLabel(item.kind)}</h4>
          <StatusBadge tone={statusTone(item.status)}>
            {taskStatusLabel(item.status)}
          </StatusBadge>
          {item.kind === "export" && (
            <StatusBadge tone={isAbnormal(item) ? "warning" : "neutral"}>
              {directoryLabel(item)}
            </StatusBadge>
          )}
        </div>
        <p className="history-summary">{historySummary(item)}</p>
        <div className="history-time">
          <time dateTime={item.completed_at || item.created_at}>{date}</time>
          {item.duration_seconds != null && (
            <span>耗时 {Math.round(item.duration_seconds)} 秒</span>
          )}
        </div>
        {item.error_summary && (
          <p className="history-error">{item.error_summary}</p>
        )}
        {hasDetails && (
          <details className="history-details">
            <summary>
              查看{item.kind === "export" ? "归档" : "任务"}详情
              {warnings > 0 && <span>{warnings} 项媒体提醒</span>}
            </summary>
            <div className="history-detail-content">
              {item.formats.length > 0 && (
                <p>
                  输出格式：
                  {item.formats
                    .map((format) => format.toUpperCase())
                    .join(" · ")}
                </p>
              )}
              {item.current_path && (
                <div className="history-path">
                  <span>归档位置</span>
                  <code>{item.current_path}</code>
                </div>
              )}
              {Boolean(item.superseded_count) && (
                <p>
                  {item.superseded_count}{" "}
                  个会话已有更新版本，删除旧记录不会影响当前归档。
                </p>
              )}
              {item.warning_details.length > 0 && (
                <ul>
                  {item.warning_details.map((warning, index) => (
                    <li key={`${warning.code}-${index}`}>
                      <strong>
                        {messageTypeLabel(warning.category)} · {warning.count}
                      </strong>
                      <span>{warning.message}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </details>
        )}
      </div>
      <div className="history-actions">
        {actions.canOpen && (
          <button
            className="secondary compact"
            disabled={busy}
            onClick={onOpen}
          >
            <FolderOpen size={15} />
            打开归档
          </button>
        )}
        {actions.needsRelink && actions.canRelink && (
          <button
            className="secondary compact"
            disabled={busy}
            onClick={onRelink}
          >
            <RefreshCw size={15} />
            重新定位
          </button>
        )}
        <TaskMenu
          label={`更多${taskKindLabel(item.kind)}操作`}
          compact
          disabled={busy}
          actions={menuActions}
        >
          <MoreHorizontal size={19} />
        </TaskMenu>
      </div>
    </article>
  );
}
