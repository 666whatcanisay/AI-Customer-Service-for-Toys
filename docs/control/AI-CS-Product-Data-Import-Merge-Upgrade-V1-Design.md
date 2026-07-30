# AI-CS Product Data Import Merge Upgrade V1 Design

> 中文名称：《AI-CS Product Data Import Merge Upgrade V1 Design》
>
> 需求：R009 C运营数据导入升级 V1
>
> 文档类型：架构与产品设计，不是实现说明
>
> 设计日期：2026-07-30
>
> 代码盘点来源：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`
>
> 运行保护基线：`control/r008-runtime-startup-alignment-v1@dd379278837a4f816dfb626292a26b0c54cce0cc`
>
> 当前 Gate：`PRODUCT_IMPORT_MERGE_DESIGN_READY / R009_IMPLEMENTATION_INTERFACE_FREEZE_REQUIRED`

## 0. 设计结论

R009 将 C Admin 现有“资料上传与审核”从“先选单个商品/SKU，再补一份资料”升级为店铺范围内的批量 Excel 识别、增量 Merge 预览和人工审核流程。

目标流程固定为：

```text
选择店铺
  ↓
选择六类既有模板之一
  ↓
上传 Excel 并预检
  ↓
按店铺内业务身份识别商品 / SKU / FAQ / 安全规则 / AI反馈 / 知识缺口
  ↓
生成旧值、新值、变化字段和合并后快照
  ↓
IDENTIFIED_PENDING_REVIEW（已识别待审核）
  ↓
运营通过 / 驳回
  ↓
