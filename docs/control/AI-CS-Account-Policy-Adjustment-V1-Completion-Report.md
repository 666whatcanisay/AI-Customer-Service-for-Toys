# AI-CS Account Policy Adjustment V1 Completion Report

> Requirement：R018
> 日期：2026-08-06
> Task Gate：`PASS`
> Final Status：`AI_CS_ACCOUNT_POLICY_READY`

## 1. 结论

AI-CS IAM 初始化策略已调整为公司内部账号模式：支持短账号、中文和大小写显示；允许8–128字符的临时初始化/重置密码，但所有此类账号必须首次改密为12–128字符后才能使用业务API；客服可自助选择多个已启用店铺；运营和管理员由角色获得全部店铺范围。

本 Gate 是源码、契约、迁移和自动化测试就绪状态。当前受控正式 Runtime 仍停在0012/pre-IAM，本轮没有迁移正式数据库、创建生产账号、生成生产Session或写入Store binding。R017 初始账号任务仍需独立部署执行。

## 2. 用户规则

### 用户名

- 长度：1–64个规范化字符。
- 允许字符：Unicode 字母、Unicode 数字、`.`、`_`、`-`。
- 保存：保留NFKC规范化后的显示形式，因此大小写和中文可正常展示。
- 唯一性/登录：使用NFKC + casefold匹配；大小写变体不能创建重复账号。
- 自动化证据覆盖 `admin`、`Wa`、`江` 三个目标标识。

### 密码

- 新建或管理员重置：8–128字符，只作为临时密码，并自动写入 `must_change_password=true`。
- 用户自助修改：新密码要求12–128字符，且不能与当前密码相同。
- 临时密码登录后，C只允许读取身份、改密和退出；所有业务权限依赖返回HTTP 403 `PASSWORD_CHANGE_REQUIRED`。
- 改密成功后清除首次改密标志并撤销该用户全部现有Session，要求用新密码重新登录。
- 密码继续使用随机salt的scrypt hash；Session继续只保存token SHA-256 digest。

初始化口令没有硬编码到Python、PowerShell、contracts、测试报告或Git，也不作为命令行参数传递。

## 3. 权限变化

| 角色 | 权限 | Store范围 |
| --- | --- | --- |
| `CUSTOMER_SERVICE` | `workspace.access`、`ai.reply`、`feedback.submit`、`customer_service.manage` | 初始可为空；改密后从已启用客服Store中选择一个或多个；没有固定默认Store。 |
| `OPERATOR` | `product.manage`、`sku.manage`、`knowledge.manage`、`faq.manage`、`ai_quality.view`、`store.view`、`feedback.view` | 服务端 `all_store_access=true`，不依赖绑定行。 |
| `ADMIN` | 上述全部权限，加 `user.manage`及客服Workspace权限 | 服务端 `all_store_access=true`。 |

服务端是授权权威：C业务router在首次改密前统一fail closed；Store目录和Workspace继续按客服绑定校验。A浏览器管理端点同步检查C返回的 `must_change_password`，避免绕过；A `/api/chat` 和Gateway路径未改变。

## 4. 店铺选择流程

新增C IAM接口：

- `GET /api/v1/auth/store-options`：仅改密完成的 `CUSTOMER_SERVICE` 可读取已启用客服Store选项。
- `PUT /api/v1/auth/store-bindings`：客服为自己提交一个或多个唯一Store ID；只允许当前启用选项。

B登录顺序为：

```text
账号密码登录
  → must_change_password=true：修改密码并重新登录
  → CUSTOMER_SERVICE且未绑定：多店选择/绑定
  → Workspace内按已绑定Store选择当前咨询范围
```

绑定行不再要求唯一默认Store；旧B“自动进入唯一默认Store”的假设已移除。Admin用户页同步支持Unicode账号、8字符临时密码、多店客服绑定和全店角色显示。

## 5. 初始化方式

### 单个管理员

`bootstrap_ai_cs_admin.ps1`继续保留，用户名校验现支持Unicode。密码只在Python `getpass`中交互输入，创建后强制首次改密。

### 三个初始账号

新增 `bootstrap_ai_cs_initial_users.ps1`：

1. 加载与Production Runtime相同的受控C数据库配置。
2. 按NFKC + casefold检查三个批准账号是否存在。
3. 已存在账号输出 `SKIPPED`，不覆盖密码、角色、状态或Store绑定。
4. 仅当存在缺失账号时，通过Python `getpass`输入并确认一次共享临时密码。
5. 创建管理员、客服主管、运营主管；客服初始Store为空，运营/管理员由角色获得全店范围。
6. 三个账号均标记首次改密。

脚本没有密码参数，也没有默认明文密码。正式执行时由Production Account Administrator在控制台输入公司批准的临时值。

## 6. Contract状态

- Repository contract：`0.10.0`，状态 `coordinated`。
- `UserProjection`新增 `must_change_password`、`all_store_access`。
- 新增改密、Store options和客服自助绑定对象，以及 `PASSWORD_CHANGE_REQUIRED`。
- 由于0.9 B依赖唯一默认Store，B/C/Admin必须同步部署0.10；不允许只更新Provider或只更新页面。
- Gateway Contract V1 wire/schema/canonical hash不变；Channel Engine、PDD Adapter、R006/R009、RAG、Prompt和模型不变。

## 7. 验证结果

| Gate | 结果 |
| --- | --- |
| A Backend | `147 passed, 3 skipped`；首次改密的A管理端点旁路测试覆盖。 |
| C Platform Backend | `130 passed`；含登录、Unicode、首次改密、Session撤销、RBAC、多店、全店、CLI和0013迁移往返。 |
| B Frontend | `34 files / 143 tests`，typecheck和production build PASS。 |
| C Admin | `33 files / 84 tests`，typecheck和production build PASS。 |
| Shared contracts | `10 passed`；Draft 2020-12 schema有效。 |
| Windows OPS | `Test-InitialUserBootstrapPolicy.ps1` PASS。 |

全部数据库测试使用隔离SQLite；没有执行正式账号登录或浏览器Production Runtime验收。

## 8. 兼容与风险

- 0.10是协调部署版本；0.9客户端和0.10 Provider混用会在客服默认Store语义上不兼容。
- 8字符仅是用户明确批准的内部临时初始化下限，不是长期密码策略；首次改密由服务端强制。
- 客服可自助选择所有当前已启用客服Store，这是本策略的授权边界；如未来需要管理员预授权Store池，须新建立权限模型任务。
- 当前正式库仍为0012。部署前必须备份、迁移0013、切换B/C/Admin/A同一兼容源码，再运行初始化脚本和真实三角色验收。

Final Status: `AI_CS_ACCOUNT_POLICY_READY`
