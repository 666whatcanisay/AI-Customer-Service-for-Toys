# AI-CS Product Knowledge Import V1 Implementation Plan

> 2026-07-30冻结更新：后端接口、状态、幂等、审核收据和数据库结构以[AI-CS Product Knowledge Import V1 Interface Freeze](interfaces/AI-CS-Product-Knowledge-Import-V1-Interface-Freeze.md)为唯一实施依据。该冻结统一采用import_batches、import_rows、import_change_sets、import_field_changes、import_review_records五表；本计划早期提出的product-specific candidate/review表名已被替代，不得按旧名称实现。

> 中文名称：《AI-CS Product Knowledge Import V1 Implementation Plan》
>
> 需求：R009 商品知识采集模板导入 V1
>
> 文档类型：实施计划，不是实现或运行验收报告
>
> 计划日期：2026-07-30
>
> 代码盘点来源：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS@dd379278837a4f816dfb626292a26b0c54cce0cc`
>
> 模板来源：`admin_web/public/templates/商品知识采集模板V1.xlsx`
>
> 模板SHA-256：`903FB51885B2ABD88CDEC19C233716B4FEB4E293C9CC1A908228309EEBA3F507`
>
> 当前 Gate：`PRODUCT_KNOWLEDGE_IMPORT_V1_READY / IMPLEMENTATION_NOT_AUTHORIZED / TARGET_RUNTIME_UNCHANGED`

## 0. 任务卡与实施结论

### 0.1 目标

只实现《商品知识采集模板V1.xlsx》的完整受控闭环：

```text
选择店铺
  ↓
选择商品知识采集模板
  ↓
上传固定Excel
  ↓
纯Python规则解析
  ↓
店铺校验
  ↓
商品识别
  ↓
字段级Merge预览
  ↓
IDENTIFIED_PENDING_REVIEW
  ↓
人工通过 / 驳回
  ↓
