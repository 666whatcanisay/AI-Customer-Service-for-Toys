# RC5 Pilot Readiness Checklist

| 项目 | 状态 | 依据 / 下一步 |
|---|---|---|
| 离线业务链 | PASS | Synthetic/Replay → ExecutionPrepared；黑盒 35/35 |
| AI 回复链 | PASS | Context、RAG、Citation、Quality Gate |
| MANUAL_CONFIRM | PASS | Decision → Approval → HUMAN Preparation |
| AUTO_LOW_RISK | PASS | 仅低风险自动准备；真实发送关闭 |
| Execution 安全门 | PASS | 授权、店铺、会话、过期、Kill Switch |
| Windows 部署 | PASS | 隔离部署 13/13；当前候选包已覆盖安装 |
| 源码→包→安装实例 | PASS | 三段一致性均为 `true` |
| 版本与 BOM | PASS | `rc5-release-bom.json` v4 |
| 数据库与启动 | PASS | Migration `0019`；普通启动 validate-only |
| 当前绿色 UI 人工验收 | PASS | Decision/Approval/ExecutionPrepared 与零真实副作用证据已归档 |
| 真实发送安全 | PASS | `real_send_enabled=false`，本轮未调用真实执行路径 |
| 真实 PDD 页面结构发现 | PASS | 官方工作台及核心页面结构已确认 |
| 真实 PDD Adapter | NOT_VERIFIED | 下一次真实 Pilot 完成 Selector、ID 映射、Observation、Spool 与 ACK |
| 真实 PDD Read | NOT_VERIFIED | Adapter PASS 后验证真实会话、消息、商品与 SKU |
| 真实 PDD AI | NOT_VERIFIED | 需手机测试消息 |
| 真实 PDD Confirm | NOT_VERIFIED | 需真实会话 MANUAL_CONFIRM |
| 真实 PDD Send | NOT_VERIFIED | 最后独立 Gate |
| 真实 PDD Auto Send | NOT_IN_SCOPE | 不允许首轮真实 Pilot 开启 |

## Gate 决策

```text
RC5_OFFLINE_STABILITY_READY = PASS
CURRENT_GREEN_UI_HUMAN_ACCEPTANCE = PASS
RC5_FINAL_READY = PASS

REAL_PDD_PAGE_STRUCTURE_DISCOVERY = PASS
REAL_PDD_ADAPTER_READY = NOT_VERIFIED
REAL_PDD_READ_READY = NOT_VERIFIED
REAL_PDD_AI_READY = NOT_VERIFIED
REAL_PDD_CONFIRM_READY = NOT_VERIFIED
REAL_PDD_SEND_READY = NOT_VERIFIED

AI_CS_PRODUCTION_READY = BLOCKED
real_send_enabled = false
```

## 进入下一次真实 Pilot 前

- [ ] 用户人工恢复/确认 PDD 登录和目标店铺。
- [ ] `real_send_enabled=false`。
- [ ] 只启动 30 分钟只读 Observer，不进入发送。
- [ ] 首先解决活动会话 selector 歧义并保存脱敏证据。
- [ ] 取得一个完整真实测试会话后立即生成脱敏 Replay。
- [ ] 验证 Observation 先落 Spool、Host ACK 后再推进 Cursor。

上述真实 Gate 未通过前，不得宣告 `AI_CS_PRODUCTION_READY`。
