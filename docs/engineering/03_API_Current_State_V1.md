# AI-CS API Current State V1

## 1. 基线与证据

本清单直接读取运行中的OpenAPI，不使用历史接口设计推断。

| 服务 | OpenAPI | Paths | Operations | Schemas | OpenAPI SHA-256 |
|---|---|---:|---:|---:|---|
| A AI Service | `http://127.0.0.1:8000/openapi.json` | 24 | 25 | 30 | `C41659C1DEA9AC8DBCEC5B9F6D6DDE04C160FF04F98C427618086FE684CF0EBE` |
| C Platform API | `http://127.0.0.1:8011/openapi.json` | 78 | 86 | 212 | `1CE6DDEF638EAD9C5E37E92C289865463CAA6B3048BB489E78557F5C55E7FB8F` |

采集基线：`AI-CS@860d102059cab00ee946512478807f8a8d6efae9`。

代码入口：`backend/app/main.py`、`backend/app/api/routes.py`、`platform_backend/app/main.py`及其注册router。C关闭Swagger/ReDoc页面（`docs_url=None`、`redoc_url=None`），但当前仍提供`/openapi.json`；A提供默认`/docs`和OpenAPI。

## 2. 浏览器调用边界

| 浏览器 | 同源前缀 | 目标 |
|---|---|---|
| B 5173 | `/rag-api` | A `127.0.0.1:8000` |
| B 5173 | `/platform-api` | C `127.0.0.1:8011` |
| Admin 5174 | `/ai-api` | A `127.0.0.1:8000` |
| Admin 5174 | `/platform-api` | C `127.0.0.1:8011` |

证据：`frontend/vite.config.ts`、`admin_web/vite.config.ts`。前端默认使用同源前缀，不在浏览器暴露SQLite、Chroma或任意代理目标。

## 3. 通用约定

- C API为业务数据Owner，使用`X-Request-ID`中间件并返回统一错误；见`platform_backend/app/main.py:50-73`。
- C允许方法：GET、POST、PATCH、PUT；允许请求头包含`Idempotency-Key`与`X-Request-ID`。
- 激活、反馈、导入审核等关键写操作使用幂等键；不能靠前端重复点击控制幂等。
- A `/api/chat`新规范请求必须同时提交`question`和`FrozenChatContext`；旧`message`仅用于兼容且不能与context同时使用，见`backend/app/models/chat.py:49-79`。
- Contracts当前为`0.5.0/additive`，共享Schema位于`contracts/schemas/**`。

## 4. A AI Service操作清单

### 4.1 System、Chat、Knowledge与配置

| Method | Path | 作用 | 主要请求/响应 |
|---|---|---|---|
| GET | `/api/health` | 进程健康 | object |
| GET | `/api/status` | ready、model configured | object |
| POST | `/api/chat` | 业务上下文RAG问答 | `ChatRequest` → answer envelope |
| GET | `/api/questions/recommended` | 推荐问题 | object |
| POST | `/api/retrieval/search` | 仅检索 | `SearchRequest` → search result |
| GET | `/api/knowledge/statistics` | 知识与collection统计 | object |
| GET | `/api/stats` | 旧统计兼容 | object |
| GET | `/api/config/model` | 当前模型配置（不返回密钥） | object |
| PUT | `/api/config/model` | 内存更新模型配置 | `ModelConfigUpdate` → object |

### 4.2 兼容接口

| Method | Path | 作用 |
|---|---|---|
| POST | `/api/ai/chat` | Java代理兼容Chat |
| GET | `/api/ai/status` | Java代理兼容Status |
| GET | `/api/ai/stats` | Java代理兼容Stats |

新B代码使用`/api/chat`，不应扩展旧兼容接口。

### 4.3 商品AI知识发布

| Method | Path | 作用 | Schema |
|---|---|---|---|
| POST | `/api/admin/ai/knowledge-publications/products` | 增量发布一个Product知识 | `ProductKnowledgePublishRequest` → `ProductKnowledgePublishReceipt` |
| POST | `/api/admin/ai/knowledge-publications/visibility` | 批量核对商品级Chroma可见性 | `ProductKnowledgeVisibilityBatchRequest` → `ProductKnowledgeVisibilityBatchResponse` |

### 4.4 AI运营与分析

