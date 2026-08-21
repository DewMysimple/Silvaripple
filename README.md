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
python -m chatwechat.app
```

也可以双击 `启动ChatWechat.pyw`。默认数据目录是
`D:\SoftWareDocuments\WeChatDownLoad\xwechat_files`。

使用顺序：

1. 应用自动恢复上次账号；已有有效密钥时不会再次触发 UAC。
2. 在“会话浏览”中筛选、预览并选择会话。
3. 在“导出工作台”选择输出目录、格式和媒体策略，先计算规模再开始导出。
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
其他情况复制。联网补全默认关闭；启用后只访问消息已有的腾讯白名单地址。旧版
`vweixinf.tc.qq.com` HTTP 表情地址还需要本次导出单独授权，并通过图片头、完整解码与
本地 MD5 校验。授权不会写入设置或预设，下载内容只进入本次导出目录。无法验证的
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

## 当前适配边界

- 已验证的目标版本为微信 `4.1.12.50`。其他版本必须先通过页 HMAC 和 SQLite 结构
  验证，程序不会静默假定兼容。
- schema 读取采用字段探测并覆盖 session/contact、分片 message、biz_message、media、
  message_resource 和 hardlink 的常见形态。未知表和消息类型不会导致整批消息丢弃。
- 授权助手会从 V2 缩略图提取 16 字节验证块和 XOR 尾部特征，再只读扫描微信可写内存
  中的 ASCII/UTF-16LE 候选。AES 候选必须把验证块解密为真实图片文件头才会与 XOR 密钥
  一起进入 DPAPI 密钥库；没有验证通过时保存原始 DAT。
