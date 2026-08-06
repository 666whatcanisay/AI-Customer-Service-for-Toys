# R017 AI-CS Initial Production Accounts Remediation V1 Task Card

## 任务身份

- Requirement ID：`R017`
- 状态：`BLOCKED`
- 当前 Gate：`AI_CS_INITIAL_ACCOUNTS_BLOCKED`
- Owner：Control / OPS / C IAM
- 创建日期：2026-08-06

## 目标

在不降低 R016 认证、密码、RBAC、Store binding 与审计边界的前提下，把三个初始生产账号安全创建到受控 Runtime，并完成登录、Session、角色和权限隔离验收。

## 当前阻塞

1. 正式 Runtime 数据库仍为0012，IAM 0013未部署，IAM 表不存在。
2. R016/R018 Candidate尚未形成可供production wrapper使用的受控clean source identity。
3. B/C/Admin/A鉴权桥必须按contracts `0.10.0 / coordinated`同批部署，不能混用0.9客户端。

R018已关闭旧策略阻塞：批准的账号格式和临时初始化值可用；`CUSTOMER_SERVICE`包含客服管理并在首次改密后自选多个已启用客服Store；`OPERATOR`和`ADMIN`由角色获得全Store。

## 解锁输入

- 明确授权受控提交、数据库备份、0013迁移和 Runtime 切换。
- 在受控控制台交互输入批准的临时初始化值；不得通过参数、文件、日志或文档传递。
- 明确由Production Account Administrator执行`bootstrap_ai_cs_initial_users.ps1`和真实三角色验收。

## 执行 Gate

1. 再次核验 branch/SHA/clean、受控配置与 Runtime DB identity。
2. 生成可恢复备份并校验完整性。
3. 迁移到0013并确认 IAM 表、默认角色和既有业务表数据不变。
4. 运行受控初始化脚本；它按规范化用户名检查重复，已存在账号逐个跳过且不覆盖。
5. 只经 R018 IAM 服务/受控初始化入口 hash 临时口令并创建角色；客服初始Store为空，运营/管理员由角色获得全Store；禁止直接 SQL 绕过。
6. 使用最小会话证据验证三类临时口令登录、强制首次改密、新Session、客服多Store、运营/管理员全Store、200/401/403和跨角色隔离；不记录 token 或密码材料。
7. 验收通过后更新报告与状态为 `AI_CS_INITIAL_ACCOUNTS_READY`。

## 禁止范围

- 不修改 R006、R009、RAG、Prompt、模型、Gateway Contract、PDD Adapter或 Channel Engine。
- 不创建虚假 Store，不覆盖重复账号，不保存/打印明文密码、hash或Session token。
- 不以 Admin UI 隐藏按钮代替服务端 RBAC，不把源码测试当作生产 Runtime 验收。

## 当前执行记录

2026-08-06：完成只读前置审计；数据库和账号零写入。详见 [Initialization Report](../AI-CS-Initial-Production-Accounts-Initialization-Report-V1.md)。

2026-08-06：R018完成账号策略源码调整并通过自动化Gate；未迁移正式数据库或创建账号。R017继续等待受控部署与Production Runtime验收。