| Method | Path | 作用 |
|---|---|---|
| GET | `/api/admin/ai/modules` | AI模块列表 |
| GET | `/api/admin/ai/modules/{module_id}` | 模块详情 |
| GET | `/api/admin/ai/modules/{module_id}/prompt` | Prompt版本/hash，不返回正文 |
| POST | `/api/admin/ai/modules/{module_id}/test` | 受限在线测试 |
| GET | `/api/admin/ai/modules/{module_id}/evaluations/latest` | 最近评估 |
| GET | `/api/admin/ai/control-center/overview` | AI控制中心总览 |
| GET | `/api/admin/ai/control-center/product-overview` | 产品化AI总览 |
| POST | `/api/admin/ai/experience-evaluations/run` | 显式运行体验案例评估 |
| POST | `/api/admin/ai/feedback-analysis/run` | 显式运行反馈分析 |
| POST | `/api/admin/ai/knowledge-quality/run` | 显式运行知识质量分析 |

### 4.5 内部测试知识入口

| Method | Path | 作用 |
|---|---|---|
| POST | `/api/test-knowledge/sync/{package_id}` | 同步测试知识包；正式配置`AutoSyncTestKnowledge=false` |

## 5. C Platform API操作清单

### 5.1 System与通用Admin读取（11 operations）

| Method | Path | 作用 |
|---|---|---|
| GET | `/health` | C健康 |
| GET | `/api/v1/admin/overview` | Admin运营总览 |
| GET | `/api/v1/admin/stores` | 只读Store列表 |
| GET | `/api/v1/admin/products` | 只读Product列表 |
| GET | `/api/v1/admin/products/{product_id}` | Product详情 |
| GET | `/api/v1/admin/products/{product_id}/skus` | Product的SKU |
| GET | `/api/v1/admin/faqs` | FAQ列表 |
| GET | `/api/v1/admin/safety-rules` | 安全规则列表 |
| GET | `/api/v1/admin/sources` | 来源列表 |
| GET | `/api/v1/admin/conflicts` | 冲突列表 |
| GET | `/api/v1/admin/import-batches` | Admin导入批次摘要 |

代码：`platform_backend/app/api/admin_routes.py`。

### 5.2 R006 Customer Available Catalog（9 operations）

| Method | Path | 作用 | 主要响应 |
|---|---|---|---|
| GET | `/api/v1/customer-service/catalog/stores` | B可用Store投影 | `StoreCatalogResponse` |
| GET | `/api/v1/customer-service/catalog/products` | B可用Product投影 | `ProductCatalogResponse` |
| GET | `/api/v1/customer-service/catalog/products/{product_id}/skus` | Product下SKU投影 | `SkuCatalogResponse` |
| GET | `/api/v1/customer-service/catalog/products/{product_id}/ai-knowledge` | 商品AI发布可见性 | `CustomerProductAiKnowledgeStatus` |
| PUT | `/api/v1/admin/operations/stores/{store_ref}/customer-service-status` | 人工启停Store | `ActivationResponse` |
| PUT | `/api/v1/admin/operations/products/{product_id}/customer-service-status` | 人工启停Product | `ActivationResponse` |
| POST | `/api/v1/admin/operations/products/customer-service-status:batch` | 批量启用Product | `BatchActivationResponse` |
| GET | `/api/v1/admin/operations/activation-receipts` | 收据列表 | `ActivationReceiptListResponse` |
| GET | `/api/v1/admin/operations/activation-receipts/{activation_receipt_id}` | 收据详情 | `ActivationReceipt` |

Customer Catalog响应必须保留：`schema_version/result_status/items/total/warnings`。`COMPLETE+0`表示真实空目录；`PARTIAL+0`表示目录异常，B不能显示成“没有商品”。契约证据：`contracts/schemas/customer-service-catalog.v1.schema.json`。

### 5.3 Store/Product运营管理（6 operations）

| Method | Path | 作用 |
|---|---|---|
| GET | `/api/v1/admin/operations/stores` | 运营Store列表 |
| POST | `/api/v1/admin/operations/stores` | 创建Store |
| GET | `/api/v1/admin/operations/stores/{store_ref}` | Store详情 |
| PATCH | `/api/v1/admin/operations/stores/{store_ref}` | 编辑Store |
| POST | `/api/v1/admin/operations/stores/{store_ref}/products` | 创建Product |
| PATCH | `/api/v1/admin/operations/products/{product_id}/basic-info` | 更新Product基础信息 |

代码：`platform_backend/app/operation_management/routes.py`。

### 5.4 商品知识、R009与AI发布（11 operations）

