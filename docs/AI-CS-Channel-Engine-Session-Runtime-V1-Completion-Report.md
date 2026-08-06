# 《AI-CS Channel Engine Session Runtime V1 完成报告》

- 版本：V1 / `session_runtime_version=1.0`
- 完成日期：2026-08-04
- 最终状态：`CHANNEL_SESSION_RUNTIME_READY`
- 运行边界：SQLite、Fake Channel Adapter、Fake Credential Provider；未连接真实 PDD、真实账号、真实 Cookie、Playwright 或发送接口。

## 1. 完成结论

Channel Engine 已建立 Store → Channel Instance → Session → Adapter → Conversation 的单节点可靠运行基础。不同店铺具有独立实例、会话、适配器、游标、消息收件箱、ACK 进度与心跳记录。单店凭据不可用、适配器异常或会话过期只改变对应实例，不传播到其他店铺。

质量门结果：

| Gate | 结果 | 证据 |
| --- | --- | --- |
| Session Model Ready | PASS | 版本化 ChannelInstance/ChannelSession、受控状态转换、SQLite 恢复 |
| Cursor ACK Ready | PASS | persist-before-source-ACK、at-least-once、连续业务 ACK 游标、重复/冲突检测 |
| Multi Store Ready | PASS | 实例级 Adapter、Inbox、Cursor、Conversation 隔离及异常隔离测试 |
| Credential Boundary Ready | PASS | 仅保存 credential_ref/provider/version/lease_ref；无 secret value 字段 |
| Channel Session Runtime Ready | PASS | Runtime 生命周期、Heartbeat 与 API 已集成，完整回归通过 |

## 2. Runtime 架构

```text
StoreAccount
    ↓ 1:1 platform + store_id
ChannelInstance
    ↓ active_session_id
ChannelSession ── credential_ref ──→ CredentialProvider
    ↓ instance-scoped adapter
CursorAckChannelAdapterV1
    ↓ receive_envelopes() [非破坏读取]
Transactional Inbox + Message Cursor
    ↓ persist 成功后才 source ACK
At-least-once Delivery
    ↓ Conversation Runtime（store-scoped conversation key）
Business ACK / Retry Marker / Manual Intervention
```

核心边界：

- AI-CS 仍是 Intelligence Layer；本模块不生成 AI 回复。
- Channel Engine 只负责会话、接收可靠性、Conversation 路由与运行状态。
- Adapter 以 `instance_id` 注册，不以平台名注册，因此同平台多店可并行存在。
- V1 不实现真实 Credential 后端，也不向 Adapter 暴露明文凭据。

## 3. Channel Instance 与 Session

### 3.1 ChannelInstance

持久字段包括 `instance_id`、`platform`、`store_id`、`status`、`adapter_type`、`active_session_id`、`failure_code`、`created_at`、`updated_at` 和版本号。数据库对 `(platform, store_id)` 设置唯一约束。

状态：

```text
CREATED → STARTING → CONNECTED
                   ↘ AUTH_REQUIRED
                   ↘ DEGRADED
                   ↘ FAILED

CONNECTED → DEGRADED / AUTH_REQUIRED / STOPPED / FAILED
DEGRADED、AUTH_REQUIRED、FAILED、STOPPED → STARTING（显式恢复）
```

### 3.2 ChannelSession

持久字段包括 `session_id`、`instance_id`、`status`、`credential_ref`、`credential_lease_ref`、`heartbeat_time`、`expires_at`、`failure_code` 及时间戳。

状态机严格限定为：

```text
CREATED → AUTH_REQUIRED → CONNECTED
   └───────────────→ FAILED

CONNECTED → EXPIRED / FAILED
AUTH_REQUIRED → EXPIRED / FAILED
```

`EXPIRED` 与 `FAILED` 是终态；恢复时创建新 Session，保留旧记录用于审计和诊断。进程重启且会话仍有效时，可挂载新的 Adapter 进程并从持久化 Cursor 继续。

