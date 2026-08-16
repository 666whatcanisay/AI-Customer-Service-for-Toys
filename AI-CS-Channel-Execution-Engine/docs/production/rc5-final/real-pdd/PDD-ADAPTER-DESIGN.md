# PDD Adapter Design

## 目标架构

```text
PDD 已渲染页面
  → Evidence-backed ReadOnly Driver
  → PDD Workspace Snapshot
  → Observation v2.2 Mapper
  → Encrypted Durable Spool
  → ChannelAgent signed submission
  → Host durable inbox / ACK
  → CustomerContext / AI-CS / 绿色助手
```

Read Driver 类型上不提供点击、输入或发送方法。正式 Windows Agent 仍使用既有 `PDDMessageObserver → PersistAckObservationForwarder` 组合，Provider 抽象不建立第二套 Cursor。

## Fail-closed 规则

- 只允许官方 PDD HTTPS 客服路径。
- 页面、活动会话、店铺必须唯一。
- Selector 缺失、多匹配、Fingerprint 漂移、iframe/虚拟列表导致事实不完整时停止。
- CUSTOMER/OPERATOR 必须由真实 Evidence 映射；BOT/SYSTEM 只有真实出现才验收，未出现为 BLOCKED。
- 相同 message ID 内容或序号变化是冲突，不覆盖。
- 当前店铺与服务端已验证 `PDDStoreBindingV1` 不一致时停止。

## 时间保护

每次 Observer 会话最长 30 分钟，第 25 分钟发出 `PDD_OBSERVER_SESSION_WARNING`，第 30 分钟停止新扫描。已落 Spool 的 Observation 可继续等待 ACK。继续读取必须由用户重新开启一轮。

## Gate 分离

| Gate | 验证范围 |
|---|---|
| `REAL_PDD_ADAPTER_READY` | 专属工作台连接、登录/店铺识别、DOM/Selector 适配和 fail-closed 已验证 |
| `REAL_PDD_READ_READY` | 真实会话、消息、商品、SKU、订单已端到端进入 Snapshot、Observation、Spool、Host、ACK/Cursor、Replay |
| `REAL_PDD_AI_READY` | Host Context、AI-CS 与 UI 一致 |
| `REAL_PDD_CONFIRM_READY` | MANUAL_CONFIRM 生成唯一 Preparation，未发送 |
| `REAL_PDD_SEND_READY` | 独立 TEST_ONLY 单条发送与真实 Receipt |

固定依赖为 `ADAPTER → READ → AI → CONFIRM → SEND`；前置 Gate 非 PASS 时后置 Gate 不得 PASS。后置 Gate 失败不回退已通过的前置 Gate。
