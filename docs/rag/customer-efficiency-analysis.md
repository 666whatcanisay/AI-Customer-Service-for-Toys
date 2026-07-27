# Customer-efficiency analysis

## Scope

The A-line consumer reads only the frozen aggregate C endpoint:

```text
GET /api/v1/admin/ai-quality/customer-efficiency/summary
```

The explicit loopback-only A entrypoint is:

```text
POST /api/admin/ai/customer-efficiency-analysis/run
GET  /api/admin/ai/customer-efficiency-analysis/latest
```

The run request may include timezone-aware `window_start` and `window_end`. It is not a polling worker, does not create customer-efficiency events, and performs no Prompt, knowledge, model, customer-message, order, or ERP action.

## Aggregate input contract

`customer-efficiency.v1` supplies only `summary_version`, `generated_at`, the half-open statistic window, `ai_request_count`, `direct_adoption_count`, `edited_adoption_count`, `not_adopted_count`, and `adoption_rate`. A validates the version, timezone-aware timestamps, non-negative counts, window order, and the C formula:

```text
(direct_adoption_count + edited_adoption_count) / ai_request_count
```

The zero-request rate is `0.0`. A does not read event rows, customer-service text, customer identity, employee identity, store/product/order data, rankings, or performance fields.

The provider has no non-adoption-reason or Badcase dimension. Therefore A output always records `not_adoption_reason_status=NOT_PROVIDED_BY_SUMMARY` and never infers a reason, a `MISSING_INFO` trend, or a Badcase relationship from these counts.

## Model output and traceability

The consumer requires local Ollama `qwen3.5:9b` and defaults `CUSTOMER_EFFICIENCY_ANALYSIS_PROMPT_VERSION` to `customer-efficiency-analysis-v1`. The model receives only aggregate metrics and returns bounded JSON containing:

- the exact supplied adoption rate and a system-level assessment;
- a generalized system summary and up to three aggregate-supported issues;
- zero to five non-executing system optimization suggestions.

The prompt prohibits employee assessment, individual comparison, ranking, fabricated reasons, unsupported Badcase claims, and automatic actions. Model output is validated before recording.

Each successful run appends a trace record to the ignored runtime path `LOG_DIR/customer_efficiency_analysis.jsonl`. The record includes `analysis_run_id`, `recorded_at`, `model_version`, `prompt_version`, a hash of the canonical aggregate summary, the summary, analysis, and suggestions. It contains no event details, customer content, or employee information and is never committed to Git.

## Real verification

The opt-in test contains no summary fixture, HTTP substitute, or model substitute. It reads C's real aggregate endpoint, calls real local qwen, validates the result, and verifies that the trace record is retrievable:

```powershell
$env:RUN_REAL_CUSTOMER_EFFICIENCY_ANALYSIS_E2E = "1"
python -m pytest backend/tests/test_real_customer_efficiency_analysis_e2e.py -q -s
```

Before running it, configure `PLATFORM_API_BASE_URL` to an isolated C service implementing `customer-efficiency.v1`. A successful result proves only aggregate trial/test analysis; it is not a personnel-performance, privacy, authorization, retention, or production-security claim.
