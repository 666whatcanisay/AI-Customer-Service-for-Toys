# AI-CS Pilot Business Catalog Interface Freeze Plan V1.1

> 需求：R006 — Pilot Business Data Activation V1 增补
>
> 业务决策：Legacy Compatibility Control（历史数据兼容控制）
>
> 实现基线：`ai-cs-pilot-baseline-v1` / `cbc77ed883cb99e2eff76ccb8eb3193bbddaba38`
>
> 前序冻结：`pilot-business-catalog.v1` / `f9257c214eba4d5cb77d4d7c290a9677bfcb88f2`
>
> 前序验证：`1ea6f3e00902f9f6f829e77814a4b9ab0b5bab6f`
>
> 当前共享 contracts：`0.2.0`（本轮不修改）
>
> 冻结接口标识：`pilot-business-catalog.v1.1`
>
> 文档状态：`INTERFACE_FREEZE_V1_1_READY_FOR_VALIDATION`
>
> 日期：2026-07-30

本文件只修改 R006 的需求与接口冻结结论，不实现接口，不修改代码、数据库、运行数据或服务。V1 和 V1 Validation 继续作为历史审计证据；当其默认值、SKU控制或级联语义与本文件冲突时，以 V1.1 为准。

## 1. 任务卡

| 项目 | 冻结结论 |
| --- | --- |
| 目标 | 历史 TEST 数据保持 Pilot 连续性并由运营主动关闭；新 PILOT 数据必须经运营确认后进入 B。 |
| Provider / Data Owner | C。C 保存并裁决来源、客服状态、状态回查和 activation receipt。 |
| Consumer | B。B 只消费 C 的最终客服目录投影，不再解释旧测试字段。 |
| A | 不修改接口、模型、Prompt 或 RAG；继续接收既有业务上下文标识。 |
| 允许的后续实现范围 | C最小状态持久化与运营启停入口、共享contracts、B最小非视觉Consumer适配、QA。 |
| 排除范围 | Master Data、ERP、RBAC、自动发送、自动退款、订单/售后自动执行、A/RAG修改、页面重设计。 |
| 成功标准 | 默认值、启停校验、SKU继承、父级隔离、状态回查、receipt、B消费和回滚均有唯一可验证语义。 |

核心业务原则：

> 运营负责业务准入，系统负责按准入状态执行。

## 2. V1.1变更摘要

V1.1取代以下V1语义：

1. 不再通过 Legacy Compatibility Matrix 自动选择“哪些旧数据可信”。历史快照内的 TEST 数据按统一政策默认启用，运营可以主动禁用。
2. 新建业务数据固定为 `PILOT + DISABLED`，必须由运营显式启用。
3. SKU 不保存独立客服启停状态，也没有独立启停入口；SKU继承所属Product的客服状态。
4. 禁用Store不级联改写Product；禁用Product不逐条改写SKU。父级禁用只阻断下游投影，重新启用后恢复仍处于ENABLED的子级。
5. C运营端允许增加最小状态列和启用/禁用操作，不授权页面结构重设计。
6. 每次实际状态变化必须由C生成并保存唯一activation receipt；幂等的同状态重放不生成新的状态变化receipt。

## 3. 冻结数据模型

### 3.1 通用枚举

```text
data_source
  TEST
  PILOT

customer_service_status
  ENABLED
  DISABLED
```

- `data_source`由C写入且创建后不可由B修改。
- `customer_service_status`是C的业务准入状态；缺失、未知或无法解析时按不可用处理。
- `test_data_mode`、`production_usable`、`trial_enabled`、`publishable`和B前端常量不得再作为客服目录准入核心。

### 3.2 Store

| 字段 | 类型/枚举 | 规则 |
| --- | --- | --- |
| `store_code` | non-empty string | 既有稳定技术标识。 |
| `store_name` | non-empty string | C运营维护的店铺名称。 |
| `platform` | 既有平台枚举 | 保留既有值，不由B转换。 |
| `data_source` | `TEST` / `PILOT` | 历史快照为TEST；C运营新建为PILOT。 |
| `customer_service_status` | `ENABLED` / `DISABLED` | C保存的显式状态。 |
| `customer_service_status_updated_at` | ISO-8601 datetime或`null` | 最近一次实际状态变化时间；尚无变化时可为空。 |
| `customer_service_status_updated_by` | non-empty string或`null` | 最近一次实际状态变化操作人/初始化来源；不宣称正式认证。 |

### 3.3 Product

