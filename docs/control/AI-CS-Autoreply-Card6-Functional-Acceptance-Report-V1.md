# AI-CS Autoreply Card 6 Functional Acceptance Report V1

日期：2026-08-14

Card 6 Task Gate：`FAIL / AI_CS_AUTOREPLY_READY_NOT_ACHIEVED`

AI-CS本仓组件结论：`PASS / AI_CS_AUTOREPLY_COMPONENT_READY / SOURCE_ONLY`

协调状态：`CROSS_REPO_HANDOFF_REQUIRED / UNCOORDINATED_CANDIDATE`

后续加固（2026-08-14）：AI-CS固定规则证据现已封存精确审核资料
revision/hash/scope与完整规则快照身份。本仓组件结论仍为PASS；由于同一
Engine Turn/Evidence/Authorization/Sender/Receipt主链仍缺失，全局Gate仍为FAIL。

## 1. 验收结论

Cards 2–5已经完成AI-CS仓负责的固定回复规则治理、C→A完整快照发布、固定规则/RAG/组合Router以及统一Quality Gate和严格证据包。最终A、C与正式契约回归全部通过。

但`AI_CS_AUTOREPLY_READY`代表完整自动回复功能链，而不是仅代表回答生成。当前Engine尚未生产`ReplyTurnEnvelopeV1`，没有把`reply_evidence_bundle.v1`映射为本地严格V2包，也没有实现绑定证据哈希和最终回复哈希的`AutoPolicyAuthorizationV2`。现有RC5 `AUTO_POLICY`只能形成`real_send_enabled=false`的离线`ExecutionPreparation`，不能证明新证据链已经进入Sender和Receipt主链。

因此本卡完成了验收审计，但整链Gate必须FAIL，不能以AI-CS本仓测试全绿替代Engine集成事实。

## 2. 完整要求矩阵

| 要求 | 当前证据 | 判定 |
| --- | --- | --- |
| 固定回复规则复用既有审核、版本、IAM和审计 | Card 2；C全量191项通过 | PASS |
| C向A发布完整有效快照，失败保留上一版本 | Card 3；A/C严格类型与Receipt测试通过 | PASS |
| 4秒聚合后的严格Turn Envelope消费 | A解析和Fail Closed已完成；Engine生产者源码不存在 | FAIL |
| 固定规则优先、未命中RAG、明确拆问后组合回复 | Card 4 Router与Gateway测试通过 | PASS |
| 统一Quality Gate与确定性证据包 | Card 5定向及全量回归通过 | PASS |
| Gateway V1开放metadata兼容且冻结Schema不漂移 | 双仓Schema字节一致；raw SHA与canonical SHA不变 | PASS |
| Engine严格消费证据包并重新验证当前状态 | Engine V1解析器只保留开放metadata；`AIReplyPackage`无证据字段，运行路径不消费 | FAIL |
| `AutoPolicyAuthorizationV2`绑定消息、revision、回复哈希、证据哈希、策略、selector、许可、TTL、nonce和签名 | Engine无该类型或等价完整绑定 | FAIL |
| 自动与人工账本严格分离，自动不得伪装人工批准 | RC5存在`AUTO_POLICY`枚举；尚未接入新证据/授权V2主链 | FAIL |
| 可配置店铺限流、Kill Switch和执行前最新状态复核 | RC5有部分独立能力；未与新V2授权形成可验收的单一链路 | FAIL |
| RC5 Sender和Receipt消费同一自动授权 | 当前自动结果止于`ExecutionPreparation(real_send_enabled=false)` | FAIL |
| 单仓契约、单元、回放与汇总回归 | A、C、正式契约和定向套件全部通过 | PASS |
| 真实PDD、Pilot和Production放量 | 本任务明确不连接真实PDD | NOT IN SCOPE |

## 3. Engine只读核对事实

只读核对同级`AI-CS-Channel-Execution-Engine`当前clean工作树和HEAD `aea8c88c1f7db3d94b8352d2b27b66958d408203`，没有修改或运行其Runtime：

- AI-CS与Engine冻结Gateway Schema原始字节相等，raw SHA-256均为`fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`，canonical SHA-256均为`e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`。
- Engine `DecisionRequest`能解析并保留候选`context.ai_cs_reply_turn`，`DecisionResponse`能解析并保留`metadata.reply_evidence_bundle`；这只证明开放Map向后兼容。
- Engine生产源码中没有`ai_cs_reply_turn`、`reply_evidence_bundle`或`AutoPolicyAuthorizationV2`实现。
- Engine `CustomerContext.gateway_context()`没有生成Turn Envelope；`AIReplyPackage`没有证据字段，且继续固定`requires_human_approval=True`。
- 现有`ExecutionPreparation`固定`real_send_enabled: Literal[False]`。现有`AUTO_POLICY`资格只检查低风险、直接回答、required fields和citation范围，没有绑定A的证据包哈希、最终回复哈希、一次性nonce或签名。
- RC5机器事实仍为`RC5_OFFLINE_STABILITY_READY=PASS`、`REAL_PDD_* = NOT_VERIFIED`、`real_send_enabled=false`。这些事实不能被AI-CS文档改写。

