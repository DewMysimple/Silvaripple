import { useState } from "react";
import { ArrowRight, MessageSquare, Search, X } from "lucide-react";
import { ChipGroup, Panel, StatusBadge } from "../../ui/layout";
import { formatDate } from "../../utils/format";
import { MESSAGE_TYPES } from "../../utils/labels";
import type { Conversation, ExportDraft } from "../../types";

interface Props {
  rows: Conversation[];
  draft: ExportDraft;
  onChange(value: Partial<ExportDraft>): void;
  onRemove(id: string): void;
  onClear(): void;
  onAdd(): void;
}

export function ExportScope({
  rows,
  draft,
  onChange,
  onRemove,
  onClear,
  onAdd,
}: Props) {
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState(false);
  const filtered = rows.filter((item) =>
    item.display_name
      .toLocaleLowerCase()
      .includes(query.trim().toLocaleLowerCase()),
  );
  const shown = expanded || query ? filtered : filtered.slice(0, 4);
  const dateError = Boolean(
    draft.startAt && draft.endAt && draft.startAt > draft.endAt,
  );
  const filterSummary = [
    draft.startAt || draft.endAt ? "自定义日期" : "全部日期",
    draft.messageTypes.length
      ? `${draft.messageTypes.length} 类消息`
      : "全部消息",
  ].join(" · ");
  return (
    <Panel
      title="01 · 导出范围"
      description="先选会话，再按需要缩小消息范围。"
      action={
        <button className="secondary" onClick={onAdd}>
          {rows.length ? "添加会话" : "选择会话"}
          <ArrowRight size={15} />
        </button>
      }
    >
      {!rows.length ? (
        <div className="export-scope-empty">
          <span>
            <MessageSquare size={24} />
          </span>
          <div>
            <strong>从一段聊天开始</strong>
            <p>前往会话浏览，选择要保存的私聊或群聊。</p>
          </div>
        </div>
      ) : (
        <>
          <div className="export-selection-heading">
            <StatusBadge tone="success">已选 {rows.length} 个会话</StatusBadge>
            <button className="text-button muted" onClick={onClear}>
              清空选择
            </button>
          </div>
          {rows.length > 6 && (
            <label className="export-selection-search">
              <Search size={16} />
              <input
                aria-label="筛选已选会话"
                placeholder="在已选会话中查找"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
              {query && (
                <button aria-label="清除筛选" onClick={() => setQuery("")}>
                  <X size={14} />
                </button>
              )}
            </label>
          )}
          <ul className="export-selection-list">
            {shown.map((item) => (
              <li key={item.conversation_id}>
                <span className="export-avatar">
                  {item.avatar_data_url ? (
                    <img src={item.avatar_data_url} alt="" />
                  ) : (
                    item.display_name.slice(0, 1)
                  )}
                </span>
                <div>
                  <strong>{item.display_name}</strong>
                  <small>
                    {item.kind === "unknown"
                      ? "详情暂不可见，仍会包含在导出中"
                      : `${item.kind === "group" ? "群聊" : "私聊"}${item.last_message_at ? ` · 最近消息 ${formatDate(item.last_message_at)}` : ""}`}
                  </small>
                </div>
                <button
                  className="icon-button"
                  aria-label={`移除 ${item.display_name}`}
                  onClick={() => onRemove(item.conversation_id)}
                >
                  <X size={15} />
                </button>
              </li>
            ))}
          </ul>
          {!filtered.length && (
            <p className="export-muted">没有匹配的已选会话。</p>
          )}
          {!query && filtered.length > 4 && (
            <button
              className="text-button export-expand-selection"
              aria-expanded={expanded}
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? "收起列表" : `查看其余 ${filtered.length - 4} 个会话`}
            </button>
          )}
        </>
      )}
      <details className="export-disclosure export-scope-filters">
        <summary>
          <span>
            按日期与消息类型筛选<small>{filterSummary}</small>
          </span>
        </summary>
        <div className="export-disclosure-body">
          <div className="export-date-range">
            <label>
              <span>开始日期</span>
              <input
                type="date"
                value={draft.startAt}
                max={draft.endAt || undefined}
                onChange={(event) => onChange({ startAt: event.target.value })}
              />
            </label>
            <label>
              <span>结束日期</span>
              <input
                type="date"
                value={draft.endAt}
                min={draft.startAt || undefined}
                aria-invalid={dateError}
                onChange={(event) => onChange({ endAt: event.target.value })}
              />
            </label>
          </div>
          {dateError && (
            <p className="error-text" role="alert">
              结束日期不能早于开始日期。
            </p>
          )}
          <ChipGroup
            label="消息类型"
            options={MESSAGE_TYPES}
            value={draft.messageTypes}
            onChange={(messageTypes) => onChange({ messageTypes })}
          />
          {(draft.startAt || draft.endAt || draft.messageTypes.length > 0) && (
            <button
              className="text-button"
              onClick={() =>
                onChange({ startAt: "", endAt: "", messageTypes: [] })
              }
            >
              恢复全部日期与消息
            </button>
          )}
        </div>
      </details>
    </Panel>
  );
}