| 字段 | 类型/枚举 | 规则 |
| --- | --- | --- |
| `product_id` | non-empty string | 既有稳定商品标识。 |
| `store_code` | non-empty string | 必须指向有效Store。 |
| `product_name` | non-empty string | C运营维护的商品名称。 |
| `product_status` | `ON_SALE` / `OFF_SALE` / `UNKNOWN` | 业务背景，不替代客服状态。 |
| `knowledge_status` | 既有知识状态枚举 | 知识完整性提示，不替代客服状态。 |
| `data_source` | 继承Store | 不允许与Store冲突。 |
| `customer_service_status` | `ENABLED` / `DISABLED` | C保存的商品显式状态。 |
| `customer_service_status_updated_at` | ISO-8601 datetime或`null` | 最近一次实际状态变化时间。 |
| `customer_service_status_updated_by` | non-empty string或`null` | 最近一次实际状态变化操作人/初始化来源。 |

知识为`MISSING_KNOWLEDGE`或`UNCONFIRMED`不自动阻止运营启用。B继续展示既有知识准备度提醒，客服必须人工核对。

### 3.4 SKU

| 字段 | 类型/枚举 | 规则 |
| --- | --- | --- |
| `sku_id` | non-empty string | 既有稳定SKU标识。 |
| `product_id` | non-empty string | 必须指向所属Product。 |
| `sku_name` | non-empty string | 既有业务展示名称。 |
| `data_source` | 继承Store | 不独立保存来源。 |
| `customer_service_status` | `ENABLED` / `DISABLED` | 只读派生值，继承Product；不允许独立写入。 |

SKU没有独立客服状态按钮、写接口或activation receipt。Product启用时，其关系有效的SKU可以被投影；Product或Store不可用时，SKU全部不可见。

## 4. Legacy Compatibility Control Matrix

| 数据类型 | 来源 | 初始状态 | 控制方式 |
| --- | --- | --- | --- |
| 历史测试店铺 | `TEST` | `ENABLED` | 运营可关闭或再次开启 |
| 历史测试商品 | `TEST` | `ENABLED` | 运营可关闭或再次开启 |
| 历史SKU | `TEST` | 继承商品 | 不可单独开启/关闭 |
| 新Pilot店铺 | `PILOT` | `DISABLED` | 运营确认后开启 |
| 新Pilot商品 | `PILOT` | `DISABLED` | 运营确认后开启 |
| 新SKU | `PILOT` | 继承商品 | 不可单独开启/关闭 |

“历史”冻结为实施时从 `cbc77ed` 业务目录形成的一次性只读迁移快照。正常C运营创建入口不创建新的TEST数据；新建Store固定为PILOT，其Product与SKU继承PILOT。

历史初始化规则：

1. 不读取 `test_data_mode`、`production_usable`、`trial_enabled`或`publishable`来选择启用对象。
2. 快照内所有结构有效、非删除的TEST Store和Product目标状态为ENABLED。
3. 数据完整性校验不是业务可信度选择：名称缺失、删除状态或父级关系无效的记录不得进入正常目录，必须进入安全异常清单；单条异常不影响其他记录。
4. 初始化使用固定幂等版本 `legacy-compat-control-v1.1@cbc77ed`。重复执行不得覆盖运营后续的启停结果，不得生成重复receipt。
5. 每个从“无正式客服状态”初始化为ENABLED的Store/Product生成一条`LEGACY_INITIALIZATION` receipt。
6. 实施前必须输出无敏感preflight manifest，记录Store/Product/SKU数量、异常数量和幂等版本；manifest是QA证据，不承担人工挑选业务数据的功能。

## 5. 状态流转与父级隔离

### 5.1 历史TEST

```text
历史快照
  ↓ 兼容初始化
ENABLED
  ↓ 运营关闭
DISABLED
  ↓ 运营再次确认
ENABLED
```

### 5.2 新PILOT

```text
C创建
  ↓
PILOT + DISABLED
  ↓ 补充基础信息
运营确认客服可用
  ↓
ENABLED
```

### 5.3 有效可见性

| Store状态 | Product状态 | B结果 |
| --- | --- | --- |
| `ENABLED` | `ENABLED` | Store、Product及其有效SKU可见 |
| `ENABLED` | `DISABLED` | Store可见，该Product及SKU不可见 |
| `DISABLED` | 任意 | Store及其全部Product/SKU不可见 |

父级禁用不删除数据、不改变知识、不逐条覆盖子级显式状态。重新启用Store后，原本仍为ENABLED的Product恢复可见；重新启用Product后，其有效SKU恢复可见。

## 6. 启用校验

### 6.1 Store

启用前必须满足：

- 店铺名称去除首尾空白后非空；
- 店铺业务状态正常且非删除；
- 既有标识与平台值可以形成有效投影。

