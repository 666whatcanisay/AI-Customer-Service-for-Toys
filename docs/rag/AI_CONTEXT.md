# A line AI context

## Scope and task

- Owner: A line (`backend/**`, `docs/rag/**`). Do not modify shared contracts, B/C code, knowledge sources, vectors, logs, or models.
- Current task: `A-T04-LONG`, the backend baseline for an AI capability center.
- Base: `origin/develop` at `36ec2d3`; PR #24 is already included in that base.
- Working branch: `agent/rag-ai-center-t04`.

## Implemented AI customer-service capability

- Existing service entry: `RAGService.query`, exposed at `POST /api/chat` and the bounded admin online-test route.
- Runtime metrics are process-local and lock-protected: calls, successes, errors, total/average latency, latest call time, and a controlled error category. They reset on restart.
- Metrics do not retain questions, prompts, source excerpts, request bodies, or exception text.
- Prompt metadata is read-only and code-managed. The API returns a version, hash, reviewed safe preview, style constraints, and forbidden internal markers; it never returns the full prompt or configuration secrets.
- Planned modules have no fabricated model, health, knowledge, or metric values.

## AI admin routes

- `GET /api/admin/ai/modules`
- `GET /api/admin/ai/modules/{module_id}`
- `GET /api/admin/ai/modules/{module_id}/prompt`
- `POST /api/admin/ai/modules/{module_id}/test`
- `GET /api/admin/ai/modules/{module_id}/evaluations/latest`

The only implemented module is `ai_customer_service`. Planned modules return `PLANNED`; online tests for them return `409 AI_MODULE_NOT_TESTABLE`. The online test is a real RAG call with no business writes or sending. Diagnostics are absent unless `include_diagnostics=true` and then contain only counts and safe codes.

## Evaluation and known boundaries

- Latest saved real evaluation is identified internally as `a-t03-v031-live`: 19/28 passed. Its A-T03 data-quality gate remains blocked and is not changed by this task.
- Evaluation queries read saved reports only; they never rerun the 28-case suite and never disclose an absolute report path.
- Real local smoke uses synthetic frozen test knowledge, temporary Chroma, offline BGE, and local `qwen3.5:9b`; it is not a production-quality claim.

## Verified evidence for A-T04-LONG

- API and regression suite: `63 passed, 2 skipped`.
- Explicit real scoped smoke, including the admin online-test API: `1 passed`.
- `git diff --check` passed. The read-only test environment at `C:\Users\EDY\Desktop\ai客服\rag-customer-service\backend\.venv` was reused without dependency changes.
