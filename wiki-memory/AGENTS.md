# ChatWechat 工程记忆维护协议

## 记忆模型

- `当前状态/`：当前有效的项目事实，每个主题只有一个 active 版本。
- `决策/`：已经确认、会约束后续工作的架构与工程决策。
- `知识/`：稳定的模块、流程、规范和运维知识。
- `日志/`：实质任务的追加式历史，不作为当前事实的唯一来源。
- 原始代码、配置、测试和用户明确指令始终优先于记忆。

## 会话开始时

1. 读取本文件。
2. 读取 `当前状态/项目概览.md`、`系统架构.md`、`当前约束.md`、`当前待办.md`。
3. 读取与任务相关的 active 决策和知识页。
4. 只有追溯问题时才读取最近日志。

启动记忆包应保持简洁，不默认加载全部历史。

## 写入规则

- 完成实质任务后新增 `日志/YYYY-MM-DD-任务标题.md`；同名时追加 `-02` 等序号。
- 日志记录目标、决策、变更、验证、结果、遗留问题和长期记忆候选。
- 日志封存后不改写；更正通过新增日志完成。
- 长期结论必须链接来源日志。新结论替代旧结论时标记 `superseded`，不得删除旧决策。
- 未经确认的长期候选保持在日志中，不直接写入 active 页面。
- 不复制源码或完整对话，只记录结论和仓库相对路径。
- 禁止写入聊天正文、联系人内部标识、密钥、令牌、完整媒体地址、私人目录和大段命令输出。

## 页面元数据

受管页面使用 YAML frontmatter：

```yaml
---
type: state | decision | knowledge | log | moc
status: active | proposed | deprecated | superseded | archived
kind: feature | ui | bug | discussion | test | maintenance | architecture | process | module | operations
importance: high | medium | low
updated: YYYY-MM-DD
topic: stable-topic-name
source_logs: []
supersedes: null
---
```

## 固定流程

- 新增或修改日志后运行 `python wiki-memory/工具/memory_lint.py index`。
- 提交前运行 `python wiki-memory/工具/memory_lint.py check`。
- Obsidian 链接使用 `[[路径|别名]]`，记忆路径统一使用 `/`。
- 每个逻辑任务在测试与本地发布成功后提交并推送 `main`。
- 普通源码推送不得创建 GitHub Release；只有用户明确要求时才发布版本标签和资产。
