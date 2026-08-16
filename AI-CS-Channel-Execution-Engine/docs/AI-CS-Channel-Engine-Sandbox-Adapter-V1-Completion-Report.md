# 《AI-CS Channel Engine Sandbox Adapter V1 完成报告》

- 版本：V1 / `sandbox_adapter_version=1.0`
- 完成日期：2026-08-04
- 最终状态：`CHANNEL_SANDBOX_ADAPTER_READY`
- 安全边界：仅 Fake Gateway、Fake Credential Provider、SQLite 与进程内 Sandbox；无真实 PDD、账号、Cookie、浏览器或网络发送。

## 1. 完成结论

已建立接近真实渠道时序的 Sandbox Adapter。它实现 ChannelAdapterV1 与 CursorAckChannelAdapterV1 边界，可在不接触真实平台的情况下验证消息拉取、source ACK、Session、Heartbeat、受控发送、Execution Receipt、Event/Outbox 以及有界恢复。

| Quality Gate | 结果 | 核心证据 |
| --- | --- | --- |
| Sandbox Adapter Ready | PASS | receive_messages、receive_envelopes、send_message、health_check、connect/recover/disconnect |
| Failure Injection Ready | PASS | 网络、Adapter 崩溃、Gateway 超时、Execution UNKNOWN、ACK 失败 |
| Recovery Verification Ready | PASS | Heartbeat 降级、Session 替换、Adapter/Browser/Gateway 恢复 |
| End-to-End Sandbox Ready | PASS | Message → Session → Fake AI-CS → Approval → Execution → Receipt → Event/Outbox |

## 2. 架构

```text
Sandbox Event Script
        ↓
SandboxChannelAdapter
        ↓ non-destructive receive_envelopes()
ChannelInstance / ChannelSession
        ↓ persist → source ACK
Transactional Inbox / Cursor
        ↓ at-least-once delivery
Conversation Runtime
        ↓
Fake AI-CS Gateway → Decision → Human Approval
        ↓ claimed lease
SandboxExecutionAdapter
        ↓ authorized send_message()
Sandbox Channel Receipt
        ↓
Execution Receipt → Event → Transactional Outbox
```

关键约束：

- Sandbox Adapter 没有平台 URL、浏览器驱动、Cookie、Token 或账号输入。
- `send_message()` 只接受由 Execution Ledger 根据 APPROVED Decision、APPROVED Approval、RUNNING Execution 和有效 lease 签发的 `AuthorizedOutboundMessage`。
- 裸文本发送直接拒绝。
- 所有 outbound receipt 固定标记 `real_platform_called=false`、`customer_message_sent=false`、`automatic_reply=false`。
- Channel Engine 不生成 AI 内容；Decision 始终来自 Fake AI-CS Gateway。

## 3. Sandbox Adapter

`SandboxChannelAdapter` 基于已冻结的 Adapter Foundation，新增：

- 平台名固定为 `sandbox`，店铺仍由 `store_id` 隔离。
- `receive_messages()`：兼容批量消费接口。
- `receive_envelopes()`：非破坏读取，并返回 `sandbox:<sequence>` cursor。
- `acknowledge()`：显式 source ACK，幂等处理重复 cursor。
- `send_message()`：复用 Ledger authorization，返回不可变模拟 Receipt。
- `health_check()`：输出 lifecycle、pending message、真实平台未调用和自动发送关闭状态。
- `recover()`：进入 RECOVERING，遵循已有有限恢复次数，不做无限重试。
- 确定性 `SandboxClock`：无需 sleep 即可测试延迟、lease 过期和重试时间。

同一店铺会话在 Adapter 中同时保留平台原始 conversation_id 与有界 SHA-256 store scope，从而与 Session Runtime 的多店 Conversation 隔离及受控 outbound authorization 一致。

## 4. Event Simulation

| 事件 | 模拟行为 | 验证点 |
| --- | --- | --- |
| `customer_message_received` | 生成合规 ChannelMessageV1 与递增 source sequence | Normalization、Store、Cursor |
| `message_duplicate` | 重放原 message_id、cursor、sequence | Inbox 返回原记录，不重复业务处理 |
| `message_delay` | 在确定性时间点前返回空批次 | 不乱序、不阻塞线程 |
| `ack_failure` | persist 后 source ACK 抛出一次或多次故障 | 已持久化消息可重投，source 不丢失 |
| `session_expired` | 时钟推进超过 credential lease，再由 Heartbeat 识别 | Session EXPIRED、实例 AUTH_REQUIRED |
| `browser_disconnected` | Browser probe 进入 UNHEALTHY | 实例 DEGRADED，其他数据保留 |

扩展故障事件包括 `network_failure`、`adapter_crashed` 与 `recovery_completed`。事件记录不保存消息正文、凭据或内部异常栈。

## 5. Failure Injection

### 5.1 网络失败

Adapter 进入 DEGRADED，receive/send/ACK 均 fail closed。Heartbeat 将该 ChannelInstance 标记为 DEGRADED；恢复后重新连接并创建或复用安全 Session。

### 5.2 Adapter 崩溃

模拟进程不可用，健康检查为 UNHEALTHY。现有 Session 标记 FAILED，恢复生成新 Session，历史记录不删除。

