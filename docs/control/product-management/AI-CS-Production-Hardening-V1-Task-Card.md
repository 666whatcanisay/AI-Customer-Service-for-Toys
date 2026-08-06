# R024 AI-CS Production Hardening V1 Task Card

- Requirement：`R024`
- Date：`2026-08-06`
- Owner：AI-CS Production Hardening Engineer
- Target：`AI_CS_PRODUCTION_HARDENING_READY`
- Status：`COMPLETE / SOURCE_ONLY`

## Baseline

- Repository：`release/product-reliability-hardening-v1@bd6e10c4cb084a4b804ec37432a93b293b3c1c08`叠加R020–R023未提交候选；任务开始时99项dirty，禁止覆盖或清理既有变更。
- Contracts：`0.12.0 / coordinated`；Gateway wire `1.0` canonical SHA-256 `fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`。
- 正式C数据库：只读revision `0013_user_management_v1`、integrity `ok`、0 foreign-key violation；源码migration head为0015。本轮不得直接迁移正式库。
- RAG保护：`backend/vector_db/chroma.sqlite3` 188416 bytes，SHA-256 `0c6ca2e39618dd81ad764e7063ec787cc441316415a3d857de86d4b47fb41417`；禁止清空、覆盖、重建或发布真实知识。
- 审计输入：[AI-CS Code Quality Audit V1 Report](../AI-CS-Code-Quality-Audit-V1-Report.md)。

## Scope

1. 为C内部投影增加独立服务身份，补齐生产API认证、授权与负面测试。
2. 修复Session撤销、过期/并发处理；增加登录失败计数、冷却与去敏审计。
3. 生产LAN入口改为预构建静态产物，禁止Vite dev server；保留开发入口。
4. 让Workspace RAG运行失败返回明确非2xx Error Envelope，同时保持legacy `/api/chat`与Gateway wire兼容。
5. 为同商品知识发布增加并发冲突防护，保留旧版本失败回滚语义。
6. 增加去敏结构化异常日志、request ID约束、CI、稳定时钟和安全测试。

## Forbidden changes

- 不修改Channel Engine、Gateway Contract、PDD Adapter、R006/R009、Prompt、模型、自动发送边界或业务流程。
- 不连接真实PDD/生产Channel Engine，不输出密码、Token、Secret、客户内容或完整上游响应。
- 不修改/迁移正式数据库，不写真实RAG/向量/知识，不使用`git add .`，不擅自提交既有dirty候选。

## Acceptance criteria

1. 审计P0/P1对应安全、稳定性、日志、CI和测试问题有代码与回归证据；未关闭项必须明确阻断Gate。
2. Backend、Frontend、Admin、Contract、Security、Build全量通过；时钟测试连续稳定。
3. 0013→head→0013隔离迁移往返及新迁移约束通过；正式DB保持0013且只读完整性正常。
4. Gateway schema SHA、RAG向量指纹和Channel Engine目录相对基线不变。
5. 输出《AI-CS Production Hardening V1 Completion Report》，Task Gate按真实证据返回PASS、CONDITIONAL PASS或FAIL。

## Acceptance result

- Gate：`PASS / SOURCE_ONLY / AI_CS_PRODUCTION_HARDENING_READY`。
- 回归：A `150 passed, 3 skipped`；C `155 passed`；B `164 passed`；Admin `85 passed`；contracts `15 passed`；Windows Runtime `16/16`；两前端typecheck/build与依赖审计通过。
- 正式数据库已恢复并保持`0013_user_management_v1`，完整性正常；0016仅在隔离数据库完成往返验证。
- Gateway canonical schema与RAG向量指纹不变；Channel Engine、PDD Adapter、Prompt、模型和自动发送边界未修改。
- 完整证据：[Completion Report](../AI-CS-Production-Hardening-V1-Completion-Report.md)。clean RC、正式迁移与TLS证书配置仍属于后续受控部署Gate。
