---
type: decision
status: active
kind: process
importance: high
updated: 2026-09-20
topic: zip-and-expanded-app-delivery
source_logs:
  - "[[日志/2026-09-20-全局工作台重设计与免安装交付]]"
supersedes: "[[决策/ADR-007-工程内安装实例与发布资产|ADR-007]]"
---

# ADR-011｜ZIP 与解压应用交付

## 决策

- 根 `dist/` 仅包含 `ChatWechat.zip` 与 `ChatWechat/`，后者必须从同一 ZIP 解压得到。验收入口为 `dist/ChatWechat/ChatWechat.exe`。
- 不再创建本地安装器、安装实例或源码 ZIP。Tauri 构建使用 `--no-bundle`；共用资源映射组装 Python sidecar、Node、FFmpeg 和许可证。
- 包内 `build-info.json` 记录版本、源码提交与逐文件摘要；构建与发布都检查解压内容及冻结后端，正式交付还需确认桌面主程序实际启动。
- 发布先验证候选产物，再整组替换 ZIP 与解压目录；普通错误回滚旧组，未知用户文件拒绝覆盖。该流程不承诺断电时的原子性。
- 设置、密钥、历史和临时数据继续存于当前用户应用数据目录；不写入可分发应用目录。
- 构建缓存保持在 `frontend/dist/`、`frontend/src-tauri/target/` 或系统临时目录，与用户交付 `dist/` 分开。
- 原有源码提交推送策略继续生效；未经用户明确要求，不创建 GitHub Release。标签发布使用版本化 ZIP 与摘要。
