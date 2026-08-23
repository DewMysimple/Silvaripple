export const formatBytes = (value = 0) => {
  if (!value) return "0 B";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  const index = Math.min(
    units.length - 1,
    Math.floor(Math.log(value) / Math.log(1024)),
  );
  return `${(value / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
};

export const formatDate = (value?: string) =>
  value
    ? new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value))
    : "无时间记录";

export const publicText = (value?: string) =>
  (value || "").replace(/wxid_[A-Za-z0-9_-]+/g, "未知成员");

export const kindLabel = (value: string) =>
  ({ group: "群聊", private: "私聊", official: "公众号", business: "业务" })[
    value
  ] || "其他";

export const clampDownloadLimit = (value: number) =>
  Math.min(2048, Math.max(1, Math.round(Number(value) || 1)));
