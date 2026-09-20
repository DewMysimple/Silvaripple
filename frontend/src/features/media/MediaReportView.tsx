import { useState } from "react";
import { Check, FileSearch, FolderOpen, Image } from "lucide-react";
import type { MediaReport } from "../../types";
import { Stat } from "../../ui/primitives";
import { Panel } from "../../ui/layout";
import { formatDate } from "../../utils/format";
import { messageTypeLabel } from "../../utils/labels";

const reasonLabels: Record<string, string> = {
  decode_failed: "本地缓存暂时无法解码，可在微信中重新打开后重试",
  local_media_missing: "本机没有缓存，请先在微信中打开这份媒体",
  remote_url_missing: "没有可下载地址，需从微信补充本地缓存",
  private_cdn_key_missing: "缺少媒体解密信息，暂时无法恢复",
  wxgf_conversion_failed: "图片转换失败，可重新检测或更新应用后重试",
};

export function MediaReportView({
  report,
  scopeLabel,
}: {
  report: MediaReport;
  scopeLabel: string;
}) {
  const [category, setCategory] = useState("all");
  const [reason, setReason] = useState("all");
  const [page, setPage] = useState(0);
  const reasons = [
    ...new Set(
      (report.items || []).map((item) => item.reason_code || "unknown"),
    ),
  ];
  const items = (report.items || []).filter(
    (item) =>
      (category === "all" || item.category === category) &&
      (reason === "all" || (item.reason_code || "unknown") === reason),
  );
  const pageSize = 20;
  return (
    <>
      <div className="stats-grid media-stats">
        <Stat
          icon={Image}
          label="媒体引用"
          value={report.referenced.toLocaleString()}
          detail={scopeLabel}
        />
        <Stat
          icon={Check}
          label="可恢复"
          value={report.recoverable.toLocaleString()}
          detail="本地已准备好"
        />
        <Stat
          icon={FolderOpen}
          label="未缓存"
          value={report.missing.toLocaleString()}
          detail="在微信中打开后重试"
        />
        <Stat
          icon={FileSearch}
          label="无法识别"
          value={report.unsupported.toLocaleString()}
          detail="需要查看具体原因"
        />
      </div>
      <Panel
        title="按媒体类型查看"
        description="汇总本次检查的媒体引用与恢复状态。"
      >
        <div className="media-table-scroll">
          <table className="media-table">
            <thead>
              <tr>
                <th>媒体类型</th>
                <th>引用总数</th>
                <th>可恢复</th>
                <th>未缓存</th>
                <th>无法识别</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(report.by_category).map(([key, value]) => (
                <tr key={key}>
                  <th scope="row">{messageTypeLabel(key)}</th>
                  <td>{value.referenced || 0}</td>
                  <td className="green-text">{value.recoverable || 0}</td>
                  <td>{value.missing || 0}</td>
                  <td>{value.unsupported || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <Panel
        title="需要关注的媒体"
        description="先在微信中打开对应图片、视频或文件，再重新检查。"
        action={<span className="media-result-count">{items.length} 项</span>}
      >
        <div className="media-filters">
          <div className="choice-chips" aria-label="媒体类型筛选">
            <button
              aria-pressed={category === "all"}
              className={category === "all" ? "active" : ""}
              onClick={() => {
                setCategory("all");
                setPage(0);
              }}
            >
              全部类型
            </button>
            {Object.keys(report.by_category).map((key) => (
              <button
                key={key}
                aria-pressed={category === key}
                className={category === key ? "active" : ""}
                onClick={() => {
                  setCategory(key);
                  setPage(0);
                }}
              >
                {messageTypeLabel(key)}
              </button>
            ))}
          </div>
          {reasons.length > 1 && (
            <select
              aria-label="恢复原因筛选"
              value={reason}
              onChange={(event) => {
                setReason(event.target.value);
                setPage(0);
              }}
            >
              <option value="all">全部原因</option>
              {reasons.map((key) => (
                <option value={key} key={key}>
                  {reasonLabels[key] || "暂时无法恢复"}
                </option>
              ))}
            </select>
          )}
        </div>
        {items.length ? (
          <div className="recovery-item-list">
            {items
              .slice(page * pageSize, (page + 1) * pageSize)
              .map((item, index) => (
                <article
                  key={`${item.conversation_id}:${item.sent_at}:${index}`}
                >
                  <span className="media-kind">
                    {messageTypeLabel(item.category)}
                  </span>
                  <div>
                    <strong>{item.conversation_name}</strong>
                    <small>{formatDate(item.sent_at)}</small>
                  </div>
                  <p>
                    {reasonLabels[item.reason_code || ""] ||
                      "本地暂时无法恢复，可在微信中打开后重试"}
                  </p>
                </article>
              ))}
          </div>
        ) : (
          <p className="media-no-issues">当前筛选下没有需要处理的媒体。</p>
        )}
        {items.length > pageSize && (
          <div className="pagination">
            <span>
              第 {page + 1} / {Math.ceil(items.length / pageSize)} 页
            </span>
            <button
              className="secondary compact"
              disabled={!page}
              onClick={() => setPage(page - 1)}
            >
              上一页
            </button>
            <button
              className="secondary compact"
              disabled={(page + 1) * pageSize >= items.length}
              onClick={() => setPage(page + 1)}
            >
              下一页
            </button>
          </div>
        )}
        {report.truncated > 0 && (
          <p className="media-footnote">
            还有 {report.truncated} 项包含在上方分类汇总中，明细仅展示前 500
            项。
          </p>
        )}
      </Panel>
    </>
  );
}
