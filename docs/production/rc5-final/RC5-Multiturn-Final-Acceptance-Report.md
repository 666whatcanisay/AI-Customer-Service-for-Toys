# RC5 真正多轮 AI 客服最终验收报告

验收日期：2026-08-12  
固定会话：`rc5-multiturn-acceptance-20260812-01`  
Provider：`rc5-multiturn-codex-customer`

## 最终结论

RC5 离线多轮客服主链已经通过。系统在不读取、不登录、不操作真实 PDD 的条件下，完成了：

`Synthetic Provider → ChannelAgent → Host → Buffer/Cursor/ACK → CustomerContext → AI-CS → Quality Gate → MANUAL_CONFIRM/AUTO_LOW_RISK → EXECUTION_PREPARED`

最终状态：

- `REAL_PDD_AI_READY prerequisites = YES`
- `REAL_PDD_ADAPTER_READY = NO`
- `可进入真实 PDD 受控只读 Pilot = YES`
- `真实发送 Pilot = NO`
- `AI_CS_PRODUCTION_READY = NO`

## 最后一轮人工确认事实

第 12 轮在 `AUTO_LOW_RISK → MANUAL_CONFIRM` 后继续同一会话：

| 字段 | 结果 |
|---|---|
| Conversation revision | `12` |
| Policy | `MANUAL_CONFIRM` |
| Policy revision | `3` |
| Decision | `decision-7727b9846dfa4eefb611b4aacc75a249` |
| Quality Gate | `PASS` |
| Preparation | `execution-preparation:ad028149573480f391511996924b54407f24faf762fb74e26ef9de88b42eb78d` |
| Preparation state | `READY` |
| Authorization | `HUMAN` |
| Real send | `false` |
| External side effect | `false` |
| Execution / Send / Real Receipt | `0 / 0 / 0` |

上下文审计共传入 17 条历史，包含 `HUMAN`、`AUTO_POLICY` 与 `SYNTHETIC` 来源；策略切换没有重置 Conversation revision，也没有丢失已获准历史。

## 最终 Gate

| 项目 | 状态 | 证据结论 |
|---|---|---|
| Synthetic 基线清理 | PASS | 首轮前固定会话不存在，Sequence 从 1 开始 |
| 真正多轮上下文 | PASS | 人工、自动、边界、高风险和切回人工均在同一会话完成 |
| 上下文来源审计 | PASS | sender、source、ID、Hash、时间、Scope、Cursor、Sequence 均留证 |
| HUMAN 优先于 AUTO_POLICY | PASS | 冲突夹具只保留 HUMAN |
| 20 条截断与去重 | PASS | 自动化覆盖排序、截断边界、内容去重 |
| 上下文污染隔离 | PASS | 多店、客户、会话、订单隔离自动化通过 |
| 多轮人工确认 | PASS | 第 1、2、12 轮生成 HUMAN Preparation |
| AUTO_LOW_RISK 低风险准备 | PASS | 低风险 Direct Answer 生成唯一 AUTO_POLICY Preparation |
| 自动准备用户视角一致性 | PASS | 顾客问题、AI 内容、风险、Quality、Preparation 与后端一致 |
| 库存/物流边界转人工 | PASS | REQUIRE_LOOKUP/BLOCKED，无 AUTO_POLICY Preparation |
| 价格优惠边界转人工 | PASS | 未承诺优惠，无 AUTO_POLICY Preparation |
| 高风险拦截 | PASS | TRANSFER_HUMAN/BLOCKED，无自动准备 |
| Agent/Host 恢复与幂等 | PASS | 恢复同一状态，重复 Cursor 未新增 Decision/Preparation |
| 策略切换历史连续性 | PASS | Revision 2→3，历史保留，第 12 轮停在人工确认 |
| 测试结束数据清理 | PASS | 固定会话及投影全部清除，安全计数保持 0 |
| HUMAN_EDIT_PREPARATION_GATE | NOT IN SCOPE | 未修改公共 ExecutionPreparation 协议 |
| 真实 PDD 读取与发送 | NOT IN SCOPE | 本轮从未接触真实 PDD |
| `REAL_PDD_AI_READY prerequisites` | YES | 离线 AI 主链和安全 Gate 具备进入只读 Pilot 的条件 |
| `REAL_PDD_ADAPTER_READY` | NO | 必须由真实只读 Pilot 验证 PDD 页面数据来源 |
| 可进入真实 PDD 只读 Pilot | YES | 仅允许 MANUAL_CONFIRM、REAL_SEND=OFF |

## 回归与清理

- Channel Engine 最终回归：`748 PASS / 1 SKIP`；Skip 是显式隔离 Edge smoke，不属于本轮。
- 既有 RC5 黑盒：`35/35 PASS`。
- 清理前固定会话：12 Observation、79 Assistant Event、12 Buffer Message、12 Buffer Turn、12 Decision、7 Preparation、72 Trace Step、12 Context Audit。
- 清理后上述固定会话记录均为 0。
- 清理前后：Offline Receipt、Real Receipt Success、Execution、Execution Receipt、ChannelAgent Receipt 均为 0。
- Identity、Device Binding、PDD Profile reference 和 Profile Hash 清理前后保持一致。

## 已接受的非阻塞 UI 限制

| 编号 | 现象 | 影响与处置 |
|---|---|---|
| RC5-UI-001 | Agent 重启后可能额外打开蓝色登录窗口 | 后端和原绿色窗口状态不丢失；人工关闭额外窗口。用户已接受，不阻塞只读 Pilot |
| RC5-UI-002 | 后端切回 MANUAL_CONFIRM 后，顶部模式下拉可能仍显示旧 AUTO_LOW_RISK | 当前 Turn 标签、Decision、Preparation 均为 MANUAL_CONFIRM；以当前 Turn 和后端为准。真实发送始终关闭 |

这两项不影响离线 AI 链、人工确认安全门或真实发送关闭，但在正式商业发布前应改善桌面窗口复用和策略状态刷新体验。

## 原始证据

- `.runtime/rc5-multiturn-acceptance-20260812-01/live/turn-12.json`
- `.runtime/rc5-multiturn-acceptance-20260812-01/live/turn-12-post-human-confirm.json`
- `.runtime/rc5-multiturn-acceptance-20260812-01/evidence/ui-turn-12-human-execution-prepared.png`
- `.runtime/rc5-multiturn-acceptance-20260812-01/evidence/ui-auto-policy-turn-11.png`
- `.runtime/rc5-multiturn-acceptance-20260812-01/cleanup-final-dry-run.json`
- `.runtime/rc5-multiturn-acceptance-20260812-01/cleanup-final-result.json`
- `.runtime/rc5-multiturn-acceptance-20260812-01/cleanup-backup-20260812-1358/`
- `.runtime/rc5-multiturn-acceptance-20260812-01/final-engine-regression.xml`

