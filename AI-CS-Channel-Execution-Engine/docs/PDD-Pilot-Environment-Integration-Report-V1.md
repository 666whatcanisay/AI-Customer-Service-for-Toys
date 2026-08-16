# PDD Pilot Environment Integration Report V1

日期：2026-08-04
目标：真实 Pilot 登录前环境准备
状态：`PDD_PILOT_ENV_READY`

## 1. 状态边界

本状态表示节点已具备安全进入“人工登录与 Selector Discovery”的环境条件，不表示店铺
已登录、消息已接收或发送能力已启用。本次没有登录 PDD、没有读取客户消息、没有发送、
没有导出 cookie，也没有修改 AI-CS 业务逻辑。

准备态强制：

- `runtime_mode=PILOT`；
- `dry_run=true`；
- Kill Switch 为开启状态；
- Inbound Transport 为 `DISABLED`；
- Outbound Transport 为 disabled；
- `automatic_login=false`、`auto_reply=false`；
- Store Binding 为 `PENDING_PAGE_DISCOVERY`，不存在手工 placeholder。

## 2. AI-CS Gateway Verification

### 2.1 运行中实例

本机 `127.0.0.1:8000` 的 `/api/health` 返回 200，但 OpenAPI 的 24 条路径中没有：

- `POST /gateway/v1/decisions`；
- `GET /gateway/v1/health`。

因此该进程被判定为旧版本或从不同加载路径启动，不能作为 Pilot Gateway。没有停止、重启
或修改该进程。

### 2.2 隔离契约验证

新增 `scripts/verify_pilot_gateway.py`，从当前 AI-CS backend 源码启动一次隔离的 18021
进程。HMAC secret 仅存在于父/子进程内存和临时环境中，验证脚本不会保存或输出它。

验证结果：

| 项目 | 结果 |
| --- | --- |
| Decision route | PASS |
| Signed health route | PASS |
| Contract | `1.0` |
| Gateway version | `ai-cs-gateway.v1` |
| Capability version | `decision.ai-cs-scope.v1` |
| HMAC signed request | PASS |
| Decision request | 未执行 |
| Secret persistence | 未发生 |

签名 Health 的业务 readiness 当前为 `UNHEALTHY`，但响应已证明真实 AI-CS Gateway 的
路由、签名、header 和 schema 兼容。AI readiness 必须在未来 Live Preflight 再次达到
HEALTHY；它不通过时仍然禁止消息进入 AI-CS。

运行连接参数已保存到不含 secret 的
`deploy/pdd-pilot-ai-cs-gateway.json`。Pilot 进程必须在启动时由外部 provider 注入
`secret-ref://ai-cs/pilot/gateway-hmac`，不得将值写入 manifest 或仓库。

## 3. Agent Environment

新增 `deploy/pdd-pilot-environment.json`：

```text
node_id         = pdd-pilot-node-windows-001
node_name       = PDD Single Store Pilot Node
gateway         = http://127.0.0.1:18021
gateway client  = channel-engine / pilot-env-v1
runtime_mode    = PILOT
store_binding   = null
kill_switch     = true
dry_run         = true
```

已注册两类 opaque reference：

- AI-CS Gateway：`secret-ref://ai-cs/pilot/gateway-hmac`；
- PDD 人工 Browser Session：`credential-ref://pdd/pilot/manual-browser-session`。

配置中没有 cookie、token、password 或 HMAC secret 值。`AgentEnvironment` 新增 PILOT
状态；PILOT 只允许 loopback server，并强制 dry-run。

## 4. Browser Pilot Preparation

已创建独立目录：

`C:\AI-CS\ChannelAgent\profiles\pdd-pilot-single-store-001`

现场检查结果：目录存在、不是 reparse point、文件数为 0。它不是用户默认 Chrome
Profile，也没有被 Chrome 打开。

浏览器准备模型使用：

