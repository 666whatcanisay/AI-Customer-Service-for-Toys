# 《AI-CS Code Quality Audit V1 Report》

- 审计日期：2026-08-06
- 审计任务：R023
- 审计对象：`release/product-reliability-hardening-v1@bd6e10c4`叠加R020–R022未提交源码候选
- 审计范围：A Backend、C Platform Backend、B Frontend、C Admin、Database/Migrations、API、RAG、Workspace、测试与生产运行入口
- 审计方式：源码/依赖/迁移/权限/运行脚本静态审查，正式数据库只读检查，隔离自动回归；未启动、迁移或写入正式Runtime
- 发布结论：`FAIL / PRODUCTION_RELEASE_BLOCKED`
- 审计交付状态：`AI_CS_CODE_AUDIT_READY`

## 1. 结论摘要

AI-CS已经具备清晰的A/B/C边界、服务端RBAC、密码与Session摘要存储、受控Store范围、Gateway HMAC边界以及较完整的单元/契约测试，未发现Python模块循环依赖、动态拼接SQL、前端`v-html`或疑似已提交生产Secret。

但当前候选**不能直接生产上线**。本轮登记22项问题：P0 1项、P1 9项、P2 10项、P3 2项。所有P0/P1必须在发布前关闭；修复必须采用小范围、可回归变更，不能借审计结论进行大规模业务重构。

最关键阻断为：

1. R020–R022仍是未提交候选，正式数据库停在0013，而源码迁移头为0015，不能形成可复现发布身份。
2. 两个“Loopback-only”知识投影接口没有鉴权，客服Web的同源代理可从LAN转发到它们。
3. 生产脚本用Vite开发服务器以明文HTTP承载客服登录和Bearer流量。
4. 管理员同时重置密码并保持账号ACTIVE时，旧Session可能不会撤销。
5. 登录没有限速/锁定/失败审计；RAG运行异常被包装为HTTP 200；知识发布没有同商品并发串行化。
6. C未记录未处理异常，C/Admin/Windows运行门禁未进入CI；B当前绑定码用例受固定过期时间影响，重复运行3次有2次失败。

## 2. 当前架构与边界

| 区域 | 当前职责 | 审计判断 |
| --- | --- | --- |
| A Backend | `/api/chat`、RAG、知识发布、Gateway独立路由 | Gateway与legacy chat边界清楚；RAG异常语义和发布并发需要修复 |
| C Platform Backend | IAM、RBAC、Store、Workspace facade、运营/知识API | 权限依赖覆盖主体路由；存在未保护内部投影、会话撤销和可观测性缺陷 |
| B Frontend | 登录、客服Workspace、人工确认与Feedback | 不直接持有Engine管理员凭证；生产Web承载、状态恢复和测试时钟需要修复 |
| C Admin | 用户、商品、知识与运行状态管理 | 服务端权限为权威；API client体积和CI覆盖需治理 |
| Database | 正式SQLite 0013；源码迁移到0015 | 只读完整性正常；发布版本不一致、并发和约束不足 |
| Shared contracts | repository `0.12.0`；Gateway wire `1.0` | 本轮未修改；Gateway canonical schema SHA-256保持不变 |

Python AST导入图检查覆盖A 31个模块、C 102个模块，未发现循环依赖。边界问题主要来自HTTP代理、运行入口和跨服务认证，而不是Python import层。

## 3. 问题清单

严重等级：P0=发布/数据/安全关键阻断；P1=高风险且上线前必须修复；P2=中风险；P3=低风险/维护债务。

### P0

| ID | 问题与证据 | 影响 | 建议 | 上线前修复 |
| --- | --- | --- | --- | --- |
| RC-001 | 审计开始前Git有97项dirty；加入本任务卡后为98项。HEAD仍为`bd6e10c4`，正式DB为0013，而源码迁移头为`0015_customer_desktop_workflow_v1`。 | 无法从一个受控SHA重建当前候选；标准启动可能在未固化源码上自动迁移正式库，回滚身份不完整。 | 精确清单审计并分线提交R020–R022；禁止`git add .`；备份正式SQLite后在clean SHA上受控迁移0014/0015，再做同SHA start/status/stop和回滚演练。 | **是** |

### P1

