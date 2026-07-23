# CONTROL-LAN-BATCH-05 交接

日期：2026-07-23

## 已完成的集成

- A 局域网 CORS 源提交 `055aaac60cdce1ad5004832c0bb71129c6ab6c97` 已无冲突 squash 为 `3f20686c48dbec4dd7d389e6eac7dcfe16eeb28f`。
- OPS 局域网启动模式源提交 `b7cb6eec0bcd686cbdd9079a2d98c47083af03b5` 已随后无冲突 squash 为 `978f884b41b8a1ea0c0f42ac5e5e319516f0cac`，并已推送到 `origin/develop`。
- A 集成回归：`backend/tests` 结果 `52 passed, 2 skipped`；两个跳过项是未显式启用的真实 RAG E2E。
- OPS 集成自测通过：验证 PowerShell 语法、本机兼容、私有 IP 选择、Public 网络拒绝、A/C CORS 与 B API 地址注入、重复启动保护、安全停止和未知进程保护。

## 主电脑已核验的本地前置

- `scripts/windows/config.local.ps1` 被 Git 忽略，且 `RepositoryRoot`、A/C Python 路径均精确指向正式主仓库。
- 端口配置为 A `8000`、B `5173`、C `8011`；原始 V0.3.1 测试 ZIP 存在且由本机配置直接引用。
- 启动前三个服务端口均无监听；本轮没有删除虚拟环境、依赖、原始 ZIP、数据库、向量库或日志。

## 当前 Gate：BLOCKED

用于局域网互访的物理以太网在 Windows 中显示为 `Public`。LAN 启动模式会因此安全拒绝启动，且不允许以 VPN/虚拟网卡、`AllowPublicNetwork=true`、关闭防火墙、手工补启动或强杀未知进程绕过。

## 恢复与验收

1. 用户在 Windows 设置中将笔记本实际连接的物理网络改为 `Private`，或接入 `DomainAuthenticated` 网络。
2. 在正式主仓库运行 `scripts\windows\启动局域网客服.bat`。
3. 以脚本显示的私有 IPv4 访问 `http://<主电脑IPv4>:5173/`，完成商品/SKU、真实 Ollama 回答、编辑、复制、反馈和无自动发送的笔记本人工验收。
4. 人工反馈成功后才可将 Gate 更新为 `READY_FOR_LAN_USER_TEST`。体验完成后使用 `scripts\windows\停止AI客服.bat` 正常停止。

## 2026-07-23 Private 网络真实启动结果

- 用户已将物理以太网改为 `Private`。正式 LAN 启动成功：A/C/B 分别监听 `0.0.0.0:8000`、`0.0.0.0:8011`、`0.0.0.0:5173`；局域网页面为 `http://192.168.1.11:5173/`。
- 迁移已在当前 revision；测试包为 `IMPORTED_TEST_ONLY`；A 同步记录为 47/47；`ready=true`、`model_configured=true`；真实 Ollama `CONTROLLED_ANSWER` 带来源且未命中兜底标记；A/C 对 LAN Origin 的 GET 与 OPTIONS CORS 均通过；C 目录为 1 店铺、5 商品、18 SKU。
- 当前不能进行笔记本交接：环境变量注入函数覆盖服务名，导致运行记录未按 `platform`、`rag`、`customer-web` 保存。状态脚本能确认健康，却无法显示受管 PID；停止脚本不能安全停止这些进程。
- 保持当前服务运行，不要手工删除 `.runtime`、强杀监听 PID 或执行停止脚本。须先以独立 OPS 修复纠正运行记录命名、重启并验证安全停止后，再继续笔记本人工验收。

## 2026-07-23 OPS-LAN-RECORD-FIX1 结果

- 修复已合并并推送为 `56acf9792bf728eaad12f8025be658a6dcfdbbcc`；后续启动会稳定登记 `platform.json`、`rag.json`、`customer-web.json`。五套正式 OPS 回归和 PowerShell 语法检查均通过。
- 停止前证据已保存至被忽略的 `.runtime/recovery-backup/`。重新读取后，8000 的错误记录可沿父子进程验证，5173 的错误记录可直接验证；8011 的 `platform` 标准记录已被覆盖而缺失。
- 8011 health 仍为 200，监听者可沿父进程到正式 C 虚拟环境，但缺少可比对的历史运行记录启动时间。此项不满足 Gate；没有停止任何服务、没有清理任何记录、也没有执行新版 LAN 重启。不要按端口结束、强杀、手工删除记录或关闭防火墙。笔记本人工验收继续等待。
