# 《AI-CS User Management & Store Binding V1 Completion Report》

> Requirement：R016
> 日期：2026-08-06
> 实现基线：`release/product-reliability-hardening-v1` / `0e422c50fd886f8b2f250ce98f11ff7a8c8b05c5`
> Contract bundle：`0.9.0`（Gateway wire仍为冻结`1.0`）
> Database revision：`0013_user_management_v1`
> Final Gate：`AI_CS_USER_MANAGEMENT_READY`

## 1. 交付结论

AI-CS现已具备用户管理V1源码能力：C是身份、角色、session和Store绑定的唯一权威；B客服工作台和C Admin都必须登录；权限和Store范围由C API服务端执行。现有Human Workspace人工确认链、R006、R009、商品知识、RAG、Prompt、模型、PDD Adapter和Gateway Contract V1未改变。

本报告的`READY`表示实现、迁移、契约和自动化质量门已完成。正式数据库迁移、首个生产ADMIN创建、TLS入口、登录限流/告警以及真实员工账号验收仍属于受控部署步骤，不在本源码任务中伪报为已执行。

## 2. 数据模型

| 表 | 关键字段/约束 | 说明 |
| --- | --- | --- |
| `users` | `id`、`username`、`username_normalized`、`password_hash`、`display_name`、`status`、时间戳 | 用户名大小写无关唯一；只存scrypt hash。 |
| `roles` | `id`、唯一`role_name` | 固定种子：`ADMIN`、`OPERATOR`、`CUSTOMER_SERVICE`。 |
| `user_roles` | 复合主键`user_id + role_id` | 用户与角色多对多。 |
| `user_store_bindings` | `id`、`user_id`、`store_id`、`is_default`、`created_at` | 复用既有`test_catalog_stores`外键；同一用户/Store唯一。客服必须恰有一个默认Store。 |
| `user_sessions` | `id`、`user_id`、`token_hash`、创建/过期/撤销时间 | 浏览器只得到一次opaque token；数据库只保存SHA-256 digest。 |

迁移`0013_user_management_v1`是对0012的纯新增演进。未创建第二套Store模型，未修改商品、知识、导入、发布、RAG或Gateway数据结构；隔离SQLite的upgrade/downgrade/upgrade已由迁移测试覆盖。

## 3. API

### 身份

| Method / Path | 认证 | 行为 |
| --- | --- | --- |
| `POST /api/v1/auth/login` | 账号密码 | 返回`ai-cs.iam.v1` opaque Bearer session和用户投影；`Cache-Control: no-store`。 |
| `GET /api/v1/auth/me` | Bearer | 返回服务端当前用户、角色、权限和Store绑定。 |
| `POST /api/v1/auth/logout` | Bearer | 立即撤销当前session，返回204。 |

### ADMIN用户管理

| Method / Path | 行为 |
| --- | --- |
| `GET /api/v1/admin/users/roles` | 返回三种固定角色。 |
| `GET /api/v1/admin/users` / `GET /{user_id}` | 用户列表/详情。 |
| `POST /api/v1/admin/users` | 创建用户并原子保存角色、Store绑定和强密码hash。 |
| `PATCH /api/v1/admin/users/{user_id}` | 修改显示名、密码或状态；改密/停用会撤销session。 |
| `DELETE /api/v1/admin/users/{user_id}` | 逻辑停用，不物理删除审计关联。 |
| `PUT /api/v1/admin/users/{user_id}/roles` | 替换固定角色集合。 |
| `PUT /api/v1/admin/users/{user_id}/store-bindings` | 替换Store绑定并校验唯一默认店铺规则。 |

### Workspace facade

- `GET /api/v1/workspace/ai-health`
- `POST /api/v1/workspace/ai-replies`

B不再通过Vite直接代理A `/api/chat`。C先验证`workspace.access`/`ai.reply`、绑定Store、Store内Product和SKU，再将原请求/响应结构转发给loopback A `/api/chat`。因此A回答协议、Human Workspace状态机与人工确认语义保持兼容，同时浏览器无法绕过Store授权直接调用A。

所有失败沿用C统一非2xx Error Envelope。401区分缺少/无效凭证和过期/撤销session；403用于角色或Store越权；422用于角色/默认Store约束；409用于用户名冲突。业务失败不返回HTTP 200。

Admin同源代理可达的A `/api/admin/ai/**`端点也会逐请求向C `/api/v1/auth/me`验证Bearer和运营权限，避免绕过页面路由直接调用模型或读取控制面。R006两条loopback-only知识发布服务接口保持原内部兼容；`/api/admin/server-runtime`继续作为不含secret/业务数据的只读运行健康投影。

## 4. 页面与Workspace集成

### B客服工作台

- 新增`/login`和`/forbidden`，路由需要`workspace.access`。
- session恢复从`/api/v1/auth/me`取得真实`user_id`、显示名、角色和Store。
- `CUSTOMER_SERVICE`自动使用管理员绑定的唯一默认Store；不再要求每次手工选择店铺。
- 所有目录、AI建议、知识状态、Feedback/interaction API均附带Bearer凭证；401会清除本地session。
- 旧tester identity仅保留给既有组件/测试兼容，不再是Runtime身份或授权来源。

### C Admin

- 新增Admin登录、无权限页和服务端身份恢复。
- 新增“用户管理”页面：查看、创建、角色分配、默认Store绑定和逻辑停用。
- 导航隐藏只改善体验；后端对全部管理接口再次执行`product.manage`、`knowledge.manage`、`feedback.view`或`user.manage`权限校验。

