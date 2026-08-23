# ChatWechat

ChatWechat 是一个 Windows 本地微信手动导出工作台。它面向微信 `4.1.12.50` 的
`xwechat_files` 数据格式，所有读取、预览和导出都由用户点击触发，不提供后台刷新、
消息监控、发消息或修改微信数据的功能。

桌面表现层使用 React 19、TypeScript、Vite、Zustand 和 Motion，生产构建作为静态资源
由 pywebview 离线加载。界面包含首页、会话预览、按需全文搜索、导出工作台、全账号
媒体完整性、任务记录和设置，并提供浅色、深色与跟随 Windows 三种主题模式。

## 安全模型

- 源数据库、WAL 和 SHM 始终只读；工作副本位于 `%LOCALAPPDATA%\ChatWechat\temp`。
- 账号昵称来自已解密 `contact.db` 的本人联系人记录，不在程序或设置中硬编码。
- 会话列表和预览可显示本机 `head_image.db`/头像缓存中的头像；头像库未授权或本地缺失时使用文字占位，不联网下载。
- “授权读取账号”启动短时管理员助手，只申请进程查询和内存读取权限。
- 助手定位 `com.Tencent.WCDB.Config.Cipher`，候选密钥必须通过对应数据库第一页
  HMAC-SHA512 才会被接受。
- 数据库密钥只以 Windows DPAPI 密文保存在当前用户配置目录，界面只显示覆盖数量。
- 数据库页使用 Windows CNG AES-256-CBC 解密，每页验证 HMAC，随后执行 SQLite
  `quick_check`。
- 日志格式化器会脱敏 wxid 和疑似十六进制密钥；应用不记录联系人或聊天正文。
- 主动导出的 HTML、Markdown、JSON 和媒体是长期明文文件，请妥善保管。

授权助手不会注入 DLL、安装服务、写入微信进程，也不会运行第三方原生程序。

## 运行

```powershell
cd C:\Users\Administrator\Desktop\ChatWechat
python -m pip install -r requirements.txt
python -m chatwechat
```

默认数据目录是 `D:\SoftWareDocuments\WeChatDownLoad\xwechat_files`。

使用顺序：

1. 应用自动恢复上次账号；已有有效密钥时不会再次触发 UAC。
2. 在“会话浏览”中筛选、预览并选择会话。
3. 在“导出工作台”选择输出目录、格式和媒体策略；规模会自动更新。
4. 需要时在“媒体完整性”手动扫描整个账号，或在“全局搜索”按需搜索正文。

历史账号必须先在微信中切换并登录，确保对应运行时密钥存在，再重新授权。密钥覆盖
不完整时默认禁止导出；勾选“允许部分导出”后才会跳过缺少密钥的消息分片。

## 导出结构

```text
输出目录/
  私聊/
    好友原昵称/
      chat.html
      chat.md
      chat.json
      media/
      _export_manifest.json
  群聊/
    群聊名称/
      chat.html
      chat.md
      chat.json
      media/
      _export_manifest.json
```

每个会话的每种格式只有一个文件。HTML 完全离线并支持正文筛选；JSON 逐条流式写入，
保存标准化消息、原始类型、原始字段和必要 XML；未知类型会显示占位并保留原始信息。
导出展示层中的本人、好友和群成员名称优先使用微信资料原昵称，不使用当前账号设置的
本地备注；内部标识仍只保留在 JSON 的结构化追溯字段中。同一会话再次导出会原子替换
固定目录，不创建按时间命名的批次；同名会话使用账号原昵称或可读序号区分。设置页可改为
扁平结构，或按账号和会话类型分组。旧版时间批次目录不会自动迁移或修改。

媒体解析只处理消息实际引用的文件，以 SHA-256 去重。同一 NTFS 卷优先创建硬链接，
其他情况复制。联网补全和受限旧腾讯表情地址默认开启，用户可在设置或导出草稿中关闭；
下载只访问受控腾讯地址，并通过文件头、完整解码和可用的本地 MD5 校验。无法验证的
缓存保留原始文件并记录细分原因。

