# AI-CS Pilot Business Catalog Interface Validation Report V1.1

> 需求：R006 — Pilot Business Data Activation V1
>
> 验证对象：Legacy Compatibility Control / `pilot-business-catalog.v1.1`
>
> 冻结提交：`7fc4e26f799fa43101cb497dda05e7cefde36f3a`
>
> 代码基线：`ai-cs-pilot-baseline-v1@cbc77ed883cb99e2eff76ccb8eb3193bbddaba38`
>
> 当前共享contracts：`0.2.0`（本轮未修改）
>
> 验证方式：冻结文档与当前C/B代码的只读静态映射；未运行或实现新接口
>
> 日期：2026-07-30

本报告只判断V1.1是否已经足以授权后续实现。它不证明API、UI、数据库迁移、Legacy初始化、receipt持久化或B消费已经存在。本轮没有修改代码、UI、contracts、数据库、运行数据或服务，也没有进入Business Data Activation。

## 1. 验证结论

V1.1的业务方向成立：C承担准入，B只消费最终投影；TEST保持连续性，PILOT默认关闭；Store只阻断投影，Product状态保留；SKU继承Product。九个场景均可由该模型表达。

但当前冻结仍有两个P0接口空白：

1. 当前同一组旧表同时承载`IMPORTED_TEST_ONLY`测试包和`MANUAL_CREATED`运营数据，V1.1没有冻结迁移时如何把前者映射为`TEST + ENABLED`、把后者映射为`PILOT + DISABLED`。仅使用“cbc77ed历史快照”会误启用本应人工确认的C运营数据。
2. V1.1冻结了activation receipt对象，却没有冻结状态PUT在`changed=true/false`时的完整响应envelope，也没有冻结持久化receipt的只读查询/复核入口；因此C Admin、contracts和QA无法形成唯一可编码、可复验的回执契约。

总体结论：`CONDITIONAL PASS / R006_IMPLEMENTATION_BLOCKED`。

## 2. 当前代码与冻结字段映射

### 2.1 C数据来源

| V1.1概念 | 当前代码事实 | 验证判断 |
| --- | --- | --- |
| 历史TEST | `TestKnowledgePackage.import_status="IMPORTED_TEST_ONLY"`由测试包导入路径写入 | 有稳定来源证据，可用于一次性迁移；不得下发给B作为运行判断 |
| C运营数据 | `schema_version="c-operation-store.v1"`且`import_status="MANUAL_CREATED"` | 有稳定来源证据，应初始化为`PILOT + DISABLED` |
| `data_source` | Store/Product/SKU当前均无正式字段 | 需要additive持久化/投影，不能复用旧测试布尔字段 |
| Store客服状态 | 当前只有`trial_enabled`，C Admin将其映射为`ACTIVE/INACTIVE` | 可继续作为C内部店铺业务状态校验，但不能代替`customer_service_status`或暴露给B做准入判断 |
| Product客服状态 | 当前只有`sales_status/review_status/publishable` | 必须新增独立状态；`OFF_SALE`和知识缺失按V1.1不自动阻止客服使用 |
| SKU客服状态 | 当前只有`publishable` | 无需新增独立写状态；投影时从Product派生 |
| activation receipt | 当前无R006 receipt模型或接口 | V1.1字段可表达，但response/read-back仍需补充冻结 |

代码证据：

- `platform_backend/app/test_catalog/models.py`：`TestKnowledgePackage`、`TestStore`、`TestProduct`、`TestSku`仍是当前业务目录实体。
- `platform_backend/app/test_catalog/repository.py:86`：测试包使用`IMPORTED_TEST_ONLY`。
- `platform_backend/app/operation_management/service.py:124,132`：C运营创建使用`c-operation-store.v1`和`MANUAL_CREATED`。
- `platform_backend/app/operation_management/service.py:146,174`：当前C运营状态仍依赖`trial_enabled`。
- `platform_backend/app/operation_management/service.py:221,226`：新商品当前为`OFF_SALE/publishable=false`，但没有客服状态。

### 2.2 B Consumer

| 当前行为 | V1.1要求 | 验证判断 |
| --- | --- | --- |
| `platformClient.ts`读取`/api/v1/test-catalog/**` | 切换为`/api/v1/customer-service/catalog/**` | 路径替换范围明确 |
| `platformAdapter.ts`强制读取`trial_enabled/test_data_mode/production_usable/publishable` | 新adapter只读取V1.1 schema并隔离单条异常 | 需要最小Consumer实现 |
| `listEnvelope(...).map(...)`任一item失败会使整批失败 | `PARTIAL`与逐条隔离 | Case 8要求的变化明确可实现 |
| `AiChat.vue`整批检查旧Store字段 | 只信任C最终投影 | 必须删除旧整批准入判断 |
| Product/SKU可选状态和标签使用`publishable` | 不得用`publishable`决定可见性 | 必须移除该字段依赖；保持现有布局和人工工作流，不构成UI重设计 |

