# 《AI-CS Production Hardening V1 Completion Report》

日期：2026-08-06

任务：R024

结论：`PASS / SOURCE_ONLY / AI_CS_PRODUCTION_HARDENING_READY`

## 1. 修复列表

| 审计项 | 生产修复 | 结果 |
|---|---|---|
| 内部接口鉴权绕过 | C内部测试知识Router与A所有非health服务路由要求独立文件凭据；A运营路由继续验证C IAM Bearer；Server Runtime Console只接受运营身份或内部服务身份。 | CLOSED |
| Session安全 | 修复密码重置后`status=ACTIVE`覆盖撤销标志；过期Session落库撤销；限制每用户活跃Session，并以SQLite短写事务串行化并发登录。 | CLOSED |
| 登录安全 | 按用户名摘要与来源摘要持久化失败窗口；达到阈值返回429和`Retry-After`；未知用户仍执行假hash；共享LAN来源采用更高阈值。 | CLOSED |
| LAN生产入口 | 正式启动改用预构建`dist`与受控静态/反向代理服务，不再启动Vite dev server；增加Host allowlist、CSP、HSTS、frame/referrer/content-type安全头、路径/重定向/正文限制；LAN强制TLS证书/key文件引用，缺失即拒绝启动。 | CLOSED |
| RAG错误状态 | 冻结A legacy成功/兼容响应；C Workspace识别A transport、RAG runtime及LLM失败，返回非2xx Error Envelope。 | CLOSED |
| 知识发布并发 | C对同商品使用带超时的generation lease与owner token；非owner不能覆盖成功/失败结果，冲突返回409。 | CLOSED |
| 异常日志 | A/C只记录request ID、method、path、最小user ID和error type；不记录异常消息、堆栈、正文、口令、Token、Secret或客户内容。 | CLOSED |
| CI质量 | 补齐A、C/迁移、B、Admin、contracts、Windows production runtime、依赖审计、测试、类型检查和生产构建Gate。 | CLOSED |
| 时钟稳定性 | 固定过期时间改为相对当前时间；B 164项连续三轮及最终复跑均通过。 | CLOSED |

同时纳入的低风险加固：SQLite启用WAL/busy timeout；数据库增加“每用户最多一个默认Store”部分唯一索引；request ID限制为安全字符和长度；B/Admin已知npm/pnpm漏洞清零。

## 2. 安全变化

- 内部凭据与Gateway HMAC secret严格分离，只从`.runtime`文件读取，均不进入源码、浏览器、响应、命令行或日志；比较使用恒定时间函数。
- 生产Web代理只转发明确allowlist中的`Authorization`、content type、idempotency key与request ID；`X-AI-CS-Service-Token`、Cookie和其他头不会从客户端转发。
- B仍只调用C的Bearer鉴权Workspace facade；C继续在服务端执行角色、权限与Store/Product/SKU范围校验，前端隐藏按钮不构成授权。
- LOCAL模式保持回环；LAN模式只暴露TLS Customer Web入口，A/C/Admin保持loopback。脚本不关闭防火墙、不开放公网，也不创建证书。
- 正式Runtime已生成独立内部服务凭据引用并限制ACL；报告未记录凭据值、hash或Session token。

## 3. API变化

| 接口/范围 | 变化 | 成功兼容性 |
|---|---|---|
| A `/api/health` | 保持匿名health。 | 不变 |
| A chat/retrieval/status/stats/compatibility | 要求`X-AI-CS-Service-Token`；缺失/错误为401，服务配置不可用为503。 | 已认证调用的成功payload不变 |
| A operations与`/api/admin/server-runtime` | operations仍需C校验的Bearer；runtime console也允许内部服务身份供受信脚本使用。 | schema不变 |
| C `/api/v1/auth/login` | 可新增429 `AUTHENTICATION_RATE_LIMITED`及`Retry-After`。 | 登录成功对象不变 |
| C `/api/v1/workspace/ai-replies` | A/RAG/LLM运行失败改为502/503 Error Envelope，禁止伪装为成功草稿。 | 成功对象不变 |
| C知识发布 | 同商品有效租约冲突返回409 `AI_KNOWLEDGE_PUBLISH_IN_PROGRESS`。 | 成功receipt不变 |
| Gateway `/gateway/v1/*` | 无schema、HMAC、route或语义变更。 | 完全不变 |

