# 《PDD Browser Observation Foundation V1》

版本：`1.0`
日期：`2026-08-04`
状态：`PDD_BROWSER_OBSERVATION_READY`

## 1. 交付结论

PDD Browser Observation Foundation V1 已完成。Channel Engine 现在具备一条 selector-governed、receive-only、可恢复的浏览器消息观察链：

```text
ACTIVE BrowserSession / BrowserPageContext
  -> BrowserPageObserver
  -> ReadOnlyBrowserPageCapturePort
  -> SequencedRawBrowserMessage
  -> PDDMessageExtractor
  -> NormalizedMessage
  -> durable cursor + immutable identity fingerprint
```

本次没有登录 PDD、没有读取真实客户消息、没有连接真实店铺、没有输入文字、没有点击、没有发送，也没有修改 AI-CS。真实 PDD selector 仍然没有证据，因此 `pdd:merchant_chat:v1` 继续保持 DRAFT；Foundation 不以猜测 selector 冒充真实页面验证。

## 2. 实现清单

| 能力 | 实现 | 结果 |
| --- | --- | --- |
| Page observer lifecycle | `BrowserPageObserver` | attach、capture、heartbeat、detach |
| Read-only page boundary | `ReadOnlyBrowserPageCapturePort` | 接口中不存在输入、点击或发送方法 |
| Page attachment | `BrowserPageReadAttachment` | 固定 page context、generation、selector fingerprint |
| Page capture | `BrowserPageCapture` | cursor、sequence、page revision、message batch |
| Message extraction | `PDDMessageExtractor` | 映射为 Channel Engine `NormalizedMessage` |
| Deduplication | `BrowserObservedIdentity` | conversation + external message ID 摘要与 payload fingerprint |
| Cursor/checkpoint | `BrowserObservationCheckpoint` | revision、cursor、sequence、selector、状态和计数 |
| Durable recovery | `SqlAlchemyBrowserObservationStore` | SQLite/SQLAlchemy CAS 提交与重启恢复 |
| Offline contract testing | `FakeReadOnlyBrowserPageCapturePort` | 不访问 Chrome 或外部网络 |

主要文件：

- `src/channel_engine/browser/observer.py`
- `src/channel_engine/browser/observation_store.py`
- `src/channel_engine/storage/orm.py`
- `tests/contract/test_pdd_browser_observation_v1.py`

## 3. Page Observer

### 3.1 Attach

`BrowserPageObserver.attach()` 必须同时满足：

1. Browser Session 为 `ACTIVE`。
2. Login State 为 `AUTHENTICATED`。
3. 存在当前 `BrowserPageContext`。
4. Selector Contract 为 `VERIFIED`。
5. Contract 包含 `RECEIVE_MESSAGE` capability。
6. 已提交 cursor 的 selector contract ID/fingerprint 与当前 contract 一致。
7. Page port 声明 `read_only=true` 且 `page_write_operations=0`。

Attachment 固定以下身份：

- `attachment_ref`
- `page_context_id`
- `page_generation`
- `selector_contract_id`
- `selector_fingerprint`
- `read_only=true`

Session recovery 后 generation 变化，旧 attachment 自动失效；必须重新 attach。

### 3.2 Capture

Capture 每次重新验证 session、login、page context、selector fingerprint 和 attachment。传给 page port 的参数包括：

- committed cursor
- committed last sequence
- batch limit
- verified selector contract

返回 capture 必须回显 attachment、page generation、selector contract 和 requested cursor。任何 identity、revision 或 cursor 不一致都 fail closed，且 cursor 不前移。

### 3.3 Heartbeat

Observer heartbeat 聚合：

- Session 是否 ACTIVE。
- Login 是否过期。
- Page Context/generation 是否仍匹配。
- Selector Contract 是否仍 VERIFIED 且 fingerprint 未漂移。
- Read attachment 是否健康。
- Page write counter 是否仍为零。

状态：

```text
DETACHED -> ATTACHED
ATTACHED -> DEGRADED   page crash / login expiry / attachment unavailable
ATTACHED -> FAILED     identity conflict / message gap / selector mismatch / write detected
DEGRADED -> ATTACHED   Browser recovery 后显式 reattach
any safe state -> DETACHED
```

