# AI-CS PDD Controlled Activation Plan V1

## 技术摘要

PDD 首次真实平台激活的工程准备包已建立，状态为
`PDD_CONTROLLED_ACTIVATION_READY`。这个状态只表示计划模型、离线检查器、
证据清单和回滚手册已经可用，不代表真实平台已经获准连接。

当前安全事实保持不变：

- `real_platform_activation_allowed=false`
- `activation_grant_issued=false`
- `real_platform_connected=false`
- `customer_messages_read=0`
- `send_operations=0`

首次激活只能申请进入 **Observe Mode**。真实发送、自动回复、订单操作和多店
扩展不在本计划授权范围内。

## 1. 激活范围冻结

`PDDActivationScope` 将一次激活限制为：

| 维度 | 固定范围 | 约束 |
|---|---:|---|
| 店铺 | 1 | 使用审批系统生成的 `store-binding-ref`，不在检查文件中手填真实店铺信息 |
| 账号 | 1 | 只保存 `account-ref` |
| Channel Instance | 1 | 不允许同一窗口创建第二实例 |
| Browser Session | 1 | 独立 Profile 对应单一 Session |
| 模式 | Observe Only | `send_enabled=false`、`automatic_login_enabled=false` |

模型通过长度为 1 的引用集合和 Literal 安全字段拒绝多店、多账号、多实例、
多 Session、自动登录和发送配置。激活计划本身不允许读取客户消息；后续真实
Observe grant 必须另行、短时、证据绑定地签发。

## 2. 激活 Gate 是严格顺序、首错即停

唯一合法顺序如下：

```text
Preflight
  ↓
Credential Check
  ↓
RBAC Check
  ↓
Selector Check
  ↓
Observation Mode
  ↓
Human Approval
  ↓
仅可申请独立的短时 Observe grant
```

任一 Gate 返回 `BLOCKED` 后，后续 Gate 标记为 `NOT_RUN`，不会继续评估或
产生任何运行时动作。

| Gate | 必须证据 | 通过条件 | 阻断后的下一步 |
|---|---|---|---|
| Preflight | 时间窗、Dormant Transport、Runtime、Gateway signed health | 位于批准时间窗；Production receive boundary 非 Fake；网络未连接；Cursor backlog=0；Gateway 健康 | 修复环境后重新完整 Preflight |
| Credential Check | reference-only 状态快照 | 引用可用、未过期、账号绑定一致、Provider 不暴露材料 | 由 Credential 管理员修复引用；不得复制 Cookie/Token |
| RBAC Check | Operator/Supervisor/Admin 身份证据 | 三个不同主体；Operator 可查看；Supervisor 可验证 Selector；Admin 可管理安全策略 | 由身份系统补齐角色；不得共享账号 |
| Selector Check | Production VERIFIED evidence | `DRAFT → DISCOVERY → VERIFIED` 完整，且证据不是 synthetic | 停止；仅做授权的只读 Discovery |
| Observation Mode | 安全策略快照 | Observe only；Kill Switch 开启；Execution/Outbound/Send/Click 均关闭；尚未采集客户消息 | 恢复安全配置后从 Preflight 重跑 |
| Human Approval | 与 Plan fingerprint 绑定的两份短时批准 | Supervisor 与 Admin 两人批准、未过期、主体不同 | 不激活；重新申请批准 |

即使六道 Gate 全部通过，`PDDControlledActivationPreflight` 也只返回
`READY_FOR_SEPARATE_ACTIVATION_AUTHORIZATION`。它固定返回：

- `activation_authorized=false`
- `activation_grant_issued=false`
- `real_platform_connected=false`
- `real_send_enabled=false`

真实 Observe grant 必须由检查器之外的受信任控制面签发，并继续满足
`PDDProductionObservationActivationGrant` 的短时、receive-only、非 synthetic
Selector evidence 等约束。

## 3. 谁批准、谁操作、谁停止

采用职责分离：

| 角色 | 责任 | 明确禁止 |
|---|---|---|
| Operator | 运行离线检查、执行人工登录步骤、观察状态、按手册停止 | 不得签发 grant、不得触发 Execution |
| Supervisor | 批准单店范围和时间窗、验证 Selector evidence、确认 Evidence 完整 | 不得代替 Admin 完成安全批准 |
| Admin | 验证 Credential/RBAC/Kill Switch，批准安全边界，负责隔离 Gateway 和关闭 Execution | 不得单人同时作为 Operator/Supervisor |