通过项受控写入正式业务数据；驳回项与审核证据保留
```

本设计遵循五个不可破坏原则：

1. Import Center 继续只负责六类 Excel 模板的说明、下载和填写规范，不承载上传、Merge 或审核。
2. Excel 不是数据库镜像；任何未出现在 Excel 中的实体或空白字段都不得被删除、清空或覆盖。
3. 所有新增和修改必须先形成 `IDENTIFIED_PENDING_REVIEW`，不得上传即生效。
4. 审核通过只代表 C 业务数据生效，不代表发布 RAG、修改 Prompt、训练模型或自动激活给 B。
5. C 是导入、识别、Merge 和审核的 Owner；A、B、contracts 在本设计阶段均不修改。

## 1. 当前资料上传流程分析

### 1.1 当前页面行为

当前页面位于 `admin_web/src/views/KnowledgeMaterialsView.vue`，上传顺序为：

```text
店铺 → 商品 → SKU（可选）→ 模板类型 → 资料名称 → 提交人 → 文件
```

后端入口位于 `platform_backend/app/api/knowledge_material_routes.py`。每次上传必须携带 `store_code`、`product_id`、可选 `sku_id`、`template_type` 和操作者信息。`knowledge_materials/service.py` 会要求 Excel 每一行的店铺、商品以及所选 SKU 与页面范围一致。

这条链路适合“给已存在的一个商品或 SKU 补充一份资料”，但不能满足店铺级批量维护：

- 页面在上传前就要求商品存在，Excel 不能识别并创建新商品。
- 一个文件被绑定到单个商品/SKU，不能同时处理同店铺多个商品。
- 识别结果是资料摘要，不是数据库旧值、新值和字段差异。
- 当前“审核通过”状态是 `APPROVED_FOR_ANALYSIS`，语义是允许进入 AI 质量分析，不是将数据 Merge 到正式业务表。
- 没有按实体生成的新增、更新、无变化、冲突结果，也没有正式数据写入收据。

### 1.2 现有模块能力与复用判断

| 模块 | 当前已有能力 | R009复用判断 | 不能直接复用的原因 |
| --- | --- | --- | --- |
| `ingestion` | `import_batches`、`import_rows`、固定商品/SKU XLSX预检、行错误、批次详情、`staged_product_skus` | 复用批次、行、哈希、预检和错误汇总框架 | 只支持旧技术模板；店铺来自Excel；没有六模板、正式数据查找、字段Merge和审核生效 |
| `knowledge_materials` | 六类模板定义、中文表头解析、必填校验、隐私/高风险规则、受控原文件保存、幂等收据、资料审核 | 复用模板注册、解析、受控存储、安全校验和幂等模式 | 当前资料审核只允许进入A分析，不能冒充业务数据审核；当前记录绑定单个商品/SKU |
| `operation_management` | 店铺创建/维护、商品创建、商品基础信息修改、店铺内同名校验 | 作为商品正式写入的领域服务入口 | 没有批量命令、SKU/FAQ/安全规则写接口，也没有字段级审核收据 |
| `product_knowledge` | 从商品、SKU、FAQ、安全规则和资料投影知识状态与缺口 | 保持只读投影，验收R009生效结果 | 不应成为导入写入Owner，也不能承担Merge决策 |
| `test_catalog` | 当前Pilot店铺、商品、SKU、FAQ、安全规则及冲突记录的实际持久化 | 在不做Master Data重构的前提下继续作为当前Pilot正式业务存储 | 旧ZIP整包导入是测试数据管道；`TestConflictRecord`缺少批次、旧/新值、审核人和生效收据，不能替代R009审计 |

### 1.3 现有资产的处理决定

- 复用 `ImportBatch` 和 `ImportRow`，通过向后兼容的扩展支持六模板和店铺绑定；不再新建一套重复的“导入批次表/导入记录表”。
- 保留 `StagedProductSku` 给旧版 `/imports/new` 兼容入口；R009不把六类实体强塞进该商品/SKU专用表。
- 复用六类 `_TEMPLATE_DEFINITIONS` 的业务字段和校验规则，但后续实现必须形成一个 C 侧 Template Registry，避免 Admin静态列表、下载文件和后端解析规则继续各自漂移。
- `KnowledgeMaterial` 继续用于不可变资料修订和AI质量分析；R009的业务数据候选、审核和生效必须使用独立状态，不改变 `APPROVED_FOR_ANALYSIS` 的既有语义。
- 当前 `test_catalog_*` 表继续作为Pilot数据落点；本需求不触发Master Data、ERP或全量数据模型重构。

## 2. 导入中心与资料上传边界说明

### 2.1 Import Center边界

Import Center 的定位保持不变：

| 保留职责 | 明确不承担 |
| --- | --- |
| 展示六类模板名称、用途和填写说明 | 不上传文件 |
| 下载既有六个 `.xlsx` 文件 | 不执行预检或Merge |
| 展示字段规范、安全边界和示例说明 | 不生成导入批次 |
| 引导运营前往“资料上传与审核” | 不执行通过、驳回或正式写入 |

六类模板标识保持为：

| 模板标识 | 中文名称 |
| --- | --- |
| `PRODUCT_KNOWLEDGE` | 商品知识采集模板 |
| `SKU_DIFFERENCE` | SKU差异知识采集模板 |
| `FAQ` | 客服FAQ知识采集模板 |
| `SAFETY_RULE` | 商品安全规则采集模板 |
| `AI_FEEDBACK` | 客服AI问题反馈模板 |
| `KNOWLEDGE_GAP` | AI知识缺口管理模板 |

不删除模板，不更改模板管理定位，不在 Import Center 增加批量导入工作台。

### 2.2 “资料上传与审核”边界

该页面是唯一的批量数据交易入口，负责：

- 选择目标店铺和模板类型。
- 上传并验证 Excel。
- 生成导入批次、行级识别结果和实体级Merge候选。
- 展示旧值、新值、变化字段、影响商品/SKU和冲突。
- 接收运营通过或驳回。
- 在审核通过后调用 C 领域服务写入正式业务数据并返回收据。

该页面不负责：

- 新建或编辑模板。
- 直接发布RAG、调用A分析、训练模型或修改Prompt。
- 激活数据给B；客服可用状态仍归R006治理。
- 自动发送、退款、ERP写入或其他业务执行。

## 3. 页面改造方案

### 3.1 页面结构

保持 AI-CS Admin 现有卡片、步骤提示、notice、badge、筛选和详情面板设计语言，不重新设计导航或全站样式。

页面固定为三步：

#### Step 1：选择店铺

- 数据来自 C `operation_management` 的有效店铺列表。
- 选项显示“店铺名称 · 平台”，例如“玩趣乐园积木店 · 拼多多”。
- 请求中提交不可变 `store_ref`；页面显示名称，不能仅以名称作为后端授权范围。
- 店铺未选择、已停用或在上传期间失效时禁止继续。
- 从 Import Center 带入的 `store_ref` 只作为预选值，后端仍需重新校验。

#### Step 2：选择模板类型

- 下拉只显示既有六类模板。
- 每项展示用途、必填字段摘要和“去导入中心下载模板”链接。
- 模板标识必须来自 C Template Registry，不在新页面复制第二份字段定义。
- 切换模板会清除已选文件、预检结果和未提交候选，避免用旧结果提交新类型。

#### Step 3：上传Excel并生成审核结果

- V1只接收 `.xlsx`；不把当前受控JSON快速补充入口扩展成批量导入入口。
- 上传后先执行预检，不直接写正式数据。
- 预检通过后生成批次和Merge候选；页面跳转或展开该批次的审核工作区。
- 审核工作区按“新增、修改、无变化、冲突/错误”分类，并支持按商品/SKU/状态筛选。

### 3.2 审核结果展示

每个候选至少显示：

- 批次号、模板类型、目标店铺和源行号。
- 实体类型与业务名称。
- 动作：`CREATE`、`UPDATE`、`NO_CHANGE`、`CONFLICT`。
- 旧值、新值、合并后值和变化字段数。
- 影响范围：商品、父商品、SKU或业务记录。
- 校验警告、冲突原因和是否可审核。
- 审核人、审核备注、决定时间和生效收据。

`NO_CHANGE` 可见但不进入人工审核；`CONFLICT` 必须先修正文件或重新识别，不能通过按钮强制覆盖。

### 3.3 页面异常和恢复

- 店铺不一致：整批阻断，展示所选店铺和Excel内检测到的店铺名称及行号。
- 单行字段错误：该行不可审核；其他合法行可以继续形成候选，但页面必须明确批次含错误，默认不提供“一键全部通过”。
- 网络中断：使用同一幂等键重试，返回同一批次，不重复建数据。
- 页面刷新：从批次接口恢复结果，不依赖浏览器本地状态作为事实来源。
- 店铺或模板变更：要求确认并清除当前未提交预检；已经落库的批次不改变原店铺/模板快照。

## 4. Excel解析方案

### 4.1 Template Registry

后续实现应把六类模板的以下信息统一为 C Provider 的受控注册表：

- `template_type`、中文名称、模板版本和文件名。
- 固定业务表头、必填字段、允许字段和字段类型。
- 目标实体、业务身份字段和父级依赖。
- 隐私、高风险、人工确认和来源规则。
- 字段到正式数据的受控映射。

Import Center 和上传页面只消费该注册表，不各自猜测模板规则。模板文件仍是现有六个文件，不重新创建。

### 4.2 解析顺序

1. 校验扩展名、MIME、ZIP/XLSX结构、文件大小、最大行数和解压大小。
2. 禁止宏、外部链接和公式；隐藏工作表只产生告警，不读取为业务数据。
3. 只读取“数据填写”，忽略“填写说明”“示例数据”“字段说明”。
4. 根据用户选择的 `template_type` 校验整套表头。
5. 若表头完整匹配另一个已知模板，返回模板类型不一致并提示识别出的模板名称。
6. 若缺少、重复或出现未知表头，返回表头校验错误。
7. 按模板完成必填、数据类型、长度、枚举、来源、人工确认和隐私校验。
8. 先完成整批店铺归属校验，再进行实体识别和Merge。

### 4.3 表头与“新字段”语义

“Excel出现数据库不存在的新字段，新增字段”只允许解释为：

> Excel中存在 Template Registry 已登记的业务字段，但当前实体该字段没有值或当前物理表没有独立列；审核通过后把该受控字段写入对应实体的规范列或命名空间化扩展JSON。

它不表示：

- 允许运营任意增加Excel列。
- 根据Excel表头自动执行 `ALTER TABLE`。
- 把未知字段静默放进数据库。

未知表头必须阻断并提示模板不匹配。这样同时满足模板安全和字段增量补充。

### 4.4 六模板处理类型

| 模板 | 识别实体 | V1处理语义 |
| --- | --- | --- |
| 商品知识 | `PRODUCT` | 新增或字段级Merge |
| SKU差异 | `SKU` | 在已解析父商品下新增或字段级Merge；不自动创建缺失父商品 |
| FAQ | `FAQ` | 以店铺、商品、可选SKU、规范化问题识别，新增或字段级Merge |
| 安全规则 | `SAFETY_RULE` | 以店铺、商品、安全主题识别，新增或字段级Merge |
| AI问题反馈 | `AI_FEEDBACK` | 审核后追加去敏反馈；按内容指纹幂等去重，不覆盖历史反馈 |
| 知识缺口 | `KNOWLEDGE_GAP` | 以店铺、商品、可选SKU和缺失主题识别，新增或更新运营缺口记录 |

AI反馈是审计型事实，不能使用“最后一行覆盖上一行”的Merge；同一内容指纹再次上传返回 `NO_CHANGE/DUPLICATE`。这是一项模板特定的安全例外，不影响商品类字段Merge原则。

## 5. 店铺校验方案

### 5.1 权威范围

- 页面提交 `selected_store_ref`。
- C根据 `store_ref` 读取当前 `store_code`、`tenant_id`、`package_id`、店铺名称、平台和有效状态。
- 批次保存这些值的不可变快照；Excel中的店铺名称只用于归属核对，不能决定写入目标。
- Excel不能创建店铺，也不能切换到另一个店铺。

### 5.2 比较规则

店铺名称比较只允许确定性规范化：Unicode NFKC、去除首尾空白、折叠连续空白。禁止模糊匹配、包含匹配、拼音匹配或自动纠错。

要求整份Excel所有非空数据行：

```text
normalized(Excel.店铺名称)
=
normalized(所选店铺.当前名称)
```

任何一行不一致、存在多个店铺名称或店铺字段为空，都整批阻断，不生成可审核Change Set。

### 5.3 错误响应

建议冻结错误码 `IMPORT_STORE_SCOPE_MISMATCH`，响应至少包含：

- `selected_store_ref`
- `selected_store_name`
- `selected_platform_name`
- `excel_store_names`
- `mismatched_row_numbers`
- 可执行提示“请确认后重新上传”

页面中文提示固定为：

```text
当前选择店铺：xxx
Excel数据所属店铺：xxx
请确认后重新上传。
```

该错误不可通过前端确认绕过；必须重新选择店铺或重新上传正确Excel。

## 6. Merge算法设计

### 6.1 实体识别

六个现有模板没有内部ID，因此V1采用店铺范围内的确定性业务身份，不做模糊合并：

| 实体 | V1身份键 | 零匹配 | 一条匹配 | 多条匹配 |
| --- | --- | --- | --- | --- |
| 商品 | `store_ref + normalized(product_name)` | `CREATE` | `UPDATE/NO_CHANGE` | `CONFLICT` |
| SKU | `resolved_product_id + normalized(sku_name)` | `CREATE` | `UPDATE/NO_CHANGE` | `CONFLICT` |
| FAQ | `resolved_product_id + optional sku_id + normalized(question)` | `CREATE` | `UPDATE/NO_CHANGE` | `CONFLICT` |
| 安全规则 | `resolved_product_id + normalized(safety_topic)` | `CREATE` | `UPDATE/NO_CHANGE` | `CONFLICT` |
| AI反馈 | 去敏后的稳定内容指纹 | `CREATE` | `NO_CHANGE/DUPLICATE` | 不覆盖 |
| 知识缺口 | `resolved_product_id + optional sku_id + normalized(missing_topic)` | `CREATE` | `UPDATE/NO_CHANGE` | `CONFLICT` |

同一店铺内商品名、同一商品内SKU名出现多义时，系统不得猜测。`SKU_DIFFERENCE`、FAQ、安全和缺口引用的父商品不存在时返回 `IMPORT_PARENT_NOT_FOUND`，不能顺手创建空壳商品。

同一文件多行指向同一实体时先按字段聚合：相同非空值可合并；同一字段存在两个不同非空值时标记 `IMPORT_INTRA_FILE_CONFLICT`，不能以“最后一行胜出”。

### 6.2 字段级Merge规则

对 Template Registry 中每个受控字段执行：

```text
current = 数据库当前值
incoming = Excel单元格值