| ID | 问题与证据 | 影响 | 建议 | 上线前修复 |
| --- | --- | --- | --- | --- |
| SEC-001 | `platform_backend/app/api/test_catalog_routes.py:110-128`的RAG export/evaluations接口无鉴权；`platform_backend/app/main.py:103-106`仅以注释声明Loopback；`frontend/vite.config.ts:39-46`把任意`/platform-api/**`转给C。 | LAN客服浏览器可经同源代理访问内部知识/评测投影，绕过IAM边界。 | 为内部Router增加明确的服务身份或至少不可由浏览器代理到达的独立监听边界；增加未认证、普通客服、代理转发三类403/404回归。 | **是** |
| SEC-002 | `scripts/windows/start_lan_ai_customer_service.ps1:64-66`直接启动Vite dev server并绑定LAN；URL和代理均为HTTP；未配置TLS、CSP、HSTS、frame/referrer/content-type安全头。 | 登录口令与Bearer在LAN明文传输；开发服务器/HMR不具备生产Web防护。 | 以`vite build`不可变产物配受信TLS反向代理/静态服务器；只暴露5173等价入口，C/A保持loopback；设置安全头、Host allowlist和证书运维Gate。 | **是** |
| SEC-003 | `platform_backend/app/iam/service.py:217-229`先在密码重置时设`revoke=True`，随后`status=ACTIVE`会把它覆盖为False。 | 一次同时包含密码和ACTIVE状态的更新可让旧Session在密码重置后继续有效。 | 改为单调OR语义，例如`revoke = revoke or status==DISABLED`；增加“密码+ACTIVE”“密码+DISABLED”组合回归并核对全部活跃Session。 | **是** |
| SEC-004 | `platform_backend/app/iam/service.py:351-375`每次登录直接执行scrypt；没有按账号/IP的限流、失败计数、退避/锁定或失败审计。 | 可被在线爆破，也可通过高成本scrypt造成CPU型拒绝服务；安全事件不可追踪。 | 在可信入口和C内实现分层限流、短期退避、失败审计与告警；日志只记最小化主体摘要/来源，不记口令或Token；增加时钟可控测试。 | **是** |
| API-001 | `backend/app/service/rag_service.py:941-964`把LLM失败变成答案文本；`1005-1030`把任意RAG异常变成普通结果；`backend/app/api/routes.py:328-334`始终返回200，C facade继续透传。 | Workspace可能把运行故障当作成功AI建议，监控、重试和客服判断失真。 | 保持冻结legacy `/api/chat`兼容时，在C Workspace facade识别明确失败码并返回503 Error Envelope；或为A增加向后兼容的结构化failure字段，禁止失败草稿进入人工采用。 | **是** |
| DATA-001 | `backend/app/service/product_knowledge_publisher.py:95-116`执行“读旧→写新→校验→删旧”但没有同商品锁；C `platform_backend/app/knowledge_publishing/service.py:58-208`在远程调用前提交GENERATING，也没有租约/CAS。 | 同商品并发发布可能互删向量、后完成旧请求覆盖新状态或产生账本/索引不一致。 | 增加按商品串行化租约和最终fingerprint CAS；幂等占位必须原子；增加并发双fingerprint、超时接管和失败保留旧版本测试。 | **是** |
| OBS-001 | `platform_backend/app/errors.py:144-152`返回通用500但完全不记录异常、类别或request_id；生产启动还使用`--no-access-log`。 | C生产故障只能看到客户端500，无法定位、告警或形成审计链。 | 增加去敏结构化错误日志与指标，包含内部request_id、路由模板、异常类别和状态，不记录请求正文、授权头、客户内容或Secret。 | **是** |
| QA-001 | B全套回归为35文件通过、`HumanInLoopWorkspace.spec.ts` 1文件失败，即162/163通过；目标用例重复3次有2次失败。测试在`317-333`写死`2026-08-06T08:10:00Z`，当前已过期，组件`HumanInLoopWorkspace.vue:202-208`会以0ms定时清除授权码。 | 当前候选测试Gate为红；时间竞争导致结果不稳定并掩盖真实回归。 | 使用fake timer和相对“当前时间+有效期”，显式推进到期时钟；发布前要求全套连续稳定通过。 | **是** |
| QA-002 | `.github/workflows/backend-test.yml`只覆盖A；没有C测试、Admin测试、Windows Runtime、迁移往返、依赖审计或LAN安全边界CI；B workflow仅build。 | C/IAM/数据库和生产脚本的大量变更可在PR中未测试合入。 | 增加A/C分Python版本矩阵、B/Admin test+typecheck+build、contracts、迁移upgrade/downgrade、Windows脚本静态/PowerShell测试及依赖审计；真实E2E保留受控非生产Gate。 | **是** |

### P2

