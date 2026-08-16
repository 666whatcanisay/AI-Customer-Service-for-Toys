# AI-CS PDD Adapter Observe Mode V1 完成报告

## 技术结论

PDD 真实接入前的只读 Observation Mode 已完成。新运行时建立了人工登录等待、Session 状态检测、登录后店铺身份发现、`ChannelInstance` 生成、DOM 元数据采集和消息入口存在性探测；没有暴露自动登录、点击、回复、审批或执行接口。

新增专项测试 **10 passed**，PDD/Browser/Session 回归 **164 passed**，全仓回归 **431 passed**。数据库与端口证据均为 `Execution=0`、`Receipt=0`、`Send=0`。本次没有实际登录 PDD、没有读取客户消息、没有连接真实店铺；交付状态表示真实只读端口的安全组合基础已经就绪，而不是声明真实页面已完成验证。

## 1. Observation Mode 与高级消息 Observe Runtime 明确隔离

仓库原有高级 Observe Runtime 会使用 VERIFIED receive-only Selector 读取消息并生成 WAITING_APPROVAL Decision。本任务没有复用该链路，而是新增更早阶段的 `PDDObservationModeRuntime`：

```text
人工登录
   ↓
Session 状态检测
   ↓
只读店铺身份发现
   ↓
ChannelInstance（内存态）
   ↓
DOM metadata + 消息入口存在性
   ↓
DRAFT Selector Evidence
```

该路径不接 Conversation、Gateway、Approval、Execution、Receipt 或 Outbox，因此不会因为观察到页面而意外进入客服执行链。

## 2. 人工登录状态机只检测，不执行登录

状态冻结为：

```text
AUTH_REQUIRED
      ↓ begin_human_login_wait
WAITING_USER
      ↓ check_session + authenticated page
CONNECTED
      ↓ login expiry
EXPIRED
      ↓ begin_human_login_wait
WAITING_USER
```

`start()` 和 `check_session()` 只读取 `PDDObservationBrowserSession`。运行时没有账号、密码、扫码、导航或表单输入方法。Session 未进入 CONNECTED 时，店铺发现直接返回 `PDD_OBSERVATION_STORE_REQUIRES_LOGIN`，真实端口不会被调用。

## 3. 店铺身份必须来自已登录只读端口

`PDDObservationPort` 是真实平台只读边界，默认要求 `real_platform_source=true`。Fake port 只有显式 `allow_synthetic_test_port=true` 才能进入测试组合，避免测试实现误配到真实运行。

登录确认后，端口返回 `PDDObservedStoreIdentity`。模型拒绝 `placeholder`、`unknown`、`todo` 等占位身份；运行时据此生成：

- `platform=pdd`
- `store_id=observed identity`
- `status=CONNECTED`
- `adapter_type=pdd-observation-mode.v1`

本阶段只生成内存 `ChannelInstance`，不把 ChannelInstance、ChannelSession 或 credential reference 写入 SQLite。

## 4. 消息观察止于“入口存在”，不读取消息

`PDDMessageEntryProbe` 只包含：页面是否可用、入口是否存在、候选数量、观察时间和固定安全声明。模型没有以下字段：

- message_id
- conversation_id
- sender
- content
- payload

DOM Capture 只允许页面 URL（移除 query/fragment）、结构计数、属性名、revision digest、网络 origin/方法/状态分类和 selector candidate fingerprint。Observation Mode 进一步拒绝 message candidate 数据和 screenshot bytes；网络 headers、bodies、cookies 均由已有模型固定为 false。

## 5. Selector 始终保持 DRAFT

每次页面观察只生成 identity-only `pdd:merchant_chat:v1` DRAFT Contract：

- `state=DRAFT`
- `bindings=()`
- `capabilities=frozenset()`
- `verified_at=null`

测试将该 Contract 注册到 `SelectorRegistry` 后，`active("pdd", "merchant_chat")` 仍返回 unavailable。Observation Mode 没有 promote、verify 或 activate 操作，也不会把结构 fingerprint 解释为可执行 CSS/XPath。

## 6. Credential 与日志安全

运行时仅接受已有 `CredentialReference` 模型；`cookie=`、`token=`、`password=`、`secret=`、Authorization 和 Bearer 等嵌入式材料会被拒绝。Credential reference 仅在内存用于建立边界，不进入 Observation Evidence、Audit Event 或 SQLite。

Audit Event 只记录 action、状态、reason code、时间，以及可选的 store identity SHA-256。它不记录店铺名称、credential reference、页面正文、客户消息、Cookie、Token 或 Password。

## 7. 零副作用证据

| 受控对象 | 结果 |
|---|---:|
| Execution rows | 0 |
| Receipt rows | 0 |
| Send operations | 0 |
| Approval rows | 0 |
| Event rows | 0 |
| Outbox rows | 0 |
| ChannelInstance persistence rows | 0 |
| ChannelSession persistence rows | 0 |
| Browser write operations | 0 |

运行时与端口均没有 `send_message`、`reply`、`click`、`approve` 或 `execute` 方法。任何端口报告 page write、send、automatic login 或 credential material persisted，构造或运行检查立即 fail closed 为 `PDD_OBSERVATION_PORT_UNSAFE`。

## 8. 测试结果

| 测试层 | 结果 |
|---|---:|
| 新增 Integration / Contract / Security | 10 passed |
| PDD / Browser / Session 回归 | 164 passed，1 warning |
| 全仓回归 | 431 passed，1 warning |

唯一 warning 是既有 Starlette TestClient 对 httpx 的第三方弃用提示，与 PDD Observation Mode 无关。

专项覆盖：人工登录状态机、未登录店铺发现阻断、店铺身份与 ChannelInstance、消息入口最小化、DRAFT Selector 不可激活、Session 过期、日志脱敏、真实端口默认门禁、page write fail closed、credential secret material 拒绝。

## 9. 方法与适用范围

测试全部使用合成 Browser Session、合成店铺身份及元数据级 Fake Port；没有调用 Chrome、CDP、PDD API 或真实账号。这个方法证明的是接口与状态机的安全属性、数据最小化和零副作用，不证明当前真实 PDD DOM、登录标识、店铺字段或消息入口位置。

真实环境验证必须由人工启动独立 Chrome Profile 和扫码登录，再将获得授权的 read-only port 接入同一协议。Selector 在本任务之后仍是 DRAFT；首次页面观察只能收集候选证据，不能直接转为 VERIFIED 或激活。

## 10. 限制、风险与下一步

- 尚未验证真实 PDD 页面结构、登录状态标识、店铺身份来源或消息入口候选。
- 真实平台可能使用 iframe、shadow DOM 或前端路由；元数据采集必须继续限制 origin、大小和字段。
- 店铺身份来源需要在实际页面/API 上证明唯一性与稳定性，不能人工填写 store_id。
- 下一阶段只应执行一次人工登录的 observe-only discovery：先确认 store identity，再记录 DOM metadata 与低置信 selector candidates。
- 在任何 Selector 进入 VERIFIED 前，继续保持 Conversation、Decision、Execution 和 Send 全部未接线。

## 11. 待确认问题

- 真实店铺身份优先来源是页面 bootstrap metadata、只读 API 响应还是可见 DOM？
- 消息入口候选如何在不读取正文的前提下稳定识别？
- 真实观察证据的保存期限、访问角色和删除策略由谁负责？

Final Status: `PDD_OBSERVATION_MODE_READY`
