export const MESSAGE_TYPES = [
  { value: "text", label: "文字" },
  { value: "image", label: "图片" },
  { value: "emoji", label: "表情" },
  { value: "audio", label: "语音" },
  { value: "video", label: "视频" },
  { value: "file", label: "文件" },
] as const;

export const MEDIA_TYPES = MESSAGE_TYPES.filter(
  (item) => item.value !== "text",
);
const typeLabels: Record<string, string> = Object.fromEntries([
  ...MESSAGE_TYPES.map((item) => [item.value, item.label]),
  ["app", "分享内容"],
  ["system", "系统消息"],
  ["link", "链接"],
  ["location", "位置"],
  ["unknown", "其他"],
]);
export const messageTypeLabel = (value: string) => typeLabels[value] || "其他";
export const operationIsRunning = (status?: string) =>
  status === "pending" || status === "running";
