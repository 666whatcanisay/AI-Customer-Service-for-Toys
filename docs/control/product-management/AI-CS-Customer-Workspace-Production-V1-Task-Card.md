# R021 AI-CS Customer Workspace Production V1 Task Card

## 任务

- Requirement：`R021`
- Owner：B Customer Workspace；C身份、Store Context、AI Interaction Event与AI Feedback接口仅作为已冻结Provider消费
- Goal：在不接真实渠道的前提下，把现有三栏副驾驶收敛为可连续处理客户会话、人工确认AI建议并记录反馈的生产工作流。
- Gate：`AI_CS_CUSTOMER_WORKSPACE_PRODUCTION_READY`

## 范围

- 三栏Workspace固定为Conversation Center、AI Reply Assistant、Decision Center。
- 客服状态覆盖`ONLINE/BUSY/OFFLINE`；会话状态覆盖`NEW/PROCESSING/WAITING_REPLY/COMPLETED`并提供队列筛选。
- 登录后自动使用C返回的授权默认Store；生成前继续调用R020 Product/SKU Resolver。
- AI建议同时展示回复草稿、商品/SKU依据、知识引用、风险和待补充字段。
- 人工决策覆盖采用原稿、修改后采用、拒绝回复、标记问题；采用事件、人工修改、拒绝/问题原因均通过既有幂等Feedback契约保存。
- 未接渠道期间提供只在当前页面内存中保留的受控人工消息入口，不把人工录入标识成PDD或Channel Engine消息。

## 契约与权限边界

- 不新增接口，不修改repository contracts `0.11.0`；只消费既有Workspace、Store Context、AI Interaction Event与AI Response Feedback契约。
- C继续在服务端执行登录、RBAC和Store scope裁决；B路由与按钮只提供UX门禁，不能替代HTTP鉴权。
- `CUSTOMER_SERVICE`仅处理授权Store；运营的数据查看和管理员全权限继续由C/Admin既有RBAC入口承担。
- 客户消息不写入localStorage/sessionStorage、日志、Git或报告；行为事件继续使用去标识化摘要和240字符客户端上限。

## 禁止边界

- 不连接PDD，不修改Channel Engine RC1、Gateway Contract V1、PDD Adapter、A `/api/chat`、RAG、Prompt或模型。
- 不自动发送客户消息，不以复制动作伪造渠道发送成功，不自动完成会话。
- 不修改C线业务源码、数据库或正式Runtime；不执行0014正式迁移。

## 验收

- 登录/路由、授权Store、客服状态、四态会话流转和新消息重开。
- Product/SKU识别、AI草稿、知识依据、风险提示和人工确认。
- 采用、修改后采用、拒绝原因、问题标记、幂等回执及失败不显示本地成功。
- B全量test/typecheck/build、A/C/Admin/contracts保护回归、Gateway与A/RAG指纹不变。
- 完成报告：`docs/control/AI-CS-Customer-Workspace-Production-V1-Completion-Report.md`。