## 4. Cursor、ACK 与 Retry Marker

可靠接收遵循 at-least-once：

1. Adapter 通过 `receive_envelopes()` 非破坏读取，返回消息、source cursor 和严格递增 sequence。
2. Engine 在同一 SQLite 事务中校验 store/channel、消息指纹、sequence 连续性，并写入 Inbox 和 Message Cursor。
3. 只有事务成功后，Engine 才调用 Adapter `acknowledge(source_cursor)`；持久化失败时不发生 source ACK。
4. Inbox 以稳定 `delivery_id=SHA256(instance_id,message_id)` 重投未业务 ACK 的消息。
5. Conversation 处理成功后调用业务 `ack()`；重复 ACK 返回同一确定性 `ack_id`。
6. `last_acked_sequence` 只连续推进，先 ACK sequence 2 不会越过未 ACK 的 sequence 1。
7. 可恢复失败写入显式 `RetryMarker(attempt, reason_code, retry_after)`；达到有限次数后进入 `MANUAL_INTERVENTION`，禁止无限重试。

Fail-closed 规则：

- 相同 message_id、相同 payload/cursor/sequence：判定为重复，返回原持久化记录。
- 相同 message_id 但内容或 cursor 不同：`MessageDeliveryConflict`。
- sequence 跳号：`CursorGapDetected`，整批事务回滚，source 不 ACK。
- sequence 回退或被其他 message 占用：`CursorConflict`。
- store_id/channel 与实例绑定不一致：拒绝持久化且不 ACK。

## 5. 多店铺隔离

`ChannelInstanceManager` 支持创建、挂载、启动、停止、查询、健康检查、消息轮询与恢复。所有运行对象使用 `instance_id` 分区：

- Adapter：`instance_id → ChannelAdapterV1`
- Session：外键绑定 instance
- Cursor：每 instance 一条独立进度
- Inbox：主键包含 instance，sequence 唯一约束也限定在 instance 内
- Credential：每 Session 只绑定自己的 reference
- Heartbeat：每 instance 独立记录
- Conversation：`ChannelMessageV1.to_runtime_message()` 携带仅限进程内的 store_id，Repository 的 external_ref 使用有界 SHA-256 store scope；旧消息线格式不增加字段，Gateway Contract 无漂移。

因此 Store A 和 Store B 可使用相同平台 message_id/conversation_id，而不会共享消息、ACK、游标或 Conversation。

## 6. Credential Boundary

`CredentialProvider` 仅定义：

- `acquire(CredentialReference) -> CredentialLease`
- `is_available(CredentialReference) -> bool`

持久化与 API 只出现：

- `credential_ref`
- `provider`
- `version`
- 不透明 `credential_lease_ref`
- lease 过期时间

`CredentialReference` 拒绝包含 `cookie=`、`token=`、`password=`、`passwd=`、`secret=`、Authorization/Bearer material 的值。Fake Provider 只持有 reference，并返回 `lease-ref://...`；不接受、保存或记录真实 secret。静态扫描确认 Session 模块不存在 `credential_value`、`cookie_value`、`token_value`、`password_value` 或 `secret_value` 字段。

## 7. Heartbeat 与恢复

`SessionHeartbeatScheduler` 支持后台周期运行及测试用 `run_once()`，每个周期聚合：

- Session：连接状态和 credential lease 有效性
- Adapter：健康状态和生命周期
- Browser：抽象 ProbeReading（当前 Fake）
- Gateway：抽象 ProbeReading（当前 Fake）
- Storage：心跳结果写入 SQLite；数据库异常由现有 Runtime Storage probe 统一反映

异常实例进入 `DEGRADED`、`AUTH_REQUIRED` 或终态 Session；其他实例不受影响。恢复有界且显式：凭据重新可用可新建 Session，Adapter 恢复后重新连接；过期/失败 Session 不原地复活。Scheduler 聚合结果通过 `ChannelSessionRuntimeHealthProbe` 接入现有 Runtime Reliability。

