# 《AI-CS Gateway Source Baseline Report V1》

> 日期：2026-08-05
> 需求：R012
> 保护锚点：`0b3367f85999f1dc840accf23742c290eb53746b`
> 当前分支：`release/product-reliability-hardening-v1`
> Gate：`PASS / AI_CS_GATEWAY_SOURCE_BASELINE_READY`

## 1. Gateway当前能力

### Current Capability Matrix

| 能力 | 当前实现 | MVP分类 | 证据/约束 |
| --- | --- | --- | --- |
| Gateway routes | `POST /gateway/v1/decisions`、认证`GET /gateway/v1/health` | Production Candidate | 独立router，不替换`/api/chat`；默认关闭 |
| Gateway service | 强制`context.ai_cs_scope`，调用既有scoped A answer service，六种A action映射为`SUGGEST_REPLY/NO_ACTION` | Production Candidate | 所有Decision固定`requires_approval=true`，不执行客户动作 |
| Authentication/HMAC | HMAC-SHA256 canonical string覆盖method/path/version/client/key/timestamp/nonce/request/correlation/idempotency/body hash | Production Candidate | secret至少32 bytes，错误统一且不泄漏credential |
| timestamp | 默认允许±300秒 | Production Candidate | 过期或无时区请求fail closed |
| nonce | 格式校验、默认600秒持久化防重放 | Production Candidate | SQLite事务保证单机并发claim |
| idempotency | client+route+key绑定canonical payload；同载荷回放同Decision，不同载荷409；默认保留7天 | Production Candidate（单实例MVP） | 跨重启持久化；租约owner token阻止旧执行者覆盖/删除新claim |
| ErrorEnvelope | auth/schema/version/media/body/idempotency/service/unknown route或method使用稳定非2xx envelope | Production Candidate | 模型/RAG失败不得伪装成HTTP 200 Decision |
| Health | 报告Gateway、AI readiness、model configured与`production_channel_connected=false` | Production Candidate | 当前外部Engine health adapter尚不兼容，见Deferred |
| vendor media type | 响应固定`application/vnd.ai-cs.channel-engine.gateway-v1+json` | Production Candidate | 规范media type |
| `application/json`请求兼容 | 当前Engine Decision signer使用该media type，服务端临时接受 | Experimental compatibility window | T4必须决定保留期限/弃用策略，不能变成第二套Contract |
| Decision metadata | `ai_cs_action/risk_level/warnings/required_fields/source_count/ai_request_id` | Experimental diagnostics | 位于开放metadata内；Engine不得把这些字段作为稳定业务控制输入 |

结论：Mission列出的routes、service、Authentication、HMAC、nonce、timestamp、idempotency和ErrorEnvelope均已存在。Production Candidate是“单实例、人工审批、默认关闭”的Server源码候选，不是生产部署声明。

## 2. 文件范围

### Production MVP源码候选

| 范围 | 文件/目录 | 作用 |
| --- | --- | --- |
| Gateway核心 | `backend/app/gateway/{contract,auth,store,service,routes}.py` | wire model、HMAC、防重放、幂等、映射、路由 |
| A集成胶水 | `backend/app/main.py`、`backend/app/config/settings.py`、`backend/.env.example` | router挂载、opt-in初始化、配置模板；属于R011既有Candidate，本轮只读 |
| Schema工具 | `backend/scripts/export_gateway_server_schema.py` | 从runtime model确定性导出checked-in schema；属于R011既有Candidate，本轮只读 |
| Shared contracts | `contracts/version.json`、`CHANGELOG.md`、`README.md`、`error-codes.md`、Gateway schema与compatibility说明 | contracts 0.6 additive治理 |
| Gateway测试 | `backend/tests/test_gateway_contract.py`、`backend/tests/test_gateway_server.py` | Contract/Auth/Idempotency/Error/Chat Regression |
| Shared contract测试 | `tests/contract/test_gateway_server_contract.py`及既有catalog contract test | schema覆盖与跨线兼容 |
| 治理文档 | R011/R012任务卡、Foundation报告、本报告及status/change/handoff/machine-context | 范围、证据、风险与T4输入 |

