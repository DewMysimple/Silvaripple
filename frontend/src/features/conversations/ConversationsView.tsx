import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowRight, MessageCircle, Search } from "lucide-react";
import { useWorkbench } from "../../store";
import { EmptyState } from "../../ui/primitives";
import { publicText } from "../../utils/format";
import { ConversationRow } from "./ConversationRow";
import { MessageBubble } from "./MessageBubble";

export function ConversationsView() {
  const {
    conversations,
    conversationResultTotal,
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
    conversationsLoading,
    previewLoading,
    olderLoading,
    account,
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
        <header className="browser-heading">
          <h2>聊天会话</h2>
          <span>{conversationResultTotal} 个</span>
        </header>
        <div className="conversation-toolbar">
          <label className="search-box">
            <Search size={17} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索会话名称"
              aria-label="搜索会话名称"
            />
          </label>
          <select
            aria-label="会话类型"
            value={kind}
            onChange={(event) => setKind(event.target.value)}
          >
            <option value="all">私聊与群聊</option>
            <option value="private">私聊</option>
            <option value="group">群聊</option>
          </select>
        </div>
        <div className="selection-bar">
          <span>已选择 {selected.length} 个</span>
          <div>
            <button className="text-button" onClick={selectVisible}>
              全选已加载
            </button>
            {selected.length > 0 && (
              <button className="text-button muted" onClick={clearSelected}>
                清空
              </button>
            )}
          </div>
        </div>
        <div className="conversation-list">
          {conversationsLoading && !conversations.length
            ? Array.from({ length: 7 }, (_, index) => (
                <div className="skeleton-row" key={index} />
              ))
            : conversations.map((item) => (
                <ConversationRow item={item} key={item.conversation_id} />
              ))}
          {!conversationsLoading && !conversations.length && (
            <EmptyState
              icon={Search}
              title={account ? "没有找到会话" : "先连接微信账号"}
              text={
                account
                  ? "尝试其他名称或切换会话类型。"
                  : "在设置中选择数据位置并授权读取。"
              }
              action={
                !account && (
                  <button
                    className="secondary"
                    onClick={() => setView("settings")}
                  >
                    前往设置
                  </button>
                )
              }
            />
          )}
          {conversations.length < conversationResultTotal && (
            <button
              className="conversation-load-more text-button"
              disabled={conversationsLoading}
              onClick={() =>
                void loadConversations({
                  query,
                  kind,
                  page: Math.floor(conversations.length / 200) + 1,
                })
              }
            >
              {conversationsLoading
                ? "正在加载…"
                : `加载更多 · 已显示 ${conversations.length} / ${conversationResultTotal}`}
            </button>
          )}
        </div>
        <footer className="conversation-footer">
          <span>选择的会话会保留在本次工作台中</span>
          <button
            className="primary wide"
            disabled={!selected.length}
            onClick={() => setView("export")}
          >
            导出已选 {selected.length} 个会话
            <ArrowRight size={16} />
          </button>
        </footer>
      </section>
      <section className="preview-panel">
        {activeConversation ? (
          <>
            <header className="preview-header">
              <div>
                <strong>{publicText(activeConversation.display_name)}</strong>
                <span>
                  {previewLoading
                    ? "正在读取聊天记录…"
                    : `${previewTotal.toLocaleString()} 条消息 · 只读预览`}
                </span>
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
                    disabled={olderLoading}
                  >
                    {olderLoading ? "正在加载…" : "加载更早的 100 条"}
                  </button>
                )}
                {previewLoading && (
                  <div className="loading-state" role="status">
                    正在读取聊天记录…
                  </div>
                )}
                {!previewLoading && !preview.length && (
                  <EmptyState
                    icon={MessageCircle}
                    title="暂无可预览的消息"
                    text="这个会话没有可读取的消息记录。"
                  />
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
            text="点击左侧会话预览聊天内容，勾选需要归档的会话后进入导出工作台。"
          />
        )}
      </section>
    </div>
  );
}