Repository contracts协调版本为`0.13.0`；Gateway wire仍为`1.0`。

## 4. 数据库与运行资产

- 新迁移：`0016_production_hardening_v1`，增加登录失败bucket、发布租约字段和默认Store数据库约束。
- 隔离验证：`0013 → head(0016) → 0013 → head`通过。
- 正式SQLite在任何验证写入前已备份；迁移验证后按任务边界恢复原件。最终状态为`0013_user_management_v1`、`integrity_check=ok`、0 foreign-key violation，SHA-256为`EA7C002D9C968C6D8A291FBBF087599B84602EFA8BA13A0192BE6E9327CD7C57`。
- 迁移前备份：`.runtime/phase-e/data/backups/production-hardening-v1/standard-platform-20260806T114400Z.sqlite3`，hash与恢复后的正式库一致。
- 所有正式服务在交接时停止，8000/8011/5173/5174均无监听。

## 5. 测试结果

| Gate | 结果 |
|---|---|
| A Backend | `150 passed, 3 skipped`；3项为显式opt-in真实外部环境E2E |
| C Backend / migrations | `155 passed` |
| B Frontend | `36 files / 164 passed`；时钟修复后连续3轮与最终复跑全绿 |
| Admin | `34 files / 85 passed` |
| Contracts | `15 passed`；20个JSON Schema语法有效 |
| Security专项 | A 6项、C 6项专项通过；另含并发Session、去敏日志、内部鉴权、TLS fail-closed与Web header strip测试 |
| Production Web | 3项静态/代理/Host与路径边界测试通过 |
| Windows Runtime | 16套完整脚本回归通过；最终受鉴权/TLS影响套件再次通过 |
| Type / Build | B和Admin typecheck、production build通过 |
| Dependency | A/C `pip check`通过；B `npm audit`、Admin `pnpm audit`均为0 known vulnerability |
| Diff / CI | `git diff --check`通过；6个Workflow YAML解析通过 |

## 6. 兼容性证明

- Gateway canonical schema SHA-256仍为`fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`，对应文件和runtime contract实现均无diff。
- RAG向量库仍为188416 bytes，SHA-256仍为`0c6ca2e39618dd81ad764e7063ec787cc441316415a3d857de86d4b47fb41417`；未执行sync、clear、rebuild、重切片或重embedding。
- 未修改或连接Channel Engine、PDD Adapter、真实PDD、Prompt、模型、R006/R009及自动发送边界。
- AI建议仍必须人工确认；本轮没有新增发送或执行能力。

## 7. 剩余风险与下一步

1. 当前仓库叠加R020–R024未提交候选，标准启动CLEAN Gate会正确拒绝。下一步必须按精确文件清单形成受控commit/clean RC，不能使用`git add .`。
2. 正式库按任务边界保持0013。部署0014–0016必须在clean SHA、停服、已验证备份与回滚窗口下执行，随后做同SHA start/status/stop。
3. LAN启动现在要求受信TLS证书/key；证书签发、信任分发、轮换与到期监控是部署输入，未配置时系统fail closed。
4. 真实RAG/模型、第二台客服电脑、真实PDD与生产Channel Engine E2E未执行，仍是独立验收Gate。
5. 现存P2维护项包括B主chunk偏大、Workspace/User列表扩展后的N+1/分页、HTTP client连接池、旧组件拆分及测试库deprecation warning；不应在本任务中做大规模业务重构。
6. Workflow已本地解析并按等价命令通过，远端GitHub Actions仍需在受控PR上实际执行。
7. 当前主机WMI/CIM进程元数据提供程序曾持续超时；Runtime保持有界查询并在身份不可验证时fail closed，稳定性测试也不再依赖主机WMI必然可用。进入正式部署验证前仍应恢复并确认Windows Management Instrumentation服务健康，否则status/stop会安全拒绝无法验证的进程。

## Final Status

`AI_CS_PRODUCTION_HARDENING_READY`