### 本轮实际变更边界

R012只修改`docs/**`。保护锚点仍是当前HEAD，Gateway Candidate仍位于dirty worktree；本报告没有把它误报为新commit、tag或已发布source baseline。未来受控提交必须把Gateway核心、A集成胶水、schema工具、contracts和测试作为一个可复核候选，不得只提交router而遗漏配置/挂载/测试。

相对保护锚点，以下禁止业务范围零差异：`frontend/**`、`extension/**`、`platform_backend/**`、`admin_web/**`、`backend/app/service/**`、`backend/app/models/**`、`backend/app/api/**`、知识库与向量目录。

## 3. Production边界

### Gateway Server负责

- 接收、严格校验和认证DecisionRequest。
- 调用既有A scoped answer能力并映射DecisionResponse。
- 只返回人工审批Decision，禁止自动执行。
- 提供认证Health与安全的readiness投影。
- 执行HMAC、timestamp、nonce replay防护。
- 提供单实例MVP的持久化Decision幂等和稳定ErrorEnvelope。

### Gateway Server不负责

- Browser、Chrome或浏览器自动化。
- PDD/其他Channel adapter、消息收取或发送。
- Execution、退款、订单、售后、工具执行或自动客户动作。
- Execution Receipt与Event ingestion。
- B客服流程或C运营流程。
- 商品权限裁决、R006客服可用状态、R009导入与商品知识生命周期。
- RAG检索、Prompt、模型和知识发布规则的重新实现。

该边界保证Gateway只是A能力的协议与安全适配层，不成为第二个Channel Engine，也不复制B/C业务所有权。

## 4. Contract状态

### contracts 0.6覆盖

| Contract对象 | 状态 | 关键约束 |
| --- | --- | --- |
| `DecisionRequest` | COVERED | `contract_version=1.0`、identity、`customer_message`、context、requested_at、unknown fields forbidden |
| `DecisionResponse` | COVERED | action/content条件、identity echo、`requires_approval=true`、gateway version、decided_at |
| `GatewayHealth` | COVERED | strict health/readiness/version/details模型 |
| `ErrorEnvelope` | COVERED | closed error codes、retryable策略、request/correlation identity、safe details |

Checked-in schema与runtime model有drift test；仓库16个schema均通过Draft 2020-12结构校验。Repository contracts为`0.6.0 additive`，Gateway wire仍为`1.0`，没有修改0.5及更早消费者语义。

### 已记录缺口

1. `context.ai_cs_scope`目前由compatibility文档和runtime `FrozenChatContext`强制，但JSON Schema中的`context`仍是通用object；T4需用外部Client/Server contract test冻结该profile，不应直接破坏通用Gateway V1。
2. HMAC headers/canonical string记录在兼容文档和代码测试中，不属于JSON body schema；T4需产出可执行的跨仓库签名向量。
3. 当前外部Engine `health_check()`仍使用未签名`GET /health`，而本Server按安全要求只支持签名`GET /gateway/v1/health`；不得在AI-CS增加匿名alias。
4. Receipt/Event不在0.6 Source MVP范围；若进入后续版本，必须另做schema/version/changelog/兼容与受影响线评审。
5. 幂等库不保存请求正文、Authorization或secret，但会保存完整DecisionResponse约7天，其中可能含客户可见建议文本；它是受治理运行时业务数据。源码未提供静态加密或备份策略，T4必须补ACL、加密/备份边界、保留清理和恢复审计。

## 5. Source Classification

### Production Candidate

