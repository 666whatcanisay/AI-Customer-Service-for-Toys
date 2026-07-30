# AI-CS Product Knowledge Import V1 Interface Freeze

> 中文名称：《AI-CS Product Knowledge Import V1 Interface Freeze》
>
> 需求：R009 商品知识采集模板导入 V1
>
> 接口标识：product-knowledge-import.v1
>
> 版本：V1
>
> 日期：2026-07-30
>
> Owner / Provider：C Platform Backend
>
> Consumer：C Admin
>
> 不受影响：A、B、RAG、R006、共享 contracts 0.2.0
>
> 当前 Gate：PRODUCT_KNOWLEDGE_IMPORT_INTERFACE_READY / IMPLEMENTATION_NOT_AUTHORIZED / TARGET_RUNTIME_UNCHANGED

## 0. 冻结结论

本接口只服务固定的《商品知识采集模板V1.xlsx》，不设计通用模板理解、不调用LLM，也不实现其他五类模板。

冻结后的链路为：

~~~text
上传固定Excel
  ↓
持久化批次与原始行证据
  ↓
固定规则预检
  ↓
商品识别与字段级Merge
  ↓
IDENTIFIED_PENDING_REVIEW
  ↓
运营逐商品APPROVE或REJECT
  ↓
APPROVE才在单商品事务内写正式C业务数据
  ↓
返回append-only review_receipt
~~~

核心约束：

1. 上传与预检只能写导入暂存区，不能写TestProduct或TestSourceEvidence。
2. 预检通过后，每个商品生成一个import_change_set；每个字段生成一个import_field_change。
3. V1审核粒度是单个商品变更集，不提供批次级“一键全部通过”。
4. APPROVE成功才允许字段级更新正式数据；REJECT只写审核记录。
5. 任何正式写入都不发布RAG、不调用A、不激活B、不修改R006状态。
6. 旧import_batches、import_rows和staged_product_skus继续兼容；不建立第二套批次表或行表。
7. 当前只冻结设计，没有创建接口、表、迁移或运行配置。

## 1. Excel上传接口设计

### 1.1 接口

| 项目 | 冻结值 |
| --- | --- |
| 方法 | POST |
| 路径 | /api/v1/admin/product-knowledge-imports |
| Content-Type | multipart/form-data |
| 首次成功 | HTTP 201 |
| 幂等重放 | HTTP 200，并返回 Idempotency-Replayed: true |
| Owner / Provider / Consumer | C / C Platform Backend / C Admin |

### 1.2 请求

| 逻辑字段 | 传输位置 | 类型与约束 | 说明 |
| --- | --- | --- | --- |
| store_ref | form | string，1..255 | C现有有效店铺的后端引用；前端显示名不是权威 |
| template_type | form | enum | V1唯一允许 PRODUCT_KNOWLEDGE |
| file | multipart file | .xlsx | 固定《商品知识采集模板V1.xlsx》结构 |
| operator | form | string，1..128 | 当前Pilot操作人标识；用于审计，不等于认证/RBAC |
| idempotency_key | Header: Idempotency-Key | string，1..255 | 必填；form和body不得再放第二份同义字段 |

请求示意：

~~~http
POST /api/v1/admin/product-knowledge-imports
Content-Type: multipart/form-data
Idempotency-Key: pk-import-20260730-001

store_ref=<store-ref>
template_type=PRODUCT_KNOWLEDGE
operator=<operator>
file=<商品知识采集模板V1.xlsx>
~~~

### 1.3 响应

~~~json
{
  "batch_id": "uuid",
  "status": "IDENTIFIED_PENDING_REVIEW"
}
~~~

响应只能包含batch_id和status，不返回原文件路径、文件内容、数据库位置或完整Parser证据。

上传采用同步V1处理：文件通过传输层准入后先创建batch，再完成固定解析、店铺校验、商品识别和Merge暂存，最后返回当前稳定状态。

允许的上传响应状态：

| status | 含义 | 是否可审核 |
| --- | --- | --- |
| PREFLIGHT_FAILED | 模板、Sheet、字段、店铺或商品识别存在阻断错误 | 否 |
| IDENTIFIED_PENDING_REVIEW | 至少一个商品存在ADD或UPDATE | 是，只审核对应change set |
| NO_CHANGE | 全部商品只有KEEP或NO_CHANGE | 否 |
| FAILED | 处理发生非业务预期错误，正式数据零写入 | 否 |

