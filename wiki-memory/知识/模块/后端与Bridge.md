---
type: knowledge
status: active
kind: module
importance: high
updated: 2026-08-23
topic: backend-and-bridge
source_logs:
  - "[[日志/2026-08-23-历史基线与工程记忆初始化]]"
supersedes: null
---

# 后端与 Bridge

Python 应用服务负责发现账号、构造只读仓库、管理异步任务并向 pywebview 暴露结构化 Bridge。Bridge 方法只返回可序列化字典，并通过统一安全包装转换异常。

## 修改原则

- 保持现有 Bridge 方法名和响应兼容。
- 新用例先在 Application 层实现，再由服务门面调用。
- 不让 UI 直接访问数据库、密钥库或文件系统实现。
- 长任务必须提供进度、取消和终态。

## 相关页面

- [[知识/模块/微信数据库与媒体|微信数据库与媒体]]
- [[知识/模块/React前端|React 前端]]
