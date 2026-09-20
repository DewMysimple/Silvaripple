import { FileSearch, Search, SlidersHorizontal, X } from "lucide-react";
import { useWorkbench } from "../../store";
import { EmptyState, Progress } from "../../ui/primitives";
import { PageIntro, Panel, StatusBadge } from "../../ui/layout";
import { formatDate, kindLabel } from "../../utils/format";
import { MESSAGE_TYPES } from "../../utils/labels";
import { useMessageSearch } from "./useMessageSearch";

export function SearchView() {
  const { account, selected, conversations, openConversation, setView } =
    useWorkbench();
  const search = useMessageSearch();
  return (
    <div className="page search-page">
      <PageIntro
        title="从聊天中，找回一条线索"
        description="搜索当前账号的聊天内容，按时间、消息类型或已选会话缩小范围。"
      />
      <Panel className="search-controls-panel">
        <form
          className="global-search"
          onSubmit={(event) => {
            event.preventDefault();
            void search.run();
          }}
        >
          <Search size={21} />
          <input
            aria-label="搜索聊天内容"
            value={search.query}
            onChange={(event) => search.setQuery(event.target.value)}
            placeholder="输入消息关键词"
          />
          {search.query && (
            <button
              type="button"
              className="icon-button"
              aria-label="清空关键词"
              onClick={() => search.setQuery("")}
            >
              <X size={16} />
            </button>
          )}
          <button
            className="primary"
            disabled={
              !account ||
              !search.query.trim() ||
              search.running ||
              !!search.dateError
            }
          >
            {search.running ? "正在搜索…" : "搜索聊天"}
          </button>
        </form>
        <div className="search-filters">
          <label className="field">
            开始日期
            <input
              type="date"
              value={search.startAt}
              onChange={(event) => search.setStartAt(event.target.value)}
            />
          </label>
          <label className="field">
            结束日期
            <input
              type="date"
              value={search.endAt}
              min={search.startAt || undefined}
              onChange={(event) => search.setEndAt(event.target.value)}
            />
          </label>
          <label className="field">
            消息类型
            <select
              value={search.messageType}
              onChange={(event) => search.setMessageType(event.target.value)}
            >
              <option value="all">全部类型</option>
              {MESSAGE_TYPES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label className="inline-check">
            <input
              className="green-check"
              type="checkbox"
              checked={search.selectedOnly}
              disabled={!selected.length}
              onChange={(event) => search.setSelectedOnly(event.target.checked)}
            />
            <span>
              仅已选会话{selected.length ? `（${selected.length}）` : ""}
            </span>
          </label>
        </div>
        {search.dateError && (
          <p className="error-text" role="alert">
            {search.dateError}
          </p>
        )}
        <div className="search-hint">
          <span>
            <SlidersHorizontal size={14} />
            不填写日期时搜索全部时间
          </span>
          <span>关键词与结果仅在本次使用中保留</span>
        </div>
      </Panel>
      {search.error && (
        <div className="search-error" role="alert">
          <strong>搜索未完成</strong>
          <p>{search.error}</p>
          <button
            className="secondary compact"
            disabled={search.running}
            onClick={() => void search.run()}
          >
            重试搜索
          </button>
        </div>
      )}
      <Panel
        className="search-results-panel"
        title={
          search.searchedQuery
            ? `“${search.searchedQuery}”的搜索结果`
            : "搜索结果"
        }
        action={
          search.running ? (
            search.operation ? (
              <button
                className="text-button"
                onClick={() => void search.cancel()}
              >
                取消搜索
              </button>
            ) : (
              <StatusBadge>正在发起搜索…</StatusBadge>
            )
          ) : search.operation?.status === "completed" ? (
            <StatusBadge>{search.items.length} 条结果</StatusBadge>
          ) : undefined
        }
      >
        {search.running ? (
          <div role="status">
            {search.operation && <Progress operation={search.operation} />}
            <div className="search-skeleton">
              {Array.from({ length: 4 }, (_, index) => (
                <div key={index}>
                  <i />
                  <span />
                </div>
              ))}
            </div>
          </div>
        ) : search.items.length ? (
          <>
            <div className="result-list">
              {search.items.map((item) => (
                <button
                  className="search-result"
                  key={`${item.conversation_id}:${item.message_id}`}
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
                  <div className="result-identity">
                    <strong>{item.conversation_name}</strong>
                    <span>
                      {kindLabel(item.conversation_kind)} · {item.sender_name}
                    </span>
                  </div>
                  <p>{item.snippet}</p>
                  <time>{formatDate(item.sent_at)}</time>
                </button>
              ))}
            </div>
            <p className="search-footnote">
              最多展示 300 条结果。点击结果可打开对应会话预览。
            </p>
          </>
        ) : (
          <EmptyState
            icon={FileSearch}
            title={
              !account
                ? "先连接微信账号"
                : search.operation?.status === "completed"
                  ? "没有找到匹配的消息"
                  : search.operation?.status === "cancelled"
                    ? "搜索已取消"
                    : "每一条记录，都有迹可循"
            }
            text={
              !account
                ? "选择本地数据位置并授权后，即可搜索聊天记录。"
                : search.operation?.status === "completed"
                  ? "尝试缩短关键词、扩大日期范围，或取消已选会话限制。"
                  : "输入关键词开始搜索。搜索通过只读快照进行，不会修改微信数据。"
            }
            action={
              !account && (
                <button className="primary" onClick={() => setView("settings")}>
                  连接账号
                </button>
              )
            }
          />
        )}
      </Panel>
    </div>
  );
}