RECEIVED和PARSING是内部短暂状态，不作为正常同步响应的最终状态。

### 1.4 模板限制

以下template_type在V1均返回HTTP 422和错误码PRODUCT_KNOWLEDGE_IMPORT_NOT_AVAILABLE：

- SKU_DIFFERENCE
- CUSTOMER_FAQ
- PRODUCT_SAFETY_RULE
- AI_CUSTOMER_FEEDBACK
- AI_KNOWLEDGE_GAP

用户提示固定为：

~~~text
该模板导入功能暂未开放，请先使用商品知识采集模板。
~~~

### 1.5 上传错误

| HTTP | error_code | 条件 |
| ---: | --- | --- |
| 400 | IMPORT_REQUEST_INVALID | multipart缺失或逻辑字段为空 |
| 404 | IMPORT_STORE_NOT_FOUND | store_ref不存在 |
| 409 | IMPORT_IDEMPOTENCY_CONFLICT | 同operator和同key绑定了不同请求指纹 |
| 409 | IMPORT_DUPLICATE_FILE | 不同key重复提交同店铺、同模板、同文件且已有非失败批次 |
| 413 | IMPORT_FILE_TOO_LARGE | 超过平台冻结上传限制 |
| 415 | IMPORT_FILE_TYPE_UNSUPPORTED | 非.xlsx或MIME不允许 |
| 422 | PRODUCT_KNOWLEDGE_IMPORT_NOT_AVAILABLE | 选择其他五模板 |
| 422 | IMPORT_STORE_NOT_ELIGIBLE | 店铺删除、失效或不可用于当前运营维护 |
| 500 | IMPORT_PROCESSING_FAILED | 批次记为FAILED；正式业务数据零写入 |

业务预检错误在已创建的批次中表达为PREFLIGHT_FAILED，不用HTTP失败吞掉批次证据。

## 2. 预检接口

### 2.1 接口

| 项目 | 冻结值 |
| --- | --- |
| 方法 | GET |
| 路径 | /api/v1/admin/product-knowledge-imports/{batch_id}/preflight |
| 说明 | 读取上传批次的持久化预检结果；不重复上传文件、不重新写正式数据 |

查询不存在的batch返回HTTP 404和IMPORT_BATCH_NOT_FOUND。

### 2.2 响应结构

~~~json
{
  "batch_id": "uuid",
  "status": "IDENTIFIED_PENDING_REVIEW",
  "can_review": true,
  "file_result": {
    "original_filename": "商品知识采集模板V1.xlsx",
    "file_sha256": "sha256",
    "file_size_bytes": 12345,
    "template_type": "PRODUCT_KNOWLEDGE",
    "template_version": "V1",
    "parser_version": "product-knowledge-parser-v1",
    "parse_status": "PASS",
    "error_count": 0,
    "warning_count": 0
  },
  "sheet_results": [],
  "field_validation_result": {},
  "product_identification_result": {}
}
~~~

### 2.3 文件解析结果

file_result冻结字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| original_filename | string | 仅安全文件名，不含目录 |
| file_sha256 | string | 64位小写SHA-256 |
| file_size_bytes | integer | 原始上传大小 |
| template_type | enum | 固定PRODUCT_KNOWLEDGE |
| template_version | string | 固定V1 |
| parser_version | string | 固定解析器版本 |
| parse_status | PASS / FAIL | 结构解析是否通过 |
| error_count | integer | 阻断问题数 |
| warning_count | integer | 非阻断问题数 |

### 2.4 Sheet识别结果

sheet_results固定包含四项，顺序固定：

1. 填写说明
2. 数据填写
3. 示例数据
4. 字段说明

单项结构：

~~~json
{
  "sheet_name": "数据填写",
  "role": "BUSINESS_DATA",
  "required": true,
  "present": true,
  "visible": true,
  "row_count": 10,
  "header_status": "MATCHED",
  "formula_cell_count": 0,
  "errors": [],
  "warnings": []
}
~~~

role枚举：

- TEMPLATE_INSTRUCTIONS
- BUSINESS_DATA
- FORMAT_EXAMPLE
- FIELD_DEFINITION

缺Sheet、改名、隐藏必需Sheet、错误表头、公式、外链、宏或额外未知Sheet均按固定Parser规则给出错误，不进行相似度猜测。

### 2.5 字段校验结果

field_validation_result：

