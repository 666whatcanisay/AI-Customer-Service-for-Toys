# 《AI-CS Channel Engine Execution Runtime Foundation V1》

| 项目 | 值 |
|---|---|
| Runtime 状态 | **READY** |
| 依赖 Gateway Contract | `AI-CS Channel Engine Gateway Contract V1 / 1.0` |
| 实现日期 | 2026-08-04 |
| 执行 Adapter | `FakeExecutionAdapter` only |
| Event Publisher | `FakeEventPublisher` only |
| 最终状态 | `CHANNEL_ENGINE_EXECUTION_RUNTIME_READY` |

## 1. 运行时边界

Execution Runtime V1 将原来的同步“批准并立即执行”拆分为持久队列和独立 Worker：

```text
Decision WAITING_APPROVAL
        |
        | human approval
        v
Decision APPROVED + Approval APPROVED + Execution PENDING
        |                         (same DB transaction)
        v
Execution Worker atomic claim
        |
        v
Execution RUNNING + Lease + EXECUTION_STARTED Event/Outbox
        |
        v
FakeExecutionAdapter
        |
        +-------- SUCCESS
        +-------- FAILED
        +-------- UNKNOWN / exception / network uncertainty
        |
        v
Terminal Execution + immutable Receipt + Events + Outbox
        |                         (same DB transaction)
        v
Fake Outbox Publisher
```

本版本只实现运行时基础能力，不启用真实渠道。`SUCCESS` 仅表示 Fake Adapter 模拟成功，绝不表示客户消息已经发送。

明确禁止：

- 拼多多或任何真实平台连接；
- 浏览器自动化；
- 自动发送客户消息；
- 真实 AI-CS Gateway；
- 退款、订单修改或资金操作。

## 2. Worker 设计

### 2.1 Execution Queue

`executions` 表本身是持久 Execution Queue，不使用易丢失的进程内队列：

| 字段 | 用途 |
|---|---|
| `execution_id` | Queue item 与 Execution Ledger 的稳定 ID |
| `decision_id` / `approval_id` | 绑定已人工批准的决策和批准记录，数据库中均为一对一 |
| `state` | `PENDING`、`RUNNING`、`SUCCESS`、`FAILED`、`UNKNOWN` |
| `idempotency_key` | `execute-{decision_id}`，全局唯一 |
| `attempt` | 成功领取次数；新任务为 0，首次领取原子加到 1 |
| `lease_owner` / `lease_token` | 当前 Worker 与本次领取的 fencing identity |
| `lease_expires_at` | 租约失效时间 |
| `started_at` / `completed_at` | 执行生命周期时间 |
| `error_code` | 终态机器错误码 |

批准接口执行一个事务：

1. 将 Decision 从 `WAITING_APPROVAL` 转为 `APPROVED`；
2. 追加 `Approval(APPROVED)`；
3. 创建 `Execution(PENDING, attempt=0)`；
4. 追加 `DECISION_APPROVED` Event 与对应 Outbox；
5. 提交后返回 `202` 和 `ExecutionEnqueued`。

批准事务不调用 Adapter。相同 Decision 的重复批准返回已有 Approval/Execution；数据库唯一约束和并发冲突回读共同保证只创建一个持久任务。

### 2.2 Worker Loop

`ExecutionWorker` 提供三个执行入口：

- `run_once()`：最多领取并处理一个任务；无任务返回 `None`；
- `run_until_idle(max_items)`：有界清空当前可领取任务；
- `run_forever(stop_event, poll_interval_seconds)`：支持优雅停止的轮询循环。

Foundation Web 进程只构造 Worker，不自动启动后台线程。部署时应由独立 Worker 进程调用 `run_forever`；测试和本地控制面使用 `run_once/run_until_idle`。这避免 Web 多实例隐式创建不可控后台任务。

每次处理流程：

1. 原子领取 `PENDING -> RUNNING`；
2. 写入 lease owner/token/expiry，`attempt += 1`；
3. 在同一事务追加 `EXECUTION_STARTED` Event/Outbox；
4. 执行前续租并重新加载 Decision/Approval；
5. 再次执行 `ApprovalPolicy`；
6. 在数据库事务外调用 Fake Adapter；
7. 以 lease token 做条件更新，写入终态、Receipt 和两个 Event/Outbox。

