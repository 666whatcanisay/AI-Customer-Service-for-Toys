# RC5 Pilot 前最小治理补丁

## 结论

本补丁只解决进入真实 PDD 只读 Pilot 前会影响判断和恢复的事实漂移，不重构 PDD Snapshot、SQLite、Gateway、ACK/Cursor 或大型模块。

唯一机器事实源是 [RC5 Offline Stability Version Matrix](RC5-Offline-Stability-Version-Matrix.json)。当前状态：

| Gate | 状态 |
|---|---|
| `RC5_OFFLINE_STABILITY_READY` | `PASS` |
| `REAL_PDD_ADAPTER_READY` | `NOT_VERIFIED` |
| `REAL_PDD_READ_READY` | `NOT_VERIFIED` |
| `REAL_PDD_AI_READY` | `NOT_VERIFIED` |
| `REAL_PDD_CONFIRM_READY` | `NOT_VERIFIED` |
| `REAL_PDD_SEND_READY` | `NOT_VERIFIED` |
| `REAL_PDD_AUTO_SEND_READY` | `NOT_IN_SCOPE` |

主 Gate 只使用 `PASS / NOT_VERIFIED / BLOCKED / NOT_IN_SCOPE`。旧版 `GateFactsV1` 中的 `may_enter_read_only_pilot`、`ai_cs_production_ready` 和 `real_send_enabled` 继续允许解析，但已标记为 deprecated/ignored：它们不参与任何判定，也不会因兼容读取而改写旧 Fixture。所有派生结论均由当前 Runtime、Storage、Source Freeze、Send Safety 和 Gate 状态重新计算。

依赖固定为：

```text
REAL_PDD_ADAPTER_READY
→ REAL_PDD_READ_READY
→ REAL_PDD_AI_READY
→ REAL_PDD_CONFIRM_READY
→ REAL_PDD_SEND_READY
```

前置 Gate 非 `PASS` 时，后续 Gate 不得写成 `PASS`。Adapter Gate 负责登录、店铺、DOM/Selector 和解析适配；Read Gate 负责真实会话、消息、商品、SKU 等端到端读取证据。

## 数据库和普通启动

- Platform 源码与受控 R027 Runtime Revision：`0019_runtime_database_identity_v1`。
- Channel Engine Runtime Storage：`1.0`。
- 普通 AI-CS 启动：`VALIDATE_ONLY`，不执行 Alembic upgrade，不初始化或同步测试知识。
- 数据库迁移：只允许受控迁移命令。
- 日常启动身份不比较整个 SQLite 文件 SHA。校验项是 DB Instance ID、Role、Environment、Schema Fingerprint、Canonical Path、Revision 和绑定 Sidecar。
- 整库 SHA 仅用于备份、迁移和 Release Evidence。
- 开发/测试 Clone 必须生成新 DB Instance ID；同一逻辑生产库的灾备 Restore 保留 DB Instance ID，并增加 Restore Generation 和 Backup Epoch。

## Runtime Catalog

Catalog 仅分类，不自动移动或删除任何 Runtime 文件：

| 分类 | 用途 | 默认保留 |
|---|---|---|
| `ACTIVE` | 当前运行实例唯一允许连接的数据库 | 运行中保留 |
| `ARCHIVE` | 正式备份和可恢复资产 | `FORMAL_90D` |
| `DO_NOT_USE` | Shadow、迁移预演、Clone、黑盒临时库 | `TRANSIENT_14D` |
| `UNCLASSIFIED` | 尚未人工确认身份的历史文件 | `MANUAL` |

对同一个 `environment_id + database_role` 必须恰好有一个 `ACTIVE`：零个或多于一个均 `BLOCKED`。ACTIVE 必须同时通过数据库内部 Identity、绑定 Sidecar 和 Canonical Path 校验。

## Pilot Preflight 的唯一判定

治理服务是 Gate 的唯一 Owner；Agent、AI-CS 和数据库只提供运行事实，绿色助手、Admin 与文档只展示结果，不自行计算 Gate。输出严格区分：

| 状态 | 含义 |
|---|---|
| `RUNTIME_HEALTH` | Host、Platform、A/RAG 的进程、端口、配置和运行身份是否一致 |
| `SOURCE_FREEZE` | Engine、AI-CS 是否对应冻结提交且工作区 CLEAN |
| `STORAGE_HEALTH` | Host、Buffer、Offline Control、Agent Spool 是否全部可用且身份/路径正确 |
| `SEND_SAFETY` | `real_send_enabled=false`，且 RealExecutionAttempt/RealSend/RealReceipt 无非预期增量 |
| `GATE_FACTS_VALIDITY` | Gate 枚举与依赖顺序是否有效 |
| `PILOT_GOVERNANCE_PREFLIGHT` | 上述五项的 fail-closed 综合结果 |

