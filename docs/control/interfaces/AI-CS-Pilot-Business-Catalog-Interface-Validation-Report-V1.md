# AI-CS Pilot Business Catalog Interface Validation Report V1

> 需求：R006 — Pilot Business Data Activation V1
>
> 代码基线：`ai-cs-pilot-baseline-v1@cbc77ed883cb99e2eff76ccb8eb3193bbddaba38`
>
> 验证对象：`f9257c214eba4d5cb77d4d7c290a9677bfcb88f2`
>
> 接口：`pilot-business-catalog.v1`
>
> 验证方式：静态架构验证 / 字段映射 / 状态机桌面推演
>
> 日期：2026-07-30

## 1. 验证结论

冻结设计能够表达并推演用户指定的九个业务场景，Owner、Provider、Consumer、状态分离、父子关系、部分成功和安全边界方向正确。Case 1–9 在设计层均可得到确定结果，其中旧测试数据兼容为条件通过，其余场景为设计通过。

Task Gate 结论为：`CONDITIONAL PASS`。

当前**不允许进入 R006 Implementation**。原因不是业务模型方向错误，而是冻结 V1 仍存在四项实施前 P0 空白：

1. 写入状态后所引用的 GET/read-back 接口没有冻结；默认 `DISABLED` 也无法通过正式 API 验证。
2. “旧测试数据继续可用”的一次性兼容集合没有固定选择规则、清单、幂等标识和数据回滚证据。
3. “不得修改 UI”与 B 当前 `AiChat.vue` 中必须移除的旧测试字段核心判断存在范围歧义。
4. 状态 receipt 的跨实体 `entity_ref` 类型，以及持久状态/人工确认记录的最小存储和迁移回滚要求尚未冻结到可编码程度。

这四项应在 `pilot-business-catalog.v1.1` 最小补充冻结中关闭。关闭并获 Interface Owner 批准后，才允许按照 Contracts → C → B → QA 顺序进入实施。

本报告不是运行测试报告，没有启动服务、写数据库、调用状态写接口或修改业务代码。

## 2. 验证范围与方法

### 2.1 范围

- 验证 Store、Product、SKU 的现有字段能否映射到冻结模型。
- 验证 `TEST/PILOT`、`DISABLED/ENABLED` 与父子级联能否覆盖九个 Case。
- 验证 B 现有目录加载、错误/空结果和人工复制路径能否迁移到新投影。
- 验证 A 可以保持不变。
- 识别实施前必须补齐的接口、兼容、数据和范围 Gate。

### 2.2 明确不包含

- 不实现或调用冻结中的新 endpoint。
- 不修改代码、UI、数据库、contracts、A、RAG、Prompt 或模型。
- 不迁移旧测试数据，不创建状态记录，不做浏览器或运行时 E2E。
- 不把静态推演写成接口已经实现或 Case 已真实运行通过。

### 2.3 证据来源

| 证据 | 用途 |
| --- | --- |
| `platform_backend/app/test_catalog/models.py` | 当前 Store/Product/SKU 的持久字段和父级关系。 |
| `platform_backend/app/operation_management/service.py` | C 新建店铺/商品的当前默认值与标识生成。 |
| `platform_backend/app/operation_management/schemas.py`、`routes.py` | 当前 C 运营 API 暴露字段；确认尚无客服可用状态读写接口。 |
| `platform_backend/app/product_knowledge/schemas.py`、`service.py` | 现有知识状态枚举与计算来源。 |
| `frontend/src/api/platformClient.ts`、`platformAdapter.ts`、`platformTypes.ts` | B 当前仍消费旧测试目录及其全量解析行为。 |
| `frontend/src/views/AiChat.vue` | B 当前整批安全判断、商品/SKU可选规则、错误优先级、A 请求上下文及人工复制边界。 |
| R004 Recovery 报告与状态看板 | 基线 contracts 0.2.0、旧测试目录 1 店/5 商品/18 SKU、47/47 知识同步。 |

## 3. 当前字段映射

### 3.1 Store

