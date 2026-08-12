# RC5 Offline Stability Readiness Report

生成时间：2026-08-12。范围：完全离线，不登录、不读取、不操作真实 PDD。

## 结论

`RC5_OFFLINE_STABILITY_READY = YES`。

本轮解决了启动迁移、数据库身份、跨库投影恢复、备份一致性、测试知识耦合和真实业务标识脱敏等必要问题。绿色助手离线闭环仍为 Gate，且已通过：

```text
Synthetic/Replay
→ ChannelAgent
→ Host / Buffer / Cursor / ACK
→ CustomerContext
→ AI-CS / Quality Gate
→ 绿色助手展示
→ MANUAL_CONFIRM
→ ExecutionPrepared
```

允许 Synthetic/Offline `ExecutionPrepared` 随测试正常增长；本轮 `RealExecutionAttempt=0`、`RealSend=0`、`RealReceipt=0`。

## 已解决问题

| 编号 | 问题 | 修复 | 验证 |
|---|---|---|---|
| STAB-001 | 普通启动执行 Alembic | 普通启动只校验 revision/identity；迁移移到显式高风险脚本 | PASS |
| STAB-002 | 默认路径可能创建空 `platform.db` | `DATABASE_URL` 缺失即失败；生产数据库必须是绝对路径、非空 SQLite | PASS |
| STAB-003 | 数据库与环境身份不唯一 | 数据库内部 metadata + sidecar 双向绑定 | PASS |
| STAB-004 | 整库 SHA 被误作启动身份 | 启动仅比对 instance/role/environment/schema/path/revision；整库 SHA 仅作备份证据 | PASS |
| STAB-005 | Clone 与灾备 Restore 语义混淆 | Clone 新 ID；Restore/Upgrade 保留 ID；Restore 增加 generation 和 backup epoch | PASS |
| STAB-006 | 多 SQLite 中间崩溃造成 UI 缺投影 | 增加 Buffer → Decision → Assistant Snapshot 幂等 Reconciler | PASS |
| STAB-007 | 多库备份不是同一静默边界 | 停止接收新操作、等待 in-flight=0、对账投影、记录 epoch、再在线备份 | PASS |
| STAB-008 | 正式启动绑定测试知识初始化 | 测试知识导入/同步移入显式 Acceptance bootstrap | PASS |
| STAB-009 | `privacy_filtered=true` 定义过宽 | 手机、证件、支付、姓名、地址、社交号脱敏；订单/物流/售后 ID 转本地 HMAC Token | PASS |
| STAB-010 | 回归入口分散、耗时不可见 | 增加 Quick/Full 分层验收脚本和逐 Gate 耗时证据 | PASS |
| STAB-011 | 绿色助手 Gate 可能被治理工作覆盖 | 保留离线黑盒 + 前端组件 + ExecutionPrepared 安全边界验收 | PASS |

## 数据库最终状态

| 数据库 | 状态 |
|---|---|
| R027 Platform Runtime | `0019_runtime_database_identity_v1`；49 表；integrity `ok`；内部身份与 sidecar 一致 |
| Standard Platform Runtime | 从 `0013` 经克隆预演升级到 `0019`；49 表；integrity `ok`；身份已绑定 |
| Channel Engine Host | `runtime_storage_version=1.0`；identity revision 1；integrity `ok` |

两个 Platform 数据库和 Engine 数据库均在服务未监听时执行：在线备份 → 克隆预演 → 显式迁移/升级 → 双向身份校验。备份 SHA 只出现在迁移 Evidence 中，不参与日常启动判断。

## 全量验证

| Gate | 结果 |
|---|---:|
| Channel Engine | 771 PASS；1 项真实 Edge smoke 为 NOT IN SCOPE |
| AI-CS Backend | 153 PASS；3 项真实本地/外部服务 E2E 为 NOT IN SCOPE |
| Platform Backend | 180 PASS |
| Contracts | 16 PASS |
| 客服前端 | 214 PASS；typecheck/build PASS |
| Admin 前端 | 90 PASS；typecheck/build PASS |
| 绿色助手离线黑盒 | 12 PASS |
| Windows 隔离部署 | 13/13 PASS；当前安装实例修改数 0 |
| Quick stability gate | PASS，约 35 秒 |
| Full stability gate | PASS，约 155 秒 |

证据位于 `.runtime/rc5-offline-stability/`；其中运行日志和数据库备份均被 Git 忽略。

## 开发缓慢的根因与处理

| 根因 | 当前处理 | 后续策略 |
|---|---|---|
| 源码、包、运行实例缺少统一身份 | 源码 commit、候选包 SHA、安装包 SHA、运行快照分别记录 | 只有四层完全一致才标正式运行版本一致 |
| 启动兼做迁移和测试初始化 | 已拆分为普通启动、受控迁移、Acceptance bootstrap | 日常开发不再等待或意外修改数据库/知识库 |
| 每个问题都跑全部测试 | Quick/Full 分层入口 | 小改跑 Quick，冻结前跑 Full |
| 多数据库故障需要人工逐层排查 | Projection Reconciler + 同 epoch 备份清单 | 增加现场一键对账命令，不改变协议 |
| PDD 多套模型和大文件增加认知成本 | 本轮不在缺少真实 Evidence 时重构 | Replay 稳定后小步收敛，一次只改一个职责 |

## 仍未完成但不阻塞本轮

- 当前安装的 Agent 仍是旧运行产物；新候选包已生成但没有覆盖安装，以保护 Identity、Binding、Profile 和 PDD Session。
- PDD Snapshot 平行模型、大型模块拆分是维护性工作；没有真实 Replay 前不重构。
- 真实 PDD Selector、读取、角色、商品/SKU、订单、真实发送均为 `NOT IN SCOPE`。
- 代码签名、企业证书、Windows Service、正式 Release Tag 属商业发布阶段。

## Pilot Gate

| 项目 | 状态 |
|---|---|
| 离线业务/AI/质量门/策略链 | PASS |
| 数据库身份与受控迁移 | PASS |
| 跨库恢复与一致备份 | PASS |
| 绿色助手人工确认闭环 | PASS |
| Windows 候选包隔离部署 | PASS |
| 真实 PDD 读取 | NOT IN SCOPE |
| 真实 PDD 发送 | NOT IN SCOPE |
| 可进入真实 PDD 只读 Pilot | YES |
| 可进入真实发送 Pilot | NO |

