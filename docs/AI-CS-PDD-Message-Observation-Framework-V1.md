# 《AI-CS PDD Message Observation Framework V1》

## 技术摘要

`PDD_MESSAGE_OBSERVATION_READY` 已达到：PDD 的受控浏览器观察路径现在具备独立的 capture-only Reader、持久化与 Gateway 之前的隐私过滤、`ChannelMessageV1` 映射、重复消息恢复、延迟门禁、Session 过期门禁，以及最终停留于 `WAITING_APPROVAL` 的 AI-CS Decision 链路。

本次没有登录真实 PDD、没有读取真实客户消息、没有保存 Cookie 或凭证材料，也没有产生 Approval、Execution、Receipt、Send 或订单操作。测试仅使用合成消息、只读 CDP 边界和受控 Mock AI-CS Gateway。

验证结果：消息观察专项 13 项通过，PDD 相关回归 147 项通过，全仓回归 442 项通过。唯一告警是既有 FastAPI `TestClient` 依赖弃用提示，与本次变更无关。

## 1. 消息观察边界

新建 `PDDMessageReader` 协议，接口仅包含：

- `capture()`：捕获人工授权且 Session 有效的消息。
- `health_check()`：返回 Reader/Session 健康状态。
- `store_id`、`read_only`、`browser_write_operations`：暴露隔离与零写证明。

协议没有 `send_message()`、`approve()`、`execute()`、`click_send()` 或自动登录能力。`BrowserPDDMessageReader` 将现有 `BrowserPageObserver` 适配为此协议；后者继续负责 VERIFIED receive-only Selector、cursor、顺序、消息缺口和原始身份冲突检测。

```text
只读 Browser Page
  -> BrowserPageObserver（Selector / Cursor / Dedup）
  -> PDDMessageReader.capture（Session / Store 边界）
  -> PDDPrivacyFilter（持久化前脱敏）
  -> ChannelMessageV1（平台无关输入）
  -> ConversationService
  -> AI-CS Gateway Sandbox
  -> Decision.WAITING_APPROVAL
  -> STOP
```

`PDDObserveModeRuntime` 已切换到该消息运行时，现有真实 CDP 只读 Page Port 路径因此不会再把捕获正文直接交给 Conversation/Gateway。

## 2. 隐私过滤先于 SQLite 与 Gateway

`PDDPrivacyFilter` 在构造 `ChannelMessageV1` 之前运行，当前确定性规则覆盖：

- 姓名：带“我叫 / 姓名 / 收件人 / my name is”语义标签的姓名。
- 手机号：中国大陆手机号及常见空格、连字符格式。
- 地址：带“地址 / 收货地址”标签的地址片段。
- 支付信息：13–19 位卡号样式及银行卡号、支付账号、付款码等带标签信息。

平台 sender 不进入持久化，统一映射为 `customer`。原始捕获模型的 sender/content 被标记为不可展示，并且只允许在进程内短暂存在；脱敏结果只记录脱敏类别、次数及脱敏后内容摘要，不保存原文副本。

合成隐私用例同时把姓名、手机号、地址和卡号送入只读 CDP 观察路径。SQLite 中的 Message 与 Mock Gateway 生成的 Decision 建议均未出现原始值。

## 3. Message Mapping 与隔离规则

`PDDObservationMessageMapper` 生成冻结的 `ChannelMessageV1`：

| PDD 捕获字段 | ChannelMessageV1 | 规则 |
|---|---|---|
| `external_message_id` | `message_id` | 必填，作为幂等身份 |
| `store_id` | `store_id` | 必须等于当前 Reader 的 StoreBinding |
| `conversation_id` | `conversation_id` | 必填，后续由 Conversation Runtime 做 store scope |
| 平台 sender | `sender=customer` | 不保存平台姓名或显示名 |
| 已脱敏 content | `content` | 原始正文不得越过过滤边界 |
| 平台 timestamp | `timestamp` | 用于延迟判断和消息时间 |

Store mismatch 会以 `PDD_MESSAGE_STORE_MISMATCH` Fail Closed。相同 `external_message_id` 和相同脱敏内容返回原 Message/Decision；同一身份对应不同内容则停止并要求人工核对。

## 4. AI-CS Decision 只能停在 WAITING_APPROVAL

`PDDMessageObservationRuntime` 调用现有 `ConversationService` 与 Gateway Contract，不生成 AI 回复本身。每次成功观察后都验证：

- Decision 状态必须是 `WAITING_APPROVAL`。
- `requires_approval=true`。
- 对应 Approval 不存在。
- 对应 Execution 不存在。
- 对应 Receipt 不存在。

