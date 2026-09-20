---
type: knowledge
status: active
kind: module
importance: medium
updated: 2026-09-20
topic: react-frontend
source_logs:
  - "[[日志/2026-09-20-全局工作台重设计与免安装交付]]"
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

## 文件组织与复用

- `App.tsx`、`app/`：启动、外壳、主题与错误反馈，不放业务页面。
- `features/`：七个功能页面及各自组件、hooks、规则和样式；`features/accounts` 共用数据源选择工作流。
- `ui/`：Panel、PageIntro、SettingRow、StatusBadge、ChipGroup、统计/进度/空态、确认弹窗；复用结构与交互，不复制整套控件。
- `styles/foundation.css`：主题、字体与间距 token；`ui/components.css`：公共样式；每个功能维护自身样式。字号优先 rem。
- `state/`：类型与账号、会话、操作切片；`context.ts` 统一重置，`store.ts` 只组合切片及少量外壳状态。
- `bridge.ts`：生产适配；`bridge/mock.ts`：仅开发加载的合成数据。
- `test/fixtures.ts`：公共测试夹具。测试使用合成账号和聊天，不读取真实用户数据。

## 回归重点

旧异步结果不得跨上下文写入；失败/同根数据发现不终止当前跟踪；筛选会话不丢选择详情；导出提交防重复且估算不能用旧配置。浏览器回归覆盖所有页面多窗口尺寸及深色、大字体。`pnpm format:check` 和 TypeScript 未用符号检查持续约束代码质量。
