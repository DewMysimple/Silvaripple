---
type: knowledge
status: active
kind: process
importance: high
updated: 2026-08-23
topic: memory-system
source_logs:
  - "[[日志/2026-08-23-历史基线与工程记忆初始化]]"
supersedes: null
---

# ChatWechat 工程记忆

本目录是 ChatWechat 的持久工程记忆。代码、配置和测试仍是事实来源；这里保存经过验证、会影响后续工作的结论、关系和决策。

## 读取入口

1. [[AGENTS|记忆维护协议]]
2. [[当前状态/项目概览|项目概览]]
3. [[当前状态/系统架构|系统架构]]
4. [[当前状态/当前约束|当前约束]]
5. [[当前状态/当前待办|当前待办]]
6. 与当前任务相关的决策和知识页

## 固定操作

- 记忆同步：新增一篇任务日志，更新确有变化的状态页，刷新工作日志索引。
- 记忆体检：运行 `python wiki-memory/工具/memory_lint.py check`。
- 日志索引：运行 `python wiki-memory/工具/memory_lint.py index`。

记忆不得保存聊天正文、联系人内部标识、密钥、令牌、完整媒体地址或用户机器的绝对路径。
