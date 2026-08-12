# PDD → AI-CS Data Flow

1. 用户手工登录并选中手机测试买家会话。
2. Driver 读取当前活动会话已渲染 DOM，不导航、不点击。
3. Mapper 生成唯一 `REAL_PDD` Observation v2.2，并附最近 20 条真实页面历史。
4. Agent 先加密持久化至 Spool。
5. Agent 提交 Host；Host 原子持久化后返回 ACK。
6. Agent 校验 ACK 的 Observation、摘要与 Cursor 后推进本地 Cursor。
7. Host 将页面商品、SKU、真实双向历史投影为 CustomerContext。
8. AI-CS 返回答案、依据、风险和动作；Quality Gate 决定人工或策略状态。
9. 绿色助手展示消息与 AI 建议。此时 `REAL_SEND=false`。
10. MANUAL_CONFIRM 只生成 ExecutionPreparation；真实发送是另一个独立 Gate。

所有真实历史只能来自页面消息。未确认草稿、Synthetic Preparation 和 Replay 数据不得进入 REAL_PDD 历史。

