# API 文档

## Browser CORS configuration

Set `CORS_ALLOWED_ORIGINS` to an English-comma-separated list of explicit Origins, for example:

```text
CORS_ALLOWED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173,http://192.168.1.20:5173
```

When omitted, only `http://127.0.0.1:5173` and `http://localhost:5173` are allowed. Entries are trimmed, canonicalized, and deduplicated. Every entry must be exactly `http(s)://host[:port]`: paths, queries, fragments, credentials, wildcards, invalid hosts, and invalid ports abort startup. CORS allows GET, POST, PUT, and OPTIONS with Content-Type only; credentials are disabled. An unlisted Origin receives no ACAO header, while a request without Origin remains a normal server-to-server request.

## POST /api/chat

新规范请求固定为 question + context；context 只接受 `TENANT-PDD-SM-TEST / pdd / PDD-SM`。

响应 `data` 固定包含：`answer`、`action`、`risk_level`、`sources`、`warnings`、`required_fields`、`model`、`latency_ms`、`request_id`、`context`。sources 固定包含 `source_name`、`page`、`chunk_id`、`distance`、`excerpt`、`knowledge_version`、`source_ids`、`product_id`、`sku_id`。

旧 `{message}` 请求仍可用于原 A-T02 客户端，但不得携带 context；B-T03 只消费 data。

## POST /api/retrieval/search

支持 `query/top_k/context`，使用与 chat 相同的 tenant、店铺、商品、SKU 范围过滤，不调用 LLM。

## POST /api/test-knowledge/sync/{package_id}

仅允许本机调用。从配置的 C 地址获取 `version=V0.3.1`、`schema_version=0.3.1-test` 的 rag-export，严格验证后写入独立测试 Collection。未配置或服务不可用返回 `503 ENV_BLOCKED`，不合格包返回 422。

## AI capability center admin APIs

All responses use the existing `{success, message, data}` envelope. These endpoints are read-only except for a bounded, no-side-effect online test; they do not publish prompts, send messages, or perform business writes.

- `GET /api/admin/ai/modules` lists the five registered modules. Only `ai_customer_service` can report `RUNNING`, `PAUSED`, or `ERROR` from the real service state. `aftersales_intent`, `shipping_note_extractor`, `appeal_writer`, and `risk_checker` remain `PLANNED`.
- `GET /api/admin/ai/modules/{module_id}` returns the customer-service model/provider, ready/configuration state, initialization error, knowledge count, prompt version/hash, supported actions, and process-local `since_start` metrics. Planned modules return `null` or `NOT_AVAILABLE` for unavailable model, health, knowledge, and metric fields.
- `GET /api/admin/ai/modules/{module_id}/prompt` returns code-managed prompt version/hash, safe preview, answer-style rules, and forbidden internal markers. It never returns the full prompt, an API key, environment values, hidden system text, or customer data.
- `POST /api/admin/ai/modules/{module_id}/test` accepts `question`, frozen `context` (`tenant_id`, `platform`, `store_code`, `product_id`, `sku_id`), and optional `include_diagnostics=false`. It calls the actual RAG service and returns `answer`, `action`, `risk_level`, `sources`, `latency_ms`, `model`, and `request_id`. Diagnostics appear only when explicitly requested and contain safe counts/codes. A planned module returns `409` with `AI_MODULE_NOT_TESTABLE`.
- `GET /api/admin/ai/modules/{module_id}/evaluations/latest` reads the newest saved `live_c_api` report. It returns its internal ID, recorded timestamp and dataset version when the report provides them (otherwise `NOT_AVAILABLE`), case/pass totals, check counts, failed IDs, and report availability. `report_path` is an internal identifier only, never an absolute filesystem path. If no saved real report exists, the route returns `NOT_AVAILABLE` instead of 500.

Runtime metrics are thread-safe and reset on process restart. They contain no question, prompt, raw request body, source excerpt, or exception text; `last_error_summary` is only a controlled error category.

### GET /api/admin/ai/control-center

Returns the versioned `ai-control-center.v1.1` management snapshot. It is a read-only summary of A process runtime state, safe Prompt metadata, the newest saved `live_c_api` evaluation summary, fixed Badcase empty-state metadata, and a process-memory-only aggregate of successfully completed feedback-analysis runs. Its `response_model` is `AiControlCenterResponse`, so the complete field schema is available in `/openapi.json`.

The route does not probe C, call Ollama, run analysis/evaluation, expose C URLs, or return feedback IDs, content hashes, raw question/answer text, analyses, suggestions, full prompts, environment values, or secrets. Existing module endpoints remain available for V1.0 clients.

### GET /api/admin/ai/operations/overview

Returns the versioned `ai-operations.v1` read-only operations metric snapshot. Its OpenAPI `response_model` is `AiOperationsOverviewResponse`.

- `answer_volume` is an A-process-since-start aggregate of request outcomes: `DIRECT_ANSWER`, `CONTROLLED_ANSWER`, `TRANSFER_HUMAN`, and other/controlled outcomes. It resets on restart and is not durable history or an employee metric.
- `answer_quality` and `knowledge_coverage` use only the newest saved `live_c_api` evaluation. Quality is the evaluation pass rate; evidence coverage is the evaluation `source_ids` check pass rate. Neither represents all production conversations or all business knowledge.
- `badcase` always exposes the fixed four categories with `null` counts until a browser-safe, de-identified aggregate contract exists. `external_data` reports feedback and efficiency dependency state without contacting C; `read_attempted` is false.
- `model_status` reports configuration and A process readiness, not a model liveness probe. `notices` supply controlled explanations and manual next steps only; every notice has `automatic_action_taken=false`.

The route never calls Ollama or C, and never returns customer content, feedback IDs, case IDs, content hashes, prompt text, platform URLs, secrets, raw errors, or individual evaluation records. It does not modify Prompt, knowledge, model, or C data.

### GET /api/admin/ai/quality-baseline/latest

Returns the versioned `ai-quality-baseline.v1` diagnosis of the newest saved `live_c_api` evaluation report. Its OpenAPI `response_model` is `QualityBaselineResponse`.

- `summary` contains only aggregate case/check counts and an internal evaluation identifier. `failed_cases` contains internal case IDs, safe evaluator failure classes, failed check names and numeric source/fact counts; it never contains the underlying question, answer, expected fact, source ID or source text.
- `cause_findings` maps recorded evaluator signals to `DATA_PROBLEM`, `KNOWLEDGE_PROBLEM`, `RETRIEVAL_PROBLEM`, `PROMPT_OR_MODEL_PROBLEM`, and `RULE_DECISION_PROBLEM`. Findings may overlap and a zero count means no direct signal in this report, not proof that the cause is impossible.
- `recommendations` are manual verification steps only. Each has `automatic_change_allowed=false`; the response itself has `model_or_prompt_changed=false` and `raw_content_exposed=false`.

The route does not run qwen, retrieval or a new evaluation; it does not contact C and cannot modify Prompt, knowledge, rules, models, vectors or reports.

原 `/api/health`、`/api/status`、统计、配置和 `/api/ai/*` 兼容路由继续保留。