## 4. Message Extractor

`PDDMessageExtractor` 接受 `SequencedRawBrowserMessage`，输出冻结的 `NormalizedMessage`：

| 输出字段 | 来源 |
| --- | --- |
| `channel` | 固定为 `pdd` |
| `conversation_id` | selector-driven page observation |
| `external_message_id` | selector-driven page observation |
| `sender` | selector-driven page observation |
| `content` | selector-driven page observation |
| `timestamp` | timezone-aware observed timestamp |

`source_sequence` 和 observation mechanism 属于观察基础设施元数据，不进入 Channel Engine 六字段消息。

无法通过 `NormalizedMessage` 校验的数据会被分类为 `BROWSER_OBSERVATION_MESSAGE_INVALID`，不提交 cursor。`UNDECIDED` mechanism 被拒绝；真实 page port 不能声称 `MOCK_FEED`。

## 5. 去重与冲突

消息身份键：

```text
SHA-256(conversation_id + NUL + external_message_id)
```

Payload fingerprint 基于规范化消息的 channel、conversation、external ID、sender、content 和 timestamp 生成。

规则：

- 相同 conversation + external message ID、相同 payload、相同 source sequence：视为 duplicate，不再次输出。
- 相同 external ID 出现在不同 conversation：身份不同，可分别接收。
- 相同身份对应不同内容、sender、timestamp 或 sequence：`BROWSER_OBSERVATION_IDENTITY_REUSED`，终止当前 stream。
- 数据库存储 identity digest 和 payload fingerprint，不保存 selector locator、消息正文或 sender 明文。
- Cursor 与 fingerprint 在同一数据库事务内提交。

## 6. Cursor、Ordering 与 Missed Message Detection

Checkpoint 保存：

- opaque cursor
- monotonic `last_sequence`
- CAS revision
- selector contract ID/fingerprint
- last page generation
- accepted/duplicate count
- last capture timestamp
- sync state/error code

Ordering 规则：

1. Capture 内 source sequence 必须严格递增。
2. 首次 capture 将页面声明的 oldest visible message 作为受控 baseline。
3. baseline 建立后，新 message sequence 必须从 `last_sequence + 1` 连续增长。
4. 未知 message 出现在 committed sequence 之前时 fail closed。
5. `oldest_available_sequence > last_sequence + 1` 表示页面历史已截断，报告 missed message。
6. 接收新消息但 cursor 未变化时拒绝提交。
7. Duplicate 可以更新 source cursor，但不能改变 committed sequence。

Missed message 或顺序异常不会尝试猜测补齐，不会静默跳过，也不会推动 cursor。

### 6.1 Restart Recovery

`SqlAlchemyBrowserObservationStore` 使用两张版本化表：

- `browser_observation_checkpoints`
- `browser_observation_identities`

新 observer 实例加载相同 stream 时，会从最后提交的 cursor/sequence 继续请求。测试已验证：旧实例提交 `cursor-11 / sequence=11`，替换实例首次 capture 自动使用该位置并接收 sequence 12。

Checkpoint 使用 revision compare-and-swap；并发 observer 不能覆盖彼此的 cursor。冲突进入 fail-closed，不做 last-writer-wins。

## 7. Selector Integration

业务代码只引用 logical selector contract，不包含 CSS、XPath、DOM class 或页面文本 locator。

Page port 接收完整、不可变的 `SelectorContract`。Foundation 强制：

- Contract 必须 `VERIFIED`。
- 必须包含 `RECEIVE_MESSAGE` capability 所需 logical keys。
- Contract fingerprint 在 cursor 生命周期中固定。
- Selector 变化必须升版并执行受控 cursor migration，不能静默复用旧 cursor。
- `real_page_transport=true` 时禁止使用 `LocatorEngine.MOCK`。

当前真实 PDD contract 没有 verified locator，因此真实 page transport 会在 attach 前被阻断。后续只能基于隔离测试账号的 sanitized evidence 冻结 locator，不能把本阶段 mock locator 提升为真实 locator。