- System Chrome；
- `https://mms.pinduoduo.com/chat-merchant/index.html`；
- Dedicated Profile；
- `ConservativeLoginDetector`；
- `selector_contract_version=pdd:merchant_chat:v1`。

`build_selector_discovery_browser_session()` 只构造 `CREATED / UNKNOWN / generation=0`
Session，不启动进程。未来由人工启动后，未知登录状态只能进入人工接管，不会自动登录。

## 5. Store Binding Model

Pilot 环境不再预填 `store_id`。`PDDStoreBindingDiscoveryService` 只接受：

1. `ACTIVE + AUTHENTICATED` Browser Session；
2. 具有 `STORE_IDENTITY` capability 的 VERIFIED Selector Contract；
3. `real_platform_source=true` 且 `read_only=true` 的页面/API source；
4. 与当前 page context、contract ID 和 fingerprint 精确绑定的 observation。

只有满足这些条件，系统才从页面/API读取 `STORE_ID`、`STORE_NAME` 并生成
`StoreBinding`。placeholder、Fake source、手工预填和未认证 Session 均被拒绝。

该流程只读取店铺身份字段，不读取会话列表或客户消息。

## 6. Selector Discovery Workflow

Selector 生命周期已扩展为：

```text
DRAFT
  -> DISCOVERY（必须有 discovery-ref）
  -> DISCOVERY candidate（必须有 evidence-ref）
  -> VERIFIED（probe 必须匹配 candidate fingerprint）
  -> active
```

VERIFIED 要求：

- contract ID 与 fingerprint 精确匹配；
- probe passed；
- missing keys 为空；
- ambiguous keys 为空；
- capability 所需 bindings 完整；
- durable evidence reference 存在。

Registry 只允许 VERIFIED contract 激活。当前真实 PDD contract 仍为 DRAFT，这是本次
禁止登录下的正确状态；环境已经可以进入 Discovery，但未知 selector 仍不可激活。

## 7. Transport Isolation

V13 Pilot 配置没有使用原来的 Fake runtime 作为真实替代：

```text
inbound_transport_mode     = DISABLED
inbound_transport_name     = null
customer_message_read      = false
outbound_transport_enabled = false
```

配置模型会拒绝名称包含 `fake` 的 Pilot transport。Transport 只有在未来完成真实只读
适配并重新通过安全 Gate 后，才允许从 DISABLED 切换到 REAL_RECEIVE_ONLY；本阶段不存在
发送 transport 的启用路径。

## 8. Reproducible Preflight

执行：

```powershell
.\.venv\Scripts\python.exe scripts\prepare_pdd_pilot_environment.py `
  --config deploy\pdd-pilot-environment.json `
  --ai-backend ..\AI-CS\backend `
  --gateway-port 18021
```

现场结果：9 项检查全部 PASS，blockers 为空，返回：

`PDD_PILOT_ENV_READY`

完整证据：`evidence/PDD-Pilot-Environment-Readiness-Evidence-V1.json`。

全量回归：`264 passed, 1 warning`。同时通过 Python compileall、三个 JSON 文件解析和
cookie/password/bearer 等敏感值标记扫描。warning 为既有 FastAPI TestClient/httpx
弃用提示，不影响环境断言。

## 9. 下一阶段允许动作

下一阶段只能在操作员在场时：

1. 从 secret provider 注入 Gateway HMAC secret，启动正确的 18021 AI-CS Gateway；
2. 再次要求 signed health 为 HEALTHY；
3. 启动 prepared Browser Session，等待人工扫码；
4. 进入 Selector DISCOVERY，只采集登录与店铺身份证据；
5. probe 通过后验证 Selector，并由真实页面派生 Store Binding；
6. 完成上述步骤前保持 Transport DISABLED。

客户消息读取、真实发送、自动登录和 cookie 导出仍不在允许范围。

## 10. Final Status

`PDD_PILOT_ENV_READY`
