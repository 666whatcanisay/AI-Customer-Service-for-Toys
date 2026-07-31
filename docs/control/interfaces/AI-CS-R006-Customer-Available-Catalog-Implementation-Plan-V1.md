# AI-CS R006 Customer Available Catalog Implementation Plan V1

日期：2026-07-31

需求：R006 — Pilot Business Data Activation V1

问题：`BUG-B-001`

实现计划基线：`stabilization/product-stable-v1@1fccb41c0b9d17f193a2924f1cf12d9c2111a53f`

正式运行保护基线：`AI-CS@42bafcf6630ccbcd1c2dd1d55cb7d3fe735cb1e2` / database `0008_customer_feedback_loop_v1`

接口基线：`pilot-business-catalog.v1.1`

文档状态：`R006_IMPLEMENTATION_PLAN_READY`

本文件只冻结实施顺序、落点和验收 Gate。没有修改 A、B、C、R009、contracts、数据库或正式业务数据，也没有重启服务。

## 0. 任务卡

| 项目 | 结论 |
| --- | --- |
| 目标 | 由 C 提供唯一权威的 Customer Available Catalog Projection，使单条异常或未启用数据不能清空 B 的全部目录。 |
| Provider / Data Owner | C：持久化来源与客服状态、生成 receipt、过滤并投影。 |
| Consumer | B：只消费 C 最终投影，不判断业务可信度。 |
| A | 不修改；继续接收既有 tenant/platform/store/product/SKU 上下文。 |
| 允许范围 | contracts 0.3.0 additive schema；C additive migration、状态服务、投影和最小运营入口；B client/adapter/type 的最小契约切换；测试。 |
| 禁止范围 | A、RAG、Prompt、R009导入、B业务兜底、正式业务数据、Master Data、ERP、自动发送、退款或订单动作。 |
| 成功标准 | C 最终投影只返回有效且可用实体；单条异常隔离；历史 TEST 连续可用；新 PILOT 默认关闭；状态变化有可复核 receipt；B 全流程恢复。 |
| 发布边界 | 实现和测试只使用隔离数据库。正式迁移、Runtime切换和业务数据变更必须另立发布任务。 |

## 1. 当前 C 商品数据流

### 1.1 持久化事实

当前 C 的店铺、商品和 SKU 共用旧测试目录表：

```text
test_knowledge_packages
  └─ test_catalog_stores
       └─ test_catalog_products
            └─ test_catalog_skus
```

它们同时承载两类来源：

| 来源证据 | 当前含义 | 2026-07-31正式只读快照 |
| --- | --- | ---: |
| `import_status=IMPORTED_TEST_ONLY` + `schema_version=0.3.1-test` | 冻结历史 TEST 包 | 1 Store / 5 Products |
| `import_status=MANUAL_CREATED` + `schema_version=c-operation-store.v1` | C 运营创建的 PILOT 数据 | 1 Store / 0 Products |

当前没有正式 `data_source` 和 `customer_service_status`。店铺使用 `trial_enabled/response_mode/test_data_mode/production_usable`，商品和 SKU 使用 `publishable`；这些字段各自有旧职责，不能继续承担客服准入。

### 1.2 写入链路

- 测试包导入写入 `IMPORTED_TEST_ONLY`、Store/Product/SKU 和旧测试安全字段。
- C `OperationManagementService.create_store()` 写入 `MANUAL_CREATED`，但仍沿用 `test_data_mode=true`、`production_usable=false`，且 `response_mode=HUMAN_CONFIRM_REQUIRED`。
- C 新商品默认 `OFF_SALE/REVIEWING/publishable=false`；这不等于客服不可用状态。
- R009审核只更新商品知识和既有商品字段，不负责客服激活，本实施不得修改其 Parser、Merge、审核或 0009 migration。

### 1.3 当前读取链路

`TestCatalogRepository.list_stores/list_products/list_skus`直接读取全部记录并原样投影旧字段，没有父级客服状态过滤，也没有单条异常隔离。

## 2. 当前 B 商品读取链路