### 6.2 Product

启用前必须满足：

- 所属Store存在、状态正常且`customer_service_status=ENABLED`；
- 商品名称去除首尾空白后非空；
- 商品非删除状态，父级关系有效。

`OFF_SALE`或知识缺失不自动阻止启用，因为客服仍可能处理售后或资料不完整场景。

### 6.3 SKU

SKU不执行独立启用。投影时只校验SKU名称、标识和Product父级关系；异常SKU单条隔离，不影响同Product其他有效SKU。

## 7. C运营控制入口

这是R006明确允许的最小C UI变更，仅增加现有列表的状态展示和启停操作，不重做导航、布局或页面信息架构。

### 7.1 店铺列表

| 展示项 | 要求 |
| --- | --- |
| 店铺名称 | 既有字段 |
| 平台 | 既有字段 |
| 数据来源 | `TEST→测试`，`PILOT→试运行` |
| 客服状态 | `ENABLED→启用`，`DISABLED→禁用` |
| 最后修改时间 | 最近一次状态变化时间 |
| 操作人 | 最近一次状态变化操作人/初始化来源 |
| 操作 | `启用客服使用` / `关闭客服使用` |

### 7.2 商品列表

| 展示项 | 要求 |
| --- | --- |
| 商品名称 | 既有字段 |
| 数据来源 | 继承Store并显示测试/试运行 |
| 客服状态 | 商品显式状态 |
| 知识状态 | 既有知识状态，不阻断按钮 |
| 最后修改时间 | 最近一次状态变化时间 |
| 操作人 | 最近一次状态变化操作人/初始化来源 |
| 操作 | `启用客服使用` / `关闭客服使用` |

SKU列表只展示继承结果，不提供独立按钮。

## 8. 冻结接口

### 8.1 B只读目录（C Provider → B Consumer）

```text
GET /api/v1/customer-service/catalog/stores
GET /api/v1/customer-service/catalog/products?store_code={store_code}
GET /api/v1/customer-service/catalog/products/{product_id}/skus
```

统一响应继续使用`COMPLETE/PARTIAL`语义，`schema_version`更新为`pilot-business-catalog.v1.1`。C只投影有效可见实体；B不得根据旧测试字段再次筛选。

### 8.2 C状态写入

```text
PUT /api/v1/admin/operations/stores/{store_ref}/customer-service-status
PUT /api/v1/admin/operations/products/{product_id}/customer-service-status
```

V1草案中的SKU状态PUT在实现前被V1.1取消，不得实现。

请求：

```json
{
  "customer_service_status": "ENABLED",
  "confirmed_by": "pilot-operator",
  "confirmation_note": "已核对业务信息和客服人工使用边界"
}
```

- Store的`store_ref`在receipt中统一序列化为非空字符串。
- 同实体、同目标状态重放返回`changed=false`，不创建新的状态变化receipt。
- 网络结果不确定时，客户端先通过C只读接口回查，不得自动重试写入。

### 8.3 C状态回查

以下既有C Admin响应必须在实施时增量包含第3节状态字段：

```text
GET /api/v1/admin/operations/stores
GET /api/v1/admin/operations/stores/{store_ref}
GET /api/v1/admin/product-knowledge/products?store_code={store_code}
GET /api/v1/admin/product-knowledge/products/{product_id}
```

Store/Product创建成功响应也必须返回`data_source`、`customer_service_status`以及可为空的最近修改元数据，从而能够验收“新PILOT默认DISABLED”。

### 8.4 Activation receipt

每次实际状态变化必须生成并持久保存：

```json
{
  "schema_version": "pilot-business-catalog-activation-receipt.v1",
  "activation_receipt_id": "ACT-...",
  "entity_type": "PRODUCT",
  "entity_ref": "C-PRODUCT-...",
  "data_source": "PILOT",
  "previous_status": "DISABLED",
  "customer_service_status": "ENABLED",
  "activation_source": "OPERATOR",
  "confirmed_by": "pilot-operator",
  "confirmation_note": "已核对业务信息和客服人工使用边界",
  "confirmed_at": "2026-07-30T10:00:00Z"
}
```

冻结约束：

- `activation_receipt_id`、`entity_ref`、`confirmed_by`均为non-empty string。
- `entity_type`只允许`STORE`、`PRODUCT`。
- `activation_source`只允许`LEGACY_INITIALIZATION`、`OPERATOR`。
- `previous_status`在历史首次初始化时允许`null`；运营操作时必须是`ENABLED`或`DISABLED`。
- `confirmation_note`可为空，但不得包含客户隐私、原始知识或真实会话。
- receipt由C生成，B不生成、不缓存、不回写。
- 同状态幂等重放没有新的状态变化，因此响应返回`changed=false`、`activation_receipt=null`和当前状态。