## 8. Failure 与 Recovery

| 场景 | 结果 | Cursor |
| --- | --- | --- |
| Page process crash | Observer `DEGRADED`，停止 capture | 不前移 |
| Browser recovery | 新 generation 显式 reattach | 从旧 cursor 继续 |
| Login expired | `BROWSER_LOGIN_EXPIRED`，人工接管 | 不前移 |
| Duplicate same payload | 抑制重复输出，duplicate count + 1 | 可更新 source cursor |
| Duplicate changed payload | Stream `FAILED` | 不前移 |
| Sequence gap/history truncated | Stream `FAILED` | 不前移 |
| Selector drift/version mismatch | Attach/capture 拒绝 | 不前移 |
| Page revision changed mid-capture | Capture 拒绝 | 不前移 |
| Port reports page write | Stream `FAILED` | 不前移 |
| Store CAS conflict | Stream `FAILED` | 不覆盖其他 writer |

恢复 page crash 时，`BrowserSessionManager` 先重建 Browser Page Context 并增加 generation，Observer 再释放旧 attachment、绑定新 context，并加载持久化 cursor。

## 9. 安全边界

- Page capture interface 不存在 type、fill、click、send 或 evaluate-write 方法。
- 观察模式固定为 `RECEIVE_ONLY`。
- 新代码没有真实 PDD domain、CSS 或 XPath 常量。
- 测试数据全部使用 synthetic conversation/message/customer。
- Checkpoint 表不保存消息正文、sender、credential、Cookie、token 或 secret。
- Identity 使用不可逆摘要，payload 只保存 fingerprint。
- 本阶段没有 outbound adapter，也不调用既有 `ControlledOutboundBrowserExecutor`。
- AI-CS、Gateway Contract、Decision 和 Execution 代码均未修改。

## 10. 测试结果

新增 6 个 contract test，覆盖：

1. attach/capture/heartbeat/detach 生命周期与六字段 normalization。
2. duplicate 抑制和相同 ID 不同内容 fail closed。
3. SQLite cursor 重启恢复与 missed message detection。
4. Page crash 阻断、Browser recovery、新 generation reattach。
5. Login expiry 阻断和人工接管状态。
6. Real page boundary 拒绝 mock selector contract。

验证结果：

```text
Browser observation targeted tests: 6 passed
Full regression suite:               195 passed, 1 existing warning
compileall:                          passed
pip check:                           passed
Forbidden-operation scan:            no match
```

唯一 warning 是既存 FastAPI TestClient 的 Starlette/httpx 弃用提示，与 Browser Observation 无关。

## 11. 当前限制与下一阶段条件

本交付是 observation foundation，不宣称已验证真实 PDD DOM：

- 真实页面读取 transport 尚不能启用，因为没有 VERIFIED PDD locator evidence。
- Source sequence/cursor 的真实 PDD 提取规则仍需隔离 staging 实验确认。
- 初次 attach 只能把最旧可见消息作为 baseline；若要证明更早历史完整性，需要平台侧稳定 cursor/API 或人工基线审计。
- Observation checkpoint 与 Conversation Runtime 尚不是同一事务；端到端 exactly-once handoff 需要后续 durable inbox/ack 设计。
- 长时间滚动、虚拟列表、iframe/shadow DOM、页面改版和多 tab 行为仍需 synthetic/sanitized fixture 验证。

后续实验必须继续 receive-only，使用专用测试账号和合成消息；在 selector/cursor 证据冻结前，不得接触真实客户或启用发送能力。

## 12. Quality Gates

| Gate | 结果 |
| --- | --- |
| BrowserPageObserver lifecycle | PASS |
| NormalizedMessage 六字段兼容 | PASS |
| Conversation + external ID 去重 | PASS |
| 相同 ID 不同内容 fail closed | PASS |
| Durable cursor restart recovery | PASS |
| Ordering/missed message detection | PASS |
| Selector Contract 无硬编码 locator | PASS |
| Page crash/login expiry 阻断 | PASS |
| 自动发送/输入/点击边界 | PASS |

Final Status: `PDD_BROWSER_OBSERVATION_READY`
