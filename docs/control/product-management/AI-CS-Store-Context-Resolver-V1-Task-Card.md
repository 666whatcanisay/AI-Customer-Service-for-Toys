# R020 AI-CS Store Context Resolver V1 Task Card

## 任务

- Requirement：`R020`
- Owner：C Workspace/IAM / B Customer Workspace / C Admin / shared contracts
- Goal：把客服多店绑定收敛为正式默认店铺工作流，并以C权威目录完成会话商品/SKU解析和AI上下文注入。
- Gate：`AI_CS_STORE_CONTEXT_READY`

## 范围

- CUSTOMER_SERVICE查看授权店铺、持久化唯一默认店铺并在授权范围内切换；OPERATOR和ADMIN继续使用角色级全店范围。
- 新增C Workspace上下文和Conversation Context Resolver；仅使用C客户可用目录匹配商品/SKU。
- 唯一候选自动解析；多候选进入人工确认；零候选返回`UNKNOWN`；不跨店猜测。
- B Workspace登录后自动使用服务端默认店铺，先解析后生成；只有歧义时要求人工确认。
- C Admin展示客服绑定/默认店铺、店铺范围和不含客户原文的解析记录。
- 共享contracts增加Store Context V1 schema、版本、changelog、兼容说明和受影响线审查。

## 禁止边界

- 不修改Gateway Contract V1、Channel Engine RC1或PDD Adapter。
- 不修改R006/R009业务语义、商品数据库核心、RAG、Prompt、模型或A `/api/chat`。
- 不自动发送，不把前端隐藏作为权限控制，不持久化客户消息原文。
- 不迁移或改写正式Runtime数据库；开发验收只使用隔离测试数据库与迁移往返。

## 验收

- 客服登录、绑定、默认店铺、授权切换、越权拒绝和全店角色回归。
- 商品唯一/多候选/未知，SKU唯一/多候选/无SKU/未知及人工确认。
- Workspace服务端上下文注入、旧chat兼容、Admin解析记录和最小审计。
- C/B/Admin/contracts全量测试、typecheck/build、0014隔离迁移往返、Gateway schema SHA与RAG基线不变。
- 完成报告：`docs/control/AI-CS-Store-Context-Resolver-V1-Completion-Report.md`。