通过项正式写入C业务数据
```

### 0.2 本次允许与禁止

| 允许规划的实现范围 | 明确禁止 |
| --- | --- |
| C Admin“资料上传与审核”三步流程 | 通用模板理解AI |
| `ProductKnowledgeTemplateParser`纯Python解析 | 调用任何LLM或A服务 |
| 固定`product_knowledge_mapping.py` | 动态猜测字段、表头或目标属性 |
| 商品级识别、Merge预览、人工审核、正式写入 | 修改Prompt、RAG、模型或知识发布 |
| 商品知识模板专项数据库、API与测试 | 自动激活客服、自动发送、退款、ERP写入 |
| 其他五模板“开发中”能力提示及服务端阻断 | 实现SKU、FAQ、安全、AI反馈或知识缺口导入 |

### 0.3 Owner与影响线

- Owner / Provider：C Platform Backend。
- Consumer：C Admin。
- QA：Parser、Merge、迁移、API、UI和负向边界验收。
- A、B、OPS、共享contracts：不修改。
- Import Center：六模板展示、下载和填写说明保持原样，不修改定位和流程。

### 0.4 成功标准

1. 商品知识模板四个固定Sheet均被读取、校验并形成可追溯解析证据。
2. Parser无数据库访问、无网络访问、无AI依赖，只按固定代码规则输出标准结构。
3. 所选店铺与Excel店铺不一致时整批阻断。
4. 商品不存在生成新增候选；商品存在只处理Excel非空字段；空白和未出现数据保持不变。
5. 新增/修改只能进入`IDENTIFIED_PENDING_REVIEW`，人工审核前正式数据零写入。
6. 审核页准确展示旧值、Excel值、合并后值和`ADD / UPDATE / KEEP / NO_CHANGE`。
7. 通过后写入C业务数据并生成幂等收据；驳回保留记录；任何结果均不发布RAG或激活B。
8. 选择其他五模板时显示指定中文提示，服务端也拒绝绕过页面的上传请求。

## 1. 当前页面改造范围

### 1.1 当前事实

当前 `admin_web/src/views/KnowledgeMaterialsView.vue` 要求运营先选择店铺、商品和可选SKU，再选择模板并上传。该流程绑定一个既有商品，审核通过语义是`APPROVED_FOR_ANALYSIS`，不具备批量商品识别、字段差异或正式Merge写入。

`admin_web/src/views/ImportCenterView.vue` 已展示六个固定中文Excel模板并提供下载。本次不得改变该页面、六个文件、填写规范或模板管理定位。

### 1.2 目标页面范围

只改“资料上传与审核”页面的主上传工作区：

- 删除上传前“商品”和“SKU”选择要求。
- 新主流程固定为“选择店铺 → 选择模板类型 → 上传Excel”。
- 上传成功后进入同页或批次详情中的商品Merge审核区。
- 保留既有 Knowledge Material 历史记录和质量审核的可访问性，不删除历史数据或既有审核能力；新商品导入审核必须使用独立标题和状态，避免与`APPROVED_FOR_ANALYSIS`混淆。

预计实施文件：

| 路径 | 计划变更 |
| --- | --- |
| `admin_web/src/views/KnowledgeMaterialsView.vue` | 三步流程、模板能力状态、上传结果和Merge审核入口 |
| `admin_web/src/api/client.ts` | C内部商品知识导入API类型与调用 |
| `admin_web/tests/KnowledgeMaterialsView.spec.ts` | 三步、未开放弹窗、差异和审核测试 |
| `admin_web/src/views/ImportCenterView.vue` | **不修改** |
| `admin_web/tests/ImportCenterView.spec.ts` | 只运行回归；六模板必须保持 |

### 1.3 模板能力状态

| 模板 | 页面状态 | 上传行为 |
| --- | --- | --- |
| 商品知识采集模板 | 已支持 | 允许进入Step 3 |
| SKU差异知识采集模板 | 开发中 | 弹窗并阻断 |
| 客服FAQ知识采集模板 | 开发中 | 弹窗并阻断 |
| 商品安全规则采集模板 | 开发中 | 弹窗并阻断 |
| 客服AI问题反馈模板 | 开发中 | 弹窗并阻断 |
| AI知识缺口管理模板 | 开发中 | 弹窗并阻断 |

未开放模板提示文案必须逐字为：

```text
该模板导入功能暂未开放，请先使用商品知识采集模板。
```

前端提示不是权限边界。任何非`PRODUCT_KNOWLEDGE`上传请求，后端都返回422和`PRODUCT_KNOWLEDGE_IMPORT_NOT_AVAILABLE`。

## 2. Excel解析流程

### 2.1 已核验的固定模板结构

| Sheet | 当前范围 | Parser用途 | 是否产生商品数据 |
| --- | --- | --- | --- |
| `填写说明` | `A1:F26` | 读取模板名称、定位、填写角色、注意事项、来源要求和AI使用边界，保存为批次模板证据 | 否 |
| `数据填写` | `A1:P55` | 第5行读取固定16列表头，第6行开始读取非空业务行 | 是，唯一业务来源 |
| `示例数据` | `A1:P7` | 校验示例表头、列顺序和示例值是否仍符合固定字段校验器；示例行永不导入 | 否 |
| `字段说明` | `A1:F22` | 校验16个字段、必填等级和固定配置是否一致，保存字段规则证据 | 否 |

当前四个Sheet均可见、无公式、无外部链接、无VBA。实现不依赖整个文件二进制哈希完全不变，因为运营用Excel保存后容器哈希可能变化；使用结构签名判断是否仍是V1模板。

### 2.2 固定结构签名

必须同时满足：

1. Sheet集合且顺序为`填写说明 / 数据填写 / 示例数据 / 字段说明`，无额外或隐藏Sheet。
2. `填写说明!A1`为`商品知识采集模板 V1`。
3. `数据填写`和`示例数据`第5行均为固定16列表头且顺序一致。
4. `字段说明`第4行为固定规则表头，第5至20行字段名称与16列表头一致。
5. 文件无宏、外部链接、公式、加密或损坏的ZIP条目。

任一结构条件不满足，不允许用“相似模板”继续解析。

### 2.3 解析流水线

```text
文件安全检查
  ↓