```text
AiChat.vue
  ↓ platformClient.ts
GET /api/v1/test-catalog/stores
GET /api/v1/test-catalog/products?store_code=...
GET /api/v1/test-catalog/products/{product_id}/skus
  ↓ platformAdapter.ts
旧字段适配与整批业务校验
  ↓ 店铺 / 商品 / SKU 选择器
```

当前行为：

1. `platformAdapter.ts`要求每条 Store 包含 `trial_enabled/test_data_mode/production_usable`，Product/SKU包含`publishable`。
2. `AiChat.loadStores()`对整批 Store 执行旧安全条件；任一条不符合即抛错并设置`stores=[]`。
3. Product/SKU仍以`publishable`禁用选项并显示“待发布”。
4. 商品和 SKU 父级关系检查在 B 进行；这些技术一致性检查可以保留，但不能演变为业务可信度判断。

## 3. BUG-B-001 根因

正式 C 目录返回两个 Store：历史 TEST Store 满足旧条件；C 运营创建 Store 的 `response_mode=HUMAN_CONFIRM_REQUIRED`。B 发现后一条“不兼容”后抛出整批契约错误，将原本可用的 TEST Store 一并清空。

根因不是 B 缺少更多过滤条件，而是：

- C 没有形成“客服最终可见”权威投影；
- B 被迫读取 Provider 内部旧字段并自行推断可用性；
- 批量响应没有在 C 侧隔离单条异常；
- 旧接口把测试包治理字段与客服业务准入耦合。

因此禁止用以下方式修复：B静默过滤、把`HUMAN_CONFIRM_REQUIRED`当可用、强制改数据库旧字段、删除异常Store、复用`publishable`或Mock目录。

## 4. Customer Available 状态设计

### 4.1 业务状态

```text
data_source = TEST | PILOT
customer_service_status = ENABLED | DISABLED
```

- Store保存`data_source`和显式客服状态。
- Product从Store派生`data_source`，保存独立客服状态。
- SKU不保存独立客服状态，运行时继承Product。
- `ENABLED`只表示“可被客服人工选择”，不代表在售、知识完整、自动发送或自动业务执行。

### 4.2 实施前来源收敛（关闭 IV11-B01）

一次性初始化只使用 Provider provenance，不读取旧业务布尔字段：

| 旧来源 | 初始化结果 | Receipt |
| --- | --- | --- |
| `IMPORTED_TEST_ONLY + 0.3.1-test` | Store=`TEST+ENABLED`；其结构有效Product=`ENABLED` | `LEGACY_INITIALIZATION`，previous_status=null |
| `MANUAL_CREATED + c-operation-store.v1` | Store=`PILOT+DISABLED`；其Product=`DISABLED` | `LEGACY_INITIALIZATION`，previous_status=null |
| 未知、冲突或父级损坏 | `data_source=null`、状态保持`DISABLED`、不进入B | 不生成业务receipt，进入preflight异常清单 |

实现约束：

- 内部 `data_source` 列允许 `null` 仅承载隔离记录；所有新建和正常投影实体必须为 TEST/PILOT。
- 一次性策略版本固定为 `legacy-compat-control-v1.1@1fccb41`，记录无敏感数量manifest。
- 重复执行不得覆盖运营后续状态，不得重复生成receipt。
- 迁移后的C运营新建Store固定`PILOT+DISABLED`；Product继承PILOT并默认DISABLED。
- 后续新测试包不属于“历史快照”，写入`TEST+DISABLED`，必须由运营开启，避免把新导入误当历史连续性数据。

### 4.3 有效可见性

```text
Store effective available =
  data_source有效
  AND customer_service_status=ENABLED
  AND C内部业务状态正常
  AND 标识/名称/平台结构有效

Product effective available =
  Store effective available
  AND Product.customer_service_status=ENABLED
  AND 商品存在、名称和父级关系有效

SKU effective available =
  Product effective available
  AND SKU标识、名称和父级关系有效
```

`sales_status`、`review_status`、`knowledge_status`和`publishable`不参与客服可见性判断。Store禁用只阻断投影，不覆写Product状态；Product禁用只隐藏自身和SKU。

## 5. C 投影接口设计

### 5.1 B只读接口

