import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import type { AccountStatisticsReport } from "../../types";
import { Panel } from "../../ui/layout";
import { formatDate, kindLabel, publicText } from "../../utils/format";

const PAGE_SIZE = 12;

export function StatisticsDetail({
  report,
}: {
  report: AccountStatisticsReport;
}) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("count");
  const [page, setPage] = useState(0);
  const rows = useMemo(
    () =>
      report.conversations
        .filter((item) =>
          item.display_name
            .toLocaleLowerCase()
            .includes(query.trim().toLocaleLowerCase()),
        )
        .sort((a, b) =>
          sort === "name"
            ? a.display_name.localeCompare(b.display_name, "zh-CN")
            : sort === "latest"
              ? String(b.latest_at || "").localeCompare(
                  String(a.latest_at || ""),
                )
              : b.message_count - a.message_count,
        ),
    [report, query, sort],
  );
  const lastPage = Math.max(0, Math.ceil(rows.length / PAGE_SIZE) - 1);
  const currentPage = Math.min(page, lastPage);
  return (
    <Panel
      title="会话统计明细"
      description="仅展示名称、数量和时间范围。"
      className="home-statistics-detail"
    >
      <div className="home-detail-controls">
        <label className="search-box">
          <Search size={17} />
          <input
            aria-label="搜索统计会话"
            value={query}
            placeholder="搜索会话名称"
            onChange={(event) => {
              setQuery(event.target.value);
              setPage(0);
            }}
          />
        </label>
        <select
          aria-label="统计排序"
          value={sort}
          onChange={(event) => {
            setSort(event.target.value);
            setPage(0);
          }}
        >
          <option value="count">消息最多</option>
          <option value="latest">最近活跃</option>
          <option value="name">名称排序</option>
        </select>
      </div>
      <div className="home-table-scroll">
        <table className="home-statistics-table">
          <thead>
            <tr>
              <th>会话</th>
              <th>类型</th>
              <th>消息数量</th>
              <th>时间范围</th>
            </tr>
          </thead>
          <tbody>
            {rows
              .slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE)
              .map((item) => (
                <tr key={item.conversation_id}>
                  <td>{publicText(item.display_name)}</td>
                  <td>{kindLabel(item.kind)}</td>
                  <td>{item.message_count.toLocaleString()}</td>
                  <td>
                    {formatDate(item.earliest_at, { year: "numeric" })} —{" "}
                    {formatDate(item.latest_at, { year: "numeric" })}
                  </td>
                </tr>
              ))}
            {!rows.length && (
              <tr>
                <td colSpan={4} className="home-table-empty">
                  没有匹配的会话，试试其他名称。
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="home-detail-pagination">
        <span>
          共 {rows.length} 个会话 · 第 {currentPage + 1} / {lastPage + 1} 页
        </span>
        <div>
          <button
            className="icon-button"
            aria-label="统计上一页"
            disabled={!currentPage}
            onClick={() => setPage(currentPage - 1)}
          >
            <ChevronLeft size={17} />
          </button>
          <button
            className="icon-button"
            aria-label="统计下一页"
            disabled={currentPage >= lastPage}
            onClick={() => setPage(currentPage + 1)}
          >
            <ChevronRight size={17} />
          </button>
        </div>
      </div>
    </Panel>
  );
}
