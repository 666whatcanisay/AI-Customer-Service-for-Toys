# A-AI-CONTROL-SUPPORT-V1

## Purpose

This document describes the A-side, product-facing read-only data projection
for the AI control center hosted at port 5174. A does not create a separate
public web UI. Port 8000 is the AI service API; the root response explicitly
directs operators to `http://127.0.0.1:5174`.

## Product projection

`GET /api/admin/ai/control-center/product-overview` returns the versioned
`ai-control-center.product.v1` envelope. It is the preferred one-request
input for a Chinese product UI and is built from A's existing safe runtime,
control-center, operations and saved-evaluation snapshots.

The projection supplies these display-ready areas without requiring the UI to
infer operational semantics:

- Service state: running/initializing/error, with no raw initialization error.
- Model state: provider and configured model, but no liveness probe; real
  availability is established only by an explicit smoke test.
- Knowledge state: indexed A-process chunk count; sync time is explicitly
  `null`/`NOT_AVAILABLE` until durable sync evidence exists.
- Answer usage: total, direct, controlled, transfer-to-human and other counts.
  They are A-process-since-start aggregates, reset on restart, and are never
  employee metrics or durable audit data.
- Latest real saved evaluation: source, version/timestamp availability, case
  totals, pass rate and display summary. Only `live_c_api` evidence is used.
- Latest quality analysis: the five evidence categories
  `DATA_PROBLEM`, `KNOWLEDGE_PROBLEM`, `RETRIEVAL_PROBLEM`,
  `PROMPT_OR_MODEL_PROBLEM`, and `RULE_DECISION_PROBLEM`, each with a
  controlled Chinese label and manual next step.
- Module list, feedback-analysis aggregate, controlled notices, and explicit
  runtime identity limits.

All `NOT_AVAILABLE` values are meaningful absence-of-data states. UI consumers
must show “暂无数据” rather than treating them as zero or fabricating a fallback.

## Read-only and privacy boundary

The endpoint only reads local A process state and the newest saved real
evaluation file. A GET does not call Qwen, call C, read raw feedback, run an
evaluation, write a business record, change Prompt, publish knowledge, or train
or switch a model.

The response does not expose question/answer text, source excerpts, source IDs,
customer identifiers, feedback IDs, content hashes, individual analysis text,
Prompt text, environment values, C URLs, secrets, raw exceptions or absolute
report paths. The top-level safety flags are fixed to:

```json
{
  "raw_content_exposed": false,
  "model_call_performed": false,
  "business_write_performed": false
}
```

## Compatibility and C/Admin consumption

This is an additive shared-contract release, `contracts/version.json` 0.1.1.
The canonical JSON Schema is
`contracts/schemas/ai-control-center-product.schema.json`; the API's
Pydantic response schema is available from `/openapi.json` as
`AiControlCenterProductResponse`.

Existing `ai-control-center.v1.1`, `ai-operations.v1`,
`ai-quality-baseline.v1`, and their endpoints remain unchanged. C/Admin can
adopt the new endpoint independently. Affected lines reviewed: A provides the
new read-only endpoint and C/Admin is an optional consumer only; no C business
code, C endpoint, error code, or data storage was changed.

Default CORS now also allows `http://127.0.0.1:5174` and
`http://localhost:5174`. It remains an explicit local-origin allowlist with
credentials disabled; operators can override it with `CORS_ALLOWED_ORIGINS`.

## Operator entry points

- `GET /` — Chinese API-service explanation, port-5174 direction, docs and
  health links.
- `GET /docs` — OpenAPI documentation.
- `GET /api/health` — A service health.
- `GET /api/admin/ai/control-center/product-overview` — stable product data.

## Verification

- API unit/contract tests validate the root guidance, strict response model,
  saved evaluation projection, non-leakage of case/source/feedback values,
  no-write flags and 5174 CORS coverage.
- The required qwen smoke remains an explicit, separate real local model call;
  it is never performed by this GET endpoint.

## Phase record

1. **Interface inventory** — reused `ai-control-center.v1.1`,
   `ai-operations.v1`, and `ai-quality-baseline.v1` as safe local sources.
2. **Projection design** — defined one additive `product.v1` endpoint and
   shared JSON Schema, with explicit empty-state, process-scope and no-probe
   semantics.
3. **Read-only implementation** — implemented the projection and added only
   `127.0.0.1:5174`/`localhost:5174` to the explicit default CORS allowlist.
4. **Port-8000 guidance** — root now identifies the service as an API and
   points operators to the 5174 AI control center, `/docs`, and `/api/health`.
5. **Validation** — full backend regression, projection safety tests and a
   real local `qwen3.5:9b` scoped smoke passed. The real local projection
   reported a running/ready model, available knowledge state and saved
   evaluation `19/28`; this historical score remains a separate quality gate,
   not a claim of production-wide quality.
6. **Delivery** — documentation, contract version/changelog, commit, push and
   Draft PR are completed as the delivery step.