```text
GET /api/v1/customer-service/catalog/stores
GET /api/v1/customer-service/catalog/products?store_code={store_code}
GET /api/v1/customer-service/catalog/products/{product_id}/skus
```

统一 envelope：

```json
{
  "schema_version": "pilot-business-catalog.v1.1",
  "result_status": "COMPLETE",
  "items": [],
  "total": 0,
  "warnings": []
}
```

规则：

- `total`只统计返回的有效items。
- `COMPLETE + items=[] + total=0`才表示真实空目录。
- 有源记录被结构隔离时返回有效items、`PARTIAL`及聚合warning。
- warning只包含`code/entity_type/count/message`，不返回原始行、知识内容或内部异常堆栈。
- disabled实体正常不投影，也不产生warning。
- products查询Store不可用时返回`COMPLETE + []`；SKU查询目标Product不存在或不可用时返回404。
- 旧 `/api/v1/test-catalog/**` 在兼容期保持原语义，不能原地改成客服投影。

最小投影字段：

| Store | Product | SKU |
| --- | --- | --- |
| tenant_id | product_id | sku_id |
| platform | platform | product_id |
| store_code | store_code | sku_code |
| store_name | product_name_official/display | sku_name_official/display |
| data_source | sales_status | relation_type及既有关系字段 |
| customer_service_status=`ENABLED` | review/knowledge提示字段 | data_source |
| allow_auto_send=`false` | data_source | customer_service_status=`ENABLED` |
|  | customer_service_status=`ENABLED` |  |

`allow_auto_send=false`作为安全声明保留，但不作为B业务准入判断。

### 5.2 C状态写入与回查（关闭 IV11-B02）

```text
PUT /api/v1/admin/operations/stores/{store_ref}/customer-service-status
PUT /api/v1/admin/operations/products/{product_id}/customer-service-status
GET /api/v1/admin/operations/activation-receipts/{activation_receipt_id}
GET /api/v1/admin/operations/activation-receipts?entity_type={STORE|PRODUCT}&entity_ref={ref}&page=1&size=20
```

PUT必须携带`Idempotency-Key`，请求体沿用V1.1：

```json
{
  "customer_service_status": "ENABLED",
  "confirmed_by": "pilot-operator",
  "confirmation_note": "已核对客服人工使用边界"
}
```

完整成功响应：

```json
{
  "schema_version": "pilot-business-catalog-activation-response.v1",
  "changed": true,
  "entity": {
    "entity_type": "PRODUCT",
    "entity_ref": "C-PRODUCT-...",
    "data_source": "PILOT",
    "customer_service_status": "ENABLED",
    "customer_service_status_updated_at": "2026-07-31T01:00:00Z",
    "customer_service_status_updated_by": "pilot-operator"
  },
  "activation_receipt": {
    "schema_version": "pilot-business-catalog-activation-receipt.v1",
    "activation_receipt_id": "ACT-...",
    "entity_type": "PRODUCT",
    "entity_ref": "C-PRODUCT-...",
    "data_source": "PILOT",
    "previous_status": "DISABLED",
    "customer_service_status": "ENABLED",
    "activation_source": "OPERATOR",
    "confirmed_by": "pilot-operator",
    "confirmation_note": "已核对客服人工使用边界",
    "confirmed_at": "2026-07-31T01:00:00Z"
  },
  "server_time": "2026-07-31T01:00:00Z"
}
```

幂等语义：

- 同key、同请求：返回原响应并标记`Idempotency-Replayed: true`。
- 同key、不同请求：409 `ACTIVATION_IDEMPOTENCY_CONFLICT`。
- 不同key、实体已经是目标状态：200，`changed=false`、`activation_receipt=null`，返回当前entity状态。
- 网络结果不确定：先用现有Store/Product detail及receipt只读接口回查，不自动重放新key。

### 5.3 错误码