B现有`tenant_id/platform/store_code/product_id/sku_id`可以继续原样传给A，A接口、Prompt、模型和RAG无变化。

## 3. 场景结果

### Case 1 — 旧TEST店铺默认可用

| 项目 | 结论 |
| --- | --- |
| 冻结规则 | 历史有效TEST Store/Product初始化为ENABLED，SKU继承Product。 |
| 可表达性 | 可以。`data_source=TEST`与显式客服状态能够保持现有Pilot连续性。 |
| 当前映射 | 只有`IMPORTED_TEST_ONLY`可以确定为真正旧测试来源；当前表中还存在`MANUAL_CREATED`。 |
| 结果 | `CONDITIONAL PASS`。须先关闭IV11-B01，禁止把整个历史表快照无差别初始化为TEST。 |

### Case 2 — 运营关闭TEST店铺

| 项目 | 结论 |
| --- | --- |
| 操作 | Store状态`ENABLED → DISABLED`，C生成OPERATOR receipt。 |
| 投影 | Store及下游Product/SKU从B目录消失。 |
| 数据影响 | 不删除Store/Product/SKU，不改知识，不覆盖Product显式状态。 |
| 结果 | `PASS`。状态和父级投影边界确定。 |

### Case 3 — 重新开启TEST店铺

| 项目 | 结论 |
| --- | --- |
| 操作 | Store状态`DISABLED → ENABLED`，C生成新的OPERATOR receipt。 |
| 投影 | Store重新可见；仍保持ENABLED的Product及其有效SKU恢复可见。 |
| 数据影响 | 不自动开启之前被运营单独关闭的Product。 |
| 结果 | `PASS`。与“不级联改写Product”一致，回滚可逆。 |

### Case 4 — 新PILOT店铺默认不可用

| 项目 | 结论 |
| --- | --- |
| 未来新建 | C运营创建固定写入`PILOT + DISABLED`，create/list/detail回查相同状态。 |
| 基线事实 | 当前创建路径以`MANUAL_CREATED`写入旧表，并错误沿用测试字段；V1.1实施后必须映射为PILOT。 |
| 历史C创建数据 | V1.1未明确一次性迁移时按`MANUAL_CREATED`初始化为PILOT/DISABLED。 |
| 结果 | `CONDITIONAL PASS`。未来默认值明确，但已有C创建数据的迁移归类仍由IV11-B01阻塞。 |

### Case 5 — 开启PILOT店铺后B可见

| 项目 | 结论 |
| --- | --- |
| 前置校验 | 店铺名称、C内部业务状态和投影标识有效。 |
| 操作 | Store`DISABLED → ENABLED`并生成receipt。 |
| B结果 | Store可见；Product仍按各自状态过滤，不因Store开启而自动启用。 |
| 结果 | `PASS`。C权威投影与父子状态分离明确。 |

### Case 6 — Store禁用时Product状态保持

| 项目 | 结论 |
| --- | --- |
| 初始 | Store和Product均为ENABLED。 |
| Store禁用 | C只修改Store状态并记录一条Store receipt。 |
| Product | 仍保存ENABLED，但因父级不可用而不进入B投影；不产生Product receipt。 |
| Store恢复 | Product恢复可见，无需再次写Product。 |
| 结果 | `PASS`。避免级联覆写，满足可逆回滚。 |

### Case 7 — SKU继承Product状态

| 项目 | 结论 |
| --- | --- |
| 控制入口 | 没有SKU PUT、按钮或独立receipt。 |
| Product ENABLED | 关系有效的SKU派生为ENABLED并进入投影。 |
| Product/Store DISABLED | SKU全部不可见，SKU自身不发生状态写入。 |
| 异常SKU | 单条关系或字段异常时仅隔离该SKU。 |
| 结果 | `PASS`。当前`TestSku.product_id`已提供父级关系，无需SKU Master Data。 |

### Case 8 — 单条异常不能导致No data

| 项目 | 结论 |
| --- | --- |
| C Provider | 返回有效items、`result_status=PARTIAL`和安全warnings。 |
| B Consumer | 逐条解析并保留成功项，不再使用当前全量`.map`失败模式。 |
| 空结果 | 仅`COMPLETE + items=[] + total=0`表示真实No data。 |
| 结果 | `PASS`。失败语义和两侧职责已冻结，实施范围明确。 |

### Case 9 — 所有状态变化生成activation receipt