Workbook固定结构检查
  ↓
读取并保存填写说明证据
  ↓
校验示例数据结构（不进入业务输出）
  ↓
校验字段说明与代码映射一致
  ↓
从数据填写第6行读取所有非空行
  ↓
固定字段类型、必填、长度和枚举校验
  ↓
规范化店铺、商品和字段值
  ↓
输出标准业务结构 + 独立Parser证据
```

### 2.4 行处理规则

- 全空行忽略；不要求数据连续。
- 最大文件5 MB、最大业务行建议2000、解压后总大小最大50 MB。
- 单元格公式一律拒绝，不读取缓存结果。
- 字符串执行Unicode NFKC、首尾空白清理和连续空白折叠；不做同义词或语义纠错。
- 日期只接受Excel日期值或明确日期字符串，并统一输出`YYYY-MM-DD`。
- 列表字段只按换行、中文分号或英文分号拆分；保留顺序、移除完全重复项，不按逗号猜测。
- 年龄只接受预定义正则格式，例如区间、`N岁+`、`N岁以上`、`N岁以下`；无法解析即行错误，不调用AI猜测。
- 同一文件中所有有效行必须只有一个规范化店铺名称，否则整批失败。

### 2.5 必填与条件必填

固定阻断字段为：店铺名称、商品名称、商品简介、核心卖点、资料来源、来源日期、是否人工确认。

`适用年龄 / 材质信息 / 安全提醒 / 包装内容 / 使用说明`在模板中为“条件必填”，但模板没有可机器判定的适用条件，且填写说明允许资料不足时留空。因此V1对其空值生成`CONDITIONAL_FIELD_EMPTY`警告，不擅自阻断或补值。

`是否人工确认`只接受`已确认`或`待确认`。`待确认`可进入导入审核，但不能因此被标记为已发布或AI可用。

## 3. Parser设计

### 3.1 文件结构

建议新增C领域目录：

```text
platform_backend/app/product_knowledge_import/
├── __init__.py
├── parser.py
├── product_knowledge_mapping.py
├── normalizers.py
├── merge.py
├── models.py
├── schemas.py
├── repository.py
├── service.py
└── routes.py
```

Parser入口固定为：

```text
ProductKnowledgeTemplateParser.parse(content: bytes, filename: str)
```

Parser必须是纯函数式领域组件：不访问数据库、不调用HTTP、不读取A/RAG、不加载模型、不使用Prompt，也不根据内容动态选择模板。

### 3.2 标准业务输出

业务输出严格使用用户指定的顶层结构：

```json
{
  "template_type": "PRODUCT_KNOWLEDGE",
  "store_name": "玩趣乐园积木店-拼多多",
  "products": [
    {
      "product_name": "积木小屋",
      "fields": {
        "summary": "儿童拼装积木玩具。",
        "core_selling_points": ["情景拼搭", "便于收纳"],
        "recommended_age": {
          "raw": "6岁+",
          "min": 6,
          "max": null
        },
        "material_information": "ABS塑料",
        "safety_notice": "含小零件，需成人陪同。",
        "package_contents": ["积木零件", "说明书"],
        "usage_instructions": "按说明书步骤拼装。",
        "play_introduction": ["情景游戏"],
        "common_customer_questions": ["适合几岁？"],
        "recommended_answer_direction": "按已确认年龄回答。",
        "source_reference": "商品说明书第2页",
        "source_date": "2026-07-30",
        "human_confirmation_status": "CONFIRMED",
        "remarks": ""
      }
    }
  ]
}
```

空Excel字段在`fields`中使用`null`或空列表的规范值，不从Parser阶段删除。Merge层必须能够区分“Excel为空”和“数据库为空”。

### 3.3 Parser证据

`填写说明`、`示例数据`和`字段说明`不塞进`products.fields`。Parser另行返回内部`ParserEvidence`，由批次保存：

- 模板标题、模板版本和结构签名。
- 填写说明的受控键值摘要。
- 四个Sheet的名称、可见性、范围和校验结果。
- 示例表头、示例行数量和示例校验结果，不保存为业务商品。
- 字段说明中的字段名、必填级别、知识级别和规则摘要。
- Parser版本、文件SHA-256、识别时间、警告和错误。

字段说明是“一致性证据”，`product_knowledge_mapping.py`才是运行映射权威。Excel文本不能改变代码目标字段。

### 3.4 错误模型

| 错误码 | 行为 |
| --- | --- |
| `PRODUCT_KNOWLEDGE_FILE_UNSUPPORTED` | 非xlsx、宏文件或超过限制，整批阻断 |
| `PRODUCT_KNOWLEDGE_TEMPLATE_STRUCTURE_INVALID` | Sheet集合、标题或固定位置错误 |
| `PRODUCT_KNOWLEDGE_TEMPLATE_HEADER_MISMATCH` | 数据/示例表头不一致 |
| `PRODUCT_KNOWLEDGE_TEMPLATE_FIELD_RULE_MISMATCH` | 字段说明与代码配置不一致 |
| `PRODUCT_KNOWLEDGE_FORMULA_NOT_ALLOWED` | 任意公式，整批阻断 |
| `PRODUCT_KNOWLEDGE_REQUIRED_FIELD_MISSING` | 指定行缺少固定必填字段 |
| `PRODUCT_KNOWLEDGE_FIELD_VALUE_INVALID` | 日期、年龄、枚举或长度非法 |
| `PRODUCT_KNOWLEDGE_MULTIPLE_STORES` | 数据行出现多个店铺，整批阻断 |
| `PRODUCT_KNOWLEDGE_TEMPLATE_EMPTY` | 没有业务数据行 |
| `PRODUCT_KNOWLEDGE_IMPORT_NOT_AVAILABLE` | 请求的模板不是商品知识模板 |

错误返回只包含最小必要的Sheet、行号、字段、错误码和中文建议，不回显整行敏感内容。

## 4. 字段映射设计

### 4.1 固定配置职责

`product_knowledge_mapping.py`定义：

- 16个Excel字段的固定顺序。
- 逻辑目标字段。
- 必填等级、类型、最大长度和规范化函数。
- Merge空值策略。
- 当前Pilot持久化适配位置。

不得从`字段说明`Sheet动态生成Mapping，不得使用列名相似度或AI推断未知字段。

### 4.2 完整固定映射

| Excel字段 | 逻辑目标 | 规范化 | 当前Pilot落点 |
| --- | --- | --- | --- |
| 店铺名称 | `import_scope.store_name` | NFKC文本 | 只做所选店铺校验和批次快照，不写商品字段 |
| 商品名称 | `product.name` | NFKC文本，2–255字符 | 新商品写`product_name_official/display`；既有商品作为身份键，V1不支持改名 |
| 商品简介 | `product_knowledge.summary` | 文本，最大4000 | `raw_data_json.product_summary` |
| 核心卖点 | `product_knowledge.core_selling_points` | 固定分隔符拆成有序列表 | `raw_data_json.main_selling_points` |
| 适用年龄 | `product_knowledge.recommended_age` | 固定正则解析raw/min/max | `TestProduct.age_min/age_max`和`raw_data_json.recommended_age_text` |
| 材质信息 | `product_knowledge.material_information` | 文本 | `raw_data_json.material` |
| 安全提醒 | `product_knowledge.safety_notice` | 文本 | `TestProduct.safety_summary` |
| 包装内容 | `product_knowledge.package_contents` | 固定分隔符拆成有序列表 | `raw_data_json.package_contents` |
| 使用说明 | `product_knowledge.usage_instructions` | 文本 | `raw_data_json.usage_instructions` |
| 玩法介绍 | `product_knowledge.play_introduction` | 固定分隔符拆成有序列表 | `raw_data_json.play_method` |
| 客户常问问题 | `product_knowledge.common_customer_questions` | 固定分隔符拆成有序列表 | `raw_data_json.common_customer_questions`；不创建FAQ记录 |
| 推荐回答方向 | `product_knowledge.recommended_answer_direction` | 文本 | `raw_data_json.recommended_answer_direction`；不是Prompt |
| 资料来源 | `governance.source_reference` | 文本 | `TestSourceEvidence.metadata_json`和导入审计元数据 |
| 来源日期 | `governance.source_date` | ISO日期 | `TestSourceEvidence.metadata_json`和导入审计元数据 |
| 是否人工确认 | `governance.human_confirmation_status` | `已确认→CONFIRMED`、`待确认→PENDING` | 来源证据和产品导入审计状态 |
| 备注 | `governance.remarks` | 文本，禁止客户个人信息 | 来源证据和导入审计元数据 |

### 4.3 映射边界

- `客户常问问题`不会在V1创建`TestFaq`；FAQ模板尚未开放。
- `推荐回答方向`是运营事实边界，不写Prompt、不调用A。
- `安全提醒`只更新当前商品安全摘要，不创建安全规则实体；安全规则模板尚未开放。
- 价格、库存、财务、采购、平台技术标识及未知列全部拒绝。
- 商品名称是V1唯一商品身份。模板没有稳定商品ID，因此无法安全识别“改名”；改名必须走现有商品维护入口。

## 5. Merge设计

### 5.1 商品识别

店铺校验通过后，在所选`store_ref`对应范围中使用：

```text
store_ref + normalized(product_name)
```

确定商品：

- 0条匹配：`CREATE`候选。
- 1条匹配：构建现有快照并执行字段级Merge。
- 多条匹配：`PRODUCT_KNOWLEDGE_PRODUCT_AMBIGUOUS`，不得模糊选择。

同一Excel内商品名称重复：完全相同的规范化字段合并为一条候选；同一字段有两个不同非空值时标记`PRODUCT_KNOWLEDGE_DUPLICATE_CONFLICT`，不采用最后一行覆盖。

### 5.2 固定Merge算法

对每个可Merge逻辑字段：

| 条件 | 合并后值 | 变化类型 |
| --- | --- | --- |
| Excel为空，数据库有值 | 数据库旧值 | `KEEP` |
| Excel为空，数据库也为空 | 空 | `KEEP` |
| Excel有值，数据库为空 | Excel值 | `ADD` |
| Excel有值，与数据库规范化值相同 | 数据库旧值 | `NO_CHANGE` |
| Excel有值，与数据库值不同 | Excel值 | `UPDATE` |

禁止整行或整对象覆盖。数据库已有但Excel没有的商品完全不参与本批次；Excel没有填写的字段不生成清空命令。

### 5.3 Merge候选输出

每个商品候选保存：

- 商品业务身份、源行号和`CREATE / UPDATE / NO_CHANGE / CONFLICT`。
- 目标`product_id`，新增时为空。
- `old_snapshot`、`excel_snapshot`、`merged_snapshot`。
- 字段差异数组：`field_key / field_name / old_value / excel_value / merged_value / change_type`。
- `base_snapshot_hash`，用于审核时防止并发覆盖。
- 警告、阻断原因和父批次信息。

只要存在`ADD`或`UPDATE`，候选进入：

```text
IDENTIFIED_PENDING_REVIEW
中文：已识别待审核
```

全部只有`KEEP/NO_CHANGE`时标记`NO_CHANGE`，不允许重复写正式数据。

### 5.4 审核并发与幂等

- 审核通过前重新读取正式商品并计算当前快照哈希。
- 哈希变化时转`STALE_REVIEW_REQUIRED`，要求重新生成预览，不覆盖他人修改。
- 审核请求必须带`Idempotency-Key`和`expected_base_snapshot_hash`。
- 同键同请求返回同一收据；同键不同决定返回409。
- 每个候选独立事务。一个商品失败不能让其他无依赖商品丢失已完成结果，批次准确显示部分状态。

## 6. 数据库落点

### 6.1 复用现有导入基础

- 复用`import_batches`：文件、哈希、批次状态和统计。
- 复用`import_rows`：原始行、规范化行、哈希、错误和警告。
- 不使用`staged_product_skus`承载商品知识；该表继续服务旧商品/SKU技术模板。
- 不创建第二套导入批次表或导入行表。

### 6.2 专项迁移建议

后续实施新增`0009_product_knowledge_import_v1`，只做向后兼容的C侧增量：

1. `import_batches`增加可空字段：`selected_store_ref`、`selected_store_code`、`selected_store_name_snapshot`、`template_type`、`template_version`、`parser_version`、`template_evidence_json`、`source_storage_path`。
2. 新增`product_knowledge_import_candidates`：每个商品一条Merge候选。
3. 新增`product_knowledge_import_reviews`：append-only通过/驳回和生效收据。

候选表最小字段：

- `candidate_id`、`batch_id`、`import_row_ids_json`。
- `product_identity_key`、`product_name`、`target_product_id`。
- `operation`、`status`、`base_snapshot_hash`。
- `old_snapshot_json`、`excel_snapshot_json`、`merged_snapshot_json`、`field_changes_json`。
- `warnings_json`、`created_at`、`updated_at`。

审核表最小字段：

- `review_id`、`candidate_id`、`decision`。
- `reviewed_by`、`review_note`、`reviewed_at`。
- `idempotency_key`、`request_fingerprint`、`expected_base_snapshot_hash`。
- `apply_receipt_id`、`apply_result`、`applied_product_id`、`applied_at`。

### 6.3 原文件和模板证据

- 上传Excel保存在Target独立、Git忽略的受控运行目录。
- 数据库只保存内部受控路径、文件哈希和Parser证据；API、日志和B/A均不得返回原始路径或文件内容。
- `示例数据`只保存结构/校验摘要，不把虚构示例存成商品。
- 原文件、数据库、日志、客户内容和运行快照绝不进入Git。

### 6.4 正式商品写入

审核通过由`OperationManagementService`新增的领域方法执行，不允许导入路由直接拼SQL：

- 新商品：生成服务端ID，写`TestProduct`，`sales_status=OFF_SALE`、`publishable=false`，不创建SKU。
- 已有商品：只写`merged_snapshot`中获审字段，不替换完整`raw_data_json`。
- 每个获批商品创建/追加`TestSourceEvidence`，记录来源、来源日期、文件哈希、批次ID和审核收据，并把`source_id`追加到商品来源列表。
- 更新`TestKnowledgePackage.counts_json`时复用现有商品创建逻辑。
- `human_confirmation_status=CONFIRMED`且导入审核通过时可将商品数据审核状态设为`APPROVED`；源状态为`PENDING`时正式保存但保持`REVIEWING`。
- 无论上述状态如何，`publishable`始终为false；不调用RAG、不调用A、不变更R006客服可用状态。

## 7. UI流程

### 7.1 Step 1：选择店铺

- 只显示C运营中心现有有效店铺，选项为“店铺名称 · 平台”。
- 页面提交`store_ref`；后端解析为`store_code/tenant/package/name`，不能只信前端名称。
- Excel所有业务行的规范化店铺名称必须等于当前店铺名称，否则整批阻断并显示：

```text
当前选择店铺：xxx
Excel数据所属店铺：xxx
请确认后重新上传。
```

### 7.2 Step 2：选择模板类型

- 六类模板全部可见。
- 商品知识模板显示绿色“已支持”。
- 其他五类显示中性“开发中”。
- 点击开发中模板后弹出指定提示，关闭弹窗后不进入上传步骤。
- 页面提供“前往导入中心下载模板”的普通导航链接；不把上传逻辑放进Import Center。

### 7.3 Step 3：上传Excel

- 只接受`.xlsx`。
- 显示文件名、大小、模板版本、目标店铺和解析进度。
- 解析完成显示：商品总数、新增数、修改数、无变化数、错误数、警告数。
- 存在整批硬错误时不生成可审核候选。

### 7.4 Merge审核区

按商品展示字段表：

| 商品 | 字段 | 旧值 | Excel值 | 合并后值 | 变化类型 |
| --- | --- | --- | --- | --- | --- |
| 积木小屋 | 适用年龄 | 3岁+ | 6岁+ | 6岁+ | `UPDATE` |
| 积木小屋 | 材质信息 | ABS | 空 | ABS | `KEEP` |
| 积木小屋 | 包装内容 | 空 | 礼盒 | 礼盒 | `ADD` |
| 积木小屋 | 商品简介 | 拼装玩具 | 拼装玩具 | 拼装玩具 | `NO_CHANGE` |

运营可以逐商品通过或驳回；驳回必须填写原因。存在`CONFLICT`或`STALE_REVIEW_REQUIRED`时禁用通过按钮。通过后显示正式收据，不显示“已发布到AI”等误导文案。

### 7.5 C内部接口提案

本轮不修改contracts；后续实施前按C内部接口评审：

| 方法与路径 | 用途 |
| --- | --- |
| `GET /api/v1/admin/product-knowledge-imports/capabilities` | 返回六模板和`SUPPORTED / IN_DEVELOPMENT`状态 |
| `POST /api/v1/admin/product-knowledge-imports` | 店铺+模板+文件上传、纯规则解析、生成批次和候选 |
| `GET /api/v1/admin/product-knowledge-imports/{batch_id}` | 批次统计、错误和模板证据摘要 |
| `GET /api/v1/admin/product-knowledge-imports/{batch_id}/candidates` | 商品Merge候选与字段差异 |
| `POST /api/v1/admin/product-knowledge-imports/{batch_id}/candidates/{candidate_id}/review` | 通过/驳回并返回生效收据 |

Owner与Provider均为C，Consumer为C Admin。A/B不得消费或推测这些状态。

## 8. 测试方案

### 8.1 Parser单元测试

- 当前真实《商品知识采集模板V1.xlsx》四Sheet全部通过。
- Sheet缺失、改名、乱序、额外/隐藏Sheet、错误标题全部失败。
- 数据/示例表头和字段说明16字段任一不一致均失败。
- `示例数据`通过校验但永不出现在`products`。
- 填写说明和字段规则被保存到`ParserEvidence`。
- 公式、宏、外链、坏ZIP、超限文件、空数据和超过行数均失败。
- Parser测试中禁止任何网络/LLM调用；依赖图不得引用A、RAG或模型模块。

### 8.2 字段映射测试

- 16个Excel字段与固定逻辑字段逐一断言。
- 7个固定必填字段缺失时返回准确行号/字段。
- 5个条件字段为空时只警告、不补值。
- 日期、年龄区间/上下界、列表分隔、NFKC和枚举转换覆盖。
- 未知列、动态字段和相似列名均拒绝。
- `客户常问问题`不创建FAQ，`推荐回答方向`不修改Prompt。

### 8.3 店铺与商品识别测试

- 所选店铺与Excel一致通过；单行不一致、多店铺、空店铺、停用或不存在店铺全部阻断。
- 同店铺商品0/1/多条匹配分别得到CREATE、MERGE、AMBIGUOUS。
- 同文件完全重复商品去重，字段冲突阻断。
- 改名不做模糊识别或自动合并。

### 8.4 Merge矩阵测试

- 空→有值为`ADD`。
- 有值→不同非空值为`UPDATE`。
- 有值+Excel空为`KEEP`。
- 相同规范化值为`NO_CHANGE`。
- Excel未出现商品和字段保持数据库原状。
- 整个产品JSON不会被覆盖；未知历史键保持。
- 基础快照变化时变为`STALE_REVIEW_REQUIRED`。

### 8.5 数据库与审核测试

- 在隔离临时SQLite执行`0008→0009→0008→0009`往返。
- 旧`import_batches/import_rows/staged_product_skus`可继续读取。
- 上传只写批次/行/候选，不写`TestProduct`。
- 审核通过才新增/更新商品和来源证据；驳回只留审计。
- 同一审核幂等键不重复写；不同请求复用键返回409。
- `CONFIRMED/PENDING`分别产生正确商品审核状态，二者都保持`publishable=false`。

### 8.6 API与UI测试

- capabilities准确返回1个已支持、5个开发中。
- 非商品知识模板API上传返回422。
- 页面严格显示三步流程和模板状态。
- 五个开发中模板均弹出逐字指定提示，不能进入上传。
- 商品Merge表完整展示旧值、Excel值、合并值和四类变化。
- 错误、警告、空状态、刷新恢复、网络重试和并发过期状态覆盖。
- 既有Knowledge Material历史记录仍可访问。
- Import Center回归证明六模板、下载和说明完全不变。

### 8.7 全量回归与禁止边界

- C Backend全量pytest通过。
- C Admin Vitest、typecheck和production build通过。
- Git只包含批准代码/文档，运行原文件和数据库不入库。
- 集成测试显式断言没有A请求、RAG同步、Prompt修改、模型调用、客服激活、自动发送、退款或ERP写入。
- 标准Runtime不直接用于迁移或写测试；使用隔离SQLite和临时受控文件目录。

## 9. 建议实施顺序与Gate

```text
Commit 1：ProductKnowledgeTemplateParser + 固定Mapping + Parser测试
  ↓