## 语音组件

项目固定包含 `silk-wasm 3.7.1` 的 WASM、Emscripten 封装及 MIT 许可证，位于
`chatwechat/vendor/silk-wasm`。解码时启动短时本地 Node.js 进程，将 SILK 写为
24 kHz 单声道 WAV；没有网络请求。如果环境缺少 Node.js，工具会保留原始语音并在
清单中标记原因。

## 测试

```powershell
python -m pytest

cd frontend
corepack pnpm install
corepack pnpm test
corepack pnpm typecheck
corepack pnpm build
```

测试使用合成密钥、数据库页、WAL、schema 和媒体，不读取真实聊天正文，也不会触发
真实微信进程内存扫描。

前端开发服务器使用 Mock Desktop Bridge；生产应用始终调用 pywebview 注入的结构化
Bridge。用户运行生产版本不需要安装 Node.js，Node 仅用于开发构建和可选语音解码。

## 架构与安装版

工程保持模块化桌面单体：`desktop` 负责启动、Bridge 和冻结资源，`application` 暴露
用例门面，`domain` 与 `infrastructure` 承载规则和平台能力，导出/媒体模块独立演进；
React 前端按应用外壳、页面、通用 UI 和 Zustand 状态切片拆分。现有 Bridge 方法保持
兼容，因此常规功能修改不需要同步重写桌面壳和所有页面。

构建安装器前会在仓库外临时目录生成 PyInstaller onedir staging；onedir 不是用户交付格式：

```powershell
python -m pip install ".[test,build]"
powershell -ExecutionPolicy Bypass -File scripts\Build-Installer.ps1
```

构建脚本在仓库外的临时目录工作，验证前端、Python、工程记忆、锁定的 Node/FFmpeg、
NSIS，并执行冻结版和隔离安装后的 `--self-test`。本地正式覆盖要求工作区已经提交且干净：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Publish-Local.ps1
```

成功后只保留工程内 `artifacts/发布版本/` 中的一个安装包、一个源码 ZIP 和一个校验文件：

```text
artifacts/发布版本/
  ChatWechat-Setup.exe
  ChatWechat-source.zip
  SHA256SUMS.txt
```

安装程序默认写入 `%LOCALAPPDATA%\Programs\ChatWechat`，设置、DPAPI 密钥、任务历史和
临时文件继续位于 `%LOCALAPPDATA%\ChatWechat`。安装器创建开始菜单和桌面快捷方式；升级
时提示关闭正在运行的应用，不删除用户数据。旧便携版不再作为交付物或构建输出。

失败不会替换上一版安装包或源码包。普通 `main` 推送不会创建 GitHub Release；只有明确发布
并推送与 `pyproject.toml` 一致的 `vX.Y.Z` 标签时，标签工作流才会创建版本化安装资产。该工作流需要仓库变量
`CHATWECHAT_FFMPEG_ARCHIVE_URL` 和 `CHATWECHAT_FFMPEG_ARCHIVE_SHA256` 指向与
`packaging/runtime.lock.json` 完全一致的 FFmpeg 归档。普通源码发布不再生成 onedir 或便携格式交付物。

## 当前适配边界

- 已验证的目标版本为微信 `4.1.12.50`。其他版本必须先通过页 HMAC 和 SQLite 结构
  验证，程序不会静默假定兼容。
- schema 读取采用字段探测并覆盖 session/contact、分片 message、biz_message、media、
  message_resource 和 hardlink 的常见形态。未知表和消息类型不会导致整批消息丢弃。
- 授权助手会从 V2 缩略图提取 16 字节验证块和 XOR 尾部特征，再只读扫描微信可写内存
  中的 ASCII/UTF-16LE 候选。AES 候选必须把验证块解密为真实图片文件头才会与 XOR 密钥
  一起进入 DPAPI 密钥库；没有验证通过时保存原始 DAT。
