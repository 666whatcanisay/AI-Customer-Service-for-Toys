# Windows AI 客服本地测试运行工具

## 配置

在 `scripts/windows` 中将 `config.local.ps1.example` 复制为 `config.local.ps1`，再按机器实际路径调整 Python 与 pnpm。该本地配置和 `.runtime/` 均不提交。默认配置假定从合并后的主仓库启动，而不是三个 Agent worktree。

`BindAddress=127.0.0.1` 为本机模式。若改为局域网地址，请同步收紧 `CorsAllowedOrigins`，并将 `CustomerWebUrl` 改为可访问的页面地址。

## 使用

双击 `启动AI客服.bat`，完成 C、A、B 的依次检查与启动；页面地址会输出并可按 `OpenBrowser` 打开。双击 `检查AI客服状态.bat` 可查看 Ollama、模型、进程 PID、端口、A/C health、B 页面、局域网模式、测试包和日志目录。双击 `停止AI客服.bat` 以 B、A、C 的顺序停止。

启动前必须已人工准备 A/C 的 `.venv`、B 的 `node_modules`、Node、pnpm、Ollama 和指定模型。脚本不会安装依赖、下载模型、改执行策略、改防火墙或杀死未知端口进程。

## 测试数据包

默认 `AutoImportTestData=$false`。需要导入时设置 ZIP 的 `TestDataPackagePath` 并显式改为 `$true`；C health 成功后才会上传。请仅使用获准的测试数据包。

## 故障处理

端口已被未知进程占用时，脚本会退出并显示 PID，不会按端口强杀。停止时若 PID 被复用、可执行路径/启动时间/命令特征不一致，脚本拒绝结束进程并要求人工核对。日志位于 `<RuntimeDirectory>/logs`。
