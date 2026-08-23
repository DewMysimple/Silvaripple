---
type: decision
status: active
kind: process
importance: high
updated: 2026-08-24
topic: git-and-release-policy
source_logs:
  - "[[日志/2026-08-23-历史基线与工程记忆初始化]]"
  - "[[日志/2026-08-24-正式安装版构建体系]]"
supersedes: null
---

# ADR-004｜Git 与发布策略

## 决策

- 每个可独立验证的逻辑任务提交一次并直接推送 `origin/main`。
- 中间失败状态不推送；禁止自动强推。
- 每项任务验收后重新构建并原子覆盖仓库外的源码包和 NSIS 安装包。
- 普通源码推送不创建 GitHub Release。
- 只有用户明确要求时才更新版本、推送 `vX.Y.Z` 标签并创建 GitHub Release；旧 Release 保留。

## 本地产物

本地只保留一个固定源码包、一个 NSIS 安装包和校验文件，路径由发布脚本默认值定义，不写入工程记忆。