| Method | Path | 作用 |
|---|---|---|
| GET | `/api/v1/admin/product-knowledge/overview` | 商品知识总览 |
| GET | `/api/v1/admin/product-knowledge/products` | 商品知识列表 |
| GET | `/api/v1/admin/product-knowledge/products/{product_id}` | 商品知识详情 |
| GET | `/api/v1/admin/product-knowledge/gaps` | 知识缺口 |
| POST | `/api/v1/admin/product-knowledge-imports` | 上传商品知识Excel |
| GET | `/api/v1/admin/product-knowledge-imports/{batch_id}/preflight` | 解析与校验结果 |
| GET | `/api/v1/admin/product-knowledge-imports/{batch_id}/merge-preview` | 字段Merge预览 |
| POST | `/api/v1/admin/product-knowledge-imports/{batch_id}/change-sets/{change_set_id}/reviews` | approve/reject变化集 |
| POST | `/api/v1/admin/product-knowledge/products/{product_id}/ai-publications` | 发布AI知识 |
| POST | `/api/v1/admin/product-knowledge/products/{product_id}/ai-publication-checks` | 检查AI知识可见性 |
| GET | `/api/v1/admin/product-knowledge/products/{product_id}/ai-publication-receipts` | 发布收据历史 |

R009上传请求为multipart，包含`store_ref/template_type/operator/file`及`Idempotency-Key`；当前只实现商品知识采集模板的完整导入闭环。代码：`platform_backend/app/product_knowledge_import/routes.py`。

### 5.5 资料、知识质量与客服知识状态（8 operations）

| Method | Path | 作用 |
|---|---|---|
| GET | `/api/v1/admin/knowledge-materials` | 资料列表 |
| POST | `/api/v1/admin/knowledge-materials` | 上传资料 |
| GET | `/api/v1/admin/knowledge-materials/{material_id}` | 资料详情 |
| POST | `/api/v1/admin/knowledge-materials/{material_id}/review` | 人工审核资料 |
| GET | `/api/v1/admin/knowledge-quality/analysis-inputs` | A读取已审核质量输入 |
| POST | `/api/v1/admin/knowledge-quality/analysis-results` | A回写质量分析 |
| GET | `/api/v1/admin/knowledge-quality/assessments` | 质量评估列表 |
| GET | `/api/v1/customer-knowledge-status` | 客服侧知识准备度兼容读取；新商品主链优先使用商品级AI知识状态接口 |

### 5.6 R005 Interaction、AI问题与知识任务（7 operations）

| Method | Path | 作用 |
|---|---|---|
| POST | `/api/v1/ai-interaction-events` | 保存客服采用/编辑采用/拒绝事件 |
| GET | `/api/v1/admin/ai-feedback-loop/events` | Admin查看interaction events |
| GET | `/api/v1/admin/ai-feedback-loop/issues` | AI问题聚合列表 |
| PATCH | `/api/v1/admin/ai-feedback-loop/issues/{problem_id}/status` | 人工改变问题状态 |
| POST | `/api/v1/admin/ai-feedback-loop/issues/{problem_id}/knowledge-tasks` | 创建知识优化任务 |
| PATCH | `/api/v1/admin/ai-feedback-loop/knowledge-tasks/{task_id}/status` | 更新任务状态 |
| POST | `/api/v1/admin/ai-feedback-loop/knowledge-tasks/{task_id}/verifications` | 记录人工复验结果 |

`REJECTED` interaction才会形成/聚合AI问题；采用类事件仍保存审计，但不创建问题。代码：`platform_backend/app/customer_feedback_loop/service.py:112-192`。

### 5.7 AI回答问题分类反馈（6 operations）

| Method | Path | 作用 |
|---|---|---|
| POST | `/api/v1/ai-response-feedback` | 客服提交问题类型/说明 |
| GET | `/api/v1/ai-response-feedback` | 查询反馈 |
| POST | `/api/v1/admin/ai-response-feedback/{feedback_id}/confirm` | 运营人工确认反馈 |
| GET | `/api/v1/admin/ai-quality/analysis-results` | 分析结果列表 |
| POST | `/api/v1/admin/ai-quality/analysis-results` | A回写分析结果 |
| GET | `/api/v1/admin/ai-quality/badcases` | 导出已确认badcase给A |

### 5.8 体验案例与AI优化（9 operations）

| Method | Path | 作用 |
|---|---|---|
| POST | `/api/v1/customer-experience-cases` | 客服创建体验案例 |
| GET | `/api/v1/customer-experience-cases` | 客服查询案例 |
| GET | `/api/v1/admin/customer-experience-cases` | Admin案例列表 |
| GET | `/api/v1/admin/customer-experience-cases/{case_id}` | Admin案例详情 |
| PATCH | `/api/v1/admin/customer-experience-cases/{case_id}/review` | 人工审核案例 |
| GET | `/api/v1/admin/ai-optimization/cases` | AI优化案例池 |
| GET | `/api/v1/admin/ai-optimization/cases/{case_id}/evaluations` | 案例评估历史 |
| GET | `/api/v1/admin/ai-optimization/cases/export` | A读取已审核案例快照 |
| POST | `/api/v1/admin/ai-optimization/evaluation-results` | A回写评估结果 |

