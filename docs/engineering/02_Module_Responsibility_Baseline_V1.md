# AI-CS Module Responsibility Baseline V1

## 1. 责任模型

AI-CS当前采用A/B/C三条业务线与共享治理层：

| 责任域 | Owner | 代码范围 | 不能承担的职责 |
|---|---|---|---|
| A AI能力 | A | `backend/**`、`docs/rag/**` | 不决定商品准入，不自动执行业务动作，不直接写C业务主数据 |
| B 客服工作台 | B | `frontend/**`、`extension/**`、`docs/customer/**` | 不自行判断C数据可信度，不绕过Customer Catalog，不自动发送 |
| C 运营与业务数据 | C | `platform_backend/**`、`admin_web/**`、`docs/platform/**` | 不把模型或Prompt状态当作业务主数据，不自动替代人工审核 |
| Shared Contracts | A/B/C共同评审 | `contracts/**` | 不允许单方破坏兼容性 |
| Control/OPS/QA | 项目总控 | `docs/control/**`、`docs/engineering/**`、`scripts/**`、`tests/**` | 不绕过Runtime身份、数据库迁移或业务Owner |

所有权依据：根目录`AGENTS.md`与当前代码布局。

## 2. 当前目录结构

```text
AI-CS/
├── backend/                 A：FastAPI、RAG、模型、知识发布
├── frontend/                B：客服工作台
├── platform_backend/        C：业务API、SQLite ORM、Alembic
├── admin_web/               C：运营后台
├── contracts/               A/B/C共享JSON Schema，当前0.5.0
├── scripts/
│   ├── windows/             四服务生命周期与身份治理
│   └── database-health-check/ 只读数据库健康检查
├── tests/
│   ├── contract/            共享契约验证
│   ├── database_health/     数据健康脚本测试
│   └── e2e/                 B/C/R006/R009浏览器流程
├── docs/
│   ├── control/             需求、发布、Gate和治理记录
│   ├── customer/            B线文档
│   ├── platform/            C线文档
│   ├── rag/                 A线文档
│   └── engineering/         当前工程事实基线
├── extension/               目前只有说明文件，无运行扩展实现
├── .github/                 CI和Issue/PR模板
├── .runtime/                本机运行资产，Git忽略
└── README.md                正式项目入口
```

当前Git跟踪文件分布显示主要资产位于：`platform_backend`、`admin_web`、`frontend`、`backend`、`contracts`、`scripts`、`tests`和`docs`。`node_modules`、`.venv`、`dist`、SQLite、Chroma和日志属于本地运行/依赖资产，不是源码模块。

## 3. A模块责任

### 3.1 入口与子模块

| 子模块 | 路径 | 责任 |
|---|---|---|
| FastAPI入口 | `backend/app/main.py` | 初始化RAG、注册`/api`、CORS、异常边界 |
| API | `backend/app/api/routes.py` | health/status、chat/search、AI控制、发布与分析接口 |
| 配置 | `backend/app/config/settings.py` | 模型、Embedding、Chroma、C API与检索参数 |
| Chat模型 | `backend/app/models/chat.py` | `ChatRequest`与C来源的`FrozenChatContext` |
| RAG主链 | `backend/app/service/rag_service.py` | 检索、规则决策、Prompt、模型调用、引用输出 |
| 业务上下文检索 | `backend/app/service/test_knowledge.py` | tenant/store/product/SKU过滤与安全规则检索 |
| 向量库 | `backend/app/service/vector_store.py` | Chroma、Embedding、upsert/search/delete |
| 商品发布 | `backend/app/service/product_knowledge_publisher.py` | 商品级增量向量发布与验证 |
| 运营分析 | `experience_evaluation.py`、`feedback_analysis.py`、`knowledge_quality.py` | 从C读取受控快照，调用模型，结果回写C |

### 3.2 A必须保持的边界

- `FrozenChatContext`由调用方提供；A只做安全和完整性校验，见`backend/app/models/chat.py:13-26`。
- A不读取Store/Product的客服启用字段决定权限。
- A知识发布按Product/fingerprint增量处理，不全量重建其他商品。
- Prompt正文不通过管理接口暴露，只返回版本和hash，见`backend/app/service/ai_capability.py:119-123`。
- A返回建议，不执行发送、退款或订单动作。

