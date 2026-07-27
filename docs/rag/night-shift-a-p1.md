# NIGHT-SHIFT A P1 — AI control output hardening

## Status

Local A-line hardening is complete. The existing AI control success envelope,
module state semantics, C export path, and C writeback shape are unchanged.
Feedback-analysis model output is bounded before JSON decoding and accepts only
the frozen result shape.

## Change record

- Added a 16,384-character total response bound before decoding local model
  output.
- Accepted complete json and application/json code fences case-insensitively.
- Added six focused parser regressions covering plain JSON, fenced JSON,
  malformed structure, incomplete assessments, and oversized output.

## Verified evidence

- Focused parser regression: 6 passed.
- Full backend suite: 77 passed, 3 opt-in real integration tests skipped.
- Local qwen3.5:9b synthetic smoke: 945-character JSON parsed with all five
  assessment keys, a valid outcome, and one bounded suggestion.

The smoke used de-identified synthetic text only. It did not read C, write C,
create feedback data, or claim cross-service success.

## Handoff

The remaining independent integration gate requires an isolated C service, one
human-confirmed de-identified ANALYZING snapshot with a final answer, and an
explicit real feedback-analysis E2E run. That run may read C, call local qwen,
write C evidence, and verify the idempotent replay. Do not run it against
production or customer data.

This change does not modify shared contracts, B/C code, prompts, knowledge,
model configuration, databases, vector stores, or automatic business actions.