| 冻结字段 | 当前来源 | 映射结论 | 备注 |
| --- | --- | --- | --- |
| `tenant_id` | `TestStore.tenant_id` | 直接映射 | B→A 既有上下文必需。 |
| `store_code` | `TestStore.store_code` | 直接映射 | 保持现有稳定标识。 |
| `store_name` | `TestStore.store_name` | 直接映射 | 无需新业务模型。 |
| `platform` | `TestStore.platform` | 直接映射并保留原值 | 旧数据可为 `pdd`，C 新建可为 `pinduoduo`；B→A 不得擅自互换。 |
| `data_source` | 当前无正式字段 | 需要新增权威持久状态 | 旧测试数据仅在一次性初始化时可参考包属性；新 C 运营数据应固定为 `PILOT`。运行时不得由 B 推断。 |
| `customer_service_status` | 当前无正式字段 | 需要新增权威持久状态 | `trial_enabled` 只是 C 当前运营状态，不能替代。 |

当前 C 新建店铺同时产生 `tenant_id`、`store_code` 和内部整数 `store_ref`，写入 `test_data_mode=true`、`production_usable=false`、`response_mode=HUMAN_CONFIRM_REQUIRED`、`allow_auto_send=false`。这些值证明新店铺可以复用现有目录实体，但不能证明它已被客服启用。

### 3.2 Product

| 冻结字段 | 当前来源 | 映射结论 | 备注 |
| --- | --- | --- | --- |
| `product_id` | `TestProduct.product_id` | 直接映射 | C 新建值形如 `C-PRODUCT-...`。 |
| `store_code` | `TestProduct.store_code` | 直接映射 | 用于父级范围校验。 |
| `product_name` | `TestProduct.product_name_display` | 直接映射 | 不使用内部技术名称替代。 |
| `product_status` | `TestProduct.sales_status` | Provider 规范化 | `ON_SALE/ACTIVE → ON_SALE`；`OFF_SALE/INACTIVE → OFF_SALE`；其他为 `UNKNOWN`。 |
| `knowledge_status` | `ProductKnowledgeListItem.ai_status` | 直接使用 C 现有投影 | 枚举已存在：`EFFECTIVE`、`PARTIALLY_AVAILABLE`、`MISSING_KNOWLEDGE`、`UNCONFIRMED`。 |
| `customer_service_status` | 当前无正式字段 | 需要新增权威持久状态 | `review_status` 与 `publishable` 不能替代。 |

C 新建商品当前默认 `sales_status=OFF_SALE`、`review_status=REVIEWING`、`publishable=false`。冻结设计正确地把商品运营状态、知识状态和客服可用状态分开，因此无需重构 Product。

### 3.3 SKU

| 冻结字段 | 当前来源 | 映射结论 | 备注 |
| --- | --- | --- | --- |
| `sku_id` | `TestSku.sku_id` | 直接映射 | 保持既有标识。 |
| `product_id` | `TestSku.product_id` | 直接映射 | 当前数据库已有父级外键。 |
| `sku_name` | `TestSku.sku_name_display` | 直接映射 | 无需 Master Data。 |
| `customer_service_status` | 当前无正式字段 | 需要新增权威持久状态 | 旧 `publishable` 不能长期替代。 |
| `data_source` | 继承 Store | 设计可行 | 不需要在 B Contract 中重复声明。 |

当前 C 运营 API 没有手工创建 SKU 的入口，但基线测试目录已有 SKU。R006 V1 可以先覆盖既有/导入 SKU 的启停和投影；不得把本需求扩大为 SKU 创建或 Master Data 项目。

### 3.4 B Consumer 与 A 下游

| 当前行为 | 冻结后映射 | 验证结论 |
| --- | --- | --- |
| B 调用 `/api/v1/test-catalog/**` | 改为 `/api/v1/customer-service/catalog/**` | 路径可一一替换，调用层级不变。 |
| B 用 `trial_enabled/test_data_mode/production_usable/response_mode/allow_auto_send` 检查整批 Store | C 只投影已 `ENABLED` Store；B 只校验 schema、状态和父级关系 | 必须移除旧核心判断，否则 PILOT Store 永远会被拒绝。 |
| B 用 `publishable` 禁用 Product/SKU | 新投影只返回已启用实体 | Consumer 可将“存在于投影”视为可选择，不再推断 C 内部发布状态。 |
| B 解析任一 item 失败即整批失败 | 按 item 隔离，消费 `PARTIAL/warnings` | 需要 B adapter 行为变化，但不需要页面重设计。 |
| B 向 A 发送 `tenant_id/platform/store_code/product_id/sku_id` | 原样保留 | A 接口、模型、Prompt、RAG 无需修改。 |

