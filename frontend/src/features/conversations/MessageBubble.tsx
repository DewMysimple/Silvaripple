import { Image } from "lucide-react";
import { formatDate, publicText } from "../../utils/format";
import { messageTypeLabel } from "../../utils/labels";
import type { Message } from "../../types";

export function MessageBubble({ message }: { message: Message }) {
  if (message.system_event)
    return (
      <div className="system-message">
        {publicText(message.system_event.text)}
      </div>
    );
  const text =
    publicText(message.display_text || message.text) ||
    (message.attachments.length
      ? ""
      : `[${messageTypeLabel(message.message_type)}]`);
  const mediaOnly =
    !text && !message.quote_preview && message.attachments.length > 0;
  return (
    <article className={`message ${message.outgoing ? "outgoing" : ""}`}>
      <div className="message-avatar">
        {message.sender_avatar_data_url ? (
          <img src={message.sender_avatar_data_url} alt="发送者头像" />
        ) : (
          publicText(message.sender_name).slice(0, 1) || "未"
        )}
      </div>
      <div className="message-stack">
        <span className="message-sender">
          {publicText(message.sender_name) || "未知成员"}
        </span>
        <div className={`bubble ${mediaOnly ? "media-only" : ""}`}>
          {message.quote_preview && (
            <blockquote>
              <strong>
                {publicText(message.quote_preview.sender_name) || "未知成员"}
              </strong>
              <span>
                {publicText(message.quote_preview.text) ||
                  `[${messageTypeLabel(message.quote_preview.message_type || "unknown")}]`}
              </span>
            </blockquote>
          )}
          {text && <p>{text}</p>}
          {message.attachments.map((attachment) =>
            attachment.preview_data_url ? (
              <img
                className={
                  attachment.category === "emoji"
                    ? "emoji-media"
                    : "message-media"
                }
                src={attachment.preview_data_url}
                alt={attachment.category === "emoji" ? "表情包" : "聊天图片"}
                key={attachment.attachment_id}
              />
            ) : (
              <div className="media-placeholder" key={attachment.attachment_id}>
                <Image size={16} />
                <div>
                  <strong>
                    {attachment.category === "emoji"
                      ? "表情缓存不完整"
                      : attachment.category === "video"
                        ? "视频暂不可预览"
                        : attachment.category === "file"
                          ? "文件暂不可用"
                          : "媒体暂不可用"}
                  </strong>
                  <span>{attachment.reason || "导出时将继续尝试恢复"}</span>
                  {attachment.reason_code && (
                    <details>
                      <summary>诊断详情</summary>
                      <code>{attachment.reason_code}</code>
                    </details>
                  )}
                </div>
              </div>
            ),
          )}
        </div>
        <time>{formatDate(message.sent_at)}</time>
      </div>
    </article>
  );
}
