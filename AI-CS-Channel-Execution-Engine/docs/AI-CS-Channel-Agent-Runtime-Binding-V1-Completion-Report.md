# 《AI-CS Channel Agent Runtime Binding V1 Completion Report》

日期：2026-08-06
结论：`CHANNEL_AGENT_RUNTIME_BINDING_READY`

## 技术结论

Channel Agent 已具备从 Windows 客服电脑到 Channel Engine 的受控身份绑定运行链：设备先注册，管理员签发一次性绑定码，Agent 在安全传输上完成用户及多店铺绑定，管理员再显式激活；运行期间由心跳同步服务端权威绑定版本。解绑后身份进入 `DISABLED` 并立即失去生产运行资格。

本次没有引入 PDD、浏览器、消息读取或发送能力；Gateway Contract V1 未修改，规范化 SHA256 仍为 `e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`。

## 1. Agent 结构

新增或增强的主要模块如下：

| 模块 | 职责 |
| --- | --- |
| `channel_agent.binding` | Enrollment 请求/响应、公开绑定快照、原子本地存储 |
| `channel_agent.identity` | 用户、设备、多店铺、绑定修订号及在线状态模型 |
| `channel_agent.client` | 注册、一次性 Enrollment、心跳与权威状态同步 |
| `channel_agent.runtime` | 将服务端绑定状态并入 Agent 生命周期与断线恢复 |
| `channel_agent.windows_app` | `enroll` 与 `binding-status` Windows 命令 |
| `channel_engine.agent.node_api` | Enrollment Gate、绑定治理、Admin 查询与状态同步 API |
| `channel_engine.agent.binding_repository` | SQLite 身份绑定持久化 |
| `channel_engine.storage.orm` | `channel_agent_identities` 持久表 |

Windows Client 版本由 `1.0.0` 提升为 `1.1.0`，Agent 协议版本保持 `1.0`，Channel Engine 保持 `0.1.0rc1`。

## 2. Runtime 状态与绑定生命周期

绑定状态机冻结为：

```text
UNBOUND --一次性授权绑定--> BOUND --管理员核验激活--> ACTIVE
   |                         |                         |
   +-------------------------+-------------------------+
                             管理员解绑
                                  |
                                  v
                              DISABLED
```

- `UNBOUND`：设备已注册，但没有用户或店铺权限，不能进入生产运行。
- `BOUND`：用户与至少一个店铺引用已由管理员授权绑定，仍需显式激活。
- `ACTIVE`：身份可进入受控生产运行；这不启用消息读取或发送。
- `DISABLED`：解绑后的终止状态；用户和店铺引用被清除，心跳及配置访问 fail closed。

每次 Enrollment、激活、店铺变更或解绑都会增加 `binding_revision`。同一 `device_id` 不能注册为第二个 Agent；同一 Agent 也不能切换到另一设备。

## 3. 通信与 Enrollment 流程

### 首次绑定

```text
Windows Agent
  -> POST /channel-agent/v1/agents/register
管理员
  -> POST /channel-agent/v1/admin/enrollment-grants
Windows Agent
  -> POST /channel-agent/v1/agents/enroll
管理员
  -> POST /channel-agent/v1/admin/agents/{agent_id}/activate
```

Enrollment 使用 32 位十六进制一次性绑定码：有效期 60 至 3600 秒，只能使用一次，并严格绑定 `agent_id + device_id`。服务端只保留 SHA256 摘要；客户端通过隐藏输入或标准输入接收绑定码，不支持将其作为命令行参数，也不会写入配置、状态、绑定快照或日志。

Enrollment 仅允许 HTTPS，或用于本机部署的 loopback HTTP。用户和店铺权限来自管理员签发的授权内容，Agent 不能自行选择角色、用户或店铺。

### 多店铺绑定

一个 Agent 可关联 1 至 32 个唯一 `store_reference`。第一个引用作为兼容旧接口的主店铺，其余引用通过 `store_ids` 同步。店铺调整仅允许拥有 `AGENT_IDENTITY_MANAGE` 权限的管理员执行：

- `PUT /channel-agent/v1/admin/agents/{agent_id}/stores`
- Agent 下次心跳获得新的服务端权威绑定和修订号。
- 客户端上报与当前修订相同但引用不一致时，服务端返回冲突并拒绝状态更新。

## 4. 心跳与状态同步

心跳继续使用版本化 V1 接口：

- `PUT /channel-agent/v1/agents/{agent_id}/status`
- 上报 `agent_id`、`device_id`、用户引用、店铺引用、`binding_revision`、Agent 版本、主机名、运行状态和时间戳。
- 服务端返回权威 `AgentIdentity`、生产资格、配置修订和服务端时间。
- 断线时 Agent 进入 `DEGRADED`；连接恢复后重新注册/心跳，并同步最新店铺集合和绑定修订号。