## 4. B模块责任

### 4.1 页面

真实路由来自`frontend/src/router/index.ts`：

| 路由 | 页面 | 责任 |
|---|---|---|
| `/` | WorkspaceHome | 客服工作台首页 |
| `/ai-chat` | AiChat | 店铺/商品/SKU选择、问题、AI建议与人工处理 |
| `/suggestions` | SuggestionForm | 提交产品意见 |
| `/suggestions/mine` | MySuggestions | 查看本人建议 |
| `/experience-cases` | ExperienceCases | 查看本人案例 |
| `/feedback` | FeedbackGuide | 问题反馈引导 |
| `/modules/:moduleKey` | ModuleInfo | 现有/后续模块说明 |

`/chat`兼容重定向到`/ai-chat`，`/app`重定向到首页。

### 4.2 API适配层

| 文件 | 责任 |
|---|---|
| `frontend/src/api/platformClient.ts` | 获取C Customer Catalog Store/Product/SKU |
| `frontend/src/api/platformAdapter.ts` | 保留`COMPLETE/PARTIAL/total/warnings/items`语义，隔离坏项 |
| `frontend/src/api/ragClient.ts` | 调用A health/chat |
| `frontend/src/api/customerKnowledgeStatusClient.ts` | 获取商品AI知识发布状态 |
| `frontend/src/api/aiInteractionEventClient.ts` | 记录采用、编辑采用、拒绝事件 |
| `frontend/src/api/aiResponseFeedbackClient.ts` | 提交可选AI问题分类反馈 |
| `frontend/src/api/experienceCaseClient.ts` | 保存可复用客服案例 |
| `frontend/src/api/suggestionClient.ts` | 产品意见与建议 |

B默认使用Vite同源代理：`/platform-api`→C 8011，`/rag-api`→A 8000。代理目标固定在`frontend/vite.config.ts`，浏览器不能指定任意上游。

### 4.3 B必须保持的边界

- B只消费C投影，不判断`test_data_mode`、`production_usable`、`publishable`作为准入条件。
- `PARTIAL+total=0`必须显示目录异常，不能伪装成真实空目录。
- 商品切换时必须清理旧商品/SKU与回答上下文。
- AI回答只能由客服人工确认后使用；B不自动发送。

## 5. C Platform Backend责任

### 5.1 入口与共享基础

- FastAPI入口和router注册：`platform_backend/app/main.py:50-110`；
- SQLAlchemy Session与数据库配置：`platform_backend/app/db.py`、`platform_backend/app/config.py`；
- 统一错误与request id：`platform_backend/app/errors.py`、`middleware.py`；
- Alembic链：`platform_backend/migrations/versions/0001_*.py`至`0012_*.py`。

### 5.2 业务域

| 业务域 | 路径 | Owner能力 |
|---|---|---|
| 基础导入 | `app/ingestion/**`、`app/api/import_routes.py` | Product/SKU模板预检、批次和staging |
| 业务目录 | `app/test_catalog/**` | 当前Store/Product/SKU/FAQ/安全规则/来源存储；名称保留历史语义，但已承载正式初始化与PILOT数据 |
| 运营维护 | `app/operation_management/**` | Store/Product创建、查看和基础信息更新 |
| 商品知识 | `app/product_knowledge/**` | 商品知识总览、详情、缺口 |
| R009知识导入 | `app/product_knowledge_import/**` | 固定Excel解析、店铺校验、Merge、人工审核 |
| R006客服目录 | `app/customer_catalog/**` | 最终Customer Available Catalog与启停收据 |
| R006.1知识发布 | `app/knowledge_publishing/**` | C侧发布状态、A调用、publication receipt |
| 资料与质量 | `app/knowledge_materials/**`、`app/api/knowledge_material_routes.py` | 上传、审核、质量分析记录 |
| 反馈闭环 | `app/customer_feedback_loop/**` | interaction event、AI问题、知识任务和复验 |
| AI问题反馈 | `app/ai_feedback/**`、`app/api/customer_ai_feedback_routes.py` | 客服问题分类与运营分析 |
| 体验案例 | `app/experience_cases/**` | 客服案例审核、导出、模型评估 |
| 意见建议 | `app/suggestions/**` | 非AI质量问题的产品建议 |

