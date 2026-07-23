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
- 当前三个服务端口均无监听；本轮没有删除虚拟环境、依赖、原始 ZIP、数据库、向量库或日志。

## 当前 Gate：BLOCKED

用于局域网互访的物理以太网在 Windows 中显示为 `Public`。LAN 启动模式会因此安全拒绝启动，且不允许以 VPN/虚拟网卡、`AllowPublicNetwork=true`、关闭防火墙、手工补启动或强杀未知进程绕过。

## 恢复与验收

1. 用户在 Windows 设置中将笔记本实际连接的物理网络改为 `Private`，或接入 `DomainAuthenticated` 网络。
2. 在正式主仓库运行 `scripts\windows\启动局域网客服.bat`。
3. 以脚本显示的私有 IPv4 访问 `http://<主电脑IPv4>:5173/`，完成商品/SKU、真实 Ollama 回答、编辑、复制、反馈和无自动发送的笔记本人工验收。
4. 人工反馈成功后才可将 Gate 更新为 `READY_FOR_LAN_USER_TEST`。体验完成后使用 `scripts\windows\停止AI客服.bat` 正常停止。