## 4. 九个测试场景

以下结论是“冻结设计推演结果”，不是新接口运行结果。

### Case 1 — 旧测试数据兼容

| 项目 | 结论 |
| --- | --- |
| 输入 | 基线中 B 已可用的旧测试目录：1 Store、5 Product、18 SKU。 |
| 冻结规则 | 一次性初始化为 `data_source=TEST`；原本可选择的实体初始化为 `ENABLED`；技术标识保持不变；旧 endpoint 保留兼容期。 |
| 预期 | B 切换新投影后仍看到相同可用测试范围，A 继续收到相同上下文标识。 |
| 验证 | `CONDITIONAL PASS`。设计支持兼容，但“原本可用”的精确选择规则和实体清单尚未冻结。 |

一次性候选映射必须以当前 B 的真实可用语义生成，而不是把所有旧记录无条件启用：

- Store 候选：`trial_enabled=true`、`test_data_mode=true`、`production_usable=false`、`response_mode=SUGGESTION_ONLY`、`allow_auto_send=false`。
- Product 候选：属于候选 Store 且当前 `publishable=true`。
- SKU 候选：属于候选 Product 且当前 `publishable=true`。

上述旧字段只允许用于一次性兼容盘点，不能进入新 B 运行判断。

### Case 2 — 新增店铺默认 `DISABLED`

| 项目 | 结论 |
| --- | --- |
| 输入 | C 通过现有运营入口创建 Store。 |
| 冻结规则 | C 同时写入 `data_source=PILOT`、`customer_service_status=DISABLED`。 |
| 预期 | 创建成功但不出现在 B 目录投影。 |
| 验证 | `PASS`。现有 Store 身份字段足够，默认状态明确；但必须补充正式 read-back 才能无数据库直连地验收默认值。 |

### Case 3 — 开启店铺后 B 可见

| 项目 | 结论 |
| --- | --- |
| 输入 | 人工调用 C Store 状态 PUT，将目标状态设为 `ENABLED`。 |
| 冻结规则 | PUT 幂等；C 成为唯一状态权威；B Store 投影只返回已启用数据。 |
| 预期 | receipt 显示 `DISABLED → ENABLED`；B 刷新后可见 Store。 |
| 验证 | `PASS`。路径、状态和投影关系明确；实施前仍需补齐状态 GET/read-back。 |

### Case 4 — Product `DISABLED` 不可见

| 项目 | 结论 |
| --- | --- |
| 输入 | 在已启用 Store 下创建 Product。 |
| 冻结规则 | Product 默认 `DISABLED`，与 `OFF_SALE/REVIEWING/publishable=false` 相互独立。 |
| 预期 | B Store 可见，但其商品投影中没有该 Product。 |
| 验证 | `PASS`。Provider 过滤即可实现，B 不再解释旧 `publishable`。 |

### Case 5 — Product `ENABLED` 可见

| 项目 | 结论 |
| --- | --- |
| 输入 | 父 Store 已启用，人工将 Product 设为 `ENABLED`。 |
| 冻结规则 | 父级满足后允许启用；C Product 投影只返回已启用 Product。 |
| 预期 | B 在正确 Store 下看到并可选择 Product。 |
| 验证 | `PASS`。`store_code` 足以保持父级范围，B→A 的 `product_id` 不变。 |

### Case 6 — SKU 继承和隔离

| 项目 | 结论 |
| --- | --- |
| 输入 | 同一 Product 下存在已启用、未启用或父级异常 SKU。 |
| 冻结规则 | `data_source` 继承 Store；启用 SKU 要求 Store/Product 均启用；Product/Store 禁用时向下原子级联禁用。 |
| 预期 | 只返回自身和父级均启用、关系有效的 SKU；异常 SKU 被隔离，不影响同 Product 的有效 SKU。 |
| 验证 | `PASS`。当前 `TestSku.product_id` 已提供父级关系；不要求新增 SKU 创建功能。 |

