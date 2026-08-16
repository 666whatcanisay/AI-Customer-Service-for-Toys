# 《AI-CS PDD Adapter Discovery Framework V1》

- 版本：V1 / `discovery_framework_version=1.0`
- 完成日期：2026-08-04
- 最终状态：`PDD_ADAPTER_DISCOVERY_READY`
- 环境边界：Fake Observation Port、合成元数据、内存 Observation Store；没有真实 PDD、登录、客户数据或写操作。

## 1. 完成结论

已建立 PDD 真实渠道接入前的 observe-only Discovery Framework。框架可以记录经过脱敏的页面、DOM、Selector 候选、截图、网络和 Session 元数据，并提供只接受合成测试数据的 `ChannelMessageV1` 映射预览。

Discovery 组合根没有 `send_message`、`reply`、`click`、`login`、Execution 或 Receipt 接口；Selector Contract 固定为 identity-only `DRAFT`，不能激活，也不会进入 Conversation Runtime。

## 2. Discovery 架构

```text
Injected Existing Browser/Page Context
              ↓ read-only
PDDDiscoveryObservationPort
              ↓ sanitized metadata only
PDDDiscoveryAdapter
  ├─ capture_metadata()
  ├─ observe_only()
  └─ health_check()
              ↓
PDDDiscoveryObservation
  ├─ Page metadata
  ├─ DOM metadata
  ├─ non-executable selector candidates
  ├─ screenshot metadata
  ├─ network aggregate metadata
  ├─ Browser/Login/ChannelSession states
  └─ message candidate metadata
              ↓
PDDDiscoveryObservationStore (V1 in-memory)
```

核心端口：

```python
class PDDDiscoveryObservationPort(Protocol):
    @property
    def port_name(self) -> str: ...

    def capture_metadata(self) -> PDDDiscoveryCapture: ...
    def health_check(self) -> PDDDiscoveryPortHealth: ...
```

端口故意不包含 navigation、evaluate mutation、input、click、send 或 login 方法。未来真实只读实现必须注入已有、人工建立的 Browser Session；Discovery Adapter 本身不启动登录流程。

### 生命周期

```text
READY → OBSERVING → READY
          ↓ capture failure
       DEGRADED
          ↓ successful explicit retry
        READY
```

同一 Adapter 不允许并发 capture。失败只记录固定错误码 `PDD_DISCOVERY_CAPTURE_FAILED`，不展示技术栈或页面数据。

## 3. Browser 观察

### 3.1 Page metadata

记录：

- 去除 query、fragment 和 userinfo 的 HTTP(S) page URL；
- `page_title=[REDACTED]`；
- page title SHA-256 digest 与长度；
- page revision digest。

框架不保存原始 title。URL 含 username、password、query 或 fragment 时模型直接拒绝，避免把 token/cursor 等参数写入 Evidence。

### 3.2 DOM metadata

仅记录：

- element、iframe、shadow root、text node 数量；
- 去重后的 attribute name；
- DOM revision digest。

不记录 HTML、DOM text、attribute value、input value、客户名称或聊天正文。

### 3.3 Selector candidate

候选模型只保存：

- logical `SelectorKey`；
- locator engine hint；
- structural fingerprint；
- observed match count；
- LOW/MEDIUM/HIGH confidence。

候选不保存可执行 locator。Discovery 模型结构性拒绝：

- `COMPOSER`
- `SEND_CONTROL`
- `SEND_CONFIRMATION`

因此本阶段只能发现登录、店铺身份和消息读取方向的候选元数据，不能发现或测试写 selector。

### 3.4 Screenshot metadata

只保存：

- 是否捕获；
- width/height；
- image digest；
- 是否完成 redaction；
- `bytes_retained=false`。

若标记已捕获但没有 redaction、尺寸或 digest，模型拒绝。Framework 不接收图片 bytes、文件路径或 screenshot reference。

### 3.5 Network behavior metadata

只允许聚合统计：

- request count；
- WebSocket upgrade count；
- origin（禁止 path/query/fragment/userinfo）；
- HTTP method 集合；
- resource type 集合；
- 1xx–5xx response class count。

固定安全字段：

```text
headers_captured = false
bodies_captured  = false
cookies_captured = false
```

该模型只能帮助判断“存在何类网络行为”，不能读取 request/response body、header、Cookie 或推断真实 PDD 私有协议。

## 4. Selector 流程

每次 `observe_only()` 都附带：

```text
platform     = pdd
page         = merchant_chat
version      = v1
state        = DRAFT
capabilities = []
bindings     = []
verified_at  = null
```

Selector candidates 与 Selector Contract 分离。候选出现不会修改 Contract、添加 binding 或进入 DISCOVERY/VERIFIED。

```text
本任务：DRAFT + candidate metadata

后续单独授权：
DRAFT → DISCOVERY → evidence collection → probe

未来独立 Gate：
DISCOVERY → VERIFIED
```

当前 DRAFT 可以注册到 `SelectorRegistry`，但 `active(pdd, merchant_chat)` 必须失败。框架不调用 `SelectorDiscoveryWorkflow.verify()`。

## 5. Message Observation 与 Mapping

### 5.1 观察模型

真实候选只保存元数据：

- message/conversation identity digest 是否存在；
- sender category；
- content 是否存在及长度；
- timestamp 是否存在、是否含时区；
- 是否为 synthetic test data。

不保存 message content、customer identity、conversation display name 或原始平台 payload。

### 5.2 ChannelMessageV1 映射预览

`PDDDiscoveryMessageMapper` 只接受 `SyntheticPDDMessageEvidence(synthetic_test_data=true)`：