Policy 不通过时不调用 Adapter，Execution 以 `FAILED` 和 Receipt 完成。

## 3. Lease 机制

### 3.1 原子领取

领取使用条件更新：

```text
UPDATE executions
SET state=RUNNING,
    lease_owner=:worker,
    lease_token=:unique_token,
    lease_expires_at=:expiry,
    attempt=attempt+1
WHERE execution_id=:candidate
  AND state=PENDING
```

只有 `rowcount=1` 的 Worker 获得任务。即使多个 Worker 同时读到同一 candidate，也只有一个能完成 `PENDING -> RUNNING`；其他 Worker 不得调用 Adapter。

SQLite 配置 `busy_timeout=5000` 和 WAL，以支持 Foundation 的多线程领取测试。领取索引为 `(state, created_at)`。

### 3.2 Fencing 与续租

- `worker_id` 标识 Worker 实例；每次领取生成唯一 `lease_token`。
- 续租必须同时匹配 `execution_id + RUNNING + worker_id + lease_token`，且旧 lease 尚未过期。
- 终态提交使用相同条件，并要求 `lease_expires_at > now`。
- 旧 Worker 即使在 lease 失效后恢复，也不能覆盖新状态或追加第二个 Receipt。
- 默认 lease 为 30 秒，配置项为 `CHANNEL_ENGINE_EXECUTION_LEASE_SECONDS`。

V1 Fake Adapter 是本地、短时调用，Worker 在调用前续租。未来真实 Adapter 若允许长任务，必须增加周期 heartbeat，且 Adapter timeout 必须小于 lease；该扩展不得改变 `UNKNOWN` 的禁止重试规则。

## 4. Execution 流程与 Fake Adapter

### 4.1 状态机

```text
PENDING -> RUNNING -> SUCCESS
                   -> FAILED
                   -> UNKNOWN
```

三个终态都不可重新进入 `PENDING/RUNNING`。`UNKNOWN` 必须人工核对，状态机继续执行 `assert_not_automatic_retry`。

### 4.2 FakeExecutionAdapter

Fake Adapter 支持确定性配置：

| 配置/结果 | Execution | Receipt | error_code |
|---|---|---|---|
| `SUCCESS` | `SUCCESS` | `SUCCESS` | `null` |
| `FAILED` | `FAILED` | `FAILED` | `FAKE_ADAPTER_FAILED` |
| `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `FAKE_ADAPTER_UNKNOWN` |
| 模拟网络不确定 | `UNKNOWN` | `UNKNOWN` | `ADAPTER_NETWORK_UNKNOWN` |
| 未分类 Adapter Exception | `UNKNOWN` | `UNKNOWN` | `ADAPTER_EXCEPTION_UNKNOWN` |

Adapter 明确记录：

- `mode=FAKE`；
- `real_channel_called=false`；
- `customer_message_sent=false`。

Adapter 以 `ExecutionCommand.idempotency_key` 缓存首次结果：同 key、同 command 返回原结果且不增加调用次数；同 key、异 command 抛出幂等冲突。Execution Worker 本身不会自动重新领取终态任务。

异常被保守归类为 `UNKNOWN`，因为运行时不能仅凭异常证明外部副作用没有发生。虽然 Foundation Fake Adapter 不产生真实副作用，这条规则为未来 Adapter 保留安全语义。

## 5. Receipt 设计

所有已经开始的 Execution 最终都必须产生一个 Receipt：

- Worker 正常完成：在终态事务中追加 Receipt；
- Adapter 返回 `FAILED/UNKNOWN`：追加对应 Receipt；
- 网络异常或未知 Exception：追加 `UNKNOWN` Receipt；
- Worker 崩溃：lease 到期后由 Recovery 追加 `UNKNOWN` Receipt。

Receipt 的不可变约束有两层：

1. `execution_receipts.execution_id` 数据库唯一；
2. Repository 在追加前显式拒绝已有 execution receipt。

Receipt 与 `EXECUTION_SUCCEEDED/FAILED/UNKNOWN`、`RECEIPT_RECORDED` 事件及其 Transactional Outbox 在同一数据库事务提交。任何一步失败，终态、Receipt、Event 和 Outbox 一起回滚，不会出现“终态无回执”。

Receipt `details` 记录 worker、attempt、error code 和 Fake 安全标记，但不得存放认证材料或客户敏感正文。

`to_gateway_execution_receipt()` 将 Ledger 中的 Execution + Receipt 映射为已冻结的 Gateway `ExecutionReceipt`：补齐 `decision_id`、`attempt`、`idempotency_key=receipt_id`、条件 `error` 和 `reconciliation_required`，并处理 SQLite 取回时间的 UTC 归一化。映射只生成可验证 payload，不执行网络发送。

## 6. Outbox Publisher

### 6.1 状态与领取

Transactional Outbox 使用以下内部状态：

```text
PENDING -> PROCESSING -> PUBLISHED
                      -> PENDING (retry scheduled)
                      -> FAILED  (retry budget exhausted)