### 5.3 C必须保持的边界

- C是Store/Product客服准入唯一Owner；状态变化必须生成activation receipt。
- C Customer Catalog逐条隔离异常数据，不能让一条坏记录清空全部目录。
- R009上传和预检不得直接覆盖正式商品；人工审核通过后才应用。
- C保存AI发布状态和收据，但向量写入由A完成。
- 所有状态变更保存operator、时间或幂等证据；不能用前端文案代替数据库状态。

## 6. C Admin责任

真实路由来自`admin_web/src/router/index.ts`。

### 6.1 默认运营入口

| 路由 | 业务用途 |
|---|---|
| `/overview` | 运营工作台 |
| `/store-management` | Store/Product运营维护和客服启停 |
| `/knowledge-center` | 商品知识、客服状态、AI知识状态 |
| `/import-center` | 六类模板展示与下载说明 |
| `/knowledge-materials` | 资料上传、R009商品知识导入与审核 |
| `/customer-operations` | 客服运营入口 |
| `/ai-capabilities` | AI业务状态与技术信息折叠展示 |

### 6.2 高级与兼容路由

`/knowledge-editor`、`/knowledge-review`、`/knowledge-gaps`、`/faqs`、`/safety-rules`、`/sources`、`/conflicts`、`/suggestions`、`/experience-cases`、`/ai-optimization-pool`、`/ai-feedback-optimization-pool`、`/ai-issues`、`/knowledge-quality-pool`、`/system-status`等路由继续有效。

测试导入路由`/imports*`和`/test-data-packages`只有在`VITE_ENABLE_TEST_TOOLS=true`时注册，见`admin_web/src/router/index.ts:23-48`。

Admin通过`/platform-api`访问C，通过`/ai-api`访问A；不直接连接SQLite或Chroma。

## 7. Shared Contracts责任

当前`contracts/version.json`：

```json
{"contract_version":"0.5.0","status":"additive"}
```

关键契约：

- `customer-service-catalog.v1.schema.json`
- `customer-service-catalog-activation-*.schema.json`
- `customer-product-ai-knowledge-status.v1.schema.json`
- `ai-product-knowledge-publication.v1.schema.json`
- `ai-interaction-event-create.v1.schema.json`
- `assistant-request.schema.json` / `assistant-response.schema.json`

修改共享契约必须同时更新version、CHANGELOG、兼容说明、受影响消费者测试；不能只修改单侧TypeScript或Pydantic模型。

## 8. OPS与QA责任

### OPS

- `scripts/windows/start_ai_customer_service.ps1`：按记录/偏好选择LOCAL或LAN入口；
- `status_ai_customer_service.ps1`：核对PID、端口、health、Repository Root、SHA、source fingerprint和运行模式；
- `stop_ai_customer_service.ps1`：只停止受信任记录中的进程；
- `common_ai_customer_service.ps1`：配置、身份、PID、健康与启动公共实现；
- `scripts/database-health-check/**`：只读检查revision、完整性、外键、孤儿、状态与收据一致性。

### QA

- A/C后端使用Pytest；
- B/Admin使用Vitest、typecheck和build；
- `tests/contract/`验证共享Customer Catalog契约；
- `tests/e2e/customer/`、`admin/`、`catalog/`、`import/`、`workflows/`保存关键业务浏览器流程。

## 9. 变更路由表

| 需求类型 | 首要Owner | 必须联合评审 |
|---|---|---|
| 商品、Store、SKU业务字段 | C | Contracts、B、数据库治理 |
| 客服准入规则 | C | Contracts、B；A原则上不改 |
| 客服页面与目录提示 | B | C契约与QA |
| RAG、Embedding、模型回答 | A | C知识发布、B输出兼容、QA |
| 商品知识Excel导入 | C/R009 | 数据库、Admin、QA；A/B不应被顺带修改 |
| 共享Schema | Contracts | A/B/C全部消费者 |
| 端口、启动脚本、Runtime身份 | OPS | A/B/C启动Owner、Control |
| Migration | C/DB Owner | Control、备份与回滚评审 |
