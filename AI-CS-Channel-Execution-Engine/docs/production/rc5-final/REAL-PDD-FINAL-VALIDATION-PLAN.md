# REAL PDD Final Validation Plan

真实 PDD 只替换 Provider 与最后的 Send Adapter，不修改已冻结的 AI 客服核心。Gate 主状态只使用 `PASS / NOT_VERIFIED / BLOCKED / NOT_IN_SCOPE`。

## 依赖顺序

```text
REAL_PDD_ADAPTER_READY
  → REAL_PDD_READ_READY
  → REAL_PDD_AI_READY
  → REAL_PDD_CONFIRM_READY
  → REAL_PDD_SEND_READY
  → AI_CS_PRODUCTION_READY
```

`ADAPTER_READY != PASS` 时 `READ_READY` 不允许 PASS；后续 Gate 失败不撤销已有的前置证据。订单/物流/售后形成 `REAL_PDD_ORDER_CONTEXT_READY` 独立 Gate，不阻塞核心 Adapter/Read。

## Gate 1：REAL_PDD_ADAPTER_READY

人工打开专属 Edge、登录并进入唯一工作台。验证 Login/Store/DOM/iframe/虚拟列表/Selector Evidence；Snapshot 标准化为 `provider_kind=REAL_PDD`，先写 Durable Spool，再提交 Host，ACK 后推进 Cursor。缺失、多匹配、漂移、错店均 fail-closed。

## Gate 2：REAL_PDD_READ_READY

读取真实会话、消息 ID、时间、顺序、CUSTOMER/OPERATOR、商品、SKU；BOT/SYSTEM 未真实出现则 BLOCKED，不猜测。重放、刷新、重启不重不漏。真实历史只来自页面实际记录，不以 Synthetic Preparation 冒充。

首个完整会话立即生成审批后的脱敏 Replay；未经 `Fixture SHA → Approval Sidecar → Sidecar SHA Registry` 三段校验不得导出。

## Gate 3：REAL_PDD_AI_READY

真实消息进入 CustomerContext、AI-CS、Quality Gate 与绿色助手。核对店铺/客户/会话/商品/SKU/历史隔离，UI 回复 Hash 与 Decision 一致；此阶段 `REAL_SEND=false`。

## Gate 4：REAL_PDD_CONFIRM_READY

固定 `MANUAL_CONFIRM`：AI 原稿 → 人工确认 → Approval → 唯一 ExecutionPrepared。店铺、会话、客户消息、Decision 和回复 Hash 必须一致；不点击 PDD 发送按钮，不增加 Real Receipt。

## Gate 5：REAL_PDD_SEND_READY

该 Gate 独立于读取成果。第一次只允许指定测试会话、单条低风险、人工确认发送：

- 五分钟、`max_attempts=1` 的 ExecutionAuthorization/ControlledSendGrant。
- 发送前再次展示店铺、测试买家 Hash、会话和回复全文。
- 多窗口、错店、错会话、输入框非空、Selector 漂移立即停止。
- 页面出现新的真实 OPERATOR message ID 后才写 `transport_kind=REAL_PDD_BROWSER`、`simulation_only=false` Receipt。
- 超时或无法确认记 `UNKNOWN`，禁止自动重试，必须人工对账。
- 验证 Kill Switch、失败恢复和一段约定的真实长时间运行。

在人工受控发送稳定后，另行审批一次低风险 `AUTO_LOW_RISK` 真实发送验证；它是生产完成条件，但不是第一次真实发送方式。必须继续受白名单、策略 revision、Quality PASS、LOW risk、唯一会话和 Kill Switch 约束。

## 完成交付条件

只有 ADAPTER、READ、AI、CONFIRM、SEND 全部 PASS，低风险自动真实发送、Kill Switch、UNKNOWN 对账与长时间运行均通过，且没有未关闭 P0/P1，才能将 `AI_CS_PRODUCTION_READY` 改为 PASS 并正式交付。
