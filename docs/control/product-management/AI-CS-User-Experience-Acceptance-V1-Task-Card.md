# R026 AI-CS User Experience Acceptance V1 Task Card

- Requirement：`R026`
- Date：`2026-08-06`
- Owner：AI-CS Product Experience QA Lead
- Target：`AI_CS_USER_EXPERIENCE_ACCEPTANCE_READY`
- Status：`COMPLETE / GATE_BLOCKED`

## Baseline

- Source：`ai-cs-production-rc-v1@ae3fc58732ed7b11beed3f2361479b7b0be7e3c4`。
- Formal database：`0013_user_management_v1`；本任务只复制并迁移隔离副本，不写正式数据库。
- Product scope：IAM、RBAC、Store Context、Workspace、AI Reply、Feedback与Desktop Workflow。
- External scope：不连接真实PDD或生产Channel Engine，不产生自动发送。

## Participant journeys

1. 老板/管理员：登录、员工管理、角色说明、店铺绑定与系统状态。
2. 运营主管：商品、SKU、知识、FAQ、AI质量与店铺数据。
3. 客服主管：首次登录、店铺选择、客服状态与设备状态。
4. 新人客服：客户消息、AI建议、依据/来源/风险与人工确认。
5. 客服电脑：安装说明、启动、绑定、上线与异常恢复提示。

## Test rules

- 以没有技术背景的中国电商员工理解能力为准，不以接口或自动化测试存在代替页面可用性。
- 实际页面操作使用隔离Runtime；不打印密码hash、session token、客户内容或绑定码。
- 账号创建、首次改密、权限分配和设备绑定的最终提交不在正式环境执行；只检查页面引导，并用隔离测试证据验证链路。
- 记录所有英文技术词、内部ID、无下一步建议的错误和容易误操作的位置。

## Forbidden changes

- 不修改业务功能、API、数据库Schema、RAG、Prompt、Gateway Contract、Channel Engine、PDD Adapter或自动发送边界。
- 不写正式账号、Session、店铺、商品、知识、Feedback或Agent状态。
- 不提交Runtime、数据库、Secret、日志、截图、客户数据、依赖或构建产物。

## Acceptance criteria

1. 五类参与者旅程均有页面或可复核源码/测试证据。
2. 密码错误、权限不足、未绑定店铺、Agent离线和服务器异常均完成提示审查。
3. 问题按P0/P1/P2/P3分级，并明确上线前必须修复项。
4. 输出《AI-CS User Experience Acceptance Report V1》并同步状态、变更、交接和machine-context。
5. 最终状态只表示体验验收完成，不自动表示产品通过上线Gate。

## Outcome

- 独立 Edge、隔离 Runtime、四角色核心路径审查、最小 UX 修复和全量回归已完成。
- 代码层 P0/P1 已关闭；管理员凭据不匹配、AI 知识集合为空和普通客服账号缺失仍为 3 项环境 P0。
- Gate：`BLOCKED / AI_CS_USER_EXPERIENCE_ACCEPTANCE_BLOCKED`。
- Report：[`AI-CS User Experience Acceptance Gate V1`](./AI-CS-User-Experience-Acceptance-Gate-V1.md)。
