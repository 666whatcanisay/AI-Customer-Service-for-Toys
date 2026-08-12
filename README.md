# AI-CS Channel Execution Engine

AI-CS Channel Execution Engine 是 AI-CS 的独立渠道执行层。AI-CS 负责业务上下文、知识与回复决策；Channel Engine 负责 Provider 标准化、会话状态、人工审批、安全执行、Receipt、Outbox 与可观测性；Channel Agent 负责客服电脑上的边缘身份、消息观察和受控执行边界。

当前 RC5 收口版本：

- Channel Engine：`0.2.0rc3`
- Channel Agent：`2.0.0rc5`
- Agent Control：`2.1`
- Gateway Contract wire：`1.0`
- Gateway Contract canonical SHA-256：`e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`
- RC 状态：`RC5_FINAL_READY`（仅在最终交付清单全部 PASS 后成立）

## RC5 范围

本轮目标是在不连接真实拼多多的条件下冻结完整离线产品链：

`Synthetic / Recorded Replay → ChannelAgent → Host → Buffer/Cursor/ACK → CustomerContext → AI-CS → Quality Gate → MANUAL_CONFIRM / AUTO_LOW_RISK → EXECUTION_PREPARED`

真实 PDD 读取、真实页面 Selector、真实发送和长时间真实环境运行属于后续 Pilot Gate。代码签名、企业证书、Windows Service 与正式 Release Tag 属于商业发布阶段，本轮统一标记为 `NOT IN SCOPE`，不阻塞离线 RC5。

## 已冻结安全边界

- Agent Identity、Device Binding、Edge Profile 与 PDD Session 不因普通升级或离线验收被清理。
- Gateway Contract V1 已冻结；无兼容性审查不得修改 wire schema 或 canonical SHA。
- Cursor 只在 Host 持久化并返回有效 ACK 后推进；重复消息必须幂等。
- 所有执行必须经过店铺、会话、权限、策略和 Kill Switch 安全门。
- `UNKNOWN` Receipt 禁止自动重试，必须进入人工对账。
- Synthetic Receipt 与真实 Receipt 使用不同来源语义，测试成功不能表示真实发送成功。
- 当前 RC5 保持 `real_send_enabled=false`，不会把离线验收转换为真实平台副作用。

完整冻结清单、变更触发条件、测试证据和 Pilot 结论见 [RC5 最终交付索引](docs/production/rc5-final/README.md)。

## 开发与验证

要求 Windows、CPython 3.12 和 SQLite：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-rc1.lock
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
.\.venv\Scripts\python.exe -m pytest
```

只启动本地受控 API：

```powershell
.\.venv\Scripts\python.exe -m uvicorn channel_engine.production_app:create_host_control_app --factory --host 127.0.0.1 --port 18020
```

执行 RC5 后端黑盒验收（不会启动浏览器或调用真实发送）：

```powershell
.\.venv\Scripts\python.exe scripts\run_rc5_backend_blackbox_suite.py
```

生产 Windows 包必须通过 `packaging/windows-client-v2/production-composition.json` 的显式 allowlist 构建；Fake、Sandbox、Pilot、`run_real_*`、真实发送和明文凭据不得进入安装包。