| HTTP | code | 条件 |
| ---: | --- | --- |
| 422 | `CUSTOMER_SERVICE_STATUS_INVALID` | 状态、confirmed_by或请求格式无效 |
| 404 | `CUSTOMER_SERVICE_ENTITY_NOT_FOUND` | Store/Product不存在 |
| 404 | `ACTIVATION_RECEIPT_NOT_FOUND` | Receipt不存在 |
| 409 | `CUSTOMER_SERVICE_ENTITY_QUARANTINED` | 来源未知或结构异常，不能启用 |
| 409 | `CUSTOMER_SERVICE_STORE_NOT_ENABLED` | Product启用时父Store未启用 |
| 409 | `CUSTOMER_SERVICE_ENTITY_INVALID` | 名称、平台或父级关系不满足启用条件 |
| 409 | `ACTIVATION_IDEMPOTENCY_CONFLICT` | 幂等key被不同请求复用 |

## 6. 数据过滤规则

Provider按层级查询和逐条投影，不先构建“全量必须全部合法”的列表：

1. Store：只投影effective available Store；异常Store计入PARTIAL warning，不影响其他Store。
2. Product：查询必须限定已可用Store；只投影自身ENABLED且父级一致的Product。
3. SKU：只查询已可用Product；忽略旧`publishable`，逐条验证SKU父级、标识和名称。
4. 父级DISABLED是正常业务过滤，不是异常。
5. 缺失/未知客服状态、未知来源、孤儿关系、空标识或空名称一律隔离，绝不推断ENABLED。
6. `OFF_SALE`和知识不足不自动过滤，继续由B既有资料准备度提示和人工流程控制。
7. 数据库或查询整体失败返回受控5xx，不伪装成空目录。

## 7. B 消费调整范围

B只做契约切换，不承担业务兜底：

- `platformClient.ts`切换三个路径到`/customer-service/catalog/**`。
- `platformTypes.ts`替换为V1.1字段；删除Store旧准入布尔和Product/SKU `publishable`依赖。
- `platformAdapter.ts`校验envelope、schema_version和父级标识；`PARTIAL`中只消费C已投影items，不根据warning或旧字段决定可用性。
- 技术上隔离单条schema损坏只能保护页面不崩溃，不得把缺失/未知状态推断为可用；该场景应记录契约错误并由C修复。
- `AiChat.vue`删除整批旧Store安全判断、Product/SKU `publishable`禁用和“待发布”标签；保留现有布局、选择流程、错误提示和父级一致性检查。
- B传给A的`tenant_id/platform/store_code/product_id/sku_id`完全不变。

禁止在B增加本地白名单、默认店铺硬编码、旧字段兼容矩阵、自动启用或数据库绕过。

## 8. 数据库与实现落点

源树已有R009 `0009_product_knowledge_import_v1`，R006必须新增独立`0010_customer_available_catalog_v1`，不得修改0009。

建议最小结构：

- `test_catalog_stores` additive列：`data_source`、`customer_service_status`、`customer_service_status_updated_at/by`。
- `test_catalog_products` additive列：`customer_service_status`、`customer_service_status_updated_at/by`；data_source从Store派生。
- `catalog_activation_receipts`：receipt字段、idempotency_key、request_fingerprint、创建时间；主键receipt_id，实体时间索引，幂等key唯一。
- `catalog_activation_initializations`：policy_version、source_baseline、执行时间、分类/隔离数量，用于证明一次性初始化没有重放。
- SKU不加状态列，不加独立receipt。

迁移必须在隔离SQLite完成：preflight只读统计 → 在线副本backup → upgrade 0010 → 规则/receipt核对 → downgrade隔离测试 → 再upgrade。正式0008库不在Implementation阶段执行。

## 9. 实施顺序

Phase 0 必须一次性交付共享契约治理资产：`contracts/version.json=0.3.0`、Customer Available Catalog schema、Activation Request/Response/Receipt schema、错误码、changelog、0.2.0兼容说明，以及B/C实现评审和A“无接口变化”复核。缺任一项不得进入C编码。

```text
Phase 0  Contracts 0.3.0 additive schema
  ↓
Phase 1  0010 migration + provenance初始化 + receipt persistence
  ↓
Phase 2  C Customer Available Catalog Projection
  ↓
Phase 3  C Store/Product状态API与最小Admin控制入口
  ↓
Phase 4  B client/adapter/type最小切换
  ↓
Phase 5  Contract/C/B/E2E回归
  ↓
Phase 6  隔离Runtime浏览器验收
  ↓
独立Production Release任务（不属于本计划执行）
```

