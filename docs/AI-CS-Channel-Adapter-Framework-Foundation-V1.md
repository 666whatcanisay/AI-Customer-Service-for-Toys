# 《AI-CS Channel Adapter Framework Foundation V1》

| 项目 | 值 |
|---|---|
| Framework 状态 | **READY** |
| 目标模块 | `src/channel_engine/channel/` |
| 首个实现 | `FakePDDAdapter` |
| 真实平台连接 | **DISABLED** |
| 实现日期 | 2026-08-04 |
| 最终状态 | `CHANNEL_ADAPTER_FRAMEWORK_READY` |

## 1. 边界与执行链

Adapter Framework V1 建立以下入站边界：

```text
Synthetic External Channel Input
              |
              v
       ChannelAdapter
              |
              v
      NormalizedMessage
              |
              v
     ConversationService
              |
              v
       Decision Request
```

当前唯一平台形状实现是纯内存 `FakePDDAdapter`。名称中的 PDD 只表示测试数据形状，不包含拼多多 SDK、HTTP 地址、Cookie、浏览器控制、账号或真实消息能力。

出站 `send_message()` 也是显式调用的模拟端口。Execution Worker 没有绑定它；Decision、人工批准和 Fake Execution 完成后均不会自动调用渠道 Adapter。

## 2. ChannelAdapter Interface

`ChannelAdapter` 是 runtime-checkable Python Protocol，以 `channel` 作为 Registry 稳定键：

```python
class ChannelAdapter(Protocol):
    @property
    def channel(self) -> str: ...

    def receive_message(self) -> NormalizedMessage | None: ...
    def send_message(self, message: OutboundMessage) -> ChannelSendReceipt: ...
    def get_conversation(self, conversation_id: str) -> ChannelConversation | None: ...
    def health_check(self) -> AdapterHealth: ...
```

| 方法 | 输入 | 输出 | 语义 |
|---|---|---|---|
| `receive_message()` | 无 | `NormalizedMessage | None` | 读取并归一化一个入站消息；队列为空返回 `None` |
| `send_message()` | `OutboundMessage` | `ChannelSendReceipt` | 对一条携带 execution/人工批准 provenance 的消息进行显式模拟发送 |
| `get_conversation()` | 渠道 conversation ID | `ChannelConversation | None` | 查询 Adapter 已知的归一化会话元数据 |
| `health_check()` | 无 | `AdapterHealth` | 返回 Adapter 本地健康状态，不接触真实平台 |

基础异常：

- `ChannelAdapterUnavailable`：Adapter 接收或发送端口不可用；
- `ChannelConversationNotFound`：发送目标会话不存在；
- `ChannelIdempotencyConflict`：同一消息/发送幂等键绑定不同内容；
- `AdapterAlreadyRegistered`、`AdapterNotRegistered`：Registry 冲突或查找失败。

正常业务失败通过 `ChannelSendReceipt.outcome` 表达；端口不可用或契约冲突使用异常并 fail closed。

## 3. 统一消息模型

### 3.1 NormalizedMessage

所有 Conversation Runtime 入站消息统一为不可变、禁止额外字段的 `NormalizedMessage`：

| 字段 | 类型/约束 | 定义 |
|---|---|---|
| `channel` | 1–80，小写 channel key | 产生消息的 Adapter/Registry key |
| `conversation_id` | 1–255 | 外部渠道会话 ID |
| `external_message_id` | 1–255 | 渠道消息 ID；在 conversation 内用于去重 |
| `sender` | 非空，最大 255 | 外部发送者 ID；不得作为内部授权身份 |
| `content` | 非空且非全空白，最大 8000 | 归一化文本内容 |
| `timestamp` | 带时区 date-time | 外部消息发生时间 |

示例：

```json
{
  "channel": "fake-pdd",
  "conversation_id": "fake-chat-1",
  "external_message_id": "fake-message-1",
  "sender": "fake-buyer-1",
  "content": "Where is my order?",
  "timestamp": "2026-08-04T12:00:00Z"
}
```