Commit 2：0009迁移 + Batch/Row复用 + Candidate/Review模型
  ↓
Commit 3：店铺校验 + 商品识别 + Merge服务 + API
  ↓
Commit 4：审核生效 + TestProduct/TestSourceEvidence领域写入
  ↓
Commit 5：KnowledgeMaterialsView三步流程 + 未开放模板弹窗 + 审核表
  ↓
Commit 6：全链路、迁移、回归与运行隔离验收
```

进入编码前必须确认：

1. 上述C内部接口、状态、错误码、幂等和收据通过Interface Owner复核。
2. `0009`迁移、受控原文件路径、保留与回滚方案通过数据治理复核。
3. 从唯一AI-CS源码基线创建不承载标准Runtime的C Feature工作区。
4. 本计划不授权其他五模板、A/B/contracts、R006、RAG、Prompt或模型开发。

## 10. Gate结论

| Gate项 | 结果 |
| --- | --- |
| 单模板范围 | `FROZEN` |
| 纯Python固定规则Parser | `FROZEN` |
| 四Sheet用途与结构 | `VERIFIED` |
| 16字段固定映射 | `READY_FOR_IMPLEMENTATION_REVIEW` |
| Merge与人工审核 | `READY_FOR_IMPLEMENTATION_REVIEW` |
| 数据库/API/UI实施 | `NOT_EXECUTED` |
| 其他五模板 | `DEFERRED / BLOCKED_BY_DESIGN` |
| Target代码、UI、数据库、Runtime是否变化 | `NO` |

最终状态：`PRODUCT_KNOWLEDGE_IMPORT_V1_READY`
