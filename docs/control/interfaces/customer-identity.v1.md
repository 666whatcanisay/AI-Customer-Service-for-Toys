# Customer Identity v1（试运行身份选择）

> 状态：**FROZEN_FOR_IMPLEMENTATION**
>
> Provider：C（业务中台）  
> Consumers：B（客服工作台）、C Admin（用户管理）  
> 共享 `contracts/**`：未修改；本协议是当前单机试运行的任务级接口冻结。

## 1. 目标与安全边界

本协议为客服工作台提供最小、可追溯的**身份选择**能力：用户先在 B 选择一名由 C 管理的启用客服，再进入客服工作台；案例、AI 反馈和效率事件使用该用户的 C 生成 `user_id` 作为来源。

它不是密码登录、SSO、令牌认证或 RBAC：当前内部测试环境没有认证/授权保障，不能据此宣称已防止冒用。系统不保存密码、手机号、邮箱或外部账号，不自动发送客户消息、退款、修改订单、训练模型、修改 Prompt 或发布知识。

## 2. 所有者与数据模型

### 2.1 `CustomerUser`

| 字段 | C 写入/管理 | 说明 |
|---|---|---|
| `user_id` | 是 | C 生成的稳定、不含姓名或联系方式的标识；B 将它用于来源字段。 |
| `display_name` | 是 | 仅内部界面显示的姓名或工号别名，长度受限。 |
| `role` | 是 | `CUSTOMER_SERVICE`、`OPERATIONS`、`ADMIN`。仅用于展示和后续权限预留，不开启复杂 RBAC。 |
| `status` | 是 | `ACTIVE` 或 `DISABLED`。停用身份不能进入 B，也不能新建案例、反馈或效率事件。 |
| `default_store_code` | 是 | 必须是该用户已绑定店铺之一。 |
| `store_bindings` | 是 | 一到多个已存在店铺；为多店切换预留。 |
| `created_at` / `updated_at` | 是 | C 服务端时间。 |

`CustomerUserStoreBinding` 只保存 `user_id` 与 `store_code` 的关系；不得保存客户、订单、聊天、联系方式或密码。

### 2.2 现有来源字段

新的 B 提交必须把所选 `user_id` 原样写入既有 `created_by`：

- `POST /api/v1/customer-experience-cases`
- `POST /api/v1/ai-response-feedback`

C 必须验证：用户存在、`status=ACTIVE`，且请求的 `store_code` 已绑定给该用户。已有历史记录不会被改写；它们可能仍含旧测试标识，但不能用来创建新记录。

效率事件使用同一不含个人信息的 `user_id` 作为 `operator_id`。C 以店铺绑定校验该来源；事件仍不得返回个人维度明细给 B 或 A，也不得用于绩效评估。

## 3. API

### 3.1 B → C：可选择身份

`GET /api/v1/customer-identities`

只返回 `ACTIVE` 用户及其店铺绑定。成功响应：

```json
{
  "items": [
    {
      "user_id": "CSU-01J...",
      "display_name": "汕明客服一号",
      "role": "CUSTOMER_SERVICE",
      "status": "ACTIVE",
      "default_store_code": "PDD-SM",
      "store_bindings": [{"store_code": "PDD-SM", "is_default": true}]
    }
  ]
}
```

`GET /api/v1/customer-identities/{user_id}` 用于 B 刷新后校验本地已选身份；停用或不存在时不返回可用身份。

### 3.2 C Admin：用户管理

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/v1/admin/customer-users` | 列表与状态筛选。 |
| `POST` | `/api/v1/admin/customer-users` | 创建用户、角色、店铺绑定和默认店铺。 |
| `PUT` | `/api/v1/admin/customer-users/{user_id}` | 编辑显示名、角色、店铺绑定和默认店铺。 |
| `POST` | `/api/v1/admin/customer-users/{user_id}/status` | 启用或停用。 |

创建与编辑请求的核心字段：

```json
{
  "display_name": "汕明客服一号",
  "role": "CUSTOMER_SERVICE",
  "store_codes": ["PDD-SM"],
  "default_store_code": "PDD-SM"
}
```

状态请求：`{ "status": "ACTIVE" }` 或 `{ "status": "DISABLED" }`。

## 4. 错误码

| HTTP | 稳定错误码 | 含义 |
|---|---|---|
| 404 | `CUSTOMER_USER_NOT_FOUND` | 用户或店铺不存在。 |
| 409 | `CUSTOMER_USER_DISABLED` | 用户已停用，不能作为新记录来源。 |
| 409 | `CUSTOMER_USER_DUPLICATE_BINDING` | 重复绑定同一店铺。 |
| 422 | `CUSTOMER_USER_VALIDATION_FAILED` | 枚举、显示名、默认店铺或字段不合法。 |
| 422 | `CUSTOMER_USER_STORE_BINDING_INVALID` | 默认店铺不在绑定中，或绑定店铺不存在。 |
| 403 | `CUSTOMER_USER_STORE_FORBIDDEN` | 身份未绑定请求中的店铺。 |

## 5. 状态机与兼容规则

```text
ACTIVE ──停用──> DISABLED
DISABLED ──启用──> ACTIVE
```

停用不会删除历史案例、反馈或效率事件；只阻止新的 B 身份选择和新写入。再次启用恢复后续写入资格。

v1 发布顺序为：先部署 C 迁移和 Provider，再部署 B 身份选择与来源写入。B 不能在未选身份时进入 AI 客服；如本地保存的身份已停用、缺失或店铺绑定失效，必须清除本地选择并回到身份选择页。C 不为 `TESTER-*` 或任意自由文本 `created_by` 建立新记录。

该规则改变的是**新写入资格**，不删除、不改写旧 API 路径、历史数据或已有字段。任何密码、令牌、真实授权、外部身份、角色细分、联系方式、审计保留期或跨部署共享契约升级，都需要新版本冻结与 A/B/C 审查。

## 6. A/B/C 影响范围

| 线路 | 负责 | 不负责 |
|---|---|---|
| C | 用户、店铺绑定、状态、校验、Admin 管理和效率事件来源持久化。 | 外部认证、SSO、复杂 RBAC、自动业务动作。 |
| B | 身份选择门禁、当前身份展示、默认店铺、来源写入与失效恢复。 | 自行创建用户、伪造店铺绑定、绕过 C 校验。 |
| A | 无实现改动；不读取个人身份或效率事件个人明细。 | 对客服用户做排名、评估或自动优化。 |

## 7. 验收

1. 没有已选且有效身份时，B 不渲染可操作的 AI 客服流程。
2. C Admin 可创建、编辑、启停用户并绑定一个或多个真实店铺。
3. 选择身份后，B 默认进入其默认店铺；多店仅保留切换入口。
4. 案例、反馈和效率事件只能由启用且绑定目标店铺的 `user_id` 新建。
5. AI 回答、人工复制与禁止自动发送等既有安全边界保持不变。
