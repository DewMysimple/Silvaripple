---
type: decision
status: active
kind: architecture
importance: high
updated: 2026-09-16
topic: tauri-python-sidecar-architecture
source_logs:
  - "[[日志/2026-09-16-Tauri架构与多账号数据发现]]"
supersedes: "[[决策/ADR-002-模块化桌面单体架构|ADR-002]]"
---

# ADR-008｜Tauri 桌面壳与 Python Sidecar

## 决策

- React 19、TypeScript 和 Vite 前端由 Tauri 2 的 Windows WebView2 窗口加载，不再使用 pywebview。
- Rust 桌面层只负责窗口、权限、原生目录选择、进程生命周期和 IPC；微信数据库、密钥、媒体和导出逻辑继续由 Python 应用层负责。
- Python 以 PyInstaller 单文件 sidecar 随 Tauri NSIS 安装包分发。Tauri 通过标准输入输出上的逐行 JSON RPC 复用一个状态化服务实例，并串行化 Bridge 调用。
- Bridge 保留既有成功/失败信封和方法语义；React 只依赖类型化适配层，不直接接触 Rust 或 Python 实现。
- Node、FFmpeg 和许可证作为 Tauri 资源随安装包提供；设置、DPAPI 密钥和运行元数据继续位于当前用户应用数据目录。

## 理由

- Tauri 提供明确的桌面权限、原生对话框、安装器和生命周期边界。
- 保留已经验证的 Python WCDB/SQLCipher 读取链路，避免为更换窗口壳重写高风险数据核心。
- 状态化 sidecar 允许长任务、取消、缓存和账号仓库继续工作，不需要为每个 UI 调用重启 Python。

## 验证

- Python、React 和 Rust 测试及类型检查通过。
- Tauri 开发窗口能够拉起 RPC sidecar 并完成 bootstrap。
- PyInstaller sidecar 自检确认冻结模式、DPAPI/CNG、WebView2、Node、FFmpeg 和服务初始化。
- Tauri NSIS 安装包执行隔离安装、已安装 sidecar 自检和静默卸载验证。
