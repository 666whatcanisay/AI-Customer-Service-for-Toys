# Real PDD Issue Resolution Report

| 编号 | 问题 | 等级 | 处理 | 验证 |
|---|---|---:|---|---|
| RPDD-001 | REAL_PDD Provider 为禁用占位 | P0 | 实现有界、来源校验的只读 Provider；正式运行仍复用 Spool/ACK 链 | PASS |
| RPDD-002 | Observation 无真实双向历史 | P0 | 新增 v2.2 `visible_history`，最多20条，Host 使用页面 OPERATOR 记录 | PASS |
| RPDD-003 | DOM 无稳定 Sequence 时可能重复/漏读 | P0 | 按稳定 message ID 持久化单调 Sequence，冲突 fail-closed | PASS |
| RPDD-004 | Observer 可无限运行 | P0 | 第25分钟预警，第30分钟停止新扫描 | PASS |
| RPDD-005 | Replay 可能保留真实标识 | P0 | 单会话、显式消息 allowlist、标识替换、敏感文本扫描 | PASS |
| RPDD-006 | Controlled Send 缺少独立短时授权 | P0 | 新增五分钟、单次、目标和内容 Hash 绑定的持久 Grant Ledger | PASS |
| RPDD-007 | 真实 Receipt 与模拟 Receipt 语义不够明确 | P0 | 新增 `REAL_PDD_BROWSER` 与 `simulation_only=false` | PASS |
| RPDD-008 | 真实 Selector/角色/商品字段仍未知 | P0 | 不猜测；保留为真实页面 Gate BLOCKED | BLOCKED |