若 Gateway 返回结果试图越过此边界，运行时以 `PDD_MESSAGE_DECISION_NOT_WAITING_APPROVAL` 停止。观察运行时没有审批和执行方法，因此无法从该对象直接进入发送链。

## 5. Observation Evidence

每个接受或幂等恢复的消息生成内存证据：

- `message_id`：Conversation Runtime 内部 Message 标识。
- `external_message_id`：平台消息标识。
- `decision_id`：AI-CS Decision 标识。
- `trace_id`：与内部 `message_id` 相同，用于串联 Message → Decision。
- `decision_state=WAITING_APPROVAL`。
- `disposition=ACCEPTED | DUPLICATE`。
- `latency_seconds` 与 `delayed`。
- 脱敏类别与次数。
- 固定的零副作用快照。

Evidence 不含原始正文、客户姓名、手机号、地址、支付信息、Cookie、Token、密码或 credential reference。

## 6. 延迟、重复与 Session 故障

默认延迟策略为：30 秒开始标记 delayed，900 秒以上拒绝，未来时间最大容忍 30 秒。专项测试使用更小的 300 秒最大窗口验证：

- 延迟 60 秒：允许进入 Decision，同时证据标记 `delayed=true`。
- 延迟 301 秒：以 `PDD_MESSAGE_STALE` 停止，Gateway 调用为 0。
- Session `EXPIRED`：以 `PDD_MESSAGE_READER_SESSION_EXPIRED` 停止，持久化与 Gateway 调用均为 0。
- 重复消息：返回原 Message/Decision，Gateway Decision 计算仍为 1。
- 相同身份不同内容：Fail Closed，不生成第二个 Decision。

延迟阈值是 Foundation 默认值，不等于生产策略冻结；真实 Pilot 前应根据平台重连窗口和业务 SLA 单独批准。

## 7. 测试结果

| 范围 | 通过 | 失败 | 告警 | 说明 |
|---|---:|---:|---:|---|
| 消息观察专项 | 13 | 0 | 0 | 11 项新增测试，加 2 项既有 Observe Runtime 测试 |
| PDD 相关回归 | 147 | 0 | 1 | 嵌套范围；既有 FastAPI TestClient 弃用告警 |
| 全仓回归 | 442 | 0 | 1 | 嵌套范围；告警与本次变更无关 |

覆盖项包括：Reader capture-only 接口、隐私规则、Store mismatch、真实 CDP 只读接线、重复消息、身份冲突、延迟、过期消息、Session 过期、Gateway Decision、Trace Evidence、敏感字段扫描与零副作用结构。

## 8. 限制与风险

1. 没有使用真实 PDD 登录、真实 Selector、真实客户消息或生产 Gateway，因此本状态表示框架准备完成，不表示真实页面协议已经验证。
2. 自由文本姓名和地址识别是确定性 pattern-based 过滤，不能证明覆盖所有自然语言变体。真实 Pilot 前必须使用脱敏合成/审核样本扩充规则，并定义无法判定时的 Fail Closed 策略。
3. 原始 Browser Observer 为了身份冲突检测会在 Observation Store 中保存不可逆摘要，不保存正文；其保留期限和访问控制仍需生产隐私评审。
4. 真实 Gateway 是否允许经过脱敏的客户问题进入 AI-CS，仍需数据处理目的、最小化字段和留存期审批。

## 9. 下一阶段建议

1. 使用安全团队批准的脱敏合成语料扩充姓名、地址和支付信息规则，增加残留 PII 阻断测试。
2. 将 Message Observation Evidence 接入现有 Observability Event Store，只保存标识、状态、延迟与脱敏计数。
3. 在不登录真实账号的前提下，用录制且完全脱敏的 PDD 页面 fixture 验证 VERIFIED Selector 与 Message Reader 的兼容性。
4. 冻结 Pilot 的消息最大年龄、未来时间偏差和 Evidence 保留期限。
5. 真实环境仍保持 `manual_approval=true`、`auto_reply=false`、`send_disabled=true`，本阶段不进入 Approval 或 Execution。

## 10. 尚待确认的问题

- 实际 PDD 页面是否提供稳定且不含客户隐私的消息唯一标识与会话唯一标识？
- 真实消息中哪些业务字段确实是 AI-CS Decision 的必要最小输入？
- PII 无法确定是否已完全脱敏时，是整条消息阻断还是仅保留意图类别？
- Observation Evidence、身份摘要和脱敏正文的保留期限分别是多少？

---

Final Status: `PDD_MESSAGE_OBSERVATION_READY`