## 5. 权限矩阵

| 角色 | 服务端权限 | Store规则 |
| --- | --- | --- |
| `CUSTOMER_SERVICE` | `workspace.access`、`ai.reply`、`feedback.submit` | 必须绑定且仅能使用自己的唯一默认Store；Product/SKU继续向下校验。 |
| `OPERATOR` | `product.manage`、`knowledge.manage`、`feedback.view` | 运营接口；不获得Workspace或用户管理权限。 |
| `ADMIN` | 上述全部 + `user.manage` | 全Store管理权限，可创建/分配/停用账号。 |

用户提交的`created_by`不再是普通账号的授权依据：C从认证principal派生用户ID。只有ADMIN为旧fixture/导入兼容保留显式引用能力。

## 6. 安全设计

- 密码：Python标准库scrypt，`N=16384/r=8/p=1`、每个密码随机16-byte salt、32-byte派生值和可升级版本编码；使用constant-time比较。
- Session：至少256-bit随机opaque token，数据库仅存SHA-256 digest；默认480分钟；logout、改密、停用立即撤销。
- 防用户名枚举：未知账号仍校验固定sentinel hash；登录错误统一返回相同401消息。
- 浏览器：token只存当前tab的`sessionStorage`，不写localStorage；登录/me响应`no-store`；401统一清理。
- 服务边界：C服务端RBAC和Store scope是权威；CORS允许头显式加入`Authorization`但不被当作授权机制。
- 初始化：`bootstrap_ai_cs_admin.ps1`加载同一受控Runtime数据库配置，再由交互式CLI通过`getpass`创建首个ADMIN；密码不进入命令参数、`.env`或脚本。

## 7. Contract状态与兼容证明

- 新增`identity-access-management.v1.schema.json`，覆盖Login、CurrentUser、User管理、角色和Store绑定对象。
- repository contract bundle由0.8.0增量提升到0.9.0，并同步schema、README、CHANGELOG、error code和compatibility note。
- Gateway `channel-engine-gateway-server.v1.schema.json`未修改，wire仍为`contract_version=1.0`。
- A `/api/chat`请求/响应语义未修改；B的人审、不自动发送、不自动退款、不修改订单边界未修改。
- R006客服目录、R009导入、商品知识库、RAG、Prompt、模型和PDD Adapter没有语义修改。

## 8. 测试结果

| Gate | 结果 |
| --- | --- |
| C IAM专项 | 登录/hash/token digest/logout、用户CRUD、RBAC、Store投影/越权、Workspace转发、客服默认Store：PASS。 |
| C迁移 | 0012→0013、表/外键/默认角色、downgrade/upgrade：PASS。 |
| C Backend全量 | `127 passed`。 |
| A IAM/控制面专项 | `32 passed`；包含Bearer向C验权、路由覆盖、角色拒绝和Authorization透传。 |
| A Backend全量 | `147 passed, 3 skipped`；跳过项均为显式环境变量启用的真实模型/服务E2E。 |
| B Frontend | `32 files / 139 tests`，typecheck PASS，production build PASS。 |
| C Admin | `32 files / 82 tests`，typecheck PASS，production build PASS。 |
| Shared Contract | `9 passed`。 |

生产构建仅有既有B大chunk和Vite依赖注释告警，无构建失败。测试未连接真实PDD、生产Channel Engine、真实客服账号或正式数据库。

## 9. 文件范围

- C Provider：`platform_backend/app/iam/**`、`platform_backend/app/workspace/**`、0013 migration、API挂载/授权依赖及测试。
- B Consumer：`frontend/src/auth/**`、登录/无权限页面、路由、authenticated HTTP和Workspace默认Store接入。
- C Admin：`admin_web/src/auth/**`、登录/无权限/用户管理页面、路由与API client。
- A Compatibility：AI管理端点向C验证Bearer运营权限；三项A→C analysis service透传同一Authorization。A不保存身份或token。
- Shared：contracts 0.9 IAM schema/compatibility/tests和A/B/C/Control上下文文档。
- OPS bootstrap：`scripts/windows/bootstrap_ai_cs_admin.ps1`只加载既有Runtime配置并启动交互CLI；不保存密码或新增运行状态。

不包含数据库文件、运行目录、日志、evidence、依赖、构建产物、明文secret、密码、token、客户数据或知识源。

## 10. 剩余风险与后续Agent依赖

1. OPS/Deployment：备份正式C数据库，使用既有wrapper迁移到0013，校验integrity/revision；禁止手工重建表。
2. Security/OPS：在任何真实员工流量前配置受信TLS/反向代理、登录失败限流/监控告警和安全header。V1没有MFA、SSO、refresh token或集中式IAM审计台。
3. Admin：通过`bootstrap_ai_cs_admin.ps1`交互创建首个ADMIN；随后立即用页面创建最小权限的OPERATOR和CUSTOMER_SERVICE，客服必须绑定默认Store。
4. QA：用三个非生产账号做真实浏览器401/403、跨店拒绝、停用session失效和默认Store验收；不连接真实PDD或生产Channel Engine。
5. Future IAM：密码重置、自助恢复、MFA/SSO、细粒度permission资源和集中审计若需要，必须另立Contract/数据保留/恢复Gate，不能在V1接口上静默扩展。

## Final Status

`AI_CS_USER_MANAGEMENT_READY`
