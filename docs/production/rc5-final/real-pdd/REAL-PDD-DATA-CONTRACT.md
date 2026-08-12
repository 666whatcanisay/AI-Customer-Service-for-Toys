# REAL PDD Data Contract

## 结论

RC5 真实输入使用 `channel-agent-pdd-observation.v2.2`。Host 继续接受 v2.1，v2.2 只增加 Provider 身份与最多 20 条页面可见历史；Gateway 和 ExecutionPreparation 公共协议未修改。

契约文件：`schemas/pdd-observation-v2.2.schema.json`。

## 数据边界

| 字段 | 页面来源 | 缺失处理 |
|---|---|---|
| `platform_store_id/store_name` | 登录后客服工作台公开店铺标识/标题 | 无法唯一确认时停止读取 |
| `conversation_id/customer_reference` | 活动会话公开稳定标识，客户标识只保存 SHA-256 | 活动会话不唯一或未选中时停止 |
| `message_id/role/content/timestamp` | 当前活动会话已渲染消息 DOM | ID 或角色无法确认时 fail-closed；UNKNOWN 不进入 AI |
| `sequence` | 页面稳定序号；缺失时由稳定 message ID 映射到 Agent 持久化单调序号 | 不使用正文拼接伪造 message ID |
| `product_id/name`、`sku_id/name`、`attributes` | 当前页面商品卡、SKU/规格可见文本 | `null` 并在 Evidence 中记录 |
| `visible_history` | 当前活动会话页面实际记录，最近 20 条 | REAL_PDD 不使用 Synthetic Preparation 回退 |
| `order` | 独立 `REAL_PDD_ORDER_CONTEXT_READY` Gate | 不阻塞 READ/ADAPTER |

`provider_kind=REAL_PDD` 只能用于真实页面读取；脱敏 Replay 使用 `RECORDED_REPLAY`，历史来源标记 `SYNTHETIC`，不得冒充真实页面事实。

## v2.1 兼容

- Host 接受 v2.1 和 v2.2。
- v2.1 不允许携带 `visible_history` 非空数据。
- v2.2 强制要求 `provider_id`、`provider_kind`、`trace_id`。
- v2.2 的真实历史必须全部为 `source=REAL_PDD`；Synthetic/Replay 必须为 `source=SYNTHETIC`。

## 隐私和幂等

- 正文进入 Observation 前执行手机号、证件号和支付号脱敏。
- 客户引用只保留不可逆 Hash。
- Spool 加密且默认保留 30 分钟。
- Observation 先落 Spool，再提交 Host；只有 Host ACK 可推进 Cursor。
- Observation ID、message ID、Cursor 和内容摘要共同用于冲突与重放保护。

