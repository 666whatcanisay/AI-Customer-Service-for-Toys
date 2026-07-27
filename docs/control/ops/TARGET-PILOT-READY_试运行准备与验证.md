# OPS-TARGET-PILOT-READY：真实客服试运行准备与验证

日期：2026-07-27

范围：`scripts/windows/**`、`docs/control/**`。未修改 A/B/C/Admin 业务代码、共享 contracts、依赖、数据库结构、网络策略或防火墙规则。

## 每日运行流程

1. 在受控 Private 网络的服务器上运行 `启动客服试运行.bat`。
2. 启动器复用既有 C → A → B → Admin 顺序，验证迁移、测试包幂等、A 就绪、知识同步和真实 Ollama smoke；`-NoBrowser` 只禁止本机浏览器打开，不改变服务启动。
3. 启动后自动运行 `check_target_pilot_readiness.ps1`：检查四项受管身份与 health，探测客服入口 TCP、页面、`/rag-api/api/health`、`/platform-api/health`，并写入 `.runtime/pilot-readiness/target-pilot-*.json`。
4. 服务器侧探测通过后，由第二台受控客服电脑访问脚本输出的 5173 URL，并运行 `Test-NetConnection <服务器IPv4> -Port 5173`。第二台设备验收不能由服务器自测替代。

## 保护与恢复

- A/C 仅监听服务器回环，B 是唯一 LAN 入口；Admin 默认只绑定 `127.0.0.1:5174`。不开放 8000、8011 或 5174，不自动改防火墙。
- 就绪报告只包含状态、端口、URL、PID 和布尔探测结果；不包含客户内容、回答、令牌、密钥、完整命令行或本地配置。
- `恢复客服试运行.bat` 要求输入 `RESTART`，随后才按 Admin → B → A → C 使用已有的受管 PID/监听 PID 验证停止器。身份不一致、未知监听者和未验证记录均拒绝处理。
- Windows TCP 监听查询使用只读 `netstat` 解析；无法读取监听状态时拒绝启动或停止，避免把“查不到”误判为“端口安全”。

## 已验证事实

- 隔离回归覆盖每日入口、服务身份、服务器侧客服访问模拟、固定代理、Admin 回环限制、LAN 配置拒绝、脱敏报告、显式恢复以及浏览器抑制。
- 真实主机已完成：安全停止 → C/A/B/Admin 启动 → 迁移/测试包/47 条知识同步/真实 Ollama smoke → 页面与固定代理探测 → 显式恢复重启 → 再次探测。
- 最终服务器侧状态为 `READY_FOR_CUSTOMER_PILOT`；四服务保持运行。此结论不包含第二台客服电脑的人工验收。

## Gate

`CONDITIONAL PASS`：主机试运行环境准备完毕，且脚本、真实生命周期和服务器侧访问模拟均已验证。下一步仅是第二台受控客服电脑的人工网络与浏览器验收；若该设备在同一受控网段仍不可达，记录 `NETWORK_SEGMENTED`，不扩大网络暴露面。