已验证案例：

- Store C Adapter 心跳失败后仅 C 进入 `DEGRADED`，Store A 保持 `CONNECTED`，Store B 保持 `AUTH_REQUIRED`。
- Store B credential reference 重新可用后独立恢复为 `CONNECTED`。
- Session lease 过期后进入 `EXPIRED`，实例进入 `AUTH_REQUIRED`；恢复产生新 Session，旧 Session 保留。
- Adapter 进程替换后从 SQLite 的 source cursor 恢复，未业务 ACK 消息使用原 delivery_id 重投，新消息从下一个 sequence 继续。

## 8. Persistence

新增 SQLite 表：

| 表 | 用途 |
| --- | --- |
| `channel_instances` | 店铺实例与生命周期 |
| `channel_runtime_sessions` | Session 历史、credential reference、lease 与心跳 |
| `channel_message_cursors` | source cursor、last_sequence、连续 ACK 进度、revision |
| `channel_message_inbox` | 消息指纹、稳定 delivery、重试与 ACK 状态 |
| `channel_session_heartbeats` | 每实例每周期聚合健康证据 |

所有记录带 `session_runtime_version=1.0`；读取到未知版本时 fail closed。现有 schema upgrade/restart recovery 测试继续通过。

## 9. API 变化

新增只读/诊断 API：

| Method | Path | 功能 |
| --- | --- | --- |
| GET | `/session-runtime/v1/instances` | 返回全部实例、活动 Session 和 Adapter health |
| GET | `/session-runtime/v1/instances/{instance_id}` | 返回单实例隔离视图；不存在返回 404 |
| POST | `/session-runtime/v1/heartbeat` | 触发一次确定性健康聚合并持久化证据 |

没有新增发送 API、凭据写入 API或真实平台入口。

## 10. 测试结果

执行环境：Windows、Python 项目虚拟环境、SQLite 临时数据库、Fake Adapter/Fake Credential Provider/Fake probes。

| 测试集 | 结果 |
| --- | --- |
| Session Runtime 专项（unit/integration/API/safety） | 18 passed |
| 兼容专项（含旧 FakeChannel 与 Adapter flow） | passed |
| 完整项目回归 `pytest -q` | **317 passed** |
| Python compileall | PASS |
| `git diff --check` | PASS |
| Credential safety test | 1 passed |
| Secret value 字段扫描 | PASS，未发现 |

唯一提示为既有依赖的 Starlette `TestClient`/`httpx` deprecation warning，不影响本次功能。

覆盖内容：Session 状态机、非法转换、Cursor 连续性、持久化后 ACK、重复 ACK、乱序 ACK、Retry Marker、重试预算、Session restart recovery、多店状态/数据/Conversation 隔离、Adapter 异常、credential reference 拒绝与日志脱敏、Heartbeat 调度和 API。

## 11. 风险与下一阶段建议

1. 当前 Credential Provider 是安全边界 Fake，真实接入前应实现 OS/企业 Secret Manager provider；接口仍只返回不透明 lease reference。
2. V1 是 Windows 单节点 SQLite 模型。若未来横向扩展，需要在不改变 ACK 语义的前提下增加跨进程 ownership/lease 和数据库并发策略。
3. Conversation 当前通过确定性 store-scope external_ref 保持兼容；下一次数据库主版本可将 `store_id` 升为 Conversation 一等列并执行显式迁移。
4. 真实 Adapter 必须通过 contract test 证明 `receive_envelopes()` 非破坏读取、`acknowledge()` 幂等，并能按持久化 Cursor 恢复；未证明前不得接真实消息源。
5. Heartbeat 顶层循环为保证调度线程存活会吞掉周期异常；生产观测阶段应增加无敏感数据的 scheduler failure metric/audit event。
6. 本阶段未验证真实平台时序、身份或凭据轮换，只证明运行抽象和 Fake 行为。

## 12. 最终状态

`CHANNEL_SESSION_RUNTIME_READY`