~~~json
{
  "expected_field_count": 16,
  "detected_field_count": 16,
  "missing_fields": [],
  "unknown_fields": [],
  "data_rows": 8,
  "valid_rows": 8,
  "invalid_rows": 0,
  "duplicate_rows": 0,
  "conflict_rows": 0,
  "issues": [
    {
      "row_number": 6,
      "field_key": "recommended_age",
      "severity": "WARNING",
      "error_code": "CONDITIONAL_FIELD_EMPTY",
      "message": "适用年龄为空，将保留现有值。"
    }
  ]
}
~~~

issues不得默认返回整行raw_data、原始文件路径或无关字段；日志也不得记录整份上传内容。

### 2.6 商品识别结果

product_identification_result：

~~~json
{
  "store_ref": "store-ref",
  "selected_store_name": "玩趣乐园积木店-拼多多",
  "excel_store_names": ["玩趣乐园积木店-拼多多"],
  "store_match_status": "MATCHED",
  "summary": {
    "product_count": 3,
    "new_count": 1,
    "existing_count": 2,
    "no_change_count": 0,
    "conflict_count": 0
  },
  "products": [
    {
      "change_set_id": "uuid",
      "product_name": "积木小屋",
      "product_identity_key": "governed-hash-or-key",
      "match_type": "EXISTING",
      "target_product_id": "product-id",
      "source_row_numbers": [6],
      "status": "IDENTIFIED_PENDING_REVIEW",
      "issues": []
    }
  ]
}
~~~

store_match_status只有MATCHED、MISMATCH、MULTIPLE、EMPTY。

match_type只有NEW、EXISTING、AMBIGUOUS、NOT_EVALUATED。

商品身份固定为store_ref范围内的规范化商品名称精确匹配。不得模糊匹配、自动识别改名或跨店匹配。

## 3. Merge预览接口

### 3.1 接口

| 项目 | 冻结值 |
| --- | --- |
| 方法 | GET |
| 路径 | /api/v1/admin/product-knowledge-imports/{batch_id}/merge-preview |
| Query | page默认1；page_size默认20、最大100；status和change_type可选 |
| 排序 | 商品首次源行号升序，字段按固定Mapping顺序 |

### 3.2 响应

