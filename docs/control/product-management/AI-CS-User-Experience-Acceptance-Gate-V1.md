# 《AI-CS User Experience Acceptance Gate V1》

- Requirement：`R026`
- Date：`2026-08-06`
- Role：AI-CS Product Release Gate Owner
- Candidate：`codex/ai-cs-user-experience-acceptance-v1`
- UX fix anchors：`ac76d22a29054d89f7e52919b0ccefda382ab181`、`373031ded316d31f3f2f004bda7fd91d9caa00fc`
- Decision：`BLOCKED`
- Final Status：`AI_CS_USER_EXPERIENCE_ACCEPTANCE_BLOCKED`

## 1. 验收环境

- 使用系统 Edge，启动前确认可见旧 Edge 窗口为 0；以独立 Profile、`--no-first-run`、固定登录 URL 和独立调试端口启动。
- 启动后只有 1 个页面，标题为“木木小栈管理平台”，URL 为隔离 Admin 登录页。
- 隔离 Runtime 使用 LOCAL 网络模式和独立端口；A、C、B、Admin 均健康，运行身份为 clean `373031ded316`。
- 正式数据库只读复制后在隔离副本执行至 `0016_production_hardening_v1`；正式数据库未写入，验收前后 SHA-256 均为 `EA7C002D9C968C6D8A291FBBF087599B84602EFA8BA13A0192BE6E9327CD7C57`。
- 未连接真实 PDD、生产 Channel Engine，也未发送客户消息。验收结束后 Edge、四项服务、隔离数据库、日志、Secret 和 Profile 均已停止并删除，隔离端口全部释放。

## 2. 四角色结果

| 角色 | 核心路径 | 结果 | 证据与结论 |
| --- | --- | --- | --- |
| 管理员 | 登录→首次改密→创建员工→分配岗位→绑定店铺 | **BLOCKED** | 当前环境提供的管理员初始化凭据返回 HTTP 401；页面错误为中文且不暴露状态码，但无法进入首次改密和用户管理。未修改数据库密码、未绕过登录。 |
| 运营主管 | 登录→查看商品→查看 SKU→查看知识 | **PASS** | 可进入运营工作台；入口已改为“店铺与商品”，知识中心可按店铺查看商品、规格和知识状态；默认页面不再显示迁移码、RAG、fingerprint、Collection 或回执 ID。 |
| 客服主管 | 登录→选择/切换店铺→进入工作台 | **PARTIAL / BLOCKED** | 登录、两店选择、默认店铺切换和工作台加载通过；切换接口由 500 修复为 HTTP 200。运行时 AI 知识库为 0 条，无法产生可供采用的有效建议。 |
| 普通客服 | 登录→客户消息→AI 建议→确认回复 | **BLOCKED** | 当前数据库只有管理员、运营主管和客服主管三类初始化账号，没有普通客服验收账号；按任务边界未创建生产账号。客服主管代行验证了工作台布局和错误护栏，但不能替代新人账号的完整验收。 |

管理员页面的自动化证据确认岗位显示为“管理员 / 运营 / 客服”，店铺使用业务名称；但由于真实登录阻塞，不把自动化结果冒充管理员人工验收通过。

## 3. P0 / P1 问题

### 已修复

| 编号 | 原等级 | 问题 | 最小修复 | 回归 |
| --- | --- | --- | --- | --- |
| UX-001 | P0 | 客服在两个已绑定店铺间切换时触发唯一索引冲突和 HTTP 500。 | 默认店铺改为“全部清除并 flush→设置目标默认”的两阶段事务。 | 双向切换 API 测试通过；Edge 实测返回 200。 |
| UX-002 | P0 | 未发布知识仍形成可进入人工确认的草稿，存在采用内部提示语的风险。 | 检测未发布/AI 运行异常状态，草稿置为失效，隐藏采用按钮并提示联系运营。 | 单元测试和 Edge 实测均无采用按钮、无技术错误码。 |
| UX-003 | P1 | Workspace 三栏、状态和设备区域大量英文。 | 改为“客户消息 / AI 回复建议 / 回复确认”，状态和设备术语全部中文业务化。 | 客服前端 167 项通过；Edge 页面核对通过。 |
| UX-004 | P1 | 店铺代码、商品/规格内部 ID、反馈回执、fingerprint、Collection、迁移码直接可见。 | 默认员工页面只显示业务名称、依据和操作结果；移除技术证据块与回执号。 | Store、Workspace、Knowledge、Product Detail 回归通过。 |
| UX-005 | P1 | 原始 500、`Request failed`、RAG/C 目录契约诊断可能直接展示。 | 统一为中文原因和下一步，不回显 HTTP 状态、内部服务代号或契约字段。 | 新增错误映射测试 2 项并纳入全量前端回归。 |
| UX-006 | P1 | “商品”入口进入“店铺管理”，运营难判断商品位置。 | 入口和页面标题统一为“店铺与商品”。 | Edge 实测可找到新增商品、商品和知识入口。 |

