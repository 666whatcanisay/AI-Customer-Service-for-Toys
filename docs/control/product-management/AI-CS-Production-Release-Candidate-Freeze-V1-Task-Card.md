# R025 AI-CS Production Release Candidate Freeze V1 Task Card

- Requirement：`R025`
- Date：`2026-08-06`
- Owner：AI-CS Release Engineer
- Release reference：`ai-cs-production-rc-v1`
- Target：`AI_CS_PRODUCTION_RC_READY`
- Status：`COMPLETE`

## Baseline

- Repository：`release/product-reliability-hardening-v1@bd6e10c4cb084a4b804ec37432a93b293b3c1c08`，叠加R020–R024源码候选。
- Candidate inventory：110个tracked diff文件、58个untracked文件；任务开始时工作树dirty，禁止覆盖、丢弃或使用`git add .`。
- Formal database：`0013_user_management_v1`，integrity `ok`、0 foreign-key violation；本任务只在隔离数据库验证0014–0016，不迁移正式Runtime。
- Gateway wire：`1.0`，canonical SHA-256 `fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`。
- RAG vector baseline：188416 bytes，SHA-256 `0c6ca2e39618dd81ad764e7063ec787cc441316415a3d857de86d4b47fb41417`。

## Scope

1. 审计并精确固化R020 Store Context、R021 Customer Workspace、R022 Desktop Workflow、R023 Audit与R024 Hardening协调候选。
2. 冻结并验证`0013 → 0014 → 0015 → 0016`迁移顺序、升级、降级与再次升级。
3. 执行A/C/B/Admin/contracts/security/build/依赖/Windows Runtime全量Gate。
4. 创建独立Release branch、受控commit和本地annotated RC tag，最终工作树必须clean。
5. 输出部署清单、环境要求、备份/回滚方案和RC冻结报告。

## Forbidden changes

- 不修改Gateway Contract V1 canonical schema、Gateway HMAC/route/语义、Channel Engine、PDD Adapter、自动发送逻辑、Prompt、模型或R006/R009业务逻辑。
- 不连接真实PDD或生产Channel Engine，不执行RAG sync/clear/rebuild/re-slice/re-embedding，不写真实知识。
- 不提交`.env`、数据库、向量、知识源、Runtime、secret、日志、evidence、依赖、构建产物或客户数据。
- 不使用`git add .`；每个暂存路径必须来自审计后的显式manifest，提交前必须检查`git diff --cached`。

## Acceptance criteria

1. Release branch、commit和annotated RC tag存在，工作树clean，source fingerprint可复核。
2. 0013–0016线性单head，隔离升级/降级/再升级与约束检查通过；正式数据库保持0013。
3. Backend、Frontend、Admin、Contract、Security、Build、依赖与Windows Runtime Gate全部通过。
4. Secret/禁止资产扫描通过，Gateway canonical SHA与RAG向量指纹不变，外部Channel Engine目录没有本任务写入。
5. 生成《AI-CS Production Release Candidate Freeze V1》并同步README、状态看板、变更、交接和四线machine-context。

## Acceptance result

- Gate：`PASS / AI_CS_PRODUCTION_RC_READY`。
- Release：`release/ai-cs-production-rc-v1`与annotated tag `ai-cs-production-rc-v1`；精确SHA由Git解析并在最终交接输出。
- Migration：单head 0016；0014、0015及`0013→0016→0013→0016`隔离回归通过；正式数据库保持0013且hash不变。
- Tests：A150/3 skipped、C155、B164、Admin85、contracts15、Production Web3、Windows Runtime16/16；typecheck/build/audit/pip check通过。
- Protection：Gateway canonical schema与RAG向量指纹不变；无禁止资产或真实secret；Channel Engine、PDD Adapter和自动发送边界未修改。
- Evidence：[Freeze Report](../AI-CS-Production-Release-Candidate-Freeze-V1.md)与[Deployment Checklist](../AI-CS-Production-RC-V1-Deployment-Checklist.md)。
