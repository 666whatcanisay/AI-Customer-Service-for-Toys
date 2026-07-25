# Windows AI 客服本地测试运行工具

## 配置

在 `scripts/windows` 中将 `config.local.ps1.example` 复制为 `config.local.ps1`，再按机器实际路径调整 Python 与 pnpm。该本地配置和 `.runtime/` 均不提交。默认配置假定从合并后的主仓库启动，而不是三个 Agent worktree。

`BindAddress=127.0.0.1` 为本机模式。若改为局域网地址，请同步收紧 `CorsAllowedOrigins`，并将 `CustomerWebUrl` 改为可访问的页面地址。

## 使用

双击 `启动AI客服.bat`，完成 C、A、B、Admin 的依次检查与启动；页面地址会输出并可按 `OpenBrowser` 打开。双击 `检查AI客服状态.bat` 可查看 Ollama、模型、进程 PID、端口、A/C health、B 页面、Admin 页面、局域网模式、测试包和日志目录。双击 `停止AI客服.bat` 以 Admin、B、A、C 的顺序停止。

管理后台默认仅绑定 `http://127.0.0.1:5174/`。启动器必须经 `admin_web/package.json` 的真实 `dev` script 调用 pnpm，并检查 Node、pnpm、锁文件和已安装的 `admin_web/node_modules`；不会安装依赖。双击 `打开运营后台.bat` 可在服务器本机默认浏览器打开已通过 HTTP 检查的页面。`AdminEnableLanMode=$true` 只会显示风险提示和地址，本工具不会创建或修改 5174 的防火墙规则。

启动前必须已人工准备 A/C 的 `.venv`、B 与 Admin 的 `node_modules`、Node、pnpm、Ollama 和指定模型。脚本不会安装依赖、下载模型、改执行策略、改防火墙或杀死未知端口进程。

## 测试数据包

默认 `AutoImportTestData=$false`。需要导入时设置 ZIP 的 `TestDataPackagePath` 并显式改为 `$true`；C health 成功后才会上传。请仅使用获准的测试数据包。

## 故障处理

端口已被未知进程占用时，脚本会退出并显示 PID，不会按端口强杀。停止时若 PID 被复用、可执行路径/启动时间/命令特征不一致，脚本拒绝结束进程并要求人工核对。`admin-web.json` 还同时校验监听 PID、监听进程路径和启动时间，只停止已验证的 pnpm 进程及其已登记监听进程/子进程。日志位于 `<RuntimeDirectory>/logs`。

状态检查将服务未运行、端口未监听和 health 不可用作为有效状态展示，不会以这些状态返回错误。启动前若 A 的 `.venv` 缺失，会输出完整缺失路径以及本次流程中 A、B、C 是否已启动；脚本不会自动安装依赖。
