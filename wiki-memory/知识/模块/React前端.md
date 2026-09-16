---
type: knowledge
status: active
kind: module
importance: medium
updated: 2026-09-16
topic: react-frontend
source_logs:
  - "[[日志/2026-08-23-历史基线与工程记忆初始化]]"
  - "[[日志/2026-09-16-Tauri架构与多账号数据发现]]"
supersedes: null
---

# React 前端

前端使用 React、TypeScript、Vite、Zustand 和 Motion。浏览器开发模式调用 Mock Bridge；Tauri 开发和生产模式通过 `@tauri-apps/api` 调用 Rust 命令与原生目录对话框。

## 边界

- 页面组件不直接拼接 Bridge 参数，统一经过类型化适配层。
- 导出草稿、搜索结果、预览和媒体扫描明细只保存在运行内存。
- 主题、字体和非敏感默认值由设置保存。
- 账号切换必须重置账号相关页面局部状态，异步任务回写必须核对账号标识。
- 生产构建输出到 `frontend/dist`，由 Tauri 嵌入，不进入 Python 包。