## 9. B Consumer冻结行为

1. B只消费C的`/customer-service/catalog/**`投影。
2. B不得读取或判断`test_data_mode`、`production_usable`、`trial_enabled`、`publishable`来决定可见性。
3. B不得因为一条异常Store/Product/SKU把整批有效数据变为`No data`。
4. `PARTIAL`、超时、503和结构错误继续使用目录异常语义；只有`COMPLETE + items=[] + total=0`表示真实空目录。
5. 允许后续实现修改B adapter/client及`AiChat.vue`中的最小非视觉旧判断；禁止重新设计客服UI、文案和工作流。
6. B传给A的`tenant_id/platform/store_code/product_id/sku_id`保持不变。

## 10. 安全边界

`customer_service_status=ENABLED`只表示“可被客服看到并人工选择”，不代表：

- 自动发送客户消息；
- 自动退款、换货、售后、订单修改或ERP写入；
- 自动发布知识、同步RAG、修改Prompt或训练模型；
- 商品在售、知识完整或AI回答一定可直接采用。

所有AI建议继续经过客服人工核对和人工复制。

## 11. 回滚与兼容

### 11.1 运营误操作回滚

```text
ENABLED → DISABLED
```

回滚只新增一条状态变化receipt，不删除Store/Product/SKU，不改变知识状态，也不修改A。

### 11.2 发布回滚

1. C Provider先支持V1.1及旧测试目录并行读取。
2. B切换到V1.1后再执行跨服务验证。
3. 如需回滚，B先恢复旧Consumer；确认历史Pilot可用后再回滚C新接口。
4. 不删除已写入的客服状态和receipt；它们作为C事实保留，后续迁移必须向后兼容。

### 11.3 Contracts

本轮不修改`contracts/**`，版本继续为`0.2.0`。V1.1验证通过并获得明确实施授权后，首个实现提交必须以additive `contracts 0.3.0`交付schema、version、changelog、compatibility和B/C/A影响复核。

## 12. V1 Validation阻塞关闭设计

| 阻塞 | V1.1处理 | 状态 |
| --- | --- | --- |
| IV-B01 状态read-back缺失 | 第8.3节冻结现有Store/Product list/detail与create响应的回查字段 | 设计已补齐，待V1.1验证 |
| IV-B02 旧测试集合不精确 | 第4节改为确定性Legacy Control政策、快照边界、幂等版本和preflight manifest | 设计已补齐，待V1.1验证 |
| IV-B03 B范围与禁止UI冲突 | 第7、9节明确允许C最小控制入口与B最小非视觉Consumer适配，禁止重设计 | 设计已补齐，待V1.1验证 |
| IV-B04 receipt与持久化不完整 | 第8.4节冻结ID、类型、来源、幂等与C权威持久化 | 设计已补齐，待V1.1验证 |

## 13. V1.1验证场景

后续静态验证必须至少覆盖：

1. 历史有效TEST Store/Product默认ENABLED，SKU继承Product。
2. 运营关闭历史Store后B不可见；再次开启后，仍为ENABLED的Product恢复可见。
3. 运营关闭单个Product只隐藏该Product及SKU，不影响同Store其他商品。
4. 新PILOT Store和Product创建后均为DISABLED且可通过C响应回查。
5. Store/Product满足校验后可由运营开启，并生成唯一receipt。
6. 同状态重放不产生重复receipt。
7. SKU没有独立启停入口，Product状态变化决定其可见性。
8. 单条历史异常进入安全清单，不导致全部`No data`。
9. 知识缺失Product仍可由运营启用，但继续显示人工核对提醒。
10. ENABLED不产生自动发送、退款、订单、ERP、Prompt、RAG或模型动作。

## 14. Gate

| Gate | 结论 |
| --- | --- |
| 业务默认规则 | 已冻结 |
| C/B/A Owner | 已冻结 |
| Store/Product/SKU控制层级 | 已冻结 |
| 状态read-back | 已冻结，待验证 |
| activation receipt | 已冻结，待验证 |
| Legacy初始化、幂等与回滚 | 已冻结，待验证 |
| Contracts实现 | 未开始 |
| C/B实现 | 未开始 |
| 数据迁移 | 未开始 |

最终Gate：`INTERFACE_FREEZE_V1_1_READY_FOR_VALIDATION`。

下一步只能执行《AI-CS Pilot Business Catalog Interface Freeze Validation V1.1》。验证通过并获得明确授权前，继续禁止R006 Implementation和Business Data Activation开发。
