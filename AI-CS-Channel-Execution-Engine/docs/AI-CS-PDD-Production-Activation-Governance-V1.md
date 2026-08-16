# AI-CS PDD Production Activation Governance V1

## 技术摘要

生产激活治理能力已建立，最终工程状态为
`PDD_PRODUCTION_ACTIVATION_GOVERNANCE_READY`。统一 Gate Controller、不可变
Evidence Bundle、治理状态机、六场景 Synthetic Production Drill、Rollback
Governance 和离线 CLI 均已实现。

本次生产决策为 **`CONDITIONAL_READY`**：系统已具备“被批准进入 Observe Only
验证”的治理能力，但当前工作区未封版、真实 Credential/RBAC 未注入、Gateway/Session
未运行、真实 Selector evidence 未生成。因此当前仍不允许激活真实平台。

三个关键标志从模型、检查、Evidence、State 和 Drill 到最终输出始终为：

```text
real_platform_activation_allowed=false
activation_grant_issued=false
real_send_enabled=false
```

本任务没有连接 PDD、启动浏览器、等待扫码、读取客户消息或发送。

## 1. Architecture Audit：复用已有安全边界，不重复建设

| 领域 | 已有能力 | 本次复用 | 原缺口 | 主要风险 |
|---|---|---|---|---|
| Activation | 单店 Scope、顺序 Preflight、双人批准、短时授权边界 | `PDDControlledActivationPlan` 与 offline Preflight | 缺跨域生产决策 | “计划 Ready”被误解为“平台已授权” |
| Runtime | Session/Cursor/Browser/Adapter/Recovery 聚合状态 | `PDDRuntimeStatus` | 缺 Version/SHA/Contract hash 联合判定 | 运行代码与证据不一致 |
| RBAC | Operator/Supervisor/Admin、职责分离、Deny All 默认 | `RBACAuthorizer` 与 evidence snapshot | 缺生产 Gate 汇总 | 角色证据缺失时误放行 |
| Credential | reference-only Provider、opaque lease、过期检查 | `PDDCredentialActivationSnapshot` | 缺与生产决策绑定 | Cookie/Token 被复制到证据 |
| Selector | `DRAFT → DISCOVERY → VERIFIED`、Production 拒绝 synthetic | `PDDSelectorContract` | 缺统一 Platform Gate | DRAFT/synthetic 被错误激活 |
| Gateway | Versioned Contract、signed health、错误 Envelope | Gateway Contract hash 与 Gateway snapshot | 缺合同漂移阻断 | 客户端/服务端 Schema 不一致 |
| Evidence | Activation Manifest、Receipt、Event、Audit | 现有显式字段模型 | 缺跨域、不可变 Bundle | 控制证据分散、不可复核 |
| Monitoring | Runtime component status 与 reason code | `PDDRuntimeStatusMonitor` | 缺生产 Decision 映射 | 运维只看到状态，不知道是否可批准 |
| Execution | Approval、Lease、Receipt、UNKNOWN 不自动重试 | 现有 Execution safety semantics | 缺生产 Gate 汇总 | 未审批、无租约或 UNKNOWN 重试 |

本次没有修改 AI-CS、Gateway Contract 或 PDD Adapter 核心协议；新增内容位于治理
编排层及其离线工具和测试。

## 2. Production Gate Controller

统一 Gate 顺序冻结为：

```text
RUNTIME → SECURITY → CHANNEL → EXECUTION → PLATFORM
```

所有 Gate 输出 `PASS`、`WARNING` 或 `BLOCKED`：

### Runtime Gate

- 校验 System/Runtime version；
- 校验 40 位 source commit SHA；
- 重新计算 Gateway、Activation、Governance 三份 Contract hash；
- 校验 pytest、compileall、security、contract 结果；
- 检查 Runtime services、Cursor backlog、manual intervention 和 signed Gateway
  health。

### Security Gate

- Credential 必须 reference-only、不可暴露材料、可用且未过期；
- RBAC 必须提供三个不同主体的 Operator/Supervisor/Admin evidence；
- Preparation 阶段缺少真实 evidence 为 WARNING；Activation Request 阶段为 BLOCKED。

### Channel Gate

- 限制单店、单账号、单实例、单 Browser Session；
- Adapter 必须注册；
- Activation Request 要求 Adapter healthy、Session connected；
- Cursor 必须遵循 Persist → Commit → ACK，且 backlog=0。

### Execution Gate

- `approval_required=true`；
- `automatic_approval_enabled=false`；
- Lease、Receipt、failure Receipt 均为必需；
- Receipt 不可变；
- UNKNOWN 禁止自动重试；
- `execution_creation_enabled=false`。

### Platform Gate

- Production Transport 必须非 Fake、read-only、send unsupported、Dormant、未连接；
- Selector Runtime execution 必须关闭；
- Activation Request 必须有非 synthetic 的 VERIFIED Selector evidence。

判定规则：任一 BLOCKED 得到 `BLOCKED`；无 BLOCKED 但存在 WARNING 得到
`CONDITIONAL_READY`；全部 PASS 得到 `READY`。无论判定为何，Controller 都不
产生 activation authority 或平台动作。

## 3. Activation Evidence System

`PDDActivationEvidenceBundle` 包含：

