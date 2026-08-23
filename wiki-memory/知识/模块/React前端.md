---
type: knowledge
status: active
kind: module
importance: medium
updated: 2026-08-23
topic: react-frontend
source_logs:
  - "[[日志/2026-08-23-历史基线与工程记忆初始化]]"
supersedes: null
---

# React 前端

前端使用 React、TypeScript、Vite、Zustand 和 Motion。开发模式调用 Mock Bridge，生产模式通过 `window.pywebview.api` 访问 Python。

## 边界

- 页面组件不直接拼接 Bridge 参数，统一经过类型化适配层。
- 导出草稿、搜索结果、预览和媒体扫描明细只保存在运行内存。
- 主题、字体和非敏感默认值由设置保存。
- 生产构建输出到 Python 包内的 `chatwechat/web`，随 EXE 发布。
