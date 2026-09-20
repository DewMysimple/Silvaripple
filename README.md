# ChatWechat

ChatWechat 是一个 Windows 桌面归档应用，面向微信 `4.1.12.50` 的 `xwechat_files`
数据格式。所有读取、预览和归档操作都由用户点击触发，不提供后台刷新、消息监控、
发消息或修改微信数据的功能。

桌面表现层使用 React 19、TypeScript、Vite、Zustand、Motion 和 Tauri 2，生产构建由
Windows WebView2 离线加载。Tauri 通过受控 JSON-RPC sidecar 调用 Python 微信解析核心。
界面包含首页、会话预览、按需全文搜索、归档设置、全账号媒体
完整性、任务记录和设置，并提供浅色、深色与跟随 Windows 三种主题模式。

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
python -m pip install -r requirements.txt
corepack pnpm@10.34.5 --dir frontend install
python -m chatwechat
```

首次启动不会使用开发者电脑的路径。应用会自动检查微信的当前用户注册表路径、Windows
实际“文档”目录、OneDrive 重定向文档、AppData 中的兼容路径、
`Documents/xwechat_files`、`Documents/WeChat Files/xwechat_files` 和各本地
磁盘的标准微信目录；选择过的有效目录会作为当前用户设置保存。若微信把数据迁移到了
其他位置，可在首次连接页或“设置 → 账号与数据”手动选择 `xwechat_files`、
`WeChat Files` 或单个 `wxid_*` 账号目录，应用会校验并归一化为真实数据根目录。

使用顺序：

1. 应用自动定位微信数据并展示候选目录；没有命中时手动选择目录。
2. 顶部账号切换器选择当前账号；已有有效密钥时不会再次触发 UAC。
3. 未授权账号在“设置 → 账号与数据”执行一次“授权读取”。
4. 在“会话浏览”中筛选、预览并选择会话，再到“导出工作台”确认输出。
5. 需要时在“媒体完整性”扫描当前账号，或在“全局搜索”按需搜索正文。

会话、统计、选择状态和任务历史均跟随当前账号切换；任务历史按账号隔离展示，避免把
另一个账号的结果误认为当前账号数据。

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
corepack pnpm format:check
corepack pnpm typecheck
corepack pnpm build
corepack pnpm test:e2e
cargo test --manifest-path src-tauri/Cargo.toml
```

测试使用合成密钥、数据库页、WAL、schema 和媒体，不读取真实聊天正文，也不会触发
真实微信进程内存扫描。

前端开发服务器使用 Mock Bridge；Tauri 开发/生产窗口调用 Rust 命令，再由同一状态化
Python sidecar 执行结构化 Bridge。用户运行生产版本不需要安装 Python、Rust 或 Node.js；
后端、Node 语音运行时和 FFmpeg 都随应用压缩包提供。

## 架构与交付

工程保持模块化桌面单体：`frontend/src-tauri` 负责窗口、权限、原生目录选择和 Python
sidecar 生命周期，`desktop/bridge.py` 保持稳定 RPC 合约，`application` 暴露用例门面，
`domain` 与 `infrastructure` 承载规则和平台能力，导出/媒体模块独立演进；React 前端按
应用外壳、功能模块、通用 UI 和 Zustand 状态切片拆分：

```text
frontend/src/
  app/          # 导航外壳、主题、全局反馈
  features/     # 首页、会话、搜索、导出、媒体、任务、设置及共享账号工作流
  ui/           # 公共面板、状态、表单控件、确认交互
  state/        # 账号 / 会话 / 操作切片、统一上下文重置
  styles/       # 全局主题、字号与间距 token
  bridge/       # RPC 信封和仅开发加载的合成数据
  utils/        # 日期、消息类型等公共转换
```

新增页面应复用公共 UI 与上下文边界，业务行为留在对应功能模块；不向根 App 或全局样式中
继续堆放页面实现。统一质量门同时检查行为、格式、类型、多窗口浏览器布局和桌面后端生命周期。

构建时用 PyInstaller 生成单文件 Python sidecar，再由 Tauri 嵌入前端并生成桌面主程序。
统一打包脚本组装主程序、后端、锁定运行时和许可证，生成可直接解压运行的应用：

```powershell
python -m pip install ".[test,build]"
powershell -ExecutionPolicy Bypass -File scripts\Build-Portable.ps1
```

构建脚本验证 React、Python、Rust/Tauri、工程记忆及锁定的 Node/FFmpeg。应用压缩后必须
重新解压，逐文件核验构建清单，再在隔离用户配置和精简 PATH 下执行后端自检，确认只使用
包内运行时。本地正式覆盖要求工作区已经提交且干净：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Publish-Local.ps1
```

成功后根目录 `dist/` 只有以下两项，解压目录来自同一个已验证的 ZIP：

```text
dist/
  ChatWechat.zip
  ChatWechat/
    ChatWechat.exe
    chatwechat-backend.exe
    runtime/
    licenses/
    THIRD_PARTY_NOTICES.md
    README.txt
    build-info.json
```

直接运行 `dist/ChatWechat/ChatWechat.exe` 验收；分发时发送 `dist/ChatWechat.zip`，完整
解压后运行即可。用户无需安装 Python、Node.js 或 Rust，Windows 需具备 WebView2 Runtime。
设置、DPAPI 密钥、任务历史和临时文件继续位于 `%LOCALAPPDATA%\ChatWechat`；更新时关闭
应用并替换整个应用文件夹，不影响微信数据和既有导出文件。包内 `build-info.json` 记录
版本、源码提交和每个应用文件的 SHA-256；ZIP 的 SHA-256 由发布命令返回。`dist/` 被 Git 忽略。

发布将 ZIP 和解压目录作为一组替换；最终目录自检失败会恢复上一组文件。源码继续以 GitHub
仓库为唯一分发来源。普通 `main` 推送不会创建 GitHub Release；只有明确发布并推送与
`pyproject.toml` 一致的 `vX.Y.Z` 标签时，标签工作流才会创建版本化应用 ZIP 和校验文件。该工作流需要仓库变量
`CHATWECHAT_FFMPEG_ARCHIVE_URL` 和 `CHATWECHAT_FFMPEG_ARCHIVE_SHA256` 指向与
`packaging/runtime.lock.json` 完全一致的 FFmpeg 归档。构建中间文件位于系统临时目录，
Tauri 缓存位于 `frontend/src-tauri/target/`，前端静态构建位于 `frontend/dist/`；它们都不是用户交付目录。

## 当前适配边界

- 已验证的目标版本为微信 `4.1.12.50`。其他版本必须先通过页 HMAC 和 SQLite 结构
  验证，程序不会静默假定兼容。
- schema 读取采用字段探测并覆盖 session/contact、分片 message、biz_message、media、
  message_resource 和 hardlink 的常见形态。未知表和消息类型不会导致整批消息丢弃。
- 授权助手会从 V2 缩略图提取 16 字节验证块和 XOR 尾部特征，再只读扫描微信可写内存
  中的 ASCII/UTF-16LE 候选。AES 候选必须把验证块解密为真实图片文件头才会与 XOR 密钥
  一起进入 DPAPI 密钥库；没有验证通过时保存原始 DAT。