- Decision/Health routes与严格四类Contract对象。
- HMAC、timestamp、nonce、body hash和header/body identity。
- `context.ai_cs_scope` fail-closed范围校验。
- 六种A action映射、人工审批和非2xx失败语义。
- 单实例SQLite nonce/idempotency、跨重启回放和租约owner保护。
- 默认关闭、secret不入Git、Gateway配置失败不阻断原A/B链路。
- Contract/Auth/Idempotency/Error/Chat Regression及schema drift tests。

### Deferred

- 生产Channel Engine连接和真实credential配置。
- 外部Engine health adapter改为签名`/gateway/v1/health`。
- TLS/mTLS、secret manager、key rotation/多key过渡、文件ACL、ingress body limit与rate limiting。
- 幂等Decision响应的静态加密、备份隔离、保留清理与恢复审计。
- 多主机/多实例共享nonce和idempotency store、灾难恢复与容量验证。
- 生产审计/指标/告警、部署脚本、灰度、回滚演练和SLO。
- Receipt、Event与Execution；它们必须另立Contract Phase。

### Experimental

- `application/json`输入兼容窗口；canonical输出仍是vendor media type。
- `DecisionResponse.metadata`中的A诊断投影；不得作为Engine稳定业务依赖。
- 任何本地mock/stub/合成provider证据；不能替代T4非生产跨仓库E2E。

## 6. 测试结果

| 验证 | 结果 | 说明 |
| --- | --- | --- |
| Gateway专项 | `24 passed` | Contract drift、六action、HMAC、timestamp、nonce、idempotency、lease owner、ErrorEnvelope、health、chat regression |
| Shared contracts | `6 passed` | contracts 0.6与既有R006 contract兼容 |
| A全量 | `133 passed, 3 skipped` | 3项为显式opt-in真实模型/真实C服务E2E，本轮未启用 |
| R006/R009定向 | `26 passed` | catalog/API/migration、knowledge publishing、product knowledge import；临时测试DB，不访问正式库 |
| JSON Schema | `16 valid` | Draft 2020-12 schema check |
| 禁止路径 | `PASS` | R006/R009、B、C、RAG核心及商品数据库业务代码相对锚点零差异 |

本轮证据属于源码、合成请求、stub answer provider与临时数据库验证。没有读取客户数据、真实知识源或正式向量，没有运行真实模型，也没有调用生产Channel Engine。

## 7. 下一步T4输入

T4建议命名为“Gateway Non-Production Integration & Deployment Readiness”，输入固定为：

1. 在独立评审后将本报告的Production Candidate文件集形成受保护commit；不得改写`0b3367…`锚点。
2. 由外部Engine owner把health改为签名`GET /gateway/v1/health`，保持Decision canonical/HMAC不变。
3. 使用非生产credential完成真实外部`AICSGatewayClient → AI-CS` Decision/Health E2E，覆盖签名向量、时间偏差、nonce replay、同key回放/冲突和服务重启。
4. 冻结单实例MVP拓扑；如需多实例，先替换为受控共享nonce/idempotency store并完成故障测试。
5. 配置TLS/私网、secret manager与轮换、ACL、ingress 64 KiB、rate limit、安全日志与告警；将含完整Decision响应的幂等库作为受治理业务数据，验证静态加密、备份隔离、7天保留清理和恢复审计。日志不得含客户完整消息、Authorization、secret、Prompt或source正文。
6. 明确`application/json`兼容窗口和metadata非依赖策略。
7. 保持Gateway默认关闭；灰度、rollback和生产连接必须另行授权。Receipt/Event继续排除，除非创建新的跨线Contract任务。

## 8. Gate结论

R012已完成当前能力审计、源码分类、Production职责冻结、contracts 0.6覆盖复核、专项/全量/业务回归和T4输入整理：

`AI_CS_GATEWAY_SOURCE_BASELINE_READY`

该状态只表示Candidate已经整理为可维护的源码基线输入；不表示已提交、已部署或已通过生产安全与联通验收。