### 5.3 Gateway 超时

`SandboxGateway.timeout_next()` 在 Decision 调用点抛出确定性 timeout。Conversation UoW 整体回滚，不留下 Conversation、Message 或 Decision 半成品；Inbox 保持未业务 ACK，可写 Retry Marker 后重新投递。

### 5.4 Execution UNKNOWN

Sandbox send 返回 UNKNOWN 后，Worker 创建 UNKNOWN Execution Receipt 与 `EXECUTION_UNKNOWN` Event。Execution attempt 保持 1，后续 `run_once()` 不会再次领取，符合 UNKNOWN 禁止自动重试规则。

### 5.5 ACK 失败

流程严格保持：

```text
receive → SQLite persist 成功 → source ACK 失败
                   ↓
下次 receive 重放同一 envelope
                   ↓
Inbox 指纹/sequence 判重 → source ACK 成功 → 业务处理一次
```

## 6. Recovery 验证

自动恢复均有明确触发点和有限次数：

```text
异常注入
  ↓
SessionHeartbeatScheduler.run_once()
  ↓
Instance DEGRADED / AUTH_REQUIRED
  ↓
显式 recover_instance()
  ↓
Adapter RECOVERING → CONNECTED
  ↓
旧 Session FAILED/EXPIRED 时创建新 Session
  ↓
Heartbeat HEALTHY / 继续读取持久化 Cursor
```

已验证：

- Network failure → Heartbeat UNHEALTHY → Adapter recover → 新 Session CONNECTED。
- Adapter crash → Session FAILED → recover → 新 Session CONNECTED。
- Browser disconnected → Instance DEGRADED → probe recover → 原有效 Session 恢复运行。
- Credential lease expiry → Session EXPIRED / AUTH_REQUIRED → 新 Session CONNECTED。
- ACK failure → Cursor 已持久化、source 未 ACK → 重放后无重复处理。
- Gateway timeout → Conversation 无部分状态 → Retry Marker → Gateway recover → Decision WAITING_APPROVAL。

## 7. End-to-End Sandbox Flow

通过的成功场景：

1. Sandbox customer message 写入 Adapter。
2. Channel Session 拉取 envelope，事务持久化并 source ACK。
3. Conversation Runtime 将消息发送给 Fake AI-CS Gateway。
4. Fake Gateway 返回 requires_approval Decision。
5. Human operator 显式批准并创建 Execution。
6. Worker 领取 lease，SandboxExecutionAdapter 请求 Ledger authorization。
7. Sandbox send 返回 SUCCESS Channel Receipt，不产生真实发送。
8. Worker 追加 Execution Receipt、`EXECUTION_SUCCEEDED` 和 `RECEIPT_RECORDED` Event。
9. 每个 Domain Event 均有对应 transactional Outbox 记录。

证据断言包括 Decision `WAITING_APPROVAL`、Execution `SUCCESS`、Receipt `SUCCESS`、业务 ACK cursor=1、human_approved=true、automatic_reply=false、real_channel_called=false，以及 Event/Outbox 一一对应。

## 8. 新增模块与测试

### 实现

- `src/channel_engine/channel/sandbox.py`
  - SandboxChannelAdapter
  - SandboxClock
  - SandboxDependencyProbe
  - SandboxGateway
  - SandboxExecutionAdapter
  - SandboxScenarioController
  - SandboxEventRecord / SandboxEventType
- `store_scoped_conversation_ref()` 改为有界、稳定、跨店隔离的 SHA-256 key，避免长 store/conversation id 超出 outbound contract 长度。

### 测试

- `tests/unit/test_channel_sandbox_adapter.py`
- `tests/integration/test_channel_sandbox_recovery.py`
- `tests/e2e/test_channel_sandbox_e2e.py`

Sandbox 新增测试：**10 passed**。

| 验证 | 结果 |
| --- | --- |
| Sandbox + Adapter/Session 兼容专项 | 34 passed |
| 完整项目回归 `pytest -q` | **327 passed** |
| Python `compileall` | PASS |
| `git diff --check` | PASS |

唯一 warning 为既有 Starlette TestClient/httpx 弃用提示，不影响 Sandbox 行为。

## 9. 风险与下一阶段建议

1. Sandbox 能验证协议时序和 Engine 恢复，不能证明真实 PDD payload、认证、限流或网络行为。
2. 真实 Adapter 必须复用 `receive_envelopes → persist → acknowledge` 顺序，并通过同一 contract/failure suite；不得用破坏式 receive 替代。
3. 真实 outbound transport 必须继续由 Ledger authorization 包装；Sandbox 的成功不能授权生产自动发送。
4. 当前 Scheduler 顶层线程异常仍以保持运行优先；生产前应增加不含敏感信息的 scheduler failure metric/audit。
5. UNKNOWN、cursor conflict、payload mismatch 与恢复预算耗尽均需人工 reconciliation，不能扩展为自动重发。
6. 下一阶段应只接入本地 Mock PDD Server 或录制后脱敏的合成 fixture，继续禁止真实账号。

## 10. 最终状态

`CHANNEL_SANDBOX_ADAPTER_READY`