### Case 7 — 单条异常不能导致全部 `No data`

| 项目 | 结论 |
| --- | --- |
| 输入 | 一批 items 中一条名称缺失、状态非法或父级关系错误，其余有效。 |
| 冻结规则 | C 返回有效 items、`result_status=PARTIAL` 和安全 warnings；B 按 item 隔离。只有 `COMPLETE + items=[] + total=0` 才是真实空目录。 |
| 预期 | B 保留有效记录；不能把 `PARTIAL`、503、超时或 envelope 错误显示为 `No data`。 |
| 验证 | `PASS`。失败优先级已定义；当前 B 的 `.map` 整批解析必须在实施时改为逐条结果。 |

若所有条目都异常，结果应是 `PARTIAL + items=[] + warnings!=[]`，B 进入目录异常语义而非真实空目录。

### Case 8 — 客服可用不代表自动发送

| 项目 | 结论 |
| --- | --- |
| 输入 | Store/Product/SKU 均为 `ENABLED`，客服获得 AI 建议。 |
| 冻结规则 | `ENABLED` 只允许显示和人工选择；不授权发送、退款、订单、售后或 ERP 动作。 |
| 预期 | B 仍是“生成建议 → 人工核对/修改 → 人工复制”；没有自动发送网络路径。 |
| 验证 | `PASS`。当前 B 已是复制而非发送结构，并持续显示不自动发送/退款边界；R006 不改变该结构。 |

安全验收必须检查没有新增发送/退款/业务执行请求，而不能只检查页面文案。

### Case 9 — 知识缺失 Product 仍可使用

| 项目 | 结论 |
| --- | --- |
| 输入 | Product 为 `MISSING_KNOWLEDGE` 或 `UNCONFIRMED`，但 C 人工确认其 `customer_service_status=ENABLED`。 |
| 冻结规则 | `knowledge_status` 不自动启停客服可用状态；B 的既有知识准备度提示不阻断选品、提问、编辑或复制。 |
| 预期 | Product 可进入 B 并发起既有 A 请求；客服看到知识不足提醒并人工核对。A 可以返回追问、转人工或受控无答案，不保证产生可直接采用的回答。 |
| 验证 | `PASS`。目录可用与知识质量已正确解耦；不得把“可选择”写成“AI 一定能回答”。 |

## 5. 设计风险

| 风险 | 等级 | 影响 | 处理要求 |
| --- | --- | --- | --- |
| 状态 PUT 后没有已冻结的 GET/read-back | P0 | 网络超时后无法判断是否已提交；Case 2 默认状态无法通过 API验收。 | 在 V1.1 冻结三类状态读取路径或在现有 Admin GET/create receipt 中冻结等价字段。 |
| 旧测试兼容集合定义不精确 | P0 | 可能误启用不可选择数据，或切换后丢失原可用 Product/SKU。 | 固定基线实体清单、选择规则、初始化版本、幂等和回滚证据。 |
| “禁止修改 UI”范围歧义 | P0 | B 当前 `AiChat.vue` 仍强制 `testDataMode=true`；不允许任何 Consumer 逻辑改动则 PILOT Store 无法进入。 | 明确允许最小非视觉 Consumer 逻辑修改；禁止的是布局、交互和产品设计变更。 |
| `entity_ref` 类型不统一 | P0 | Store 是整数 `store_ref`，Product/SKU 是字符串；共享 receipt schema 无法唯一确定类型。 | V1.1 固定全部传输为 non-empty string，或按实体拆分强类型 receipt。 |
| 状态持久化与确认记录未落到最小方案 | P0 | 不能保证重启后状态、人工确认、级联事务和回滚可复核。 | C 实施前提交最小 additive 存储/迁移/降级方案；禁止放在 `raw_data_json` 或复用测试字段。 |
| 并发采用提交顺序决定最终状态 | P1 | 两名运营同时启停时，后提交覆盖前提交。 | Pilot 可接受，但必须记录每次确认；未来需要正式权限时另行冻结 optimistic concurrency。 |
| `pdd` 与 `pinduoduo` 并存 | P1 | 错误规范化会使 A 的范围查询失配。 | Provider 原样投影，B 原样传 A；只对真正未知平台映射 `other`。 |
| `PARTIAL` warning 没有运营可视入口 | P1 | 异常可被技术记录但运营不一定看到。 | V1 先保证有效数据不丢失并保留安全诊断；是否增加运营视图必须另立 UI 需求。 |
| `confirmed_by` 不是认证 | 已知限制 | 不能证明正式身份或权限。 | 仅限受控内部 Pilot；不得宣称 RBAC/审计合规。 |
| 知识缺失仍可选择 | 业务风险，可控 | 客服可能得到无答案或低可用建议。 | 保留非阻断知识提醒、来源核对和人工复制；不自动发送。 |