| ID | 问题与证据 | 影响 | 建议 | 上线前修复 |
| --- | --- | --- | --- | --- |
| DB-001 | 正式库为SQLite；`platform_backend/app/database.py:15-23`只开启foreign keys，没有WAL、busy timeout或写并发策略。 | 多客服、审计和运营写并发时可能出现`database is locked`和长事务互阻塞。 | 上线前做真实并发压测；短期配置WAL/busy timeout并缩短事务，达到规模阈值时迁移受管RDBMS。 | 多用户上线前是 |
| DB-002 | 0013只对`(user_id, store_id)`唯一；`(user_id,is_default)`只是普通索引，DB未保证每用户至多一个默认Store。 | 并发或绕过Service写入可产生多个默认项，`scalar()`行为不可靠。 | 新迁移先修复存量，再增加`is_default=true`部分唯一索引或等价约束，并保留Service校验。 | 建议是 |
| PERF-001 | `platform_backend/app/workspace/service.py:70-81`逐Store调用`list_stores({id})`；后者在`customer_catalog/service.py:84-93`每次扫描全部Store。 | Admin/Operator全店上下文形成N次全表扫描，30秒设备轮询会放大为O(N²)。 | 用一次过滤查询/批量投影返回可用Store；增加query-count和100/1000 Store负载测试。 | 否，扩店前 |
| PERF-002 | `platform_backend/app/iam/service.py:181-183`全量读取用户，再由`project_user:104-113`逐用户查询roles和bindings；API无分页。 | 用户数增长后形成2N+1查询和大响应。 | 增加分页、总数与批量预加载；Admin UI按页消费。 | 否，扩员前 |
| PERF-003 | C Workspace和Agent upstream使用顶层`httpx.request/get`，每次新建Client；B每30秒每浏览器请求一次Agent全量列表。 | 连接无法复用，浏览器数线性放大Engine管理面请求。 | 使用应用生命周期Client、连接池和超时；对用户/Store状态做短TTL合并缓存，并保持权限变更快速失效。 | 建议是 |
| ARCH-001 | `AiChat.vue` 2687行、`admin_web/src/api/client.ts` 1847行、`rag_service.py` 1186行；旧AiChat与新Workspace、B/Admin auth/client存在重复。 | 修改影响面大、审查困难、重复错误处理容易漂移。 | 不做发布前大重构；先冻结legacy页面，按“类型/transport/domain adapter/UI section”小步抽取并以现有测试保护。 | 否 |
| PORT-001 | C `.venv`为Python 3.12.13，A为3.11.9；C源码在3.11因`knowledge_materials/service.py:144`的PEP 701语法失败；requirements无`requires-python`，旧脚本仍寻找3.11。 | 错误解释器可在部署时直到启动才失败。 | 明确A/C独立Python版本清单，preflight校验major/minor；用`pyproject.toml`/构建元数据声明C>=3.12并在CI验证。 | **是** |
| DEP-001 | B和Admin生产依赖审计各报1个PostCSS moderate公告（<=8.5.22）；C requirements为宽范围，Python无锁定/哈希。 | 构建结果不可完全复现，已知依赖风险未关闭。 | 在隔离分支升级到PostCSS>=8.5.23并回归；为A/C生成受控锁文件/constraints和定期漏洞扫描，不直接运行无审查的自动fix。 | **是** |
| SEC-005 | A模型配置、测试知识同步和知识发布等写接口主要依赖`require_loopback_client`，没有独立服务身份。 | 同主机恶意进程或未来代理误配可修改模型配置/RAG。 | 给C→A管理面增加服务身份和最小路由allowlist；保留loopback作为第二层，不改Gateway Contract。 | 建议是 |
| API-002 | `platform_backend/app/middleware.py:9-16`原样接受并回显任意`X-Request-ID`，无长度/字符校验。 | 未来结构化日志可能被超长值或控制字符污染，内外部相关ID混淆。 | 验证限定字符/长度；内部ID始终生成，外部ID作为单独、去敏字段保留。 | 与日志修复同批 |

### P3

| ID | 问题与证据 | 影响 | 建议 | 上线前修复 |
| --- | --- | --- | --- | --- |
| DB-003 | 过期/撤销`user_sessions`没有清理任务，登录成功只追加记录。 | 长期增长增加索引和备份体积。 | 定期清理超过审计保留期的记录并记录聚合结果。 | 否 |
| MAINT-001 | A测试有66条httpx废弃警告，C有TestClient/Alembic废弃警告；旧`Test-OpsLanMode.ps1`仍断言已移除的`/rag-api`。 | 依赖升级和旧脚本容易造成噪声或误判。 | 分期清除废弃API，标记/修复过期脚本并让权威测试入口唯一化。 | 否 |

## 4. 分域审计结果

### 4.1 Backend / API / RAG

- Gateway router、service、auth、store与legacy `/api/chat`保持独立，canonical schema SHA-256为`fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`。
- A/C主要使用Pydantic与SQLAlchemy参数化查询，未检出应用源码动态拼接SQL。
- C Workspace会重新验证Store/Product/SKU归属，B提交的实体ID不是授权依据。
- 主要缺口是RAG失败语义、内部投影鉴权、C可观测性和知识发布并发。

### 4.2 Frontend / Admin / Workspace

