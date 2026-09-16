---
type: log
status: archived
kind: bug
importance: medium
updated: 2026-09-17
topic: windows-powershell-script-encoding
source_logs: []
supersedes: null
---

# 2026-09-17｜Windows PowerShell 发布脚本编码兼容

## 目标

修复 Tauri 本地发布在 Windows PowerShell 5 中因 UTF-8 无 BOM 中文字面量被错误解码而无法解析的问题。

## 决策

- 发布脚本的可执行源码保持 ASCII；需要保留的中文产物目录名由 Unicode 码点在运行时构造。
- 自动测试检查四个正式构建/发布 PowerShell 脚本均为 ASCII，避免后续补丁重新引入兼容问题。

## 变更

- `Publish-Local.ps1` 的异常文本改为英文，中文产物目录仍保持原名称。
- `test_packaging.py` 新增 Windows PowerShell 5 编码防回归检查。

## 验证

- Windows PowerShell 5 能成功解析发布脚本。
- 打包测试通过；最终本地发布继续使用干净提交重新执行。

## 结果

源码文件是否带 UTF-8 BOM 不再影响正式构建与发布入口。

## 遗留问题

- 无。
