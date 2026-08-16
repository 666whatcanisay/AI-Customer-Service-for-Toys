# 《AI-CS Channel Agent Identity Binding V1 Completion Report》

## 1. 完成结论

Channel Agent Identity Binding V1 已完成。系统现在可以以引用关系明确记录：一个 Agent 运行在哪个设备、被管理员绑定到哪个用户引用、服务哪个店铺引用，并通过 `UNBOUND → BOUND → ACTIVE → DISABLED` 生命周期阻止未绑定或已禁用节点取得生产运行资格。

Agent 注册时可以声明 `user_reference` 和 `store_reference`，但声明不会自动形成绑定，也不会使 Agent 取得生产资格。只有外部身份提供者认证、且具备 `AGENT_IDENTITY_MANAGE` 权限的管理员才能执行绑定、激活和解绑。

Final Status: `CHANNEL_AGENT_IDENTITY_BINDING_READY`

## 2. 数据模型

`AgentIdentity` 是冻结、拒绝额外字段的 V1 模型：

| 字段 | 含义 | 安全约束 |
| --- | --- | --- |
| `agent_id` | Agent 稳定标识 | 仅引用，不复制用户数据 |
| `device_id` | 客服电脑设备标识 | 一个 Agent 不能静默切换设备 |
| `user_id` | 用户引用 | 仅 `BOUND/ACTIVE` 时存在 |
| `store_id` | 店铺引用 | 必须与用户引用同时存在 |
| `status` | 身份生命周期状态 | 非法跳转拒绝 |
| `created_at` | 创建时间 | aware datetime |
| `updated_at` | 最近绑定变更时间 | 不得早于创建时间 |

绑定审计使用 `AgentIdentityAuditEvent`，记录操作人引用、动作、时间、原因和前后状态。事件对象不可变；原因在保存前脱敏，不包含 Cookie、Token 或密码。

## 3. API 变化

### Agent 控制面增强

| 方法 | 路径 | 变化 |
| --- | --- | --- |
| `POST` | `/channel-agent/v1/agents/register` | 增加 `agent_version`、`user_reference`、`store_reference`；返回身份状态和生产资格 |
| `PUT` | `/channel-agent/v1/agents/{agent_id}/status` | Heartbeat 增加 `device_id`、`user_id`、`store_id`；服务端校验绑定一致性 |
| `GET` | `/channel-agent/v1/agents/{agent_id}/config` | 返回 `identity_status` 与 `production_eligible` |

注册仍兼容既有 `version` 输入别名，但新客户端统一发送 `agent_version`。

### 管理查询与受控绑定

| 方法 | 路径 | 权限 |
| --- | --- | --- |
| `GET` | `/channel-agent/v1/admin/agents` | `AGENT_IDENTITY_READ` |
| `GET` | `/channel-agent/v1/admin/agents/{agent_id}` | `AGENT_IDENTITY_READ` |
| `GET` | `/channel-agent/v1/admin/identity-audit` | `AGENT_IDENTITY_READ` |
| `PUT` | `/channel-agent/v1/admin/agents/{agent_id}/binding` | `AGENT_IDENTITY_MANAGE` |
| `POST` | `/channel-agent/v1/admin/agents/{agent_id}/activate` | `AGENT_IDENTITY_MANAGE` |
| `DELETE` | `/channel-agent/v1/admin/agents/{agent_id}/binding` | `AGENT_IDENTITY_MANAGE` |

Admin 查询返回 Agent 列表、设备、运行状态、最后心跳、用户引用和店铺引用，不返回用户资料或凭证。默认 Operator Identity Provider 拒绝全部请求；部署必须显式注入外部认证提供者。

## 4. Agent 身份生命周期

| 状态 | 引用要求 | 生产资格 | 允许的下一状态 |
| --- | --- | --- | --- |
| `UNBOUND` | 用户/店铺引用为空 | 否 | `BOUND` |
| `BOUND` | 用户与店铺引用同时存在 | 否 | `ACTIVE`、`DISABLED` |
| `ACTIVE` | 用户与店铺引用同时存在 | 是 | `DISABLED` |
| `DISABLED` | 引用清除 | 否 | 无 |

规则如下：

- Agent 自报引用在 `UNBOUND` 状态下只作为声明，不改变服务端绑定。
- `BOUND` 仍不能进入生产运行，必须由管理员独立执行激活。
- `ACTIVE` Heartbeat 必须同时匹配 Agent、设备、用户和店铺引用。
- 解绑进入终态 `DISABLED`，清除当前引用并保留审计；后续注册、Heartbeat 和配置读取均 fail closed。

## 5. 安全设计

- 复用现有 Operator、Supervisor、Admin RBAC 体系，新增 `AGENT_IDENTITY_READ` 与 `AGENT_IDENTITY_MANAGE` 权限；只有 Admin 默认拥有这两项权限。
- 身份提供者通过不透明 Session Reference 认证操作人；API 请求体不接收密码、Cookie 或 Token。
- Agent 注册和 Heartbeat 没有管理权限参数，不能通过请求字段提升身份状态。
- 相同 `agent_id` 使用不同 `device_id` 时返回冲突。
- 已绑定 Agent 上报不一致用户或店铺引用时返回 `AGENT_IDENTITY_CLAIM_MISMATCH`。
- 所有绑定、激活和解绑变更追加不可变审计事件，敏感原因在写入前脱敏。
- Admin API 只返回引用，不复制用户、店铺或账号业务数据。

## 6. 测试结果

| 验证项 | 结果 |
| --- | --- |
| Identity Binding 新增专项 | `9 passed, 0 failed, 1 warning` |
| Foundation + Identity 联合专项 | `21 passed, 0 failed, 1 warning` |
| 全仓最终回归 | `532 passed, 0 failed, 1 warning` |
| Contract Validation | `123 passed, 0 failed, 1 warning` |
| Security Validation | `17 passed, 0 failed` |
| `compileall` | PASS |
| `pip check` | PASS |
| `git diff --check` | PASS |

新增测试覆盖：Agent 注册、声明不可自绑定、身份绑定、激活、解绑、权限拒绝、Heartbeat 引用一致性、禁用阻断、异常状态、审计脱敏和完整 FastAPI 注入链。

全仓首轮曾出现一个既有 Runtime Reliability 恢复用例的瞬时失败；该用例单独复跑通过，随后完整全仓复跑 `532 passed`，且没有为此修改无关 Runtime 代码。

Gateway Contract schema 工作树改动为 `0`，canonical SHA-256 保持：

`e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`

## 7. 限制与后续 PDD 账号绑定依赖

当前 Registry、Identity 和 Audit 仍为单进程内存实现；它们适合 Foundation 验证，不是生产身份数据库。下一阶段至少需要：

1. 将 AgentIdentity 与 Audit 持久化到现有 SQLite 边界，并保证事务一致性。
2. 接入真实企业身份提供者或 Windows 设备证书，Session Reference 不得替换为明文 Token 配置。
3. 建立用户目录与店铺目录的只读解析接口；Agent 仍只保存引用。
4. 将 PDD 登录后发现的店铺身份与 `store_reference` 做服务端匹配，禁止 Agent 或操作人手填平台身份作为可信来源。
5. 在 Browser/Session/Adapter 启动前统一检查 `identity_status=ACTIVE`，并继续通过现有 Approval、Execution、Receipt 安全链。
6. PDD 真实登录、消息观察和发送仍需独立授权，本任务没有启用这些能力。

Final Status: `CHANNEL_AGENT_IDENTITY_BINDING_READY`
