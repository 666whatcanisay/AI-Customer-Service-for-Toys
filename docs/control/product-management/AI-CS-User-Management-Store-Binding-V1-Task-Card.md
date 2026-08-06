# AI-CS User Management & Store Binding V1 Task Card

## 任务

- Requirement：`R016`
- Owner：C IAM / B Workspace / C Admin / A control-route authorization and credential bridge / shared contracts
- Goal：为客服、运营和管理员建立真实身份、固定RBAC、Store绑定与服务端Workspace授权。
- Gate：`AI_CS_USER_MANAGEMENT_READY`

## 范围

- 新增C权威用户、角色、用户角色、Store绑定和opaque session。
- 新增登录、当前用户、退出、ADMIN用户管理及authenticated Workspace facade。
- B使用服务端身份和默认Store；Admin提供登录和用户管理。
- A的AI管理路由向C验证Bearer运营权限，并为既有A→C分析桥接透传发起人的同一凭证。
- 共享contracts增加IAM V1 schema、版本、changelog和兼容说明。

## 禁止边界

- 不修改Channel Engine RC1、Gateway Contract V1或PDD Adapter。
- 不修改R006、R009、商品数据库语义、RAG、Prompt或模型。
- 不以浏览器按钮隐藏代替服务端授权，不保存明文密码或session token。

## 验收

- 用户CRUD、登录/退出、session撤销、RBAC、默认Store和越权Store拒绝。
- B登录/路由/默认Store、Admin登录/路由/用户管理。
- C迁移往返、共享Contract、A/B/C/Admin全量回归、typecheck和production build。
- 完成报告：`docs/control/AI-CS-User-Management-Store-Binding-V1-Completion-Report.md`。