```

Outbox 保存的 `payload` 是已冻结 Gateway Contract V1 的 wire `Event`，而不是内部 Domain Event：它显式包含 `contract_version=1.0`、`source=CHANNEL_ENGINE` 和 `causation_id`。Publisher 在发布前再次使用 Gateway `Event` 模型验证；既有 Foundation 产生的旧形状 payload 会在内存中规范化为 V1 Event 后再交给 Fake Publisher，无法规范化的记录进入失败重试而不会被静默发布。

新增运行时字段：

| 字段 | 用途 |
|---|---|
| `attempt_count` | 发布领取次数 |
| `next_attempt_at` | 下一次允许领取时间 |
| `lease_owner` / `lease_token` / `lease_expires_at` | Publisher 领取租约 |
| `published_at` | 成功发布时间 |
| `last_error` | 最后一次安全截断的错误文本 |

Publisher 使用与 Execution 类似的条件领取。过期的 `PROCESSING` 可以被其他 Publisher 接管，因为事件传输是 at-least-once，消费者必须按冻结 Event Contract 的 `event_id` 去重。

### 6.2 Fake Publisher 与重试

`FakeEventPublisher` 只写入内存，不访问网络。它支持按 event 注入前 N 次失败，并按 `event_id` 幂等：

- 同 event ID、同内容不会重复发布；
- 同 event ID、异内容产生冲突；
- `published_events` 仅保留一个事实。

默认发布策略：

- 最大 5 次尝试；
- 指数退避：`1s, 2s, 4s, 8s...`；
- 最大单次退避 5 分钟；
- 每次失败释放 publisher lease；
- 达到预算后进入 `FAILED`，等待人工检查，不进行无限重试。

配置项：`CHANNEL_ENGINE_OUTBOX_PUBLISHER_ID`、`CHANNEL_ENGINE_OUTBOX_MAX_ATTEMPTS`。

## 7. Recovery

### 7.1 Execution Recovery

`ExecutionRecovery.recover_expired()` 扫描 lease 已过期的 `RUNNING`：

1. 使用 `execution_id + RUNNING + lease_token + expired` 条件更新；
2. 原子转为 `UNKNOWN`，清除 lease，写入 `WORKER_LEASE_EXPIRED`；
3. 追加 `UNKNOWN` Receipt；
4. 追加 `EXECUTION_UNKNOWN`、`RECEIPT_RECORDED` 和 Outbox；
5. 以后任何 Worker 都不能再次领取该 Execution。

不尝试判断 Worker 在 Adapter 调用前还是调用后崩溃；无法证明无副作用时统一选择 `UNKNOWN`，这是防止重复发送的关键规则。

### 7.2 故障矩阵

| 故障 | 恢复结果 | 自动重试真实执行 |
|---|---|:---:|
| 批准事务崩溃 | Approval/Execution/Event 一起回滚，或全部提交 | 否；重新提交相同批准请求 |
| Worker 领取前崩溃 | Execution 保持 `PENDING`，其他 Worker 可领取 | 可领取，因为 Adapter 尚未开始 |
| Worker 领取后崩溃 | lease 到期后 `UNKNOWN` + Receipt | **禁止** |
| Adapter 网络中断 | 立即 `UNKNOWN` + Receipt | **禁止** |
| Adapter 明确 `FAILED` | `FAILED` + Receipt | V1 不自动重试 |
| Adapter 明确 `UNKNOWN` | `UNKNOWN` + Receipt | **禁止** |
| Worker 终态事务失败 | lease 保持 `RUNNING`，到期后 Recovery 置 `UNKNOWN` | **禁止** |
| Outbox 发布失败 | 按 event ID、退避策略重试 | 允许，仅重试事件传输 |
| Outbox Publisher 崩溃 | lease 到期后接管，可能重复投递 | 允许，消费者按 `event_id` 去重 |

Execution 的副作用重试与 Outbox 的无副作用事件重投是两个不同语义，禁止混用。

## 8. API 行为变化

`POST /v1/decisions/{decision_id}/approve` 现在返回：

- HTTP `202 Accepted`；
- `ExecutionEnqueued`；
- `execution_state=PENDING`。

该接口不会调用 Adapter。Worker 完成后，Execution/Receipt 通过 Repository 查询。拒绝接口不创建 Execution，也不会触发 Worker。

Gateway Contract V1 未修改；本阶段没有添加真实 Gateway endpoint 或网络客户端。

## 9. Schema 升级与运行配置

`create_schema()` 对既有 Foundation SQLite 数据库执行只增不删的安全升级：

- 为 `executions` 增加 lease 字段；
- 为 `transactional_outbox` 增加 attempt、next-attempt 和 lease 字段；
- 使用 `CREATE INDEX IF NOT EXISTS` 创建领取索引；
- 不删除、不重命名、不覆盖既有业务记录。

运行时配置：

| 环境变量 | 默认值 |
|---|---|
| `CHANNEL_ENGINE_WORKER_ID` | `foundation-execution-worker` |
| `CHANNEL_ENGINE_EXECUTION_LEASE_SECONDS` | `30` |
| `CHANNEL_ENGINE_OUTBOX_PUBLISHER_ID` | `foundation-outbox-publisher` |
| `CHANNEL_ENGINE_OUTBOX_MAX_ATTEMPTS` | `5` |

## 10. 测试结果

运行时专项测试覆盖：

- 批准入队及顺序/并发幂等；
- Worker loop 清空队列；
- 8 个并发 Worker 对同一 Execution 只调用一次 Adapter；
- lease 领取、续租、过期和 fencing；
- Fake Adapter 幂等与同 key 异 command 冲突；
- `SUCCESS`、`FAILED`、`UNKNOWN` 三种 Receipt；
- Receipt 不可变和一个 Execution 一个 Receipt；
- Worker 崩溃后的 lease recovery；
- 网络不确定性转 `UNKNOWN` 且不重新入队；
- Outbox 指数退避、成功重试、重试预算耗尽；
- Outbox Publisher 崩溃后的过期 lease 接管；
- 既有 Foundation SQLite schema 的只增升级及重复升级幂等；
- 原有 Gateway Contract、状态机、API 和 Foundation 集成回归。

验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_execution_runtime.py -q
.\.venv\Scripts\python.exe -m pytest --cov=channel_engine --cov-report=term-missing -q
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pip check
```

当前结果：

- Runtime 专项：`15 passed`；
- 全量：`48 passed`，`0 failed`；
- 真实平台/浏览器/AI-CS 网络调用：`0`。

## 11. Quality Gates

| Gate | 结果 |
|---|---|
| Execution Queue / Worker Loop | PASS |
| Atomic Lease / Concurrent Worker | PASS |
| Fake Adapter SUCCESS/FAILED/UNKNOWN | PASS |
| Immutable Receipt / Event / Outbox transaction | PASS |
| Outbox Publisher retry/recovery | PASS |
| Worker crash/network/UNKNOWN recovery | PASS |
| Forbidden boundary audit | PASS |

最终状态：`CHANNEL_ENGINE_EXECUTION_RUNTIME_READY`