incoming为空：
  merged = current
  result = PRESERVED

incoming有值 且 current为空：
  merged = incoming
  result = ADDED

incoming有值 且 与current规范化后相同：
  merged = current
  result = NO_CHANGE

incoming有值 且 与current不同：
  merged = incoming
  result = UPDATED
```

V1不提供“用空白清空字段”的语义。未来如需清空，必须设计显式清除标记并重新冻结接口；不得借空字符串、`NULL`、`-`或“无”推断删除。

### 6.3 三个核心情况

#### 情况1：Excel实体不存在于数据库

- 创建 `CREATE` Change Set。
- 只保存候选和差异，不写正式表。
- 候选状态为 `IDENTIFIED_PENDING_REVIEW`。
- 审核通过后由对应领域服务生成正式ID并写入；审核驳回后只保留候选和审核记录。

#### 情况2：数据库实体不存在于Excel

- 不生成删除或修改命令。
- 数据库原记录、字段、知识资料和状态保持不变。
- 批次报告不把它计为遗漏或异常。

#### 情况3：Excel和数据库同时存在实体

- 读取当前正式快照并逐字段Merge。
- Excel非空字段新增或更新；Excel空白字段保留旧值。
- 没有实际变化则记为 `NO_CHANGE`，不产生审核动作和写操作。
- 有变化则保存旧快照、传入快照、合并后快照和字段差异，进入 `IDENTIFIED_PENDING_REVIEW`。

### 6.4 并发与防覆盖

识别时保存正式数据的 `base_snapshot_hash`。运营点击通过前，C重新读取正式数据并计算当前哈希：

- 哈希一致：允许按已审核的合并后快照生效。
- 哈希变化：状态改为 `STALE_REVIEW_REQUIRED`，禁止覆盖，要求重新生成Merge预览。

现有表缺少统一版本列时可先使用规范化快照哈希，不允许省略并发检查。

### 6.5 生效原则

- 审核与生效由C在服务端完成；前端不能直接提交整份“最终对象”覆盖数据库。
- 每个Change Set使用独立事务，单条失败不回滚已经成功且无依赖的其他审核项，但批次必须准确显示部分成功。
- 有父子依赖时先应用商品，再应用SKU/FAQ/安全/缺口；父项失败时子项保持未生效并显示依赖错误。
- 每次通过、驳回和生效都必须幂等并返回可复核收据。
- 正式写入不得设置 `publishable=true`，不得触发RAG同步或A调用。
- R006未实施前，本需求不能声称导入后的商品会进入B；未来R006实施后，新PILOT数据仍应默认客服不可用，需运营单独开启。

## 7. 数据库影响分析

### 7.1 复用与新增建议

| 数据能力 | 结论 | 说明 |
| --- | --- | --- |
| 导入批次表 | 复用并扩展 `import_batches` | 增加所选店铺快照、模板类型、处理/审核/生效计数和批次状态；保留旧字段兼容 |
| 导入记录表 | 复用并扩展 `import_rows` | 增加模板类型、实体类型、业务身份、识别结果；保留原始/规范化JSON、行哈希和错误 |
| 旧商品/SKU暂存表 | 保留，不作为R009主表 | `staged_product_skus`继续服务旧入口，避免把FAQ等异构实体塞入专用表 |
| 实体Merge候选 | 需要新增 `import_change_sets` | 保存实体动作、目标ID、基础哈希、旧/传入/合并快照、源行和状态 |
| 字段变化记录 | 需要新增 `import_field_changes` | 保存字段路径、旧值、Excel值、合并值、变化类型和源行，供审核与审计 |
| 审核/生效记录 | 需要新增 `import_review_records` | Append-only保存决定、审核人、备注、幂等键、时间、生效结果和收据 |
| 运营知识缺口 | 需要新增独立业务表或先冻结等价结构 | 现有Assessment gaps是A分析证据，KnowledgeOptimizationTask又要求来源Problem，均不能冒充运营Excel缺口 |

### 7.2 建议实体最小字段

`import_change_sets` 至少需要：

- `change_set_id`、`batch_id`、`template_type`、`entity_type`、`operation`
- `source_row_numbers_json`
- `business_identity_json`
- `target_entity_id`（新增时可空）
- `base_snapshot_hash`
- `old_snapshot_json`、`incoming_snapshot_json`、`merged_snapshot_json`
- `review_status`、`apply_status`
- `created_at`、`updated_at`

`import_field_changes` 至少需要：

- `change_set_id`、`field_path`
- `old_value_json`、`incoming_value_json`、`merged_value_json`
- `change_type`：`ADDED / UPDATED / PRESERVED / NO_CHANGE`
- `source_row_number`

`import_review_records` 至少需要：

- `review_id`、`change_set_id`、`decision`
- `reviewed_by`、`review_note`、`reviewed_at`
- `idempotency_key`、`request_fingerprint`
- `apply_receipt_id`、`apply_result`、`applied_at`

### 7.3 正式业务落点

| 模板 | 推荐正式落点 | 当前缺口 |
| --- | --- | --- |
| 商品知识 | `TestProduct`规范列 + 命名空间化 `raw_data_json` | 需冻结模板字段到列/JSON的唯一映射 |
| SKU差异 | `TestSku`规范列 + 命名空间化 `raw_data_json` | 需增加C领域写入服务和父商品校验 |
| FAQ | `TestFaq` | 需冻结风险、回答动作、来源及问题身份映射 |
| 安全规则 | `TestSafetyRule` | 当前表没有商品关系；需小型向后兼容迁移或受控关联表，实施前必须选定 |
| AI问题反馈 | 既有 `AIResponseFeedback` | 需冻结中文分类到既有枚举的映射；只追加/去重，不覆盖历史 |
| 知识缺口 | 新的运营缺口记录 | 不能写入A Assessment伪造分析来源，也不能在无Problem时创建KnowledgeOptimizationTask |

### 7.4 数据安全与Git边界

- 原始Excel、数据库、导入快照、审核数据、日志和客户/客服内容不得进入Git。
- 原文件继续写入Target独立、Git忽略的受控运行目录；数据库只保存受控路径和哈希。
- AI反馈必须先确认已去除姓名、电话、地址、订单、支付和其他敏感信息；未确认整行阻断。
- API与日志不得输出原始文件内容；错误只返回最小必要字段、行号和业务提示。
- 驳回记录按审计保留，不物理删除；具体保留周期在实施前由数据治理冻结。

### 7.5 数据库实施Gate

本设计不执行迁移。实施前必须完成：

1. Alembic向上/向下迁移设计及隔离SQLite往返测试。
2. 对现有 `import_batches/import_rows` 的兼容性验证。
3. 安全规则商品关联方案确认。
4. 运营知识缺口正式表及状态所有权确认。
5. 备份、回滚、保留周期和生产数据迁移说明。

## 8. 状态流转设计

### 8.1 批次状态

| 状态 | 中文 | 含义 |
| --- | --- | --- |
| `RECEIVED` | 已接收 | 文件已受控接收，尚未完成校验 |
| `VALIDATING` | 校验中 | 正在校验模板、表头、必填项和店铺 |
| `VALIDATION_FAILED` | 校验失败 | 整批硬错误，不能生成可审核候选 |
| `IDENTIFIED_PENDING_REVIEW` | 已识别待审核 | 至少一个新增/修改候选等待人工决定 |
| `PARTIALLY_REVIEWED` | 部分已审核 | 批次中仍有待审核项 |
| `APPLIED` | 已生效 | 所有获批项已写入正式业务数据 |
| `PARTIALLY_APPLIED` | 部分生效 | 部分获批项失败或因依赖未生效 |
| `REJECTED` | 已驳回 | 全部可审核项被驳回 |
| `NO_CHANGE` | 无变化 | 所有合法行与正式数据一致 |
| `FAILED` | 处理失败 | 非业务校验的系统错误，保留证据可重试 |

### 8.2 Change Set状态

所有 `CREATE` 或 `UPDATE` 统一首先进入：

```text
IDENTIFIED_PENDING_REVIEW
中文：已识别待审核
```

合法流转：

```text
IDENTIFIED_PENDING_REVIEW
  ├─ 通过且基础快照未变化 → APPLIED
  ├─ 驳回                   → REJECTED
  └─ 基础快照已变化         → STALE_REVIEW_REQUIRED