`ChannelMessage` 保留为兼容名称，并允许 Foundation 旧调用使用 `channel_name`、`conversation_external_ref`、`text`、`received_at` 输入别名；序列化和新代码只使用统一字段名。

Conversation Runtime 使用：

- `(channel, conversation_id)` 查找/创建内部 Conversation；
- `external_message_id` 去重；
- `content/timestamp` 创建内部 Message；
- `channel/sender` 进入最小化 Decision context；
- 同 ID、异 content 立即产生冲突，不重新调用 Gateway。

### 3.2 OutboundMessage

`OutboundMessage` 包含：

- `channel`、`conversation_id`、`content`；
- `execution_id`：必须来自执行账本；
- `approved_by`：非空人工批准 provenance；
- `idempotency_key`：1–128 字符稳定发送键；
- `requested_at`：带时区创建时间。

这些字段只建立安全端口，不代表 Framework 已验证数据库中的 Approval。未来把真实 Adapter 接到 Execution Worker 前，必须在调用点复用现有 `ApprovalPolicy` 和 lease/fencing；V1 故意不做该连接。

### 3.3 ChannelSendReceipt

每次首次模拟发送返回不可变 Receipt：

| 字段 | 定义 |
|---|---|
| `receipt_id` | Adapter 生成的唯一回执 ID |
| `channel` / `conversation_id` | 发送目标 |
| `execution_id` | 对应执行 ID |
| `idempotency_key` | 回显发送幂等键 |
| `external_message_id` | 模拟成功时生成 fake ID；失败/未知为 `null` |
| `outcome` | `SUCCESS`、`FAILED`、`UNKNOWN` |
| `error_code` | SUCCESS 必须为 `null`；其他结果必须存在 |
| `details` | Fake 边界和人工 provenance |
| `recorded_at` | 回执时间 |

所有 Fake Receipt 明确记录：

- `real_platform_called=false`；
- `customer_message_sent=false`；
- `simulated_reply_recorded=true|false`。

因此 Fake `SUCCESS` 只表示内存模拟记录成功，不表示客户收到消息。

## 4. FakePDDAdapter

### 4.1 入站模拟与转换

测试控制面使用 `FakePDDInboundMessage`，映射如下：

| Fake 平台字段 | NormalizedMessage |
|---|---|
| `chat_id` | `conversation_id` |
| 固定 `fake-pdd` | `channel` |
| `message_id` | `external_message_id` |
| `buyer_id` | `sender` |
| `body` | `content` |
| `created_at` | `timestamp` |

`enqueue_customer_message()` 将归一化消息放入线程安全 FIFO，并更新内存 `ChannelConversation` 的 participant、message count 和 last message time。`receive_message()` 每次最多返回一个消息。

入站去重作用域为 `(chat_id, message_id)`：

- 同 ID、同原始 payload：返回 `False`，不重复入队或增加 message count；
- 同 ID、异 payload：抛出 `ChannelIdempotencyConflict`；
- 已消费消息再次投递仍按历史 fingerprint 去重。

### 4.2 模拟发送

`send_message()` 的处理顺序：

1. 验证 Adapter channel；
2. 验证会话存在；
3. 计算完整 `OutboundMessage` fingerprint；
4. 按 `idempotency_key` 查找首次结果；
5. 生成配置的 `SUCCESS/FAILED/UNKNOWN` Fake Receipt；
6. 将 Receipt 缓存在内存中供重放和测试审计。

同 key、同 command 返回完全相同的 Receipt 且 `send_call_count` 不增加；同 key、异 command fail closed。Fake Adapter 可注入 receive/send unavailable，用于验证异常恢复，但不会产生网络异常或真实平台副作用。

### 4.3 健康检查

Fake health 返回：

- `adapter_name=FakePDDAdapter`；
- `channel=fake-pdd`；
- `HEALTHY` 或注入的 `UNHEALTHY`；
- `real_platform_connected=false`；
- `real_pdd_connected=false` 和当前 pending message 数。

## 5. Adapter Registry

`AdapterRegistry` 使用锁保护注册表，支持：