### 5.9 产品意见建议（4 operations）

| Method | Path | 作用 |
|---|---|---|
| POST | `/api/v1/customer-suggestions` | 客服提交产品建议 |
| GET | `/api/v1/customer-suggestions` | 客服查询本人建议 |
| GET | `/api/v1/admin/customer-suggestions` | Admin建议列表 |
| PATCH | `/api/v1/admin/customer-suggestions/{suggestion_id}` | Admin更新建议状态 |

### 5.10 旧Product/SKU导入中心能力（7 operations）

| Method | Path | 作用 |
|---|---|---|
| GET | `/api/v1/import-templates/product-sku` | 下载Product/SKU模板 |
| POST | `/api/v1/import-batches/product-sku/preflight` | Product/SKU预检 |
| POST | `/api/v1/import-batches/product-sku` | 创建导入批次 |
| GET | `/api/v1/import-batches` | 批次列表 |
| GET | `/api/v1/import-batches/{batch_id}` | 批次详情 |
| GET | `/api/v1/import-batches/{batch_id}/rows` | 批次行 |
| GET | `/api/v1/import-batches/{batch_id}/errors` | 错误报告 |

这些接口属于原Product/SKU导入链，不等同于R009商品知识Excel导入。

### 5.11 内部测试包兼容接口（8 operations）

| Method | Path | 作用 |
|---|---|---|
| POST | `/api/v1/test-data-packages/preflight` | 测试包预检 |
| POST | `/api/v1/test-data-packages` | 导入测试包 |
| GET | `/api/v1/test-data-packages` | 测试包列表 |
| GET | `/api/v1/test-catalog/stores` | 旧测试Store读取 |
| GET | `/api/v1/test-catalog/products` | 旧测试Product读取 |
| GET | `/api/v1/test-catalog/products/{product_id}/skus` | 旧测试SKU读取 |
| GET | `/api/v1/test-knowledge-packages/{package_id}/rag-export` | A读取测试RAG包 |
| GET | `/api/v1/test-knowledge-packages/{package_id}/evaluations` | A读取测试评估包 |

新B主链不使用`/test-catalog/**`，而使用`/customer-service/catalog/**`。这些接口当前为历史兼容/内部资产，不能重新作为生产准入来源。

## 6. 前端真实消费映射

### B

| 功能 | C/A路径 | 代码 |
|---|---|---|
| 目录 | `/api/v1/customer-service/catalog/stores|products|.../skus` | `frontend/src/api/platformClient.ts` |
| AI知识状态 | `/api/v1/customer-service/catalog/products/{id}/ai-knowledge` | `customerKnowledgeStatusClient.ts` |
| AI回答 | `/api/chat` | `ragClient.ts` |
| Interaction | `/api/v1/ai-interaction-events` | `aiInteractionEventClient.ts` |
| AI反馈 | `/api/v1/ai-response-feedback` | `aiResponseFeedbackClient.ts` |
| 体验案例 | `/api/v1/customer-experience-cases` | `experienceCaseClient.ts` |
| 建议 | `/api/v1/customer-suggestions` | `suggestionClient.ts` |

### Admin

`admin_web/src/api/client.ts`实际消费C的overview、商品知识、运营Store、activation、R009、资料、反馈、AI问题和旧导入接口，并通过`/ai-api`读取A控制中心与模块状态。新增页面前必须先检查该client是否已有真实接口，不得用前端假统计代替API。

## 7. 兼容与废弃边界

- `/api/ai/**`：A兼容入口，新B不应扩展依赖。
- `/api/v1/test-catalog/**`和测试包接口：内部/历史兼容，不是R006最终目录。
- C数据库表仍使用`test_catalog_*`历史名称，但正式Customer Catalog通过C投影封装，不允许B直读或推断这些表。
- Import Center六模板展示属于Admin页面资产；API层只有已实现模板对应的真实解析链，不能从卡片数量推断六类均已实现。

## 8. API一致性复核方法

文档更新时至少执行：

1. 读取运行中的A/C `/openapi.json`并记录paths、operations、schemas和hash；
2. 与`backend/app/api/routes.py`和`platform_backend/app/main.py`注册router核对；
3. 搜索`frontend/src/api/**`、`admin_web/src/api/client.ts`的实际消费路径；
4. 运行`tests/contract/**`与受影响消费者测试；
5. 若Shared Contract变化，更新`contracts/version.json`、`CHANGELOG.md`和兼容说明。