| 项目 | 结论 |
| --- | --- |
| 实际变化 | Store/Product每次合法状态变化生成唯一receipt；历史初始化使用`LEGACY_INITIALIZATION`，人工操作使用`OPERATOR`。 |
| 幂等重放 | 同状态请求`changed=false`且不生成新状态变化receipt。 |
| SKU | 不发生独立状态变化，因此不生成SKU receipt。 |
| 当前缺口 | receipt对象字段已冻结，但PUT完整response envelope和持久化receipt复核入口未冻结。 |
| 结果 | `CONDITIONAL PASS`。语义成立，IV11-B02关闭前不能形成唯一contracts和QA验收。 |

场景汇总：`PASS=6`、`CONDITIONAL PASS=3`、`FAIL=0`。

## 4. 设计风险

| 风险 | 等级 | 影响 | 控制要求 |
| --- | --- | --- | --- |
| 旧表混合两种来源 | P0 | 误把C运营数据当TEST自动启用，直接违反PILOT默认DISABLED | 关闭IV11-B01后才能实施迁移 |
| receipt响应和持久化复核不完整 | P0 | contracts、C Admin和QA可能各自发明envelope；无法证明所有变化已持久保存 | 关闭IV11-B02并形成schema |
| 历史TEST默认全启用 | 已接受业务风险 | 可能保留运营已经不再使用的数据 | 切换前输出preflight manifest；运营可即时关闭；异常记录隔离 |
| Store业务状态仍由`trial_enabled`投影 | P1 | 容易被误当作新的客服状态 | 仅允许C内部映射为ACTIVE/INACTIVE启用前置条件，禁止进入B契约 |
| Product当前无soft-delete字段 | P1 | “非删除”在当前基线只能解释为实体存在且父级有效 | 实施不得临时发明删除状态；未来若增加soft delete需另行冻结 |
| B当前在展示和准入中使用`publishable` | P1 | 只改API路径仍会继续错误禁用商品/SKU | 实施必须同时删除准入和标签依赖，但保持布局、导航和人工工作流 |
| `confirmed_by`不是认证身份 | 已知Pilot限制 | receipt不能证明正式权限或合规身份 | 只用于受控内部Pilot；不得宣称RBAC或正式审计合规 |
| 并发最后写入获胜 | P1 | 两名运营同时启停时后提交覆盖前提交 | 每次实际变化均留receipt；正式并发控制另立需求，不阻塞单运营Pilot |
| 新状态需要additive迁移 | P1 | 迁移/回滚不严谨会破坏旧目录 | C实现必须提供隔离迁移、幂等初始化、降级和旧接口兼容测试 |

## 5. 实施前剩余阻塞

### IV11-B01 — 冻结旧表来源迁移映射

Owner：Control / Interface Owner、C Data Owner、QA。

必须在任何migration或初始化代码前冻结：

```text
IMPORTED_TEST_ONLY
  → data_source=TEST
  → customer_service_status=ENABLED（结构有效记录）

MANUAL_CREATED / c-operation-store.v1
  → data_source=PILOT
  → customer_service_status=DISABLED

未知或冲突来源
  → 不进入B
  → 进入preflight异常清单
```

该映射只用于C的一次性迁移，不得成为B运行判断。必须附快照边界、幂等版本、分组数量和回滚规则。

### IV11-B02 — 冻结状态写入response与receipt复核

Owner：Interface Owner、C、contracts、QA。

必须明确：

- Store/Product状态PUT的完整成功response envelope；
- `changed=true`时`activation_receipt`必填，`changed=false`时为`null`；
- 当前实体状态、`activation_receipt_id`和服务器时间位于何处；
- 网络不确定后如何通过只读API确认最终状态；
- 持久化receipt按ID或实体查询的只读路径，或等价的可复核机制；
- receipt重放、唯一性、排序、404和权限边界。

关闭证据必须是可进入contracts 0.3.0的字段级schema，不是数据库表设计或UI截图。

## 6. Implementation Gate

| Gate | 结论 |
| --- | --- |
| 九个业务场景可表达 | PASS |
| TEST/PILOT未来默认值 | PASS |
| 当前混合来源可确定迁移 | FAIL：IV11-B01 |
| Store阻断但不覆写Product | PASS |
| SKU继承且无独立开关 | PASS |
| B只消费C投影 | PASS，需后续最小实现 |
| 单条异常隔离 | PASS，需C/B双侧测试 |
| receipt状态语义 | PASS |
| receipt可编码与持久化复核 | FAIL：IV11-B02 |
| A、安全与人工边界 | PASS |

最终Gate：`CONDITIONAL PASS / R006_IMPLEMENTATION_BLOCKED`。

当前不允许进入R006 Implementation。下一入口只能是`AI-CS Pilot Business Catalog Interface Freeze V1.1 Remediation`，仅关闭IV11-B01和IV11-B02；不得修改代码、UI、contracts、数据库或运行服务。两项阻塞完成并复核后，才可明确授权按`contracts 0.3.0 → C Provider/Data → B Consumer → QA`顺序实施。

最终状态：`INTERFACE_VALIDATION_V1_1_COMPLETE`