~~~json
{
  "batch_id": "uuid",
  "status": "IDENTIFIED_PENDING_REVIEW",
  "items": [
    {
      "product": {
        "change_set_id": "uuid",
        "product_name": "积木小屋",
        "target_product_id": "product-id",
        "operation": "UPDATE",
        "status": "IDENTIFIED_PENDING_REVIEW",
        "base_snapshot_hash": "sha256",
        "version": 1
      },
      "fields": [
        {
          "field_key": "recommended_age",
          "field_label": "适用年龄",
          "old_value": "3岁+",
          "incoming_value": "6岁+",
          "merged_value": "6岁+",
          "change_type": "UPDATE"
        }
      ]
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
~~~

old_value、incoming_value和merged_value使用JSON标量、数组或null；接口不返回任意嵌套数据库对象。

### 3.3 change_type

| change_type | 固定条件 | merged_value |
| --- | --- | --- |
| ADD | Excel非空，旧值为空 | incoming_value |
| UPDATE | Excel非空，与旧值规范化后不同 | incoming_value |
| KEEP | Excel为空 | old_value；旧值也为空时为null |
| NO_CHANGE | Excel非空，与旧值规范化后相同 | old_value |

禁止定义DELETE、CLEAR或REPLACE_OBJECT。Excel未出现的商品和字段不进入删除流程。

### 3.4 商品operation

| operation | 条件 |
| --- | --- |
| CREATE | 当前店铺中不存在该规范化商品名称 |
| UPDATE | 当前店铺中存在唯一商品，且至少一个字段ADD/UPDATE |
| NO_CHANGE | 全部字段KEEP/NO_CHANGE |
| CONFLICT | 多实体匹配或同Excel非空字段冲突 |

只有CREATE和UPDATE且status为IDENTIFIED_PENDING_REVIEW时允许审核。

## 4. 审核接口与review_receipt

### 4.1 接口

| 项目 | 冻结值 |
| --- | --- |
| 方法 | POST |
| 路径 | /api/v1/admin/product-knowledge-imports/{batch_id}/change-sets/{change_set_id}/reviews |
| Content-Type | application/json |
| 首次成功 | HTTP 201 |
| 幂等重放 | HTTP 200，并返回同一review_receipt |
| 粒度 | 单商品change set |

Idempotency-Key请求头必填。

### 4.2 请求

~~~json
{
  "decision": "APPROVE",
  "operator": "operator-id",
  "review_note": "已核对商品资料来源。",
  "expected_base_snapshot_hash": "sha256",
  "expected_change_set_version": 1
}
~~~

decision固定为：

- APPROVE
- REJECT

规则：

- APPROVE的review_note可选。
- REJECT的review_note必填，去除首尾空白后1..1000字符。
- operator必填，1..128字符；是Pilot审计标识，不替代正式认证。
- expected_base_snapshot_hash和expected_change_set_version均必填。

### 4.3 成功响应

~~~json
{
  "review_receipt": {
    "receipt_id": "uuid",
    "batch_id": "uuid",
    "change_set_id": "uuid",
    "decision": "APPROVE",
    "outcome": "APPLIED",
    "reviewed_by": "operator-id",
    "reviewed_at": "2026-07-30T10:00:00Z",
    "applied_product_id": "product-id",
    "applied_field_count": 2,
    "before_snapshot_hash": "sha256-or-null",
    "after_snapshot_hash": "sha256-or-null"
  }
}
~~~

review_receipt是生效或驳回事实，不表示RAG发布、AI训练、客服激活或自动业务执行。

outcome固定为：

| outcome | 含义 |
| --- | --- |
| APPLIED | APPROVE事务成功，正式商品已字段级写入 |
| REJECTED | REJECT已留痕，正式商品零写入 |
| STALE_REVIEW_REQUIRED | 当前正式快照与预览基础不一致，没有写正式数据 |
| APPLY_FAILED | 生效事务失败并回滚，正式业务数据零写入 |

### 4.4 状态与错误

| HTTP | error_code | 行为 |
| ---: | --- | --- |
| 404 | IMPORT_BATCH_NOT_FOUND | 不创建审核记录 |
| 404 | IMPORT_CHANGE_SET_NOT_FOUND | 不创建审核记录 |
| 409 | IMPORT_REVIEW_IDEMPOTENCY_CONFLICT | 同key不同请求指纹 |
| 409 | IMPORT_REVIEW_ALREADY_FINALIZED | 已终态后提交相反决策 |
| 409 | IMPORT_REVIEW_STALE | 快照或version变化；记录STALE_REVIEW_REQUIRED，不写正式数据 |
| 422 | IMPORT_REVIEW_NOT_ALLOWED | NO_CHANGE、CONFLICT、PREFLIGHT_FAILED等不可审核 |
| 422 | IMPORT_REJECT_REASON_REQUIRED | REJECT无原因 |
| 500 | IMPORT_APPLY_FAILED | 事务已回滚；记录失败收据，不伪造APPLIED |

IMPORT_REVIEW_STALE和IMPORT_APPLY_FAILED已经形成审核尝试事实，其错误响应必须携带同一结构的review_receipt，outcome分别为STALE_REVIEW_REQUIRED或APPLY_FAILED。请求校验、资源不存在、幂等冲突和不可审核状态发生在审核事实创建前，不返回伪造receipt。

## 5. 数据库设计

### 5.1 关系总览

~~~mermaid
erDiagram
  import_batches ||--o{ import_rows : contains
  import_batches ||--o{ import_change_sets : identifies
  import_change_sets ||--o{ import_field_changes : describes
  import_change_sets ||--o{ import_review_records : audited_by
  import_batches ||--o{ import_review_records : aggregates
~~~

正式业务表TestProduct和TestSourceEvidence不作为级联子表；它们只在APPROVE事务中通过领域服务写入，并由review_receipt保存结果引用。

### 5.2 import_batches

定位：复用现有批次表，保存上传身份、状态、统计、文件哈希、店铺范围、Parser证据和上传幂等。

现有字段保持：

- id
- tenant_id
- import_type
- original_filename
- file_sha256
- status
- total_rows
- valid_rows
- invalid_rows
- duplicate_rows
- created_at
- completed_at
- created_by
- error_message

0009新增可空兼容字段：

| 字段 | 类型 | 约束与用途 |
| --- | --- | --- |
| store_ref | String(255) | PRODUCT_KNOWLEDGE新批次必填；旧批次可空 |
| store_code_snapshot | String(96) | 上传时店铺代码快照 |
| store_name_snapshot | String(255) | 上传时店铺名称快照 |
| platform_snapshot | String(32) | 上传时平台快照 |
| file_size_bytes | Integer | 上传文件大小；用于稳定预检投影 |
| template_type | String(64) | 新批次固定PRODUCT_KNOWLEDGE |
| template_version | String(32) | 固定V1 |
| parser_version | String(64) | 固定Parser版本 |
| idempotency_key | String(255) | 新上传必填；旧批次可空 |
| request_fingerprint | String(64) | store_ref、template_type、file_sha256的规范化哈希 |
| template_evidence_json | Text | 四Sheet与结构签名摘要，不保存示例为正式数据 |
| source_storage_path | String(500) | 仅内部受控相对路径；API和日志不得回显 |
| version | Integer | 乐观并发版本，默认1 |
| updated_at | DateTime(TZ) | 最近批次聚合更新时间 |

API请求中的operator写入现有created_by，不增加第二个同义操作人字段；tenant_id由store_ref在后端解析，不接受前端单独提交。

索引与唯一约束：

- 保留ix_import_batches_tenant_id。
- 保留ix_import_batches_file_sha256。
- 新增uq_import_batches_idempotency_scope(import_type, created_by, idempotency_key)；旧NULL不冲突。
- 新增ix_import_batches_store_template_status(store_ref, template_type, status)。
- 新增ix_import_batches_duplicate_guard(store_ref, template_type, file_sha256)；非唯一，失败重试由应用状态判断。
- 新增ix_import_batches_created_at(created_at)。

批次status：

- RECEIVED
- PARSING
- PREFLIGHT_FAILED
- IDENTIFIED_PENDING_REVIEW
- NO_CHANGE
- PARTIALLY_REVIEWED
- COMPLETED
- FAILED

PARTIALLY_REVIEWED表示部分change set已终态、部分仍待审核。COMPLETED表示所有可审核change set已进入APPROVED_APPLIED或REJECTED；具体结果必须读change set和receipt，不能从COMPLETED推断全部通过。

### 5.3 import_rows

定位：复用现有行表，保存数据填写Sheet每个业务行的原始、规范化、校验和商品识别证据。

现有字段保持：

- id
- batch_id
- source_row_number
- raw_data_json
- normalized_data_json
- row_hash
- validation_status
- error_codes_json
- warning_codes_json
- created_at

0009新增可空兼容字段：

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| sheet_name | String(64) | 新流程固定数据填写 |
| product_identity_key | String(512) | store_ref + normalized product name的受控身份键或其稳定投影 |
| product_match_type | String(32) | NEW / EXISTING / AMBIGUOUS / NOT_EVALUATED |
| target_product_id | String(96) | 唯一匹配时保存；新增和冲突为空 |

状态复用：

- VALID
- INVALID
- DUPLICATE
- CONFLICT

索引与约束：

- 保留uq_import_row_batch_source(batch_id, source_row_number)。
- 保留ix_import_rows_batch_status(batch_id, validation_status)。
- 保留ix_import_rows_row_hash(row_hash)。
- 新增ix_import_rows_batch_product(batch_id, product_identity_key)。

raw_data_json只用于受控审核和追溯，不由B/A消费，不进入普通日志。

### 5.4 import_change_sets

定位：每个识别商品一个字段级Merge候选，是V1审核对象。

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| id | String(36) | UUID主键 |
| batch_id | String(36) | FK import_batches.id，ON DELETE CASCADE |
| source_row_ids_json | Text | 参与该商品候选的import_rows.id有序数组 |
| product_identity_key | String(512) | 非空 |
| product_name | String(255) | 非空 |
| target_product_id | String(96) | 新增时可空 |
| operation | String(32) | CREATE / UPDATE / NO_CHANGE / CONFLICT |
| status | String(40) | 见下方状态 |
| base_snapshot_hash | String(64) | 新增候选使用固定EMPTY哈希 |
| old_snapshot_json | Text | 只含允许Merge的治理字段 |
| incoming_snapshot_json | Text | 只含Excel明确提供字段 |
| merged_snapshot_json | Text | 确定性合并结果 |
| error_codes_json | Text | 默认[] |
| warning_codes_json | Text | 默认[] |
| applied_product_id | String(96) | APPLIED后填写 |
| version | Integer | 默认1 |
| created_at | DateTime(TZ) | 非空 |
| updated_at | DateTime(TZ) | 非空 |
| applied_at | DateTime(TZ) | 可空 |

status：

- IDENTIFIED_PENDING_REVIEW
- NO_CHANGE
- CONFLICT
- APPROVED_APPLIED
- REJECTED
- STALE_REVIEW_REQUIRED
- APPLY_FAILED

合法状态流转：

~~~text
IDENTIFIED_PENDING_REVIEW → APPROVED_APPLIED
IDENTIFIED_PENDING_REVIEW → REJECTED
IDENTIFIED_PENDING_REVIEW → STALE_REVIEW_REQUIRED
IDENTIFIED_PENDING_REVIEW → APPLY_FAILED
~~~

NO_CHANGE和CONFLICT不可审核。所有终态不可反向修改；需要重新处理时创建新批次。

索引与约束：

- uq_import_change_set_batch_identity(batch_id, product_identity_key)。
- ix_import_change_sets_batch_status(batch_id, status)。
- ix_import_change_sets_target_product(target_product_id)。

### 5.5 import_field_changes

定位：一个change set下每个固定业务字段一条差异，直接支撑Merge预览。

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| id | Integer | 自增主键 |
| change_set_id | String(36) | FK import_change_sets.id，ON DELETE CASCADE |
| field_key | String(128) | 固定Mapping逻辑键 |
| field_label | String(128) | 冻结中文展示名 |
| field_order | Integer | 固定Mapping顺序 |
| old_value_json | Text | JSON scalar/list/null |
| incoming_value_json | Text | JSON scalar/list/null |
| merged_value_json | Text | JSON scalar/list/null |
| change_type | String(16) | ADD / UPDATE / KEEP / NO_CHANGE |
| created_at | DateTime(TZ) | 非空 |

索引与约束：

- uq_import_field_change_key(change_set_id, field_key)。
- ix_import_field_changes_set_type(change_set_id, change_type)。

禁止在此表加入DELETE或自动发布字段。

### 5.6 import_review_records

定位：append-only审核和生效收据。禁止UPDATE和DELETE业务操作；数据清理只能走独立保留政策。

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| id | String(36) | receipt_id，UUID主键 |
| batch_id | String(36) | FK import_batches.id，ON DELETE RESTRICT |
| change_set_id | String(36) | FK import_change_sets.id，ON DELETE RESTRICT |
| decision | String(16) | APPROVE / REJECT |
| outcome | String(32) | APPLIED / REJECTED / STALE_REVIEW_REQUIRED / APPLY_FAILED |
| reviewed_by | String(128) | 操作人审计标识 |
| review_note | Text | REJECT必填 |
| idempotency_key | String(255) | 必填 |
| request_fingerprint | String(64) | 必填 |
| expected_base_snapshot_hash | String(64) | 必填 |
| observed_base_snapshot_hash | String(64) | 审核时重读所得 |
| expected_change_set_version | Integer | 必填 |
| applied_product_id | String(96) | APPLIED时填写 |
| applied_field_count | Integer | 默认0 |
| before_snapshot_hash | String(64) | 可空 |
| after_snapshot_hash | String(64) | 可空 |
| error_code | String(64) | 失败或过期时可填 |
| created_at | DateTime(TZ) | 审核发生时间 |

索引与约束：

- uq_import_review_idempotency(change_set_id, reviewed_by, idempotency_key)。
- ix_import_review_records_batch_created(batch_id, created_at)。
- ix_import_review_records_change_set_created(change_set_id, created_at)。
- ix_import_review_records_outcome(outcome)。

重放相同请求返回原id，不新增第二条receipt。

## 6. 正式写入规则

### 6.1 审核前

允许写入：

- import_batches
- import_rows
- import_change_sets
- import_field_changes

禁止写入或修改：

- TestProduct
- TestSourceEvidence
- TestSku
- FAQ
- SafetyRule
- RAG/向量
- Prompt/模型
- R006客服可用状态

因此审核前正式业务数据必须为零写入。

### 6.2 APPROVE事务

每个change set独立事务，固定顺序：

1. 读取并锁定change set逻辑版本，确认仍为IDENTIFIED_PENDING_REVIEW。
2. 按store_ref和商品身份重新读取当前TestProduct。
3. 重新计算observed_base_snapshot_hash。
4. 比对expected hash、change set base hash和当前version。
5. 不一致时不写正式数据，记录STALE_REVIEW_REQUIRED收据。
6. CREATE时再次确认同店同规范化名称仍不存在。
7. UPDATE时只写ADD/UPDATE字段；KEEP和NO_CHANGE不产生SQL字段覆盖。
8. raw_data_json只合并允许键，保留未知历史键，不替换整对象。
9. 创建或追加TestSourceEvidence，记录批次ID、文件哈希、来源、来源日期和receipt_id。
10. 新商品保持sales_status=OFF_SALE、publishable=false且不自动创建SKU。
11. human_confirmation_status=CONFIRMED时商品review_status可为APPROVED；PENDING时保持REVIEWING。
12. 写入APPROVED_APPLIED change set状态和APPLIED review receipt。
13. 提交事务后更新批次聚合状态。

任一步失败，正式商品、来源证据、change set生效状态和成功receipt必须整体回滚。随后单独记录APPLY_FAILED审计收据；不得把失败显示为已生效。

### 6.3 REJECT事务

REJECT只执行：

- 校验change set仍可审核。
- 追加REJECTED review receipt。
- change set转REJECTED。
- 更新批次聚合状态。

不得修改任何正式商品或知识数据。

### 6.4 批次独立性

一个商品审核失败不能回滚已完成的其他商品事务。批次通过各change set状态汇总为PARTIALLY_REVIEWED或COMPLETED，不允许用单条异常把全部结果投影成No data。

## 7. 幂等规则

### 7.1 上传重复

上传幂等scope固定为：

~~~text
import_type=PRODUCT_KNOWLEDGE + operator + Idempotency-Key
~~~

请求指纹固定为规范化后的：

~~~text
SHA256(store_ref | template_type | file_sha256)
~~~

规则：

1. 同scope、同指纹：返回原batch_id和当前status，不重复解析、不重复写行。
2. 同scope、不同指纹：HTTP 409 IMPORT_IDEMPOTENCY_CONFLICT。
3. 不同key、同store_ref、同template_type、同file_sha256，且已有非FAILED/PREFLIGHT_FAILED批次：HTTP 409 IMPORT_DUPLICATE_FILE，并只返回existing_batch_id。
4. 原批次为FAILED或PREFLIGHT_FAILED时允许用新key重新提交，形成新批次；旧批次保留。
5. 文件名不参与指纹；改名不能绕过相同内容判断。

### 7.2 审核重复

审核幂等scope固定为：

~~~text
change_set_id + operator + Idempotency-Key
~~~

请求指纹固定包含：

~~~text
batch_id | change_set_id | decision | normalized_review_note |
expected_base_snapshot_hash | expected_change_set_version
~~~

规则：

1. 同scope、同指纹：返回同一个review_receipt，不重复写商品和来源证据。
2. 同scope、不同指纹：HTTP 409 IMPORT_REVIEW_IDEMPOTENCY_CONFLICT。
3. change set已APPROVED_APPLIED，再提交相同决策：返回原APPLIED receipt，不新增记录。
4. change set已REJECTED，再提交相同决策：返回原REJECTED receipt。
5. 已终态后提交相反决策：HTTP 409 IMPORT_REVIEW_ALREADY_FINALIZED。
6. STALE_REVIEW_REQUIRED和APPLY_FAILED不得原地改写为成功；修正后必须新批次或另行冻结的恢复流程。

### 7.3 网络重试

- 客户端超时后必须使用同一Idempotency-Key和相同请求体重试。
- 服务端先查询幂等scope，再执行Parser或正式写入。
- 首次成功返回HTTP 201；重放返回HTTP 200和Idempotency-Replayed: true。
- 重放不得刷新reviewed_at、重复增加applied_field_count或再生成来源证据。
- 日志只记录batch_id、change_set_id、receipt_id、状态和请求指纹，不记录Excel内容、完整商品快照或客户信息。

## 8. 迁移方案

### 8.1 是否需要0009

需要。

原因：

1. import_batches需要店铺、模板、Parser证据和上传幂等字段。
2. import_rows需要商品识别投影。
3. 当前没有import_change_sets、import_field_changes和import_review_records。
4. staged_product_skus语义属于旧商品/SKU技术模板，不能承载商品知识字段Merge。

未来迁移名冻结为：

~~~text
0009_product_knowledge_import_v1
~~~

down_revision固定为：

~~~text
0008_customer_feedback_loop_v1
~~~

本轮不创建迁移文件，也不执行任何数据库命令。

### 8.2 upgrade顺序

未来实施时：

1. 只对隔离临时SQLite完成0008→0009→0008→0009往返验证。
2. 对正式库变更前执行SQLite在线备份和manifest，不清空、不重建数据库。
3. 向import_batches增加可空兼容列和索引。
4. 向import_rows增加可空兼容列和索引。
5. 创建import_change_sets。
6. 创建import_field_changes。
7. 创建import_review_records。
8. 不修改、迁移或删除staged_product_skus。
9. 旧批次不回填伪造store_ref、template_type或receipt。
10. 迁移完成后验证旧导入查询、C完整pytest和Admin回归。

SQLite列变更必须使用Alembic batch operation兼容策略；不得以删除重建整个业务数据库代替迁移。

### 8.3 downgrade与回滚

技术downgrade顺序：

1. 确认商品知识导入入口已关闭且无进行中请求。
2. 导出并保护review receipt审计摘要。
3. 删除新表的索引和新表，顺序为review records、field changes、change sets。
4. 使用SQLite batch operation删除import_rows和import_batches新增列/索引。
5. 保留原import_batches、import_rows、staged_product_skus和旧数据。
6. 验证revision回到0008且旧导入测试通过。

重要限制：

- 0009 downgrade会删除V1暂存与审核审计结构，执行前必须获得数据保留批准。
- 如果已有APPROVE写入TestProduct/TestSourceEvidence，schema downgrade不会也不得自动撤销正式业务数据。
- 已生效数据需要按review_receipt进行独立业务补偿评审，不能用Alembic回滚冒充业务回滚。
- 未完成备份、审计保护和业务补偿判断时禁止对正式库downgrade。

## 9. 状态汇总

### 9.1 批次状态机

~~~text
RECEIVED → PARSING
PARSING → PREFLIGHT_FAILED
PARSING → NO_CHANGE
PARSING → IDENTIFIED_PENDING_REVIEW
PARSING → FAILED
IDENTIFIED_PENDING_REVIEW → PARTIALLY_REVIEWED
IDENTIFIED_PENDING_REVIEW → COMPLETED
PARTIALLY_REVIEWED → COMPLETED
~~~

### 9.2 Change Set状态机

~~~text
IDENTIFIED_PENDING_REVIEW
  → APPROVED_APPLIED
  → REJECTED
  → STALE_REVIEW_REQUIRED
  → APPLY_FAILED

NO_CHANGE（终态，不审核）
CONFLICT（阻断，不审核）
~~~

### 9.3 不允许的解释

- COMPLETED不等于全部APPROVE。
- APPROVED_APPLIED不等于知识已发布。
- TestProduct已更新不等于B客服已激活。
- operator字段不等于已实现登录或RBAC。
- Idempotency-Key不等于权限控制。
- review_receipt不包含原Excel、完整商品快照或数据库路径。

## 10. 兼容性与Owner

| 项目 | 冻结结论 |
| --- | --- |
| Provider | C Platform Backend |
| Consumer | C Admin |
| 数据Owner | C运营 |
| A / B / RAG | 不调用、不消费、不修改 |
| R006 | 不读取、不写入customer_service_status |
| Shared contracts | 0.2.0不变；本接口是C内部V1 |
| 旧导入 | 保留原路径、表和语义 |
| 其他五模板 | 422阻断，不实现 |
| Runtime | 不切换、不重启、不修改 |

未来若B、A或外部系统需要消费任一状态、字段或receipt，必须建立新的跨线contracts版本和受影响线复审；不得直接复用本C内部接口。

## 11. 实施前Gate

进入编码前仍必须满足：

1. 用户明确授权R009 Implementation。
2. 从唯一AI-CS源码基线创建不承载当前标准Runtime的独立C Feature工作区。
3. 0009 migration在隔离SQLite通过往返、旧表兼容、备份和downgrade测试。
4. API schema、状态、错误码、幂等和receipt测试逐项实现，禁止静默改名。
5. 当前Admin缺少正式认证/RBAC；V1只能维持受控本机Pilot边界，不得因本接口开放5174 LAN或宣称生产权限完成。
6. QA准备固定模板、店铺不匹配、重复上传、并发过期、重复审核和应用失败的去标识化样本。

## 12. Gate结论

| Gate | 结果 |
| --- | --- |
| 上传请求/响应 | FROZEN |
| 预检响应 | FROZEN |
| Merge预览与change_type | FROZEN |
| APPROVE / REJECT与review_receipt | FROZEN |
| 五表数据库结构 | FROZEN |
| 正式写入边界 | FROZEN |
| 上传/审核/网络重试幂等 | FROZEN |
| 0009 upgrade/downgrade设计 | FROZEN |
| 代码、UI、Runtime、现有数据库变更 | NONE |
| Implementation授权 | NO |

最终状态：PRODUCT_KNOWLEDGE_IMPORT_INTERFACE_READY
