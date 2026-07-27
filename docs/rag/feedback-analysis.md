# AI feedback analysis consumer

## Scope and control boundary

This A-line consumer implements the frozen C `ai-feedback.v1` flow only:

1. An operator explicitly calls `POST /api/admin/ai/feedback-analysis/run` from loopback with `{"maximum": 1}` (up to 100).
2. A reads only C's `GET /api/v1/admin/ai-quality/badcases` export.
3. A sends the in-memory comparison to locally configured Ollama `qwen3.5:9b`.
4. A validates the bounded JSON result and writes evidence only to C's `POST /api/v1/admin/ai-quality/analysis-results`.

There is no polling worker, no Mock case generation, no Prompt/knowledge/model change, no publication, and no customer, order, or ERP action.  `maximum` is a per-request bound, not a background batch configuration.

The C interface is frozen and unchanged by this work.  A never consumes the unsupported `/feedback-cases` path, never invents a `feedback_type`, and sends the exact exported `feedback_id`, `revision`, `content_hash`, and `feedback_type` with every writeback.

## Input and model evidence

For each C-human-confirmed `ANALYZING` snapshot, A requires non-empty `feedback_id`, `revision`, `content_hash`, `question`, `ai_answer`, `final_answer`, `feedback_type`, and `redaction_version`.  `final_answer` is required because this task compares the AI answer with the human final answer; a partial snapshot is not sent to a model or written back.

The local model is configured with `LLM_PROVIDER=ollama` and `LLM_MODEL=qwen3.5:9b`.  `FEEDBACK_ANALYSIS_PROMPT_VERSION` defaults to `ai-quality-feedback-v1`.  The model must return JSON with:

- a generalized `summary` and `answer_difference`;
- an independent `PRESENT`, `NOT_FOUND`, or `UNCERTAIN` assessment for `FACT_ERROR`, `MISSING_INFO`, `STYLE_ISSUE`, `RISK_ISSUE`, and `OTHER`;
- `NEEDS_REVIEW` or `NO_ACTION` as `analysis_outcome`;
- zero to five non-executing suggestions, each with a category, description, and generalized evidence summary.

The prompt instructs the model not to quote or repeat the raw question, answers, identifiers, or personal data.  A does not log the source snapshot, prompt, or model result, and its local API returns only a safe trace receipt rather than the source content.

Before JSON decoding, A rejects a model response over 16,384 characters. It accepts plain JSON plus a complete json or application/json fenced JSON object (language marker is case-insensitive), then requires the exact frozen object keys, all five feedback-type assessments, bounded text fields, and no more than five bounded suggestions. Any other shape remains FEEDBACK_ANALYSIS_OUTPUT_INVALID (422) and is never written to C.

The C `redaction_version` is a reminder rather than an automatic redaction guarantee.  Before any real run, the C operator must ensure the human-confirmed export is already de-identified and suitable for this test environment.  This implementation makes no authentication, authorization, retention, or production-security claim.

## Writeback and idempotency

Each new analysis has `analysis_run_id` in the `AQR-<uuid>` form and includes the configured `model_version` and `prompt_version`.  C is the sole persistence owner.  A accepts a successful C receipt only when it reports the same run ID and `ANALYZED` status.

The real opt-in test replays the identical complete writeback once with the same `analysis_run_id`; C must return the stored `ANALYZED` evidence idempotently.  Production requests do not issue that replay.

## Real integration verification

No HTTP or model substitute is used by `backend/tests/test_real_feedback_analysis_e2e.py`.  It requires all of the following:

1. `PLATFORM_API_BASE_URL` points to an isolated reachable C service implementing the frozen endpoints.
2. C exposes one human-confirmed, de-identified `ANALYZING` snapshot with a non-empty `final_answer`.
3. Local Ollama has `qwen3.5:9b` available.

Run:

```powershell
$env:RUN_REAL_FEEDBACK_ANALYSIS_E2E = "1"
python -m pytest backend/tests/test_real_feedback_analysis_e2e.py -q -s
```

The test performs one real read, one real qwen analysis, one C writeback, and one idempotent replay.  It leaves the C record in `ANALYZED`; it must not be pointed at production customer data.
