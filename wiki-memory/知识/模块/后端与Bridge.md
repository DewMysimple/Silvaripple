---
type: knowledge
status: active
kind: module
importance: high
updated: 2026-09-16
topic: backend-and-bridge
source_logs:
  - "[[日志/2026-08-23-历史基线与工程记忆初始化]]"
  - "[[日志/2026-09-16-Tauri架构与多账号数据发现]]"
supersedes: null
---

# 后端与 Bridge

Python 应用服务负责发现数据根和账号、构造只读仓库、管理异步任务，并通过逐行 JSON RPC sidecar 向 Tauri 暴露结构化 Bridge。Bridge 方法只返回可序列化字典，并通过统一安全包装转换异常。

## 修改原则

- 保持现有 Bridge 方法名和响应兼容。
- 新用例先在 Application 层实现，再由服务门面调用。
- 不让 UI 直接访问数据库、密钥库或文件系统实现。
- 长任务必须提供进度、取消和终态。
- Tauri 串行化 RPC 请求并复用同一 Python 服务实例；桌面退出时关闭 sidecar。
- 原生目录对话框由 Tauri 提供，数据根是否有效由 Python 应用层验证。

## 相关页面

- [[知识/模块/微信数据库与媒体|微信数据库与媒体]]
- [[知识/模块/React前端|React 前端]]