## 6. 实施前阻塞项

### IV-B01 — 冻结状态只读回查

Owner：Control / Interface Owner，C Provider 评审。

必须在 V1.1 中选择并冻结一种方式：

- 新增与三类 PUT 对应的三类 GET；或
- 在现有 C Admin create/get/list response 中加入 `data_source`、`customer_service_status` 和最近确认元数据，并明确网络不确定后的查询路径。

必须定义 404、父级失效、未知状态、默认 `DISABLED` 和级联后的返回。关闭证据是请求/响应 schema 与 C/B/QA 评审，不是代码。

### IV-B02 — 固定旧测试兼容清单

Owner：C Data Owner、Control、QA。

必须从 `cbc77ed` 的只读基线生成无敏感实体清单，至少记录 Store/Product/SKU 标识、旧可用判断、目标 `TEST/ENABLED` 状态、初始化版本和总数。初始化必须幂等；重新执行不得产生重复记录或改变人工后续状态。必须有降级/回滚说明。

### IV-B03 — 明确 B 实施文件边界

Owner：Control、B Consumer。

必须明确：不允许 UI 重设计、布局/文案/交互扩张；但允许为消费新接口而进行最小非视觉逻辑修改，包括移除 `AiChat.vue` 的旧测试字段整批拒绝、让 Product/SKU可选性来自 C 投影，并保持现有错误优先级和人工复制路径。若 `AiChat.vue` 被绝对禁止修改，则 R006 在当前 B 架构上不可实现。

### IV-B04 — 固定 receipt 标识和最小持久化 Gate

Owner：Interface Owner、C、Contracts。

必须固定 Store/Product/SKU receipt 的 `entity_ref` 类型；同时明确客服可用状态和人工确认记录必须是独立、持久、可迁移/降级的 C 权威事实，禁止藏入 `raw_data_json` 或继续复用 `test_data_mode`、`production_usable`、`trial_enabled`、`publishable`。物理表/列可由 C 在最小设计中选择，但代码开始前必须评审迁移和回滚方案。

## 7. 是否允许进入 R006 Implementation

| Gate | 结论 |
| --- | --- |
| 九个业务 Case 可表达性 | PASS：9/9 可由冻结规则得到确定结果。 |
| 当前字段可映射性 | PASS：现有实体与标识足够，不需要 Master Data；新业务状态需要最小持久化。 |
| A 不修改 | PASS：B 可继续传既有上下文，A Contract 不变。 |
| 安全边界 | PASS：启用不产生自动发送、退款或业务执行授权。 |
| 错误与 `No data` 语义 | PASS：`COMPLETE`、`PARTIAL`、503/超时已分离。 |
| 接口可编码完整性 | FAIL：缺少状态 read-back，receipt 标识仍有类型歧义。 |
| 兼容迁移可执行性 | FAIL：旧测试数据集合、幂等初始化和回滚证据未冻结。 |
| 实施范围无歧义 | FAIL：B 最小 Consumer 逻辑改动与“禁止修改 UI”尚未澄清。 |

最终 Gate：`CONDITIONAL PASS / R006_IMPLEMENTATION_BLOCKED`。

决定：**当前不允许进入 R006 Implementation。**

下一入口是 `AI-CS Pilot Business Catalog Interface Freeze V1.1 Remediation`，仅关闭 IV-B01–IV-B04；仍不得修改代码、UI、数据库或运行服务。四项关闭并获 Interface Owner批准后，R006 才可从 `ai-cs-pilot-baseline-v1` 进入 Contracts 0.3.0 的第一个实施提交。

最终状态：`INTERFACE_VALIDATION_COMPLETE`