三个 principal 必须不同。最终人工批准至少包含一个 Supervisor 和一个 Admin，
且批准对象必须绑定当前 Plan fingerprint 并在激活窗口内有效。

## 4. Runtime Evidence 清单

每次 Preflight 生成不可变 `PDDActivationEvidenceManifest`，至少记录：

- Runtime overall 和 Session、Adapter、Cursor 状态；
- Cursor persisted sequence、processed sequence、backlog；
- Gateway health、Gateway Contract/Capability version 和 signed-health 结果；
- Credential、RBAC、Selector 的非敏感 evidence reference；
- 六道 Gate 的状态、原因码和检查时间；
- Plan fingerprint；
- 检查器副作用计数。

检查器副作用计数必须恒为：

```text
network_operations=0
browser_operations=0
customer_messages_read=0
send_operations=0
```

Evidence 禁止包含 Cookie、Token、Password、Authorization header、客户消息正文
或个人信息。Evidence 只引用受控系统中的对象，不复制敏感材料。

## 5. 停止与回滚顺序

回滚动作顺序在模型中不可修改：

1. `DISABLE_EXECUTION`：先阻止新 Execution 和任何发送路径；
2. `STOP_ADAPTER`：停止 Observation Adapter；
3. `STOP_SESSION`：停止 Channel/Browser Session；
4. `ISOLATE_GATEWAY`：停止该实例的新 Decision 请求，不修改 AI-CS；
5. `SEAL_EVIDENCE`：封存 Cursor、Runtime、Audit、Event 和 Receipt 证据；
6. `REQUIRE_MANUAL_VERIFICATION`：由 Supervisor 判断是否允许恢复。

以下任一条件立即进入回滚：人工停止、时间窗到期、店铺身份不匹配、Selector
UNKNOWN、Session 过期、Cursor UNKNOWN、Gateway 不健康、检测到任何发送路径。

回滚不删除 Receipt、Event 或 Audit。UNKNOWN 后禁止自动重连；恢复必须重新运行
完整 Preflight，并重新获得两人短时批准。

## 6. 离线检查工具

输入 Schema：

```powershell
.\.venv\Scripts\python.exe scripts\check_pdd_controlled_activation.py --schema
```

检查受控输入：

```powershell
.\.venv\Scripts\python.exe scripts\check_pdd_controlled_activation.py `
  --input <由受信任控制面导出的检查文件> `
  --output <Evidence 输出文件>
```

退出码：

- `0`：六道 Gate 已通过，但仍需独立签发短时 Observe grant；
- `1`：输入或 Schema 无效；
- `2`：某个 Gate 阻断，禁止激活。

工具只读取本地 JSON 并执行纯模型校验，不解析 Credential、不启动浏览器、不连接
Gateway/PDD、不签发 grant。

## 7. 首次真实运行手册

完整步骤、停止口令、恢复入口和 Evidence 签收规则见
`AI-CS-PDD-Controlled-Activation-Runbook-V1.md`。首次运行必须安排在批准的 15 分钟
至 4 小时时间窗内，并确保 Operator、Supervisor、Admin 同时在线。

## 8. 当前限制与风险

- 本任务没有真实登录，因此没有真实 Store Identity、Session 或 Selector evidence。
- 本任务没有读取消息，因此不能证明真实消息入口、DOM 稳定性或 Privacy Filter
  对真实样本的覆盖率。
- 本任务没有连接真实 Transport，因此不能证明页面/接口兼容性、限流或断网表现。
- `PDD_PRODUCTION_READINESS_UNBLOCKED` 与本次
  `PDD_CONTROLLED_ACTIVATION_READY` 都是工程准备状态，不是生产授权。
- 第一次真实 Observe 运行应只验证连接、登录、店铺匹配、页面状态和 Cursor 初始化；
  客户消息读取需使用新的变更记录和明确授权。

## 9. 下一阶段的唯一安全入口

下一阶段只能执行《首次真实运行手册》的 Preflight 和人工登录窗口：

1. 从受信任系统生成单店 Scope、Credential reference 和三个 Operator principal；
2. 运行离线检查并关闭所有 `BLOCKED`；
3. 人工登录后验证 Store identity；不匹配立即停止；
4. 完成只读 Selector Discovery，非 VERIFIED 立即停止；
5. Supervisor 与 Admin 对同一 Plan fingerprint 完成短时批准；
6. 另行签发 receive-only Observe grant；
7. 时间窗结束或出现 UNKNOWN，执行固定回滚并重新 Preflight。

Final Status: `PDD_CONTROLLED_ACTIVATION_READY`
