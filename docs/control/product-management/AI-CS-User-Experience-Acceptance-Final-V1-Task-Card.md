# R028 AI-CS User Experience Acceptance Final V1 Task Card

- Requirement: `R028`
- Date: `2026-08-07`
- Owner: AI-CS Final Release Validation Engineer
- Target: `AI_CS_USER_EXPERIENCE_ACCEPTANCE_READY`
- Status: `IN_PROGRESS`

## Objective

关闭 AI-CS Production RC 的最终 UX Gate：修复启动脚本中匿名调用 `/api/chat` 的 smoke，在不恢复匿名访问的前提下使用现有内部服务身份；随后在隔离 Runtime 与全新 Edge Profile 中完成四角色真实页面验收、AI 回复验收和全量发布回归。

## Authorized source scope

- `scripts/windows/common_ai_customer_service.ps1` 中 `Invoke-RagChatSmoke` 的内部认证调用。
- `scripts/windows/tests/**` 中与该 smoke 身份边界直接相关的回归测试。
- `frontend/src/views/HumanInLoopWorkspace.vue`、`frontend/src/components/humanLoop/**`、`frontend/src/stores/humanLoopWorkspace.ts`及其测试：仅限真人验收发现的人工回复阻断、中文业务流程和浅绿色界面最小修复。
- `docs/customer/**` 中对应B线状态、变更、交接和机器上下文记录。
- R028 报告、任务卡以及三线状态、变更、风险、交接和 machine context 文档。
- 忽略目录 `.runtime/r027-ux-acceptance-data-v1/**` 中的隔离验收数据库、向量、secret reference、Edge Profile 和非提交证据。

## Safety boundary

- 不恢复 `/api/chat` 匿名访问，不走用户登录，不向前端暴露内部 service token。
- 不修改 Gateway Contract、Channel Engine、PDD Adapter、Prompt、RAG 核心或自动发送；只允许修复真人验收确认的B端UX阻断和界面表达。
- 不连接 PDD，不发送真实消息，不使用真实客户数据。
- 不提交 secret、session/token、数据库、向量、日志、浏览器 Profile、知识源、构建产物或客户数据。
- 不清空、覆盖或全量重建正式数据库与向量库；验收只使用已隔离的 R027 数据资产。

## Acceptance criteria

1. `/api/chat` 匿名请求继续失败；启动 smoke 使用现有内部服务身份成功，且 token 仅由 secret reference 在 Runtime 读取。
2. 全新独立 Edge Profile 从固定登录 URL 启动；`admin`、`江`、`Wa`、`ux_kefu` 均通过真实登录、首次改密和各自核心业务页面验收。
3. 管理员完成查看用户、创建验收员工、分配中文岗位和绑定测试店铺；运营完成商品、SKU、知识查看；客服主管完成店铺选择/切换和工作台查看；普通客服完成 Workspace 与人工确认边界检查。
4. 问题“这个积木缺件怎么办？”返回 AI 建议、知识依据和风险提示，并保持人工确认、禁止自动发送。
5. 普通员工页面不显示 `store_id`、`product_id`、`resolution_id`、`session` 等内部技术字段，核心业务名称中文化，错误提示提供中文原因和下一步。
6. Backend、Frontend、Admin、Contract 与 Windows Runtime 回归通过；Gateway schema 指纹和 Channel Engine 工作树保持不变。
7. 正式数据库与正式向量资产指纹不变；隔离服务停止、Edge 关闭、验收 session 撤销。
8. 商品无法识别时仍可在同一回复草稿直接输入、确认和复制人工回复；人工内容不冒充AI、不提交AI采用数据、不自动发送，工作台采用浅绿色内容底色。

## Current verified progress

- 管理员、运营主管和客服主管真人核心流程已通过；客服主管完成店铺切换、浅绿工作台和未知商品人工回复检查，并接受当前人工复制发送边界。普通客服与最终AI回复仍待继续。
- 客服工作台人工回复与浅绿色主题源码完成并通过真人页面确认；B `37 files / 169 tests`、typecheck和production build通过。
- 最终Gate仍为`IN_PROGRESS`，不得在四角色与AI回复真人验收完成前声明READY。
