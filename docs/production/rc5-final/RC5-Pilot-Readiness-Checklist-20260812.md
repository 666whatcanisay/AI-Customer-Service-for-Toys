# RC5 Pilot Readiness Checklist（2026-08-12 最终版）

| 项目 | 状态 |
|---|---|
| 离线业务链 | PASS |
| 真正多轮上下文 | PASS |
| AI 回复链 | PASS |
| MANUAL_CONFIRM | PASS |
| AUTO_LOW_RISK | PASS |
| Quality Gate 与风险边界 | PASS |
| Execution Prepared 安全链 | PASS |
| Host/Agent 恢复与幂等 | PASS |
| 测试数据清理 | PASS |
| Identity/Binding/Profile 保护 | PASS |
| 文档与验收证据 | PASS |
| 重复窗口 | ACCEPTED P2 UI LIMITATION |
| 顶部策略显示刷新 | ACCEPTED P2 UI LIMITATION |
| 人工编辑后准备执行 | NOT IN SCOPE |
| 真实 PDD 读取 | NOT IN SCOPE |
| 真实 PDD 发送 | NOT IN SCOPE |
| `REAL_PDD_AI_READY prerequisites` | YES |
| `REAL_PDD_ADAPTER_READY` | NO |
| 当前是否进入真实 PDD 只读 Pilot | YES |
| 当前是否允许真实发送 | NO |

## Pilot 强制条件

1. 初始策略保持 `MANUAL_CONFIRM`。
2. `REAL_SEND=OFF`，发送按钮和真实 Receipt 保持关闭。
3. 只验证真实店铺、会话、消息角色、商品、SKU、订单和 Cursor 的读取映射。
4. 发现未知页面结构或字段缺失时转人工，不允许 Synthetic 历史冒充真实 PDD 历史。
5. 额外蓝色登录窗口可人工关闭；不要在该窗口执行 PDD 登录。
6. UI 顶部策略显示与当前 Turn 不一致时，以当前 Turn 标签和后端 Policy revision 为准，并暂停自动策略。

