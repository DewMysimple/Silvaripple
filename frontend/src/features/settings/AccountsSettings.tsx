import { useState } from "react";
import { KeyRound, Users } from "lucide-react";
import { invoke } from "../../bridge";
import { useWorkbench } from "../../store";
import type { Account } from "../../types";
import { Panel, StatusBadge } from "../../ui/layout";
import { formatBytes } from "../../utils/format";
import { DataSourcePicker } from "../accounts/DataSourcePicker";

function AccountCard({ item }: { item: Account }) {
  const { account, selectAccount, initialize } = useWorkbench();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const current = account?.account_id === item.account_id;
  const authorize = async () => {
    setPending(true);
    setError("");
    try {
      await invoke("authorize_account", item.account_id);
      await initialize();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setPending(false);
    }
  };
  return (
    <article className={`account-settings-card ${current ? "current" : ""}`}>
      <div className="account-settings-identity">
        <div className="account-settings-avatar">
          {item.avatar_data_url ? (
            <img src={item.avatar_data_url} alt="" />
          ) : (
            item.display_name.slice(0, 1)
          )}
        </div>
        <div>
          <strong>{item.display_name}</strong>
          <span>
            {formatBytes(item.size_bytes)} · {item.database_count} 个数据库
          </span>
        </div>
        {current && <StatusBadge tone="success">当前账号</StatusBadge>}
      </div>
      <div className="account-settings-access">
        <span>
          <i className={item.coverage.complete ? "ready" : ""} />
          {item.coverage.complete ? "读取已就绪" : "需要补充授权"}
        </span>
        <span>
          已授权 {item.coverage.covered} / {item.coverage.total}
        </span>
      </div>
      <div className="account-settings-actions">
        {!current && (
          <button
            className="secondary compact"
            disabled={pending}
            onClick={() => void selectAccount(item)}
          >
            切换到此账号
          </button>
        )}
        <button
          className={item.coverage.complete ? "text-button" : "primary compact"}
          disabled={pending}
          onClick={() => void authorize()}
        >
          <KeyRound size={15} />
          {pending
            ? "正在授权…"
            : item.coverage.complete
              ? "重新授权"
              : "授权读取"}
        </button>
      </div>
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
    </article>
  );
}

export function AccountsSettings() {
  const accounts = useWorkbench((state) => state.accounts);
  return (
    <>
      <Panel
        title="本机微信账号"
        description="切换账号后，会话、已选列表、统计和任务记录随之切换。"
        action={<StatusBadge>{accounts.length} 个账号</StatusBadge>}
      >
        {accounts.length ? (
          <div className="account-settings-grid">
            {accounts.map((item) => (
              <AccountCard key={item.account_id} item={item} />
            ))}
          </div>
        ) : (
          <div className="account-settings-empty">
            <Users size={27} />
            <strong>尚未找到本机账号</strong>
            <p>先在下方检测或选择微信数据位置。</p>
          </div>
        )}
      </Panel>
      <Panel
        title="微信数据位置"
        description="更换电脑或迁移数据后，可以重新检测或手动定位。"
      >
        <DataSourcePicker />
      </Panel>
    </>
  );
}
