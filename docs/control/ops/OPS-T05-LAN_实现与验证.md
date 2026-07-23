# OPS-T05-LAN 局域网一键客服体验模式

日期：2026-07-23

范围：`scripts/windows/**`、`docs/control/ops/**`。未修改 A/B/C 业务代码或共享 contracts。

## 交付

- 新增 `启动局域网客服.bat`、`检查局域网客服状态.bat`、`start_lan_ai_customer_service.ps1` 和 `status_lan_ai_customer_service.ps1`；原有本机启动、状态和停止入口没有修改。
- LAN 入口固定将 A/C/B 绑定到 `0.0.0.0:8000`、`0.0.0.0:8011`、`0.0.0.0:5173`，健康检查仍经 `127.0.0.1` 在主电脑执行。
- `LanAdvertisedHost` 明确配置时必须是已连接、非虚拟物理网卡上的私有 IPv4；为空时只接受唯一候选。候选过滤 loopback、link-local、Docker、WSL、虚拟/VPN/TAP 网卡和断开网卡，多候选拒绝猜测。
- Public 网络默认阻止；`AllowPublicNetwork=true` 是显式覆盖并会警告。脚本只读取防火墙状态并提示可能的入站拦截，从不关闭防火墙或创建放通规则。
- LAN 运行时为 A/C 注入三个显式 CORS Origin：局域网页面、本机 `127.0.0.1` 和 `localhost`；为 B 注入局域网的 RAG/C API 地址。没有通配符 CORS。
- 状态入口同时报告本机/局域网页面、A/C/B 监听地址、Ollama 和模型、C 迁移、测试包、47 条同步、`model_configured`、网络配置类型、防火墙提示和日志目录。

## 验证证据

`powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\windows\tests\Test-OpsLanMode.ps1`：通过。

该隔离测试覆盖本机默认配置兼容、明确 LAN IP、唯一自动 IP、多网卡拒绝、Public 网络阻止、非法/公网 IP、A/B/C 绑定、前端 API 与 A/C CORS 环境、重复启动拦截、已记录进程安全停止、未知端口进程保护、PowerShell 语法，以及含空格和中文的仓库/配置路径。

这是脚本级验证；公司 Wi-Fi 的实际设备隔离与经管理员配置的防火墙放行，需在目标网络由操作者按手册完成验证。没有提交本地配置、日志、数据库、模型、测试包或客户数据。