- 未检出`v-html`或应用代码直接`innerHTML`；Vue默认转义降低当前存储型XSS面。
- Bearer保存在`sessionStorage`，一旦出现XSS仍可被读取；在TLS/CSP和生产静态承载关闭前不能声称浏览器安全就绪。
- Workspace消息明确只保留页面内存、无真实渠道与自动发送；刷新丢失会话是当前声明边界，不是持久会话能力。
- `loadWorkspaceContext`失败时应清空旧Store/设备投影，避免权限撤销后仍在UI短暂展示旧上下文；服务端403仍能阻止实际操作。

### 4.3 Database / Migration

- 只读正式DB检查：revision=`0013_user_management_v1`、`integrity_check=ok`、foreign-key violations=0、44张业务表、77个索引。
- Alembic源码只有一个head：`0015_customer_desktop_workflow_v1`；0014/0015迁移测试通过，但尚未部署正式库。
- 上传路径做了basename/resolve和大小限制，ZIP解析有条目、单文件和解压总量限制；未发现直接Zip Slip写盘路径。

### 4.4 Security

- 正向控制：scrypt随机盐密码hash、Session只存token digest、固定RBAC在服务端dependency执行、CORS拒绝`*`、Gateway保留HMAC/timestamp/nonce/signature。
- 启发式tracked文件扫描未发现私钥、常见云Key或长API token模式；5个tracked env文件均为`.env.example`。这不是完整DLP证明。
- 当前安全声明必须降级为“源码具备基础控制但生产入口未加固”，直到SEC-001～SEC-004和TLS关闭。

## 5. 测试与质量门禁证据

| 检查 | 结果 | 判定 |
| --- | --- | --- |
| A pytest | 147 passed，3个真实E2E opt-in skipped，66 warnings | PASS，真实模型闭环未纳入本轮 |
| C pytest | 145 passed，迁移测试包含0014/0015 | PASS |
| B Vitest | 162 passed，1 failed；目标重复3次2次失败 | **FAIL** |
| B typecheck | PASS | PASS |
| Admin Vitest/typecheck | 33 files / 84 tests；typecheck PASS | PASS |
| Contract tests | 15 passed | PASS |
| Python `pip check` | A、C均无破损依赖 | PASS |
| JS production dependency audit | B 1 moderate；Admin 1 moderate，均为PostCSS公告 | CONDITIONAL FAIL |
| JSON syntax | Node解析38个JSON，0 invalid | PASS |
| Git diff check | PASS；仅既有CRLF转换警告 | PASS |
| 正式DB只读检查 | integrity ok，0 FK violation，revision 0013 | PASS，但版本落后源码head |

同一源码候选在本日R022完成时已有B/Admin production build PASS证据；本轮为避免重复生成构建产物，只重跑测试与typecheck。A的3个真实RAG/反馈E2E仍需在隔离非生产运行环境显式执行，不能用skipped结果代替上线验收。

## 6. 修复优先级与最小路线

### Gate A：安全与发布身份（必须先完成）

1. 关闭SEC-001内部接口暴露，增加代理级负面测试。
2. 修复SEC-003 Session撤销和SEC-004登录限流/失败审计。
3. 用受信TLS静态承载替代LAN Vite dev server。
4. 精确固化R020–R022到clean SHA；不得包含数据库、runtime、日志、证据、Secret或build产物。

### Gate B：可靠性与质量（生产启动前）

1. 修复B时钟测试并要求连续全量绿灯。
2. 修复RAG故障非2xx语义、C结构化日志与request ID校验。
3. 为知识发布增加同商品并发控制；为SQLite完成并发压测/WAL策略。
4. 升级受影响PostCSS并锁定Python依赖/解释器版本。
5. 建立C/Admin/Windows/迁移CI。

### Gate C：受控部署

1. 正式SQLite离线/在线备份及hash/完整性记录。
2. clean SHA上执行0014/0015并核对IAM、Workspace、审计表与存量数据。
3. 四服务同SHA start/status/stop，TLS入口登录/RBAC/Store/AI/Feedback回归。
4. 仅连接非生产Channel Agent完成第二台客服电脑E2E；仍禁止PDD、自动发送和生产Channel Engine。

## 7. 明确未做事项与兼容性

- 未修改任何业务代码、API、数据库、RAG、Prompt、模型或产品知识。
- 未修改Gateway Contract、Channel Engine或PDD Adapter；Gateway schema hash保持不变。
- 未启动正式四服务，未迁移0014/0015，未清空/重建/重切/重Embedding RAG，也未读取或输出用户口令、password hash、Session token、Gateway secret或客户内容。
- 本报告完成表示审计证据就绪，不表示生产发布通过。

## 8. 最终Gate

```text
AUDIT: AI_CS_CODE_AUDIT_READY
PRODUCTION RELEASE: FAIL / PRODUCTION_RELEASE_BLOCKED
REQUIRED NEXT INPUT: P0/P1 Remediation Task Cards + clean RC + controlled deployment validation
```