| 操作 | 行为 |
|---|---|
| `register(adapter)` | 首次注册返回 `True`；相同对象重复注册返回 `False` |
| 重复 channel | 不同对象占用同一 channel 时抛出 `AdapterAlreadyRegistered` |
| `get(channel)` | 返回已注册 Adapter；未知 channel 抛出 `AdapterNotRegistered` |
| `discover()` | 返回排序后的 channel tuple，结果稳定 |
| `health_check()` | 返回每个 channel 的 `AdapterHealth` |

Registry 不在持锁状态下执行 Adapter health，避免慢 Adapter 阻塞注册表。某个 Adapter 的 health 抛出异常时，Registry 将该 Adapter 标为 `UNHEALTHY` 并仅记录异常类型；其他 Adapter 的健康结果不受影响，也不会泄露异常消息或凭据。

Foundation App 启动时注册一个 `fake-pdd` Adapter，并通过 `application.state.adapter_registry` 暴露给本地测试控制面。

## 6. Runtime 集成与安全规则

现有 `POST /v1/fake-channel/messages` 路径现在执行：

```text
FakeMessageRequest
  -> FakePDDInboundMessage
  -> FakePDDAdapter.enqueue_customer_message()
  -> FakePDDAdapter.receive_message()
  -> NormalizedMessage
  -> ConversationService.receive()
  -> Fake Gateway Decision WAITING_APPROVAL
```

重复 API 消息先由 Adapter 去重，再由 Conversation Repository 去重；任何层发现同 ID 异内容都会阻断。

V1 安全规则：

1. 不包含真实拼多多 URL、SDK、Cookie、token、账号或认证逻辑；
2. 不导入 Playwright、Selenium 或浏览器执行端口；
3. Fake PDD 不调用 HTTP、socket 或外部进程；
4. `send_message()` 只记录 Fake Receipt，始终声明客户未收到消息；
5. Execution Worker 使用 `FakeExecutionAdapter`，没有绑定 Channel Registry 或 FakePDD send；
6. Decision 仍强制 `requires_approval=true`；
7. Framework 不调用 AI，也不修改 AI-CS；
8. sender 是外部数据，不能替代 `approved_by` 或内部 operator 身份。

## 7. 测试结果

专项测试覆盖：

- Fake PDD 原始消息进入与六字段归一化；
- FIFO 接收和 ChannelConversation 更新；
- 入站同消息幂等、异内容冲突；
- Fake 发送 SUCCESS/FAILED/UNKNOWN Receipt；
- Receipt 不可变与发送结果幂等重放；
- 未知会话、channel 不匹配、缺少人工 provenance；
- receive/send unavailable 异常；
- Registry 注册、重复注册、发现、查找和健康检查；
- 单 Adapter health exception 隔离；
- 无时区 timestamp、空白 content 拒绝；
- FakePDD -> NormalizedMessage -> Conversation -> Decision 完整链路；
- 重复入站不重复调用 Gateway；
- Decision 和 Fake Execution 不会自动触发 FakePDD send；
- 原有 Gateway Contract、Execution Runtime、Receipt、Outbox 和 Recovery 回归。

验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_channel_adapter_framework.py tests\integration\test_channel_adapter_flow.py -q
.\.venv\Scripts\python.exe -m pytest --cov=channel_engine --cov-report=term-missing -q
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pip check
```

当前结果：

- Adapter Framework 专项：`11 passed`；
- 全量：`59 passed`，`0 failed`；
- 真实平台、浏览器、自动发送和 AI 网络调用：`0`。

## 8. Quality Gates

| Gate | 结果 |
|---|---|
| ChannelAdapter Interface | PASS |
| NormalizedMessage | PASS |
| FakePDD receive/send/receipt | PASS |
| Adapter Registry discovery/health | PASS |
| Adapter exception/idempotency tests | PASS |
| Conversation Runtime integration | PASS |
| Forbidden boundary audit | PASS |

最终状态：`CHANNEL_ADAPTER_FRAMEWORK_READY`
