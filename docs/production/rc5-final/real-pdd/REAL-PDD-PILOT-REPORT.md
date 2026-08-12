# Real PDD Pilot Report

## 当前 Gate

| Gate | 状态 | 说明 |
|---|---|---|
| 运行实例保护 | PASS | 已保存版本、进程、配置、DB 与受保护状态；未关闭现有 Edge |
| `REAL_PDD_LOGIN_READY` | BLOCKED | 等待用户手工打开 PDD 工作台 |
| `REAL_PDD_STORE_READY` | BLOCKED | 等待真实页面与服务端绑定核对 |
| `REAL_PDD_READ_READY` | BLOCKED | 等待当前页面 Selector Evidence |
| `REAL_PDD_ADAPTER_READY` | BLOCKED | 软件基础完成，需真实 Observation/ACK 实证 |
| `REAL_PDD_ORDER_CONTEXT_READY` | BLOCKED | 独立 Gate，不阻塞 Adapter |
| `REAL_PDD_AI_READY` | BLOCKED | 等待手机测试消息进入正式链 |
| `REAL_PDD_CONFIRM_READY` | BLOCKED | 等待真实消息的人工确认实证 |
| `REAL_PDD_SEND_READY` | NOT RUN | 独立可选；必须另行当次确认 |
| `REAL_PDD_AUTO_SEND_READY` | NOT IN SCOPE | 本轮禁止 |

## 已完成的软件基础

- Observation v2.2 与 v2.1 向后兼容；
- REAL_PDD/Synthetic/Replay 来源隔离；
- 真实页面双向历史、20 条上限、Hash 与隐私过滤；
- message ID → 持久化单调 Sequence 回退；
- 30 分钟 Observer 会话保护；
- 精确店铺绑定投影；
- 明确消息 allowlist 的脱敏 Replay Builder；
- 五分钟、单次、目标/正文绑定的 Controlled Send Grant；
- Real Receipt 明确 transport/simulation 标志。

## 测试证据

- 相关聚焦回归：27 PASS。
- 完整单元回归：346 PASS、1 个隔离 Edge 烟测显式跳过。

真实页面 Gate 未完成前，不得把上述软件回归解释为 `REAL_PDD_READ_READY`。

