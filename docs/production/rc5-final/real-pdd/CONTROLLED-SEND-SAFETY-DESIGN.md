# Controlled Send Safety Design

Controlled Send 与 Read Adapter 独立，且不进入正式 Windows Agent source allowlist。

第一条真实发送固定为：AI 原稿 → MANUAL_CONFIRM → 用户核对完整目标与正文 → 五分钟 TEST_ONLY Grant → 单条发送。

`ControlledSendGrantV1` 绑定：店铺、测试买家 Hash、会话、客户消息、Decision、回复 SHA-256、操作员、五分钟 TTL、`max_attempts=1`。SQLite Ledger 在触发浏览器动作前消费 Grant，重启后也禁止第二次使用。

发送前重新验证：

- 当前店铺、买家、会话和客户消息精确匹配；
- Selector Evidence 仍有效；
- 输入框为空；
- 只存在唯一发送控件；
- 回复正文 Hash 未变化。

只有页面出现新的 operator message ID 且正文匹配才记录 SUCCESS。超时或动作后无法确认记为 UNKNOWN，禁止自动重试。Receipt 必须包含：

- `transport_kind=REAL_PDD_BROWSER`
- `simulation_only=false`
- `automatic_retry_allowed=false`

`AUTO_LOW_RISK → 真实发送` 为 NOT IN SCOPE。