源码 DIRTY 只使 `SOURCE_FREEZE=BLOCKED`，不会误报成运行服务故障；但进入 Pilot 前 Preflight 必须仍为 `PASS`。Host 正常并不能掩盖 Buffer、Offline Control、Spool 或 A/RAG 缺失，任一必需依赖不可访问、陈旧或不一致时综合结果均为 `BLOCKED`。

`may_enter_read_only_pilot=true` 仅表示技术预检通过，不表示允许立即操作 PDD。真正开始真实 PDD Pilot 还必须满足 `CURRENT_GREEN_UI_HUMAN_ACCEPTANCE=PASS`，由用户当次人工触发，并再次确认 `real_send_enabled=false`。

## Runtime Activation 防陈旧规则

普通的“Manifest 写着 ACTIVE”不构成运行证据。每次受控启动都会原子写入 `RuntimeActivationV1`：

- Manifest 创建时间、服务启动时间、实际监听进程启动时间；
- PID、可执行路径、监听端口；
- 配置来源路径及摘要；
- DB Canonical Path、Instance ID、Environment、Role、Revision；
- DB Binding Sidecar 路径及摘要；
- Host 的 Buffer、Offline Control、Agent Spool 等数据路径；
- Host/Platform 的源码提交与干净工作树指纹；
- A/RAG 的源码提交、配置摘要、8420 端口归属、模型配置、Vector DB 路径、Collection 身份和 Ready 状态。

A/RAG 的 Ollama 瞬时驻留状态、请求统计、性能指标和 Collection Chunk 数只作为诊断事实，不作为强身份条件；正常模型卸载/重新加载不得造成身份误判。Frontend 和 Admin 不建立进程级 Activation，只在 BOM 中记录构建与 Manifest SHA。

状态命令重新读取当前 PID、进程启动时间、端口、配置和绑定后交叉验证，可识别 PID 复用、旧 Manifest、配置切换和 Sidecar 单独复制。补丁应用前已经在运行的进程不会伪造 Activation；应在下次受控重启后生成。

```powershell
$env:PYTHONPATH = (Join-Path $PWD 'src')
.\.venv\Scripts\python.exe scripts\verify_rc5_current_facts.py

# Host 与 AI-CS 均经补丁后的受控入口重启后执行：
.\scripts\windows\Get-Rc5PilotStatus.ps1
```

状态输出只读查询实际数据库，汇总 Observation、Host 持久化、Buffer、AI Trace、Decision、Approval、ExecutionPreparation 和 PDD 专用发送计数。`RealExecutionAttempt=0 / RealSend=0 / RealReceipt=0` 是真实发送安全口径；离线/Synthetic `EXECUTION_PREPARED` 可以按验收场景增长。

冻结后的受控恢复顺序固定为：双仓 CLEAN → 记录 Identity/Binding/Profile/PDD Session 保护事实 → 使用既有受管入口重启 Host、Platform、A/RAG → 不启动 PDD Edge → 生成/刷新三份 Activation → 校验 PID/SHA/配置 → 执行最终 Preflight。8420 若由未知 PID 占用，必须停止并请求人工确认，禁止自动强杀。

## 真实来源 Replay 导出门禁

真实来源 Fixture 本体保持不可变。该机制定义为“本地受控 Pilot 完整性锚点”，不是主机外或合规级不可篡改审计。流程是：

```text
脱敏 Fixture SHA
→ 自动残留扫描
→ 人工审核
→ 不可变 Approval Sidecar
→ Sidecar SHA 写入独立 Approval Registry
→ Registry 使用本地独立密钥 HMAC 锚定
```

加载真实来源 Replay 时同时校验 Fixture SHA、Sidecar 内容、Sidecar SHA/路径锚点和 Registry HMAC。只存在 `privacy_processed=true` 不代表允许导出；必须同时有 `manual_review_completed=true` 和 `replay_export_allowed=true`。Synthetic Fixture 不受该门禁影响。

```powershell
$env:PYTHONPATH = (Join-Path $PWD 'src')

.\.venv\Scripts\python.exe scripts\manage_pdd_replay_approval.py init `
  --registry .runtime\replay-approvals\registry.sqlite3 `
  --key .runtime\replay-approvals\registry.key

.\.venv\Scripts\python.exe scripts\manage_pdd_replay_approval.py approve `
  --fixture <脱敏Fixture.json> `
  --registry .runtime\replay-approvals\registry.sqlite3 `
  --key .runtime\replay-approvals\registry.key `
  --reviewer <受控操作员引用> `
  --reason <审批原因>
```

Registry、密钥、Approval Sidecar、真实 Fixture 和真实客户数据均属于 Runtime 资产，禁止进入 Git。

## 明确延后

- 三套 PDD Snapshot 模型：第一批真实 Replay 稳定后再评估收敛。
- 1000 行以上模块拆分：PDD 契约稳定后再排期。
- SQLite 更换：当前受控 Pilot 不需要。
- 自动真实发送：`NOT_IN_SCOPE`。

完成本补丁后停止外围治理，下一步直接进入 `REAL_PDD_ADAPTER_READY → REAL_PDD_READ_READY`。
