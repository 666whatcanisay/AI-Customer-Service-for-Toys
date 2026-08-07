# R029 AI-CS Current Capability Validation V1 Task Card

- Requirement: `R029`
- Date: `2026-08-07`
- Owner: AI-CS Production Simulation Analyst
- Target: `AI_CS_CURRENT_CAPABILITY_VALIDATION_REPORT_READY`
- Status: `COMPLETE`

## Objective

对当前AI-CS、Runtime数据、RAG集合与Windows Channel Agent进行只读能力盘点，选择下一阶段模拟客服电脑最合适的数据基线，并形成真实PDD接入前的能力与缺口报告。

## Authorized scope

- 只读检查AI-CS与AI-CS-Channel-Execution-Engine的Git、Runtime状态、版本、数据库、RAG集合、Windows Client打包证据、测试与既有报告。
- 新增本任务卡、最终能力报告，以及任务完成所需的状态、变更、交接和machine-context文档。

## Safety boundary

- 不修改业务代码、API、数据库、RAG、Prompt、模型、Gateway Contract、Channel Engine或PDD Adapter。
- 不启动真实PDD，不读取或发送真实客户消息，不执行浏览器写操作。
- 不输出密码、hash、session/token、secret、客户消息正文、完整日志或原始知识内容。
- 不清空、重建、重切片、重embedding或重命名任何RAG集合；不迁移或写入任何数据库。

## Acceptance criteria

1. 当前Runtime版本、Git SHA/clean状态、数据库revision、RAG集合、模型/服务状态和启动方式均有现场证据。
2. 盘点工作区内数据库与RAG候选，使用数量、完整性、知识覆盖和测试证据选择下一阶段推荐基线。
3. 确认Windows Channel Agent的实际版本、包形态、安装/启动方式、当前是否运行、可模拟范围及缺失能力。
4. 将用户、RBAC、Store、Product/SKU、AI回复和Feedback与PDD、消息读取、浏览器控制、发送执行明确区分为已完成、模拟可用或未完成。
5. 给出客服电脑模拟流程、人工参与点和真实PDD接入准备清单；不得把Fake/设计能力写成真实生产能力。
6. 报告、状态、变更、交接和machine-context一致，Markdown/JSON通过检查；Git仅包含文档变化。

## Completion evidence

- AI-CS审计业务源码锚点：`codex/ai-cs-user-experience-acceptance-final-v1@785cff1fbcc79e7110314615673df8d28ee491e6`；业务源码无未提交修改，最终报告commit另行由Git解析。
- 在线隔离Runtime：四服务健康，但受管记录仍指向clean `2af974148e43c13736d63510fb7466658877a112`，与审计业务源码锚点不一致；已登记为下一阶段启动前阻断项。
- 推荐数据：R027隔离数据库`0016_production_hardening_v1`与同目录RAG集合`test_knowledge_v031`（70 embeddings），只允许继续用于隔离模拟。
- Windows Client候选：`ChannelAgent.exe 1.1.1`可执行且包hash已核对；当前未安装、未运行、未签名，其来源仓库有27项dirty记录，不能当作已冻结生产RC。
- Contract保护：Gateway canonical SHA-256为`FEF35AFB67DCD5027D7AA59FF35E5B6035A4130C5C1957AB41D4397D5FA67B80`，AI-CS和Engine contract目录无改动，`15 passed`。
- 未连接PDD，未读取或发送客户消息，未操作数据库/RAG，未修改任何业务代码。