```text
synthetic PDD evidence
        ↓
ChannelMessageV1 preview
  channel = pdd
  store/conversation/message = synthetic identifiers
  sender = customer
        ↓
runtime_eligible = false
```

所有 preview 固定携带 blockers：

- `DISCOVERY_OBSERVE_ONLY`
- `SELECTOR_CONTRACT_DRAFT`
- `MAPPING_CONTRACT_DRAFT`

Preview 不写 Transactional Inbox、不调用 ConversationService、不请求 AI-CS，也不创建 Decision/Execution。它只验证未来 Mapping Contract 与 `ChannelMessageV1` 的字段兼容性。

## 6. Session Observation

`PDDDiscoverySessionMetadata` 记录：

- browser session/page context ID；
- browser generation；
- BrowserSessionState；
- BrowserLoginState；
- ChannelSessionStatus；
- page availability。

固定安全状态：

```text
automatic_login_performed      = false
credential_material_captured   = false
write_capability_enabled       = false
```

模型不包含 Cookie、token、password、credential value 或 Browser profile path。登录状态只观察，不触发自动登录；AUTH_REQUIRED/EXPIRED 只能交由未来人工流程处理。

## 7. Security Boundary

### 7.1 结构性禁止

`PDDDiscoveryAdapter` 与 `FakePDDDiscoveryObservationPort` 均不存在：

- `send_message()`
- `reply()`
- `click()`
- `login()`
- Execution Adapter
- Browser Action Port

Health 固定输出：

```text
mode                     = DISCOVERY_OBSERVE_ONLY
runtime_delivery_enabled = false
send_enabled             = false
reply_enabled            = false
click_enabled            = false
automatic_login_enabled  = false
real_platform_connected  = false
```

### 7.2 数据最小化

- page title 和 DOM/page revision 使用 digest；
- Selector candidate 不含 locator；
- screenshot bytes 不保留；
- network header/body/cookie 永不捕获；
- message candidate 不含正文；
- Observation Store 只接收通过 strict/extra-forbid 模型验证的数据。

### 7.3 当前运行边界

- Fake Port 的 `real_platform_call_count=0`；
- `write_action_count=0`；
- Framework 没有真实 PDD origin 配置；
- 测试 URL、Session 和消息均为 synthetic fixture；
- 没有启动 Chrome、Playwright、CDP 或 WebSocket client。

## 8. 测试结果

新增：

- `tests/unit/test_pdd_adapter_discovery.py`
- `tests/integration/test_pdd_adapter_discovery_safety.py`

覆盖：

1. `capture_metadata()` 只返回元数据，不写 Observation Store；
2. `observe_only()` 追加不可变 Observation；
3. Selector 始终 DRAFT、无 bindings/capabilities、不可激活；
4. URL query/token、未脱敏 screenshot、Cookie capture 和写 selector 被拒绝；
5. 合成 Message Mapping Preview 与 ChannelMessageV1 兼容但不可投递；
6. capture failure 进入 DEGRADED；
7. Discovery 模式无 send/reply/click 方法；
8. Discovery 前后 Conversation、Message、Decision、Approval、Execution、Receipt、Event、Outbox 均为零；
9. Fake Port write/real-platform call 均为零。

结果：

```text
PDD Discovery new tests:             5 passed
Discovery/Browser/Session compatibility: 30 passed
Full repository regression:          332 passed, 1 warning
Python compileall:                    PASS
git diff --check:                     PASS
```

唯一 warning 为项目既有 Starlette TestClient/httpx 弃用提示，与 Discovery Framework 无关。

## 9. 当前限制与风险

1. V1 Observation Store 是内存实现；持久 Evidence Store 需要独立的数据保留、加密和删除策略评审。
2. Framework 证明“端口形状不会写”，不能证明未来真实 Browser Port 内部没有副作用；真实实现必须接受独立代码审计和 browser action deny test。
3. Page URL path 仍需未来端口执行动态 ID 脱敏；query/fragment/userinfo 已在模型层禁止。
4. Network aggregate 不能证明真实消息来自 DOM、WebSocket 或 API，不能据此选择 PDD transport。
5. Selector fingerprint/candidate 不是可执行 locator，不具备 VERIFIED 能力。
6. Message Mapping Preview 只适用于 synthetic fixture，不能处理真实客户消息。

## 10. 下一步真实 Adapter 计划

### Step 1：离线 Real-Port Contract

- 建立 Fake Browser metadata collector；
- 参数化复用当前 Discovery security tests；
- 增加 path redaction、capture budget 和 evidence retention policy；
- 仍不连接 PDD。

### Step 2：受控人工登录、只读元数据

需要新的显式授权和专用测试店铺：

- 使用独立 Chrome profile；
- 由人工完成登录；
- 只观察 login/page/store identity metadata；
- screenshot 默认关闭；
- network 仅聚合 origin/method/resource/status，不捕获 header/body/cookie；
- Selector 保持 DRAFT 或进入 DISCOVERY，不得 VERIFIED。

### Step 3：合成消息 Observation

- 只使用测试人员发送的专用合成消息；
- 确认 message/conversation/store/timestamp 字段证据；
- 建立 Mapping Contract DISCOVERY candidate；
- 验证 duplicate、ordering、restart recovery；
- 不进入 AI-CS，不发送回复。

### Step 4：Observe-only Adapter

Mapping/Selector 通过独立验证 Gate 后，PDDChannelAdapterV1 才可接入 Session Runtime 的 `receive_envelopes → persist → source ACK`。Send capability 继续为 false。

### Step 5：受控发送

不属于 Discovery 任务。必须另行完成真实 transport 证明、Approval/lease、安全 Gate、限流、Kill Switch 和单次专用测试消息审批。

## 11. 最终状态

`PDD_ADAPTER_DISCOVERY_READY`
