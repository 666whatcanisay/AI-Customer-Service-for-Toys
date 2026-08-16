# AI-CS Channel Engine Integration Validation Report V1

## 技术摘要

冻结后的 Gateway Contract V1 已在 AI-CS 与 Channel Engine 两个独立 Python 运行时之间完成协议兼容验证，结论为 **PASS**。两仓导出的 schema version 均为 `1.0`，规范化 JSON SHA-256 均为 `e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`，原始 schema 文件也逐字节一致。跨进程 loopback HTTP 验证覆盖 HMAC、签名 health、Decision Request/Response、Error Envelope、幂等、401、403、timeout 和 invalid schema；10/10 个场景通过并全部 Fail Closed。

本次没有修改 Gateway Contract、没有增加 wire 字段、没有修改 AI-CS 业务逻辑，也没有连接 PDD、读取客户消息、创建 Execution 或发送消息。

**Final Status: `AI_CS_CHANNEL_ENGINE_INTEGRATION_VALIDATED`**

## 1. 验证范围与判定口径

验证对象是 Gateway 的 **wire contract version 1.0**，不是 AI-CS 仓库自身的发布版本号。SHA 采用冻结流程定义的规范化 JSON 哈希；同时补充逐字节 raw file SHA，避免仅规范化相同但文件内容漂移。

通过标准：两仓文件、运行时模型、认证签名、请求与响应 Envelope、Error Envelope、幂等行为、失败关闭和四段 trace 均一致；任一不一致都使总体结果失败。

## 2. Contract Verification

| 检查项 | Channel Engine | AI-CS | 结果 |
|---|---|---|---|
| wire schema version | `1.0` | `1.0` | PASS |
| canonical JSON SHA-256 | `e5ac64…4b5` | `e5ac64…4b5` | PASS |
| raw file SHA-256 | `fef35a…b80` | `fef35a…b80` | PASS |
| runtime-generated schema | 与冻结文件一致 | 与冻结文件一致 | PASS |

冻结 SHA 在任务结束时再次复核，保持不变。Channel Engine 的 HMAC signer 被 AI-CS `/gateway/v1/health` 接受并返回 200/HEALTHY；错误响应继续使用冻结的 Error Envelope。

## 3. Decision Flow Validation

验证链路为：合成 Channel Message → Channel Engine Gateway Client → loopback HTTP → AI-CS Gateway → DecisionResponse。AI-CS 返回 `SUGGEST_REPLY`，`requires_approval=true`，因此链路停留在审批边界；未创建 Execution。

两仓依赖各自虚拟环境，验证器使用两个真实进程而非混合 import：Channel Engine 负责构造、签名、重试和校验；AI-CS 进程加载其实际 Gateway App，并以 stub RAG 隔离真实模型。这证明的是 HTTP/wire 兼容性，不是进程内 mock 兼容性。

## 4. Failure、HMAC 与 Idempotency

| 场景 | 实际结果 | Fail Closed 证明 |
|---|---|---|
| 无效 HMAC | 401 `AUTHENTICATION_FAILED`，1 次尝试 | 无 Decision |
| LAN 来源未授权 | 403 `AUTHORIZATION_DENIED`，1 次尝试 | 未到达 AI-CS Core |
| timeout | 3 次有界尝试后 UNKNOWN | 无 Decision、无 Execution |
| 重复同请求 | 重放原 DecisionResponse | Decision ID 与响应相同 |
| 同 key 不同 payload | 409 `IDEMPOTENCY_CONFLICT` | 未创建第二个 Decision |
| 额外字段 | 422 `SCHEMA_VALIDATION_FAILED` | 冻结 Error Envelope，拒绝处理 |

timeout 使用 Channel Engine 传输层的确定性故障注入，验证客户端有界重试与 UNKNOWN 语义；其余认证、授权、schema、Decision 和幂等场景均通过真实跨进程 HTTP 进入 AI-CS Gateway 实现。

## 5. Trace Validation

完整关联链为 `message_id → request_id → trace_id → decision_id`。冻结 contract 没有新增 `trace_id` 字段；Channel Engine 的逻辑 `trace_id` 明确映射到 wire 中已有的 `correlation_id`，因此没有发生合同漂移。

本次样例：

- `message_id`: `message-success`
- `request_id`: `request-success`
- `trace_id` / `correlation_id`: `trace-success`
- `decision_id`: `decision-3c34f1e0196a4db0938c6981d7fe33d3`

## 6. Regression

| 测试集 | 结果 |
|---|---|
| 跨仓集成 wrapper | 1 passed |
| AI-CS Gateway contract/server 专项 | 27 passed |
| AI-CS contract suite | 7 passed |
| AI-CS backend 全量 | 143 passed, 3 skipped |
| Channel Engine contract suite | 123 passed |
| Channel Engine 全量 | 503 passed |
| Channel Engine security suite | 17 passed |
| 两仓 compileall | PASS |

这些测试集存在包含关系，不能相加为唯一测试总数。AI-CS 的 3 个 skip 是需要显式启用真实环境的 E2E 项，不属于本次沙盒协议验证；现有 warnings 为测试框架弃用或收集提示，不影响协议结论。

## 7. 方法、证据与可复现性

跨仓验证器会：读取两份 schema 原始字节；计算 raw 与 canonical SHA；分别调用两仓运行时生成 schema；启动 AI-CS Core 和 denied-edge 两个临时 loopback 服务；由 Channel Engine 的真实 HTTP Transport/HMAC Client 发起请求；最后写出无凭据、无客户数据的 JSON evidence。

证据文件：

- `evidence/ai-cs-channel-engine-integration-validation-v1/cross-repo-validation.json`
- `evidence/ai-cs-channel-engine-integration-validation-v1/regression-results.json`

仓库快照：AI-CS commit `0ff658c63b3a84ba685783aff67277952ecc1924` 且 clean；Channel Engine 基准 commit `b2c64d54987f1f066a02de8e9e667d5cc0f9857c`，工作区原本即为 dirty。本任务未清理或重写既有资产。

## 8. 限制与稳健性

当前结论严格限定为：冻结 Gateway Contract V1 在本机双进程 loopback 沙盒中的协议兼容性已验证。它不等价于 TLS、DNS、企业代理、防火墙、第二台 Windows 节点或长期运行稳定性验证，也不证明真实模型、真实渠道或真实发送可用。

Channel Engine 冻结合同资产目前位于 dirty/untracked 工作树，这不影响本次内容哈希和行为验证，但属于后续发布治理风险：在进入 RC 前应把被验证资产纳入新的受保护基线，并在该提交上重跑同一验证器。

## 9. 下一步建议

1. 将 Channel Engine 当前被验证的合同与验证资产封版为新的受保护提交。
2. 在明确授权的 AI-CS sandbox/staging 上复用同一 10 场景门禁，保持 Fake Channel 与 Execution=0。
3. 补充 TLS、凭据轮换、断网恢复和 Windows 第二节点验证。
4. 任何 timeout/UNKNOWN 继续转人工核对，禁止自动执行或自动重发。

## 10. 待确认问题

在进入 staging 前，需要决定 Channel Engine dirty 工作树的发布基线提交，以及由哪个受控环境提供 service identity。两项都不阻塞当前 wire compatibility 结论，但会阻塞可发布 RC 的来源证明和外部环境验证。

---

Final Status: `AI_CS_CHANNEL_ENGINE_INTEGRATION_VALIDATED`
