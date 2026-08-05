# AI-CS Production Server Runtime RC Report V1

## 1. 结论

AI-CS 已形成 Production MVP Server Runtime Candidate：现有 A Core 与 Gateway 共用同一 FastAPI/uvicorn 进程，既有 Windows 四服务生命周期继续负责 C API、A、B 和 Operations Console，新增 Production wrapper 在其上增加 Gateway 配置硬门、签名 Health Gate 和统一状态输出。

最终 Gate：`AI_CS_SERVER_RC_READY`。

该结论是源码 RC 与隔离运行验证结论，不是部署或生产联通声明。当前 HEAD 仍是保护锚点 `0b3367f85999f1dc840accf23742c290eb53746b`；候选改动仍在 dirty worktree，未提交、打标、推送或连接生产 Channel Engine/PDD。

## 2. Runtime 架构

```text
start_ai_cs_server.bat / start_ai_cs_server.ps1
  -> existing start_ai_customer_service.ps1
     -> C API :8011
     -> A Core + Gateway :8000
     -> B Customer Console :5173
     -> Operations Console :5174
  -> authenticated GET /gateway/v1/health
  -> GET /api/admin/server-runtime
```

保留且未删除：

- `scripts/windows/start_ai_customer_service.ps1`
- `scripts/windows/status_ai_customer_service.ps1`
- `scripts/windows/stop_ai_customer_service.ps1`

新增 RC 入口：

- 一键启动：`scripts/windows/start_ai_cs_server.bat`
- PowerShell 启动：`scripts/windows/start_ai_cs_server.ps1`
- 状态：`scripts/windows/status_ai_cs_server.ps1`
- 停止：`scripts/windows/stop_ai_cs_server.ps1`

wrapper 只做 production preflight、委派既有生命周期、Gateway 签名 Health 和汇总输出。既有启动器仍可在 `GatewayEnabled=false` 下按原语义运行，B 客服调用链未被替换。

## 3. Gateway Runtime

Production routes 保持 T4 冻结结果：

| Method | Path | 认证 | 结果 |
| --- | --- | --- | --- |
| POST | `/gateway/v1/decisions` | HMAC-SHA256 | DecisionResponse；固定 `requires_approval=true` |
| GET | `/gateway/v1/health` | HMAC-SHA256 | `status`、Gateway `version`、`contract_version=1.0`、capabilities |

Gateway Health 的 canonical schema 只接受 `HEALTHY / UNHEALTHY`。T4 prose 中多出的 `DEGRADED` 已校正，wire schema、canonical SHA 与跨仓冻结向量未改变。

新增 `GET /api/admin/server-runtime` 只为本机 Operations Console 提供：

- Server：`status`、`version=ai-cs-server-runtime.rc1`、`runtime_mode`。
- Gateway：enablement、status、`version=ai-cs-gateway.v1`、`contract_version=1.0`、configuration state。

它不返回 client/key identity、secret/secret reference、SQLite path、nonce、幂等记录、请求内容、Prompt 或知识内容；也不是 Channel Engine production API。

## 4. 统一配置与安全

既有标准 Runtime config 增加以下 opt-in 字段：

| 配置 | 语义 |
| --- | --- |
| `RuntimeMode` | `standard / shadow / recovery`；传给 A 进程 |
| `BindAddress` + `RagPort` | A Core 与 Gateway 共用 bind/port |
| `GatewayEnabled` | Production wrapper 必须为 `true`；旧入口默认仍为 `false` |
| `GatewayClientId` / `GatewayKeyId` | HMAC credential identity |
| `GatewaySecretReference` | 指向 UTF-8 单行、至少 32 bytes 的 secret 文件；不得放明文 |
| `GatewayStatePath` | 必须位于忽略的 `RuntimeDirectory` 内 |

生产模式后端只接受 `GATEWAY_HMAC_SECRET_FILE` reference。若配置 inline `GATEWAY_HMAC_SECRET`、secret reference 缺失/不可读/太短、或 reference 指向 Git tracked file，Gateway preflight 失败。secret 不进入命令行、runtime record、Console projection 或日志。

保留 inline secret 字段只为显式 `development/test` 兼容；`standard/shadow/recovery` 会 fail closed。

## 5. Operations Console

5174 的“系统状态”页通过既有 `/ai-api` 本机代理读取 `/api/admin/server-runtime`，展示：

- Server 状态、Server 版本、Runtime mode。
- Gateway 状态、Gateway 版本、Contract `1.0`。

没有修改 AI 状态页的冻结 `ai-control.v1.1`，也没有修改 R006/R009 页面或 C Backend。新 console contract 以 repository contracts `0.7.0` additive 方式登记，受影响线审查结论为 A/C compatible、B 与 Gateway wire unaffected。

## 6. 测试结果

| 验证 | 结果 | 证据范围 |
| --- | --- | --- |
| Gateway Health / Decision / Auth / Idempotency / Error / Chat regression | `36 passed`（含 Runtime 与 shared contract 专项） | TestClient、合成 provider、临时 SQLite；无生产 Engine |
| A 全量 | `138 passed, 3 skipped` | 跳过显式真实模型/真实 C opt-in E2E |
| R006/R009 定向 | `25 passed` | C catalog、migration、knowledge publishing、product import；临时数据库 |
| Operations Console | `76 passed` | 全量 Vitest |
| Console type/build | `PASS / PASS` | `vue-tsc --noEmit`、Vite production build |
| Windows lifecycle | `11/11 suites PASS` | 隔离进程/端口夹具；start/status/stop wrapper 与原入口回归 |
| PowerShell HMAC | `PASS` | content hash/signature 与 T4 冻结向量完全一致 |
| Shared contracts | `7 passed` | contracts 0.7 additive 与 Gateway 1.0 freeze |
| JSON Schema | `17 valid` | Draft 2020-12 schema check |

未执行真实模型调用、正式数据库写入、真实知识/向量变更、浏览器客户动作、生产 Channel Engine 或 PDD 连接。

## 7. 兼容证明

- `/api/chat` 路径、请求/响应语义和 B 消费代码未修改；Gateway 仍是独立 `/gateway/v1/*`。
- RAG service、Prompt、模型配置语义、知识检索/发布核心未修改。
- `platform_backend/**`、数据库 schema、R006/R009 业务逻辑未修改；定向回归通过。
- 既有 Windows start/status/stop 未删除；新增 Gateway 配置默认关闭，因此旧启动不被强制切换。
- Gateway Contract `1.0` routes、HMAC canonicalization、Decision/Health/Error schema、approval policy 与 canonical SHA 不变。

## 8. RC 风险与下一步

1. 当前是 dirty source candidate，尚无受控 commit/tag/release artifact；必须另行做 source review 与发布装配。
2. secret file reference 已替代版本化明文，但正式 secret manager、ACL/rotation/revocation 和备份恢复仍需部署阶段验收。
3. `/api/admin/server-runtime` 是本机只读投影且不含敏感值；若未来暴露到非可信网络，仍需 reverse proxy、TLS 与 Console access control。
4. Gateway 幂等状态仍是单实例 SQLite；多实例共享状态、灾备、加密保留策略和容量监控未完成。
5. 本轮没有连接生产 Channel Engine，跨进程真实网络 E2E、超时/重试/时钟漂移与运维告警仍是下一阶段输入。
6. Receipt/Event/Execution、浏览器/PDD/Chrome 能力继续明确延后，不能由 Server RC Gate 推导为已具备。

## Final Status

`AI_CS_SERVER_RC_READY`