## 4. Card 6汇总验证

执行结果：

- A全量：`213 passed, 3 skipped`；3项仍是明确opt-in的真实外部E2E。
- C全量：`194 passed`。
- 正式共享契约：`16 passed`。
- 固定规则来源证据、Router、候选契约、Gateway定向：A `76 passed`；规则治理、发布和迁移定向：C `14 passed`。
- Card 6复验器与候选契约定向：`24 passed`，覆盖严格输出、精确来源证据、合成Ready适配器、缺失适配器和候选指纹不匹配。
- 候选生成物：`export_reply_router_contract_candidates.py --check`通过，零漂移。
- Engine候选只读解析：请求和响应均PASS并保留开放扩展；本地`AIReplyPackage`证据字段检查为False。
- `git diff --check`在文档收口后重新执行。

本轮没有运行真实模型、真实PDD、浏览器发送、受控Runtime迁移或真实Receipt。历史28题RAG结果仍为`19/28`，不因Router/Quality Gate回归而改变。

## 5. 最小补救任务：Engine Autoreply V2 Integration

下一张跨仓任务必须由Engine所有者实施，AI-CS窗口不得代改Engine：

1. 从4秒Buffer的精确原消息顺序、ID、Unicode code-point范围和内容哈希生成`ReplyTurnEnvelopeV1`。
2. 严格解析并重新计算`reply_evidence_bundle.v1`，映射为本地`AIReplyPackageV2`；缺失、未知、篡改、超限、跨作用域或陈旧证据全部转人工。
3. 新增`AutoPolicyAuthorizationV2`，绑定Agent、设备、店铺、客户、会话、客户消息、decision、revision、最终回复哈希、证据哈希、质量/风险/策略版本、selector与激活许可，并使用短TTL、一次性nonce和签名。
4. 自动账本使用`Decision → PolicyAuthorization → Execution → Receipt`；不得设置或推导`human_approval_verified=true`。
5. 把Pilot限流做成版本化店铺策略，保留全局/单店Kill Switch；授权前再次检查最新客户消息、页面、输入框、selector、会话revision和知识状态。
6. 将授权接入RC5 Sender和不可变Receipt；`UNKNOWN`禁止自动重试，限流命中转人工且不得延迟补发。
7. 双仓共同运行本候选向量和新增正反例后，才选择下一个合法additive共享Contract版本；Gateway Wire 1.0和冻结Schema继续不变。
8. 完成跨仓合成/回放端到端验证后重新执行Card 6。只有全部要求PASS，才可签署`AI_CS_AUTOREPLY_READY`。

### 可执行复验入口

AI-CS已增加只读复验器：

```powershell
cd backend
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe scripts\verify_engine_autoreply_v2_readiness.py `
  --engine-root ..\..\AI-CS-Channel-Execution-Engine
```

复验器先独立核对Gateway双仓字节、冻结双哈希、Engine Git身份和当前候选清单SHA，再以`--offline-only`调用Engine所有的`scripts/verify_ai_cs_autoreply_v2.py`。Engine适配器必须输出严格`engine-autoreply-v2-acceptance.v1`候选工件，覆盖14项强制检查并声明Engine源码、Runtime、PDD和真实发送零副作用；AI-CS还会独立比较调用前后的Engine工作树指纹。

当前只读结果为`FAIL / ENGINE_ACCEPTANCE_ADAPTER_MISSING`，来源证据加固后的候选清单SHA-256为`2fbbd9d9fa1f3bded3c8ac09f6b58400cd93eda7ca5e21404c3938a543f77d4b`。这不是用“缺少测试脚本”代替功能缺口，而是为Engine实现Turn/Evidence/Authorization/Sender/Receipt后提供同一套行为复验入口。

## 6. 状态边界

- `AI_CS_AUTOREPLY_COMPONENT_READY=PASS`只表示AI-CS仓负责部分源码完成。
- `AI_CS_AUTOREPLY_READY=FAIL`，尚未形成完整自动授权、执行和Receipt链。
- `AUTO_REPLY_PILOT_READY`和`AI_CS_PRODUCTION_READY`均未验收。
- 共享Contract继续为`0.14.0 / coordinated`，候选仍在`contracts/candidates/reply-router-v1/`，本卡不冻结版本。
- 本卡没有修改Engine、连接真实PDD、创建客户数据、写入Runtime数据库或改变发送开关。
