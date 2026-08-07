# R030 AI-CS Customer PC Deployment Preparation V1 Task Card

- Requirement: `R030`
- Date: `2026-08-07`
- Owner: AI-CS Customer PC Deployment Engineer
- Target: `AI_CS_CUSTOMER_PC_DEPLOYMENT_READY`
- Status: `COMPLETE / PASS`

## Objective

以当前电脑模拟未来客服电脑，按正式Windows Client安装、Channel Agent身份绑定、AI-CS Runtime关联和Workspace设备状态流程完成受控部署准备；不接入PDD。

## Phase 1 hard gate

在任何清理候选、安装、配置、启动、授权或绑定操作前，必须核对：

- AI-CS当前Git SHA/工作树、在线Runtime SHA、R027数据库revision和RAG集合。
- Channel Agent当前分支/工作树、Client版本、ZIP与EXE SHA-256。
- 任一要求的源码/Runtime身份不一致时立即停止，只生成《Customer PC Deployment Baseline Report》并登记补救入口。

## Authorized scope after gate pass

- 在Channel Engine仓库精确固化Windows Client 1.1.1相关候选，禁止`git add .`。
- 使用Windows Client安装器安装到当前用户目录，通过外置Runtime配置连接受控Channel Engine。
- 使用既有`ux_kefu`与既有测试店铺完成人工授权、设备/用户/店铺绑定和Workspace设备状态验证。
- 生成部署准备报告、状态、变更、交接和machine-context记录。

## Safety boundary

- 不修改Gateway Contract、AI-CS业务逻辑、PDD Adapter、RAG、Prompt、模型或自动发送边界。
- 不连接PDD，不读取或发送真实客户消息，不自动输入账号密码，不绕过人工授权或扫码。
- 不把密码、Session、binding code、secret、客户内容、完整日志、数据库或RAG写入Git或报告。
- Channel Agent候选未clean、未完成身份对齐或未通过Gate时，不得安装、启动、授权或绑定。

## Acceptance criteria

1. AI-CS源码与在线Runtime同一clean SHA；R027数据库为0016且RAG为`test_knowledge_v031` 70 embeddings。
2. Channel Agent有clean commit、明确版本、ZIP/EXE hash和可追溯安装包。
3. Windows Client通过安装器完成安装、配置、启动并记录非敏感目录与状态。
4. `ux_kefu`经人工授权绑定既有测试店铺；Agent ONLINE、Server收到Heartbeat、Workspace显示设备且Store权限隔离通过。
5. 不接PDD；明确PDD Adapter、Browser Control、Message Listener与Send Executor仍是下一Gate依赖。
6. 任一Phase 1身份不一致时，任务状态转为`BLOCKED`并停止后续阶段，不得伪报最终Ready。

## Phase 1 result

- AI-CS当前HEAD为`51da46fa1748bf806fcc18530778f7b26ac5844f`；现场检查前工作树clean，本任务新增文档后仅有本任务文档变化。
- R027四个在线服务均健康，但受管记录全部指向clean `2af974148e43c13736d63510fb7466658877a112`，与当前HEAD不一致。
- R027数据库为`0016_production_hardening_v1`、完整性`ok`；RAG集合`test_knowledge_v031`为512维/70 embeddings、完整性`ok`。
- Channel Agent候选为`main@673ce7e1e89cca977463e2e98cec8d00055a6e98`，工作树27项dirty；Client 1.1.1包和EXE hash已核对，但EXE未签名、当前未安装且未运行。
- Gate：`FAIL / AI_CS_CUSTOMER_PC_DEPLOYMENT_BLOCKED_BASELINE_IDENTITY_MISMATCH`。已按用户规则停止Phase 2–5；未停止Runtime、未修改Engine、未安装Agent、未配置或绑定身份/店铺。

## Remedial entry

1. 选择包含本Baseline Report的最终AI-CS clean提交作为唯一部署SHA。
2. 在独立执行轮次使用R027受管配置安全停止四服务，从该同一clean SHA重建B/Admin并重启A/B/C/Admin；四条Runtime记录必须完全一致。
3. 身份对齐通过后，按精确清单审计并固化Channel Agent 1.1.1 dirty候选；禁止`git add .`，先完成测试、包重建、hash和签名/风险批准。
4. 重新执行Phase 1。只有AI-CS与Agent两侧均通过，才允许安装、配置、授权、绑定和Heartbeat验证。

## Final execution result

- 初始Phase 1失败已按补救入口关闭：AI-CS四服务从同一clean提交重启并通过Runtime身份核对；R027隔离数据库保持`0016_production_hardening_v1`，RAG保持`test_knowledge_v031` 512维/70 embeddings。
- Channel Agent 1.1.1候选已精确固化为clean提交`0a5a041e72bb9daec9813d5d4b7f7907eb8ce86f`；生产服务身份补齐提交为`5c105dbe855c09dfe31c9d2bbf5d18caec40b32b`，未修改Gateway Contract、PDD Adapter或渠道执行语义。
- 重建包`AI-CS-Channel-Agent-1.1.1-windows-x64.zip` SHA-256为`FD2D37746030584DC5EF34EFB7001E752B71FD4C9EC04FD25DD82F8943CD6138`；EXE SHA-256为`92252395A70B7415A524934A5661CB95C25F2ADB7B1CF69AA38E575AF392DF33`。EXE未签名，仅在用户明确批准后用于本机受控安装。
- Windows Client通过包内安装流程安装到当前用户目录，Agent自启动已启用；Agent `agent-desktop-0345200` / device `device-desktop-0345200`为`ACTIVE / ONLINE`，服务端收到Heartbeat。
- `ux_kefu`通过人工一次性授权流程绑定既有测试店铺`PDD-SM`；角色严格为`CUSTOMER_SERVICE`，只有一个默认Store绑定，Engine与AI-CS授权Store集合一致。
- 用户已人工确认Workspace显示设备在线。消息读取、浏览器自动化与发送能力均保持关闭；未连接PDD、未读取或发送真实客户消息。
- Final Gate：`PASS / AI_CS_CUSTOMER_PC_DEPLOYMENT_READY / LOCAL_CONTROLLED_DEPLOYMENT / PDD_NOT_CONNECTED`。