默认 SQLite 仓库持久化设备、用户、店铺、状态与修订号。Channel Engine 重启后仍可在管理员视图看到绑定关系；尚未重新上线的 Agent 显示为 `OFFLINE`。

## 5. Admin View

管理员只读视图提供：

- `GET /channel-agent/v1/admin/agents`
- `GET /channel-agent/v1/admin/agents/{agent_id}`
- `GET /channel-agent/v1/admin/identity-audit`

返回 Agent、设备、用户、全部店铺、绑定状态、在线状态、版本、主机名、最近心跳及运行状态。在线状态按心跳和运行状态归一为 `ONLINE`、`DEGRADED`、`OFFLINE`。

## 6. 安全设计

- Enrollment 授权由 RBAC 控制；`OPERATOR` 不能签发绑定码、改变店铺、激活或解绑，`ADMIN` 才具备管理权限。
- 一次性绑定码不落盘、不入日志，服务端只保存摘要；过期、复用、错设备和错误码全部 fail closed。
- 本地 `agent-binding.json` 只保存公开引用、状态和修订号，不包含密码、Cookie、Token 或绑定码。
- 日志沿用结构化脱敏器，不记录异常正文或敏感键值。
- `message_read_enabled=false`、`send_enabled=false`、`browser_automation_enabled=false` 保持不可被远端配置打开。
- Gateway Contract、AI-CS、PDD Adapter 和执行链均未修改。

## 7. 测试结果

最终验证基于 2026-08-06 工作区快照：

| 验证项 | 结果 | 证据 |
| --- | --- | --- |
| 全量回归 | PASS | 549 passed，0 failed，1 个第三方弃用警告 |
| Contract + RC1 Release Lock | PASS | 128 passed |
| Security + Runtime Binding 聚焦测试 | PASS | 28 passed |
| Python 编译 | PASS | `compileall` 通过 |
| 依赖完整性 | PASS | `pip check` 无 broken requirements |
| Gateway Contract | PASS | V1.0 规范化 SHA256 与冻结值一致 |
| Windows 包清单 | PASS | 1,625 个文件，0 个哈希/大小不一致，0 个禁止模块 |
| 独立安装链 | PASS | 安装、版本、配置、停止、卸载均返回 0；不可达网关返回 2 |

必须场景的覆盖关系：

- 安装/卸载：真实 PowerShell 安装布局与独立打包验证。
- 绑定：一次性 Enrollment、管理员授权、Windows 本地公开绑定落盘。
- 解绑：引用清除、状态进入 `DISABLED`、生产资格撤销。
- 断线恢复：`ONLINE -> DEGRADED -> ONLINE`，恢复后同步最新绑定修订。
- 状态同步：注册、心跳、Admin 在线视图、多店铺权威更新。

Windows RC 包：

- 文件：`dist/windows-client-v1/AI-CS-Channel-Agent-1.1.0-windows-x64.zip`
- ZIP SHA256：`af50f4b62e64c56d2741e99085f01452d4e66e0995dd08e890ebb1061bac2f4c`
- `ChannelAgent.exe` SHA256：`0ca23c07f0835caa2365af7f9925988af225a00a77c76135d962468234b8c1bf`

## 8. 限制、鲁棒性与后续依赖

本轮结论限于 Foundation 级受控绑定，不等同于真实渠道上线：

- Enrollment Grant 为内存态且刻意短期有效；Channel Engine 重启后旧绑定码失效，需要管理员重新签发。
- 身份绑定已持久化，但绑定审计事件当前仍为进程内记录；生产部署前应接入现有持久审计存储。
- V1 使用一次性 Enrollment 证明首次绑定授权，尚未实现 Windows 设备证书、TPM 或 DPAPI 支持的持续设备证明。
- 管理员身份由现有 `OperatorIdentityProvider` 提供；生产环境必须接入真实身份提供方，不能使用测试 provider。
- 未实现 PDD 账号绑定、浏览器 Session、消息观察或发送；后续接入必须继续服从 Approval、Execution、Receipt 和 Kill Switch 边界。

建议下一阶段按顺序完成：

1. 为已绑定设备增加可轮换、不可导出的设备证明，并接入 Windows 安全存储。
2. 将 Enrollment/绑定审计写入持久 Audit Ledger。
3. 增加管理员撤销后的客户端只读状态拉取，使本地 UI 可显示 `DISABLED` 原因而不放宽 fail-closed 心跳。
4. 在上述安全项完成后，再设计 PDD 账号引用与 Agent 身份的独立绑定；不得复用或保存平台 Cookie。

## 9. 最终状态

所有要求的 Foundation 能力、测试和 Windows 交付验证已完成。

`CHANNEL_AGENT_RUNTIME_BINDING_READY`
