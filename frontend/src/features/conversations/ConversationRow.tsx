import { Check } from "lucide-react";
import { useWorkbench } from "../../store";
import { formatDate, kindLabel, publicText } from "../../utils/format";
import type { Conversation } from "../../types";

export function ConversationRow({ item }: { item: Conversation }) {
  const { selected, toggleSelected, activeConversation, openConversation } =
    useWorkbench();
  const checked = selected.includes(item.conversation_id);
  return (
    <article
      className={`conversation-row ${activeConversation?.conversation_id === item.conversation_id ? "is-active" : ""}`}
    >
      <button
        className={`check ${checked ? "checked" : ""}`}
        onClick={(event) => {
          event.stopPropagation();
          toggleSelected(item.conversation_id);
        }}
        aria-label={`${checked ? "取消选择" : "选择会话"} ${publicText(item.display_name)}`}
        aria-pressed={checked}
      >
        {checked && <Check size={13} />}
      </button>
      <button
        className="conversation-open"
        onClick={() => void openConversation(item)}
        aria-label={`预览 ${publicText(item.display_name)}`}
        aria-current={
          activeConversation?.conversation_id === item.conversation_id
            ? "true"
            : undefined
        }
      >
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
      </button>
    </article>
  );
}