- System：版本、commit、三份 Contract hash；
- Runtime：服务版本、health、PDD Runtime、signed Gateway health；
- Security：RBAC 与 Credential reference status；
- Channel：Adapter、Session、Cursor 和单实例范围；
- Execution：Approval、Lease、Receipt、UNKNOWN、Execution disabled；
- Platform：Selector 与 dormant Transport descriptor；
- Testing：pytest、compileall、security、contract 结果；
- Decision：五类 Gate、条件、允许/禁止范围；
- Bundle：内容 SHA-256 与稳定 bundle id。

Evidence Model 使用 `extra=forbid`、不可变字段和敏感材料扫描。Bundle 明确固定：

- `contains_credential_material=false`
- `contains_customer_data=false`
- `real_platform_operations=0`

当前实际离线 Evidence Bundle：
`pdd-governance-evidence-5f3ee11f8df25edfd9d9`。

## 4. Activation State Governance

治理状态图定义为：

```text
DRAFT
  ↓
PREFLIGHT
  ↓
READY_FOR_APPROVAL
  ↓
APPROVED
  ↓  requires external authority + grant
ACTIVE
  ↓
PAUSED

任一未终止状态 → REVOKED
```

每次转换产生不可变 Transition 并增加 revision。非法跳转、跳级、从 REVOKED
恢复均失败。当前 Critical Flags 被固定为 false，因此治理记录最多可以到达
`APPROVED`；任何 `APPROVED → ACTIVE` 尝试都会被明确拒绝。PAUSED/ACTIVE 路径只
定义未来治理规则，本任务没有执行或模拟真实 ACTIVE 状态。

## 5. Offline Synthetic Production Drill

六个场景全部 Fail Closed：

| 场景 | Decision | 阻断位置 | 平台操作 |
|---|---|---|---:|
| 全部 Gate 通过 | READY | 无 | 0 |
| Credential 失败 | BLOCKED | SECURITY | 0 |
| Selector 未验证 | BLOCKED | PLATFORM | 0 |
| Gateway 异常 | BLOCKED | RUNTIME | 0 |
| Session 失效 | BLOCKED | CHANNEL | 0 |
| Rollback | READY + 回滚完成 | 无 | 0 |

“全部通过”的 READY 只表示治理检查通过；Result 仍固定 activation=false、grant=false、
send=false，因此不会产生真实激活。

## 6. Rollback Governance

紧急停止顺序冻结为：

1. `STOP_EXECUTION`
2. `STOP_ADAPTER`
3. `SAVE_AUDIT`
4. `PRESERVE_RECEIPTS`

Rollback Result 固定 `history_deleted=false`，保留 Receipt、Audit 和历史状态。
Rollback 工具只验证顺序和结果语义，不调用真实 Worker、Adapter 或平台。

## 7. Security Review

已验证：

- Gate/Evidence/Drill/Rollback 服务没有 connect、login、receive、send、execute、
  activate 或 issue-grant 接口；
- Governance 模块不导入 httpx、requests、urllib、websocket、Playwright 或 Selenium；
- 四个治理 Surface 的三个 Critical Flags 都是 JSON Schema `const=false`；
- Credential material 和 Customer Data 不在 Bundle 字段中；
- 无效 CLI 输入返回 BLOCKED，且不输出技术堆栈；
- Gateway/Activation/Governance Contract hash 漂移直接阻断 Runtime Gate。

测试结果：

- Governance 专项：`22 passed`
- 全仓：`502 passed`
- Contract：`123 passed`
- Security：`17 passed`
- compileall：PASS
- 唯一 warning 是既有 Starlette TestClient/httpx 弃用提示。

## 8. Production Activation Decision

### Decision：CONDITIONAL_READY

允许范围：

- 仅在后续独立变更审批、生产 Credential/RBAC、真实 Store identity、非 synthetic
  VERIFIED Selector、signed Gateway health、connected Session 全部通过后，申请
  **Observe Only** 短时授权。

当前禁止：

- 真实平台激活；
- 客户消息读取；
- Send/Auto Reply；
- Execution creation；
- 多店；
- 退款、订单修改、支付或任何资金动作。

当前五类 Gate：

| Gate | 当前状态 | 原因 |
|---|---|---|
| Runtime | WARNING | source tree 未封版、Runtime/Gateway dormant、signed health 未检查 |
| Security | WARNING | 生产 Credential/RBAC evidence 未注入 |
| Channel | WARNING | Adapter stopped、Session disconnected |
| Execution | PASS | Approval/Lease/Receipt/UNKNOWN/disabled 边界完整 |
| Platform | WARNING | Production Selector evidence 待真实只读 Discovery |

这个 Decision 是“治理能力可用于批准流程”，不是“已批准上线”。

## 9. Next Step

下一阶段只能关闭以下条件，不得扩大授权范围：

1. 将当前工作树封版为新的受保护 commit，重跑全量/Contract/Security/compileall；
2. 从生产 Identity Provider 导出三个不同 principal 的 RBAC evidence；
3. 从 Credential Provider 导出 reference-only availability/expiry evidence；
4. 在单独获批且用户在场的任务中人工登录，核验单店 Store identity；
5. 只读生成真实 Selector evidence；DRAFT、UNKNOWN、synthetic 均停止；
6. 验证 signed Gateway health、Adapter healthy、Session connected、Cursor backlog=0；
7. 用 `ACTIVATION_REQUEST` 模式重新运行五类 Gate；
8. 即使得到 READY，仍须由独立控制面签发短时 receive-only grant。

Final Status: `PDD_PRODUCTION_ACTIVATION_GOVERNANCE_READY`
