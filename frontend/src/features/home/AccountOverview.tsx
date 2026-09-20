import { ArrowRight, MessageCircle, ShieldCheck } from "lucide-react";
import { useWorkbench } from "../../store";
import { StatusBadge } from "../../ui/layout";

export function AccountOverview() {
  const { account, selected, setView } = useWorkbench();
  if (!account) return null;
  const ready = account.coverage.complete;
  return (
    <section className="home-welcome" aria-label="当前账号与下一步">
      <div className="home-welcome-copy">
        <div className="home-identity">
          <div className="home-avatar">
            {account.avatar_data_url ? (
              <img src={account.avatar_data_url} alt="" />
            ) : (
              account.display_name.slice(0, 1)
            )}
          </div>
          <div>
            <span>当前本地账号</span>
            <strong>{account.display_name}</strong>
          </div>
          <StatusBadge tone={ready ? "success" : "warning"}>
            {ready ? "已就绪" : "待授权"}
          </StatusBadge>
        </div>
        <h2>
          {!ready
            ? "先完成授权，再整理你的聊天"
            : selected.length
              ? "选好了会话，接着准备归档"
              : "让重要的聊天，有序留存"}
        </h2>
        <p>
          {!ready
            ? "部分数据库尚未授权。完成本机授权后，可以读取完整的聊天记录。"
            : selected.length
              ? `已选择 ${selected.length} 个会话。确认时间范围与输出格式，即可保存到你的电脑。`
              : "浏览并选择会话，确认导出范围，将聊天和媒体保存为可随时打开的归档。"}
        </p>
        <div className="home-welcome-actions">
          <button
            className="primary"
            onClick={() =>
              setView(
                !ready
                  ? "settings"
                  : selected.length
                    ? "export"
                    : "conversations",
              )
            }
          >
            <MessageCircle size={18} />
            {!ready
              ? "前往授权"
              : selected.length
                ? "继续导出"
                : "浏览并选择会话"}
            <ArrowRight size={17} />
          </button>
          <button className="text-button" onClick={() => setView("search")}>
            搜索聊天记录
          </button>
        </div>
      </div>
      <aside className="home-readiness">
        <span className="home-readiness-icon">
          <ShieldCheck size={25} />
        </span>
        <strong>本地只读，安心整理</strong>
        <p>读取临时快照，不修改微信源数据。</p>
        <div className="home-coverage-caption">
          <span>数据库授权</span>
          <b>
            {account.coverage.covered} / {account.coverage.total}
          </b>
        </div>
        <progress
          max={Math.max(1, account.coverage.total)}
          value={account.coverage.covered}
          aria-label="数据库授权覆盖"
        />
        <button className="text-button" onClick={() => setView("settings")}>
          管理账号与数据位置 <ArrowRight size={14} />
        </button>
      </aside>
    </section>
  );
}
