ChatWechat

完整解压 ChatWechat.zip，然后双击 ChatWechat.exe 即可运行。
请保留 chatwechat-backend.exe、runtime 和其他附带文件，勿单独移动主程序。
应用内的微信数据目录和导出目录可自由选择。

运行要求：Windows 10/11（64 位）及 Microsoft Edge WebView2 Runtime。
程序已包含 Python 后端、Node.js 和 FFmpeg；不需要另行安装开发环境。
界面和本地数据处理支持离线使用；联网媒体补全只在用户选择后使用网络。

用户设置、授权密钥及任务历史保存在当前用户的 %LOCALAPPDATA%\ChatWechat，
不会写入此应用目录。更新前关闭应用，完整解压新版后运行即可。
替换应用文件不会删除微信数据或用户已经导出的归档。

build-info.json 记录构建版本、源码提交与应用文件校验信息。
第三方声明见 THIRD_PARTY_NOTICES.md，许可证见 runtime/ 和 licenses/。
