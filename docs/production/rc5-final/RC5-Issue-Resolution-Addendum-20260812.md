# RC5 Issue Resolution Addendum（多轮最终验收）

| 编号 | 等级 | 问题 | 处理 | 验证 | 状态 |
|---|---|---|---|---|---|
| RC5-007 | P1 | Runtime 重启后旧绿色窗口本地认证失效 | 增加一次性 Bootstrap handoff，不保存 Cookie/CSRF | Desktop/Windows 针对测试与现场恢复通过 | CLOSED |
| RC5-008 | P1 | 固定多轮验收会话未包含在最终定向清理范围 | 清理选择器同时校验固定 conversation_id、provider_id、provider_kind | 9 项历史/清理测试；现场清理 PASS | CLOSED |
| RC5-UI-001 | P2 | Agent 重启后可能额外打开蓝色登录窗口 | 已增加恢复标记与 15 秒兜底，但当前 Edge 现场仍可出现额外窗口；采用人工关闭 | 后端、原绿色窗口和保护状态不丢失 | ACCEPTED LIMITATION |
| RC5-UI-002 | P2 | 切回人工后顶部策略下拉显示可能滞后 | 不再重启现有实例；当前 Turn 与后端 Policy 为权威状态 | 后端 Revision=3、Turn=MANUAL_CONFIRM、HUMAN Preparation READY | ACCEPTED LIMITATION |

`RC5-UI-001/002` 不阻塞真实 PDD 只读 Pilot，但在允许任何真实自动发送前应重新验收。

