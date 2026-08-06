# R018 AI-CS Account Policy Adjustment V1 Task Card

## 任务身份

- Requirement ID：`R018`
- 状态：`IN_PROGRESS`
- Owner：C IAM / B Customer Workspace / C Admin / Contracts / OPS / QA
- 目标 Gate：`AI_CS_ACCOUNT_POLICY_READY`
- 日期：2026-08-06

## 目标

在不硬编码初始化口令、不削弱服务端鉴权的前提下，支持公司内部短用户名、中文用户名、临时初始化密码、首次强制改密、客服多店自助选择，以及 OPERATOR/ADMIN 全店访问语义。

## 冻结策略

- 用户名：1–64个 Unicode 字母、数字或 `.`、`_`、`-`；保存规范化显示值，以 NFKC + casefold 做唯一性和登录匹配。
- 初始化密码：8–128字符，仅用于新建/重置账号并设置 `must_change_password=true`；用户自助修改后的密码仍要求12–128字符。
- 首次改密：登录可建立最小 Session，但除 `/auth/me`、`/auth/change-password` 和 `/auth/logout` 外，服务端权限依赖返回 `PASSWORD_CHANGE_REQUIRED`。
- `CUSTOMER_SERVICE`：Workspace、AI回复、Feedback及自身客服店铺管理；允许零个初始绑定，首次改密后选择一个或多个已启用客服店铺，不固定默认店铺。
- `OPERATOR`：商品、SKU、知识、FAQ、AI质量、Feedback和店铺数据的运营权限；服务端 `all_store_access=true`。
- `ADMIN`：全部权限，服务端 `all_store_access=true`。

## 契约影响

- Repository contracts：`0.9.0 → 0.10.0` coordinated revision。
- `UserProjection`新增 `must_change_password` 和 `all_store_access`。
- 新增自助改密和客服店铺选项/绑定对象及 `PASSWORD_CHANGE_REQUIRED`。
- 受影响线路：C Provider、B Workspace、C Admin、OPS初始化脚本。
- 不受影响：A `/api/chat`语义、Gateway Contract V1、Channel Engine、PDD Adapter、R006/R009、RAG、Prompt、模型。

## 实现范围

- `platform_backend/app/iam/**`
- `platform_backend/migrations/versions/0013_user_management_v1.py`
- `platform_backend/tests/**`
- `frontend/src/**`、`frontend/tests`等既有B测试
- `admin_web/src/**`、`admin_web/tests/**`
- `contracts/**`、`tests/contract/**`
- `scripts/windows/bootstrap_ai_cs_admin.ps1`
- `scripts/windows/bootstrap_ai_cs_initial_users.ps1`及专项测试
- `README.md`、`docs/**`

## 安全边界

- 初始化口令只从 Python `getpass`读取，不接受命令行密码参数，不写源码、配置、日志、报告或Git。
- 三账号初始化前按规范化用户名查重；已存在账号只跳过，不覆盖密码、角色或绑定。
- 密码始终只保存 scrypt salted hash；Session仍只保存token digest。
- 前端跳转只是体验层；首次改密、角色和Store范围全部由C服务端执行。

## 验收标准

1. 三个目标用户名的schema/service/CLI测试通过，大小写登录与中文登录通过。
2. 8字符初始化密码可创建且必须首次改密；改密后旧Session失效，新密码登录成功。
3. 客服可从启用Store中绑定多个并在Workspace选择；未绑定Store不能访问商品范围。
4. OPERATOR和ADMIN均为全店范围，三类角色权限枚举与运行鉴权一致。
5. 初始化脚本创建三类账号、重复跳过且测试证据中不出现密码/hash/token。
6. C、B、Admin、contracts、migration、OPS专项和禁止范围回归全部通过。
