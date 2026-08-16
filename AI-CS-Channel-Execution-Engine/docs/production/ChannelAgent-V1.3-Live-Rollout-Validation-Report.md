# ChannelAgent V1.3 Live Rollout Validation Report

## 1. 结论

V1.3 主机授权与设备状态受控切换已完成。

- 18443 已运行 `channel_engine.production_app:app` 对应的 V2.1 Host Control。
- 18020 已运行 `channel_engine.production_operations_app:app` 对应的纯运营控制台。
- AI-CS 已通过独立服务身份和 HMAC 签名从 18443 读取设备。
- 当前唯一设备状态为 `REGISTERED + OFFLINE`。
- 本轮没有登录 PDD、没有关闭 Edge、没有清理 Profile、没有修改用户或店铺权限、没有开启真实发送。

最终状态：`V1.3_LIVE_ROLLOUT_READY`

## 2. 切换基线

检查时间：2026-08-08 17:06:28 +08:00

| 项目 | 切换前 | 切换后 |
|---|---|---|
| 18020 | `channel_engine.app:app`，PID 21204 | `run_channel_engine_operations_console.py`，PID 29172 |
| 18443 | 未监听 | `run_channel_engine_production_host.py`，PID 27848 |
| 18020绑定地址 | 127.0.0.1 | 127.0.0.1 |
| 18443绑定地址 | 无 | 192.168.1.11，TLS |
| Channel Engine SHA | `5c105dbe855c09dfe31c9d2bbf5d18caec40b32b` | 未改变 |
| AI-CS SHA | `584f20219bc12d6caacc384579f43f20786f7459` | 未改变 |

配置来源：

- Host Control数据库：`.runtime/channel-engine.sqlite3`。
- Host Control TLS及服务引用：`.runtime/channel-agent-lan-host/`。
- AI-CS本地运行配置：`AI-CS/.runtime/r027-ux-acceptance-data-v1/ux-acceptance.local.ps1`。
- 运营控制台数据库：`.runtime/channel-agent-lan-host/operations-console.sqlite3`。
- TLS证书SHA256：`bf0a08ddf9c86cb01e20fd5ebe059dcd922a4026f6c22701e52c790cfd5be05c`。
- 服务密钥只保存在Windows Credential Manager；报告、配置、命令行和日志均未记录密钥值。

## 3. 服务状态

### 18443 Host Control

- HTTPS健康检查：200。
- 服务：`channel-engine-host-control`。
- 版本：`0.2.0rc1`。
- Agent Control协议：`2.1`。
- V1 Router：未挂载。
- AI-CS签名设备查询：`SIGNED_DEVICE_LINK_READY`。

### 18020运营控制台

- HTTP健康检查：200。
- 服务：`channel-engine-operations-console`。
- 版本：`0.2.0rc1`。
- 声明设备来源：`CHANNEL_ENGINE_HOST_CONTROL_VIA_AI_CS`。
- `/channel-agent/v1/*`：404，未挂载。
- 未认证设备查询：401，Fail Closed。

### AI-CS

- 8422平台服务已受控重载，8420、8421和8423未停止。
- AI-CS `HttpChannelAgentUpstream` 使用当前运行配置成功完成签名查询。
- 返回来源：`CHANNEL_ENGINE_HOST_CONTROL`。
- 返回设备数：1。

## 4. 数据源确认

18443权威数据库包含1条设备身份：

```text
agent-desktop-0345200
identity_status     = REGISTERED
connectivity_status = OFFLINE
last_heartbeat      = null
```

18020使用独立数据库。虽然通用Schema包含设备表定义，但该表记录数为0；生产运营入口没有Agent Repository，设备查询及写操作必须经过：

```text
18020运营控制台
→ AI-CS管理员RBAC
→ AI-CS服务身份签名
→ 18443 V2 Host Control
```

18443不可用、管理员未认证或签名失败时，18020设备管理操作均拒绝执行。

## 5. 设备状态与操作验证

当前真实设备不做绑定或权限变更，保持：

```text
REGISTERED + OFFLINE
```

以下状态流转使用隔离测试数据库验证，避免改变真实设备：

- 旧`UNBOUND`兼容映射为`REGISTERED`。
- `REGISTERED → BOUND → ACTIVE`绑定和启用流程通过。
- 心跳只将`connectivity_status`从`OFFLINE`改为`ONLINE`。
- 断线只将连接状态改回`OFFLINE`，不覆盖身份状态。
- `DISABLED → REGISTERED`恢复流程通过，旧用户和店铺授权不恢复。
- 18020恢复操作通过AI-CS和18443链路，不能直接写本地设备Repository。

## 6. 验证结果

| 验证项 | 结果 |
|---|---|
| 18443健康检查 | PASS |
| V2.1签名认证 | PASS |
| 权威设备查询 | PASS |
| AI-CS服务身份调用 | PASS |
| 18020纯运营入口 | PASS |
| 18020/18443数据源隔离 | PASS |
| 当前设备`REGISTERED + OFFLINE` | PASS |
| 恢复为待绑定语义 | PASS（隔离数据库） |
| 绑定与启用语义 | PASS（隔离数据库） |
| 心跳/离线双状态语义 | PASS（隔离数据库） |
| PDD及真实发送安全边界 | PASS |

测试记录：

- Channel Engine Host Control及Operations专项：15 passed。
- AI-CS Desktop Workflow API、安全及迁移专项：18 passed。

## 7. 运维说明

- 当前切换已满足本机AI-CS、18020和18443的正式分层运行。
- 当前终端不是管理员会话，因此本轮没有新增Windows防火墙规则。第二台客服电脑首次从局域网连接前，仍需以管理员身份运行正式局域网启动器以完成防火墙和受控发现配置。
- 该限制不影响当前主机上AI-CS经签名访问18443，也不改变本次V1.3切换结论。
