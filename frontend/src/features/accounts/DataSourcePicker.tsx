import { useState } from "react";
import { Check, FolderOpen, RefreshCw } from "lucide-react";
import { invoke } from "../../bridge";
import { useWorkbench } from "../../store";
import { StatusBadge } from "../../ui/layout";
import "./data-sources.css";

/** The same validated data-source workflow is used during setup and in settings. */
export function DataSourcePicker({
  showCurrent = true,
}: {
  showCurrent?: boolean;
}) {
  const {
    settings,
    dataRoots,
    refreshDataRoots,
    selectDataRoot,
    useAutoDataRoot,
  } = useWorkbench();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const run = async (action: () => Promise<unknown>) => {
    setPending(true);
    setError("");
    try {
      await action();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setPending(false);
    }
  };
  const choose = async () => {
    const result = await invoke<{ path?: string }>("choose_folder");
    if (result.path) await selectDataRoot(result.path);
  };
  return (
    <div className="data-source-picker" aria-busy={pending}>
      {showCurrent && settings && (
        <div className="data-source-current">
          <div>
            <span>当前微信数据位置</span>
            <StatusBadge>
              {settings.data_root_mode === "auto" ? "自动发现" : "手动选择"}
            </StatusBadge>
          </div>
          <code>{settings.data_root || "尚未设置"}</code>
        </div>
      )}
      <div className="data-source-actions">
        <button
          className="secondary"
          disabled={pending}
          onClick={() => void run(refreshDataRoots)}
        >
          <RefreshCw size={16} />
          {pending ? "正在处理…" : "重新检测"}
        </button>
        <button
          className="secondary"
          disabled={pending}
          onClick={() => void run(choose)}
        >
          <FolderOpen size={16} />
          选择数据目录
        </button>
        {settings?.data_root_mode === "manual" && (
          <button
            className="text-button"
            disabled={pending}
            onClick={() => void run(useAutoDataRoot)}
          >
            恢复自动发现
          </button>
        )}
      </div>
      <p className="data-source-help">
        可以选择 xwechat_files、WeChat Files
        或单个账号目录。若未找到，请在微信的「设置 →
        账号与存储」中查看数据位置。
      </p>
      {dataRoots.length > 0 ? (
        <div className="data-source-results">
          <span className="data-source-caption">
            检测到 {dataRoots.length} 个数据位置
          </span>
          {dataRoots.map((candidate) => (
            <button
              key={candidate.path}
              className={`data-source-option ${candidate.selected ? "selected" : ""}`}
              disabled={pending || candidate.selected}
              onClick={() => void run(() => selectDataRoot(candidate.path))}
            >
              <FolderOpen size={19} />
              <span>
                <strong>{candidate.account_count} 个本机账号</strong>
                <small>{candidate.path}</small>
              </span>
              <span className="data-source-state">
                {candidate.selected ? (
                  <>
                    <Check size={15} />
                    当前
                  </>
                ) : (
                  "使用此位置"
                )}
              </span>
            </button>
          ))}
        </div>
      ) : (
        <p className="data-source-empty">
          标准位置中尚未发现微信数据，可以手动选择迁移后的目录。
        </p>
      )}
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
