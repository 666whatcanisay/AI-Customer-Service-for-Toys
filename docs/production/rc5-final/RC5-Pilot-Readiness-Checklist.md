# RC5 Pilot Readiness Checklist

> 2026-08-12 更新：数据库身份、受控迁移、跨库投影重建、静默屏障备份与绿色助手离线 Gate 均 PASS。可进入真实 PDD **只读** Pilot；真实发送仍为 NO。详见 [RC5 Offline Stability Readiness Report](RC5-Offline-Stability-Readiness-Report.md)。

## 一页结论

| 项目 | 状态 | 结论 |
|---|---|---|
| 离线业务链 | PASS | Provider 到 ExecutionPrepared 全链通过 |
| AI 回复链 | PASS | Context、RAG、引用、Quality Gate 通过 |
| 自动策略 | PASS | MANUAL_CONFIRM / AUTO_LOW_RISK 可切换，高风险转人工 |
| Execution 安全链 | PASS | 权限、店铺、会话、Kill Switch、真实发送关闭 |
| 客服助手界面 | PASS | 最终绿色界面和后端状态联合验收通过 |
| 多会话/多店铺/恢复 | PASS | 黑盒覆盖 |
| Windows 部署能力 | PASS | 隔离 13/13；候选 ZIP 已冻结 |
| 数据库 | PASS | Head 0018；迁移矩阵通过 |
| 安全与证据 | PASS | Secret 扫描、Receipt 隔离、零真实副作用 |
| 文档资产 | PASS | 架构、BOM、部署、手册、Gate 已固化 |
| 真实 PDD 读取 | NOT IN SCOPE | 下一阶段 REAL_PDD_READ_READY |
| 真实人工确认对接 | NOT IN SCOPE | 下一阶段 REAL_PDD_CONFIRM_READY |
| 真实发送与 Receipt | NOT IN SCOPE | 最后阶段 REAL_PDD_SEND_READY |
| 商业签名/证书/Service/Tag | NOT IN SCOPE | 不阻塞本轮 |

## 是否具备进入 PDD Pilot 条件

**YES，但仅允许受控只读 Pilot：**

- 使用 BOM 指定最终候选 ZIP。
- 默认 `MANUAL_CONFIRM`。
- `real_send=false`，发送按钮和真实发送 Adapter 保持关闭。
- 先完成 `REAL_PDD_READ_READY`，再逐级放行。

**当前不允许真实发送 Pilot，也不能标记 `AI_CS_PRODUCTION_READY`。**

## Pilot 前必须现场登记

- [ ] Pilot 机器与网络环境矩阵
- [ ] 候选 ZIP SHA 校验
- [ ] 数据库与 Agent 数据备份 SHA
- [ ] 店铺/客服最小权限账号
- [ ] Kill Switch 负责人和回滚步骤
- [ ] 脱敏日志与证据目录
- [ ] 真实 PDD 只读测试时间窗
