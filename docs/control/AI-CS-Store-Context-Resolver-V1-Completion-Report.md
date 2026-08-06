# 《AI-CS Store Context Resolver V1 Completion Report》

> Requirement：R020
>
> 日期：2026-08-06
>
> Gate：`PASS / SOURCE_ONLY`
> Final Status：`AI_CS_STORE_CONTEXT_READY`

## 1. 店铺流程

- `CUSTOMER_SERVICE`仍可绑定多个C返回的启用客服Store；只要存在绑定，就必须且只能有一个`is_default=true`。
- 首次选择提交`store_ids + default_store_id`。兼容旧客户端：省略默认项时，C保留仍在授权列表中的现有默认项，否则确定性使用请求首项。
- 登录/进入Workspace后，B从`GET /api/v1/workspace/context`取得真实`user_id`、角色、授权店铺和`effective_store`，不再使用tester identity或每次重新选店。
- 客服通过`PUT /api/v1/auth/default-store`在已绑定范围内切换并持久化默认项；未授权Store返回HTTP 403。`OPERATOR`与`ADMIN`继续由角色获得全Store范围，不创建伪绑定。

## 2. 商品识别逻辑

- C只读取有效Store的Customer Available Catalog；先校验用户Store权限，再按NFKC、case-fold和字母数字规范化匹配Product ID、正式名称和显示名称。
- 一个匹配候选自动解析；多个匹配候选返回`PRODUCT_CONFIRMATION_REQUIRED`与C生成的候选列表；没有匹配返回`UNKNOWN`。有效Store只有一个可用Product时可自动解析。
- 人工确认的Product ID必须重新属于同一Store的客服可用目录，否则HTTP 422 `PRODUCT_CONFIRMATION_INVALID`。解析不跨店、不接受B自报的名称或可用状态。

## 3. SKU处理规则

- Product确定后匹配SKU ID、SKU code、正式名称和显示名称。
- 0个SKU：`sku_id=null`并完成解析；1个SKU：自动解析；多个SKU且消息不能唯一确定时返回`SKU_CONFIRMATION_REQUIRED`。
- 人工确认SKU必须重新属于已解析Product，否则HTTP 422 `SKU_CONFIRMATION_INVALID`。
- 每次解析只保存会话规范化SHA-256、用户/Store/Product/SKU/候选ID、状态、原因码和时间；不保存客户原文、AI回答、session、凭证或知识内容。

## 4. API变化

| Method | Route | 作用 | 兼容性 |
| --- | --- | --- | --- |
| `PUT` | `/api/v1/auth/store-bindings` | 可选`default_store_id`，收敛唯一默认Store | 旧请求仍有效 |
| `PUT` | `/api/v1/auth/default-store` | 客服在授权绑定内切换默认Store | 新增 |
| `GET` | `/api/v1/workspace/context` | 服务端用户/角色/Store上下文 | 新增 |
| `POST` | `/api/v1/workspace/context-resolutions` | 解析会话Product/SKU与候选 | 新增 |
| `POST` | `/api/v1/workspace/ai-replies` | 新增`resolution_id`输入，由C重建A context | 旧显式`context`保留 |
| `GET` | `/api/v1/admin/store-context/resolutions` | ADMIN查看最小解析记录 | 新增 |

Contracts为`0.11.0 / coordinated`，包含schema、changelog、兼容/回滚说明和B/C/Admin/A/Gateway受影响线复核。冻结Gateway Contract V1 schema没有内容差异，SHA-256仍为`fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`。

## 5. 测试结果

| 范围 | 结果 |
| --- | --- |
| C Platform Backend | `135 passed` |
| 0014 migration | 隔离SQLite upgrade→downgrade PASS；IAM/catalog表保留 |
| B Customer Workspace | `35 files / 148 tests passed` |
| B typecheck / production build | PASS / PASS |
| C Admin | `33 files / 84 tests passed` |
| Admin typecheck / production build | PASS / PASS |
| Shared contracts | `12 passed` |
| A全量回归 | `147 passed, 3 skipped`；3项为显式开启的真实E2E |

覆盖客服登录/默认店铺/多店切换/越权拒绝、Product唯一/歧义/未知、SKU唯一/歧义/无SKU、人工确认、Workspace上下文注入、旧chat兼容、Admin审计及无客户原文投影。

## 6. 兼容、边界与部署输入

- A `/api/chat`、Gateway/Channel Engine/PDD、R006/R009、商品知识逻辑、RAG、Prompt和模型均未修改；RAG基线保持`test_knowledge_v031=56 chunks`与model ready，本轮无sync/rebuild。
- B仍只展示AI建议，必须人工采用、复制并发送；未新增自动发送、自动重试、退款或订单动作。
- 正式Runtime数据库当前仍是`0013_user_management_v1`。本报告是源码Gate，不是生产部署声明；本轮没有迁移或改写正式SQLite，也没有启动dirty源码Runtime。
- 部署前按顺序执行：停止四服务 → SQLite在线备份/指纹/完整性 → 同批部署C/B/Admin contracts 0.11 → 标准wrapper迁移0014 → 验证默认Store、resolver、AI、Admin和回滚。A可以原版本协同，因为wire未变。
- 回滚B/Admin不要求数据回滚；回滚C到0.10前应先停止服务并将0014降到0013，降级只删除新的最小解析审计表，不修改用户绑定、Store/Product/SKU或RAG资产。

最终结论：实现和源码级证据满足R020完成标准。

`AI_CS_STORE_CONTEXT_READY`