### 仍阻塞

| 编号 | 等级 | 阻塞 | 解除条件 |
| --- | --- | --- | --- |
| ENV-001 | P0 | 管理员初始化凭据与当前 Runtime 数据不一致。 | 由正式账号管理员按受控 IAM 流程核对账号状态或重置临时密码；不得直接改库。随后重跑首次改密、创建员工、岗位和店铺绑定。 |
| DATA-001 | P0 | A 运行状态显示无成功知识同步历史，活动集合和可用集合均为 0 条；核心 AI 回复不能完成。 | 在非 PDD 环境完成已审核商品知识的受控发布/同步，并验证引用、风险、人工采用；不得用伪造回答通过 Gate。 |
| ENV-002 | P0 | 缺少普通客服验收账号，无法按新人身份完成登录和权限隔离。 | 管理员流程恢复后，仅在隔离验收环境创建普通客服账号并绑定测试店铺，再执行新人完整流程；不得创建生产测试账号。 |

当前开放 P1 为 0；但开放 P0 为 3，因此不满足 READY 条件。

## 4. 修复记录

- C IAM：修复 `PUT /api/v1/auth/default-store` 在 0016 唯一索引下的更新顺序，不改变 API、Schema 或权限语义。
- B Workspace：三栏和状态中文化；店铺切换、AI 异常和知识未发布提示提供明确下一步；内部 ID、回执 ID 和警告码不再展示。
- B Store Selection / Agent：仅显示店铺名和平台业务名；将 Channel/Agent 技术词改为客服连接程序、设备编号和程序版本。
- Admin：运营入口、商品详情、知识中心使用中文业务词；移除默认技术校验数据和系统迁移码。
- 未修改 `contracts/**`、`backend/app/gateway/**`、Gateway Contract、Channel Engine、PDD Adapter、Prompt、自动发送和数据库 Schema。

## 5. 回归结果

| Gate | 结果 |
| --- | --- |
| Backend | `150 passed, 3 skipped`；跳过项均为显式真实外部 E2E。 |
| Platform Backend | `155 passed`，包含 0013–0016 迁移与默认店铺约束回归。 |
| Frontend | `37 files / 167 tests passed`；typecheck PASS；production build PASS。 |
| Admin | `34 files / 85 tests passed`；typecheck PASS；production build PASS。 |
| Contract | `15 passed`。 |
| Gateway protection | `contracts/**` 和 `backend/app/gateway/**` 无 diff；Gateway health 为 `HEALTHY`、Contract `1.0`。 |
| Runtime | clean `373031ded316` 启动、status、Edge 验收和 stop 均 PASS；所有隔离端口已释放。 |

Frontend build 仍报告既有单个 JavaScript chunk 超过 500 kB 的警告，归为 P2，不阻塞本次 Gate。

## 6. 错误体验

- 密码错误：中文提示，不显示 401、Unauthorized 或堆栈；缺少“联系管理员/找回密码”提示，记录为 P2。
- 权限不足：运营访问用户管理被导向中文“没有访问权限”，提供返回运营首页动作。
- 店铺切换异常：不再显示原始 500，统一提示稍后重试并联系管理员。
- Agent 未配置：提示“客服设备接入尚未配置，请联系管理员”，不展示命令行。
- AI 知识未发布：提示联系运营发布知识，不生成可采用草稿。
- 服务异常：错误映射不显示 403/500、`Request failed`、RAG、C 目录或契约字段。

## 7. PDD 接入建议

当前不建议进入真实 PDD 接入。必须先按顺序关闭 `ENV-001`、`DATA-001`、`ENV-002`，再使用新的独立 Edge Profile 和隔离 Runtime 重跑四角色核心路径。复验必须看到：管理员完整创建人员、普通客服按授权店铺登录、至少一个已发布商品生成带商品依据和风险提示的建议、人工采用记录成功且没有自动发送。

## 8. 最终决定

**BLOCKED**。代码层发现的 P0/P1 已完成最小修复且全量回归通过，但三个环境/数据 P0 仍使管理员和普通客服核心流程无法完成，也使有效 AI 建议无法采用。

`Final Status: AI_CS_USER_EXPERIENCE_ACCEPTANCE_BLOCKED`