STALE_REVIEW_REQUIRED
  └─ 重新识别 → IDENTIFIED_PENDING_REVIEW
```

`INVALID`、`CONFLICT`、`NO_CHANGE`是识别结果，不允许伪装为待审核并点击通过。

### 8.3 状态语义隔离

- `IDENTIFIED_PENDING_REVIEW` 是 R009 的业务数据候选状态。
- `APPROVED_FOR_ANALYSIS` 是既有 Knowledge Material 的A分析准入状态。
- 商品正式写入后的数据审核状态与 `publishable`、RAG状态分离；R009不得自动设置可发布。
- R006 的 `customer_service_status` 与R009审核完全独立；审核通过不等于客服可用。

## 9. 审核流程设计

### 9.1 审核粒度

- 基本审核单位为一个实体 Change Set，而不是整份Excel或单个字段。
- 页面可多选合法候选执行批量通过/驳回，但服务端仍逐项验证基础哈希和父子依赖。
- 有错误、冲突或基础数据变化的项不能被批量通过。
- 驳回必须填写原因；通过高风险FAQ、安全规则和AI反馈也必须填写核对说明。

### 9.2 审核内容

运营必须能看到：

- 业务身份与目标店铺。
- 是新增还是修改。
- 每个变化字段的旧值、Excel值和合并后值。
- 因Excel空白而保留的关键字段。
- 影响的商品、SKU、FAQ或安全规则。
- 资料来源、人工确认、风险和隐私告警。
- 父子依赖及可能影响范围。

### 9.3 审核与生效接口提案

本轮不修改contracts，以下仅作为后续 Interface Freeze 的唯一提案入口：

```text
Interface: c-business-data-import.v1
Owner / Provider: C Platform Backend
Consumer: C Admin
A / B: 不修改、不消费本接口
```

建议能力：

- 创建/预检批次：提交 `selected_store_ref + template_type + file + operator + idempotency_key`。
- 读取批次与Change Set：返回店铺快照、统计、行错误、旧/新/合并值和状态。
- 审核Change Set：提交 `decision + reviewed_by + review_note + idempotency_key + expected_base_snapshot_hash`。
- 读取审核/生效收据：返回 `review_id + apply_receipt_id + changed + status + applied_entity_id + timestamp`。

建议错误码：

| 错误码 | 行为 |
| --- | --- |
| `IMPORT_FILE_UNSUPPORTED` | 阻断；重新选择XLSX |
| `IMPORT_TEMPLATE_MISMATCH` | 阻断；提示已选与识别模板 |
| `IMPORT_HEADER_MISMATCH` | 阻断；展示缺失/未知表头 |
| `IMPORT_REQUIRED_FIELD_MISSING` | 行阻断；展示行号和字段 |
| `IMPORT_STORE_SCOPE_MISMATCH` | 整批阻断；展示两个店铺名称 |
| `IMPORT_ENTITY_AMBIGUOUS` | 行阻断；不得模糊选一条 |
| `IMPORT_PARENT_NOT_FOUND` | 行阻断；先维护父商品 |
| `IMPORT_INTRA_FILE_CONFLICT` | 实体阻断；修正冲突行 |
| `IMPORT_BASE_CHANGED` | 审核阻断；重新识别 |
| `IMPORT_IDEMPOTENCY_CONFLICT` | 409；相同键不同请求不得重放 |

幂等规则：同一操作者、店铺、模板、文件哈希和幂等键返回同一批次；同一审核键与相同决定返回同一收据；同一键但负载不同返回409。网络错误和5xx可用同一键安全重试，4xx业务错误不得自动重试。

### 9.4 六模板审核后的动作

- 商品/SKU/FAQ/安全：调用C领域服务写入当前Pilot正式表。
- AI反馈：写入既有去敏反馈记录，保持 `NEW`，不自动送A分析。
- 知识缺口：写入运营缺口记录，后续由人工决定是否关联问题中心或知识优化任务。
- 任一类型都不调用A、不发布RAG、不激活B、不触发自动业务动作。

## 10. 测试方案

### 10.1 Backend单元测试

- 六类模板均能识别正确表头和数据行。
- 选错模板时返回实际识别模板；缺失、未知、重复表头阻断。
- 公式、宏、外部链接、超大文件、超行数、空数据表阻断。
- 六类模板的必填、长度、类型、枚举、来源和人工确认规则覆盖。
- AI反馈未确认去敏、高风险FAQ/安全缺来源时阻断。

### 10.2 店铺范围测试

- 所选店铺与所有Excel行一致时通过。
- 单行不一致、多店铺、空店铺、停用店铺和不存在的 `store_ref` 均阻断。
- 错误响应同时返回当前所选店铺、Excel店铺和行号。
- 只允许NFKC/空白规范化，不允许模糊名称越权。

### 10.3 Merge矩阵

- 新商品生成 `CREATE + IDENTIFIED_PENDING_REVIEW`。
- 已有商品非空字段更新，空白字段保留。
- 数据库有而Excel没有的实体和字段完全不变。
- 已登记模板字段在数据库为空时生成 `ADDED`。
- 未登记未知列被拒绝，不自动建列。
- 完全相同数据生成 `NO_CHANGE`，不写数据库。
- 同一文件重复相同记录去重；重复但值冲突时阻断。
- 商品/SKU同名多义时阻断，不做模糊Merge。
- 正式数据在识别后被修改时触发 `STALE_REVIEW_REQUIRED`。

### 10.4 六类领域落点测试

- 商品、SKU、FAQ、安全规则各自只修改目标实体和指定字段。
- SKU父商品不存在时不创建空壳商品。
- AI反馈按指纹幂等追加，不覆盖历史记录，且不自动进入A分析。
- 知识缺口保留出现次数、优先级和工作流状态，不伪造A Assessment或Customer Feedback事件。
- 新增/修改均不设置 `publishable=true`，不触发RAG、Prompt、模型或B激活。

### 10.5 审核与事务测试

- 待审核项只有通过后才写正式数据。
- 驳回保留候选、字段差异、审核人、原因和时间。
- 相同审核幂等键重复调用返回同一收据。
- 相同键不同决定返回409。
- 单项失败不导致其他无依赖成功项丢失；批次正确显示 `PARTIALLY_APPLIED`。
- 父商品失败时依赖SKU/FAQ/安全/缺口不生效。
- 审核前基础哈希变化阻断覆盖。

### 10.6 Admin UI测试

- 页面严格显示三步：店铺、模板、Excel上传。
- 不再要求上传前选择商品/SKU。
- 六类模板名称与 Import Center 一致，并提供返回下载入口。
- 店铺不一致提示完整、可读且不可绕过。
- 旧值、新值、变化字段、影响商品/SKU和状态可访问、可筛选。
- 加载、空状态、部分错误、网络重试、页面刷新恢复和重复提交均覆盖。
- Import Center回归：六个模板、说明、下载和定位不变，不出现上传或审核按钮。

### 10.7 数据库与集成测试

- Alembic在隔离临时SQLite完成 `upgrade → downgrade → upgrade`。
- 旧 `import_batches/import_rows/staged_product_skus` 数据仍可读取。
- 新表外键、唯一约束、索引、级联/限制删除和审计保留符合设计。
- 使用隔离数据库执行六模板 `预检 → 候选 → 通过/驳回 → 正式投影` 全链路。
- C Backend全量pytest、Admin Vitest、typecheck和build通过。
- 测试不连接当前标准Runtime数据库，不写 `.runtime`，结束后清理临时产物并确认Git clean。

### 10.8 安全负向测试

必须证明上传或审核不会：

- 发布或同步RAG。
- 调用A、训练模型或修改Prompt。
- 自动启用R006客服状态或改变B可见性。
- 自动发送客服消息、退款、写ERP或执行其他业务动作。
- 删除现有商品、SKU、FAQ、安全规则、知识或历史审核证据。

## 11. 实施前剩余Gate

本设计完成后，R009仍不能直接进入编码。必须先关闭：

1. `R009-IF01`：冻结 `c-business-data-import.v1` 的请求/响应、错误码、状态、分页、幂等和收据读取接口。
2. `R009-DM01`：冻结六模板字段到正式数据的唯一映射，尤其是安全规则商品关系、AI反馈分类和运营知识缺口落点。
3. `R009-DB01`：评审向后兼容迁移、回滚、数据保留和现有导入记录兼容。
4. `R009-QA01`：建立六份真实但无客户数据的验收工作簿和Merge黄金样例。
5. 实施必须从当前唯一 `AI-CS` 项目派生受控Feature分支；不得直接在正在运行的标准Runtime工作树形成脏修改。

建议实施顺序为：

```text
Interface Freeze / Data Mapping Freeze
  ↓
C Backend：Template Registry + 批次/差异/审核持久化
  ↓
C Backend：六个领域适配器
  ↓
C Admin：三步上传与Merge审核
  ↓
隔离数据库与全量回归
  ↓
影子验证 / 人工业务验收
```

R006、A、B、RAG、Prompt、模型、自动业务动作均不在该实施链中。

## 12. Gate结论

| 项目 | 结论 |
| --- | --- |
| 当前流程与代码能力已盘点 | `PASS` |
| Import Center / 上传审核边界 | `FROZEN_BY_DESIGN` |
| 三步页面与店铺校验 | `FROZEN_BY_DESIGN` |
| 增量Merge和人工审核原则 | `FROZEN_BY_DESIGN` |
| 数据库影响已识别 | `PASS_WITH_PRE_IMPLEMENTATION_GATES` |
| 是否修改代码/UI/contracts/数据库/Runtime | `NO` |
| 是否允许立即实施 | `NO — INTERFACE_FREEZE_REQUIRED` |

最终状态：`PRODUCT_IMPORT_MERGE_DESIGN_READY`