每个Phase必须独立commit；不得使用`git add .`，不得把R009、A、RAG、Prompt或正式数据混入提交。

## 10. 测试方案

### 10.1 Contracts

- schema正反例、枚举、COMPLETE/PARTIAL、空目录语义。
- Activation response/receipt、changed true/false、错误码、幂等冲突。
- B/C使用同一0.3.0 fixture，旧0.2.0仍可读取且旧接口不变。

### 10.2 C Backend

- 0010 upgrade/downgrade/upgrade，数据库仅用隔离临时SQLite。
- `IMPORTED_TEST_ONLY→TEST+ENABLED`、`MANUAL_CREATED→PILOT+DISABLED`、未知来源隔离。
- 初始化manifest数量和receipt唯一性；重放不覆盖运营状态。
- Store/Product创建默认PILOT+DISABLED。
- Store启停、Product启停、父级禁用不改子状态、SKU继承。
- 单条坏Store/Product/SKU得到PARTIAL，其他有效条目仍返回。
- 知识缺失/停售Product可人工启用；删除/孤儿/空名称不可启用。
- 幂等key重放、冲突、changed=false、receipt按ID/实体回查。
- 整体数据库错误不能返回COMPLETE空目录。

### 10.3 B Frontend

- client只调用三个V1.1路径。
- adapter不再读取`trial_enabled/test_data_mode/production_usable/publishable`。
- COMPLETE空目录、PARTIAL有效items、结构错误、404/503和超时。
- `AiChat`不再因一条不兼容Store清空可用目录。
- 店铺切换、商品切换、多SKU、连续五轮的既有行为不回归。
- Vitest、typecheck、build全量通过；不改客服页面结构。

### 10.4 跨服务与浏览器

必须使用隔离数据库和非正式端口复现：

1. 历史TEST Store/Product默认可见。
2. MANUAL_CREATED Store默认不可见且不影响TEST目录。
3. 开启PILOT Store后Store可见，Product仍按自身状态过滤。
4. 开启Product后Product/SKU可见。
5. Store关闭后Product状态保持，重新开启后恢复。
6. 单商品关闭不影响同店其他商品。
7. 单条异常得到PARTIAL但B仍可选其他记录。
8. 同状态重放无重复receipt。
9. B-001至B-006完整Playwright通过。
10. 高风险边界仍显示人工确认；没有自动发送、退款、订单、RAG或Prompt动作。

## 11. 风险与停止条件

| 风险 | 控制 |
| --- | --- |
| 混合来源误启用 | 只按import_status+schema_version映射；未知隔离；preflight计数复核 |
| R009与R006迁移混合 | 新建0010且不改0009；正式发布单独评审0008→0009→0010顺序 |
| B继续猜测业务状态 | 删除旧判断；B只读C最终items |
| Store禁用覆写Product | 服务和迁移测试证明只阻断投影 |
| receipt无法复核 | 完整response、Idempotency-Key、按ID/实体查询 |
| 单条异常放大全量失败 | C逐条投影、PARTIAL聚合warning；B不得把PARTIAL当No data |
| 实现误改正式数据 | Implementation只用隔离副本；发现正式DB连接立即停止 |

停止条件：来源分组数量与只读快照不一致、0010触碰0009/R009、正式数据库连接、A/RAG/Prompt出现diff、未知记录被推断ENABLED、receipt重放产生新记录、或B再次引入业务可信度判断。

## 12. Gate结论

本计划以字段级决策关闭了此前的两个计划缺口：

- `IV11-B01`：来源映射、未知隔离、策略版本和未来新数据默认值已明确。
- `IV11-B02`：PUT完整响应、幂等、receipt read-back、错误码和网络不确定回查已明确。

这只表示实施计划可进入评审，不表示代码、contracts、migration、API、UI或业务数据已经实现。

下一阶段入口：按`contracts 0.3.0 → C data/provider → C最小控制入口 → B consumer → QA`顺序创建实施分支，并继续保护正式Runtime。

最终状态：`R006_IMPLEMENTATION_PLAN_READY`
