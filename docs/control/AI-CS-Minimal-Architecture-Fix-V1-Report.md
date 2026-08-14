# AI-CS Minimal Architecture Fix V1

Date: 2026-08-14

Gate: `PASS / AI_CS_MINIMAL_ARCH_FIX_READY / SOURCE_ONLY`

This gate records source readiness only. It does not mean that automatic replies, real PDD access, production deployment, or the Engine send path are ready.

## Delivered fixes

- The C Runtime identity target now follows the repository's unique Alembic head, `0023_reply_readiness_v1`. The controlled migration wrapper resolves the unique head at execution time instead of hard-coding `0019`.
- Isolated migration coverage verifies the two Readiness tables and the `0019 -> 0023` path. `mark-upgraded` preserves the database instance ID, regenerates its binding, and passes Runtime identity validation.
- A compares C's expected reply-rule snapshot with the snapshot actually consumed by the Router. Mismatch blocks `FIXED_RULE` and `COMPOSITE`; a pure RAG answer records an unused rule change as diagnosis only.
- The Admin single-message debugger freezes Store/Product/SKU/message identity behind a request epoch. Scope, message, tab, route, or component-lifecycle changes invalidate late responses.
- C adds a process-local debug limiter: one in-flight request and ten attempts per minute per user plus Store. It returns HTTP 429 with `REPLY_DEBUG_RATE_LIMITED` and `Retry-After`, and releases the in-flight permit on success, timeout, or exception.
- TEST catalog products remain debuggable and are visibly labeled as test material that is not formal product fact.
- The existing XLSX knowledge parser remains backward compatible: newly added optional template fields are not required in older workbooks.
- The frozen Gateway schema has an explicit CRLF checkout rule so a fresh Windows worktree preserves its frozen raw SHA instead of silently normalizing the bytes to LF.

## Verification

- A full regression: `239 passed, 3 skipped` (external/real-service opt-in tests remain skipped).
- C full regression: `213` tests collected and completed successfully.
- Admin full regression: `38 files / 109 tests passed`; typecheck and production build passed.
- Focused database identity/migration: `10 passed`.
- Focused published-debug dependency tests: `9 passed`.
- Focused limiter/API tests: `6 passed`.
- Existing C `ReplyReadinessAiClient` called the existing A FastAPI route over a temporary loopback HTTP port with a synthetic candidate fixture; result was `COMPLETED` and no production/send permission was present.
- Reply Readiness and Reply Router candidate exporters passed drift checks.
- `git diff --check` passed (line-ending warning only).

## Frozen compatibility facts

- Formal repository contract remains `0.14.0 / coordinated`.
- Gateway Wire remains `1.0`.
- Gateway raw SHA-256 remains `fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`.
- Gateway canonical SHA-256 remains `e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`.
- No formal shared contract version was frozen and no Gateway schema was changed.

## Runtime and release boundary

- The controlled formal Runtime remains at `0019_runtime_database_identity_v1`. It was not opened, copied, migrated, restarted, or validated by this task.
- No formal database, vector collection, DataRoot, PDD Profile, or formal service port was accessed.
- Engine, AutoPolicy, Sender, Receipt, PDD, and real-send state were not changed.
- The limiter is intentionally process-local for the current single-process LOCAL topology. Shared/multi-worker limiting is deferred until such a topology is approved.
- A and C must be deployed from one identical AI-CS candidate commit. Mixed-version rolling deployment is not supported for this source candidate.
- A production `0023` migration requires a separate authorized maintenance window with backup, binding regeneration, smoke checks, and rollback evidence.

## Handoff

Use `scripts/verify_reply_readiness_synthetic_http.py` for isolated C-to-A HTTP verification. It allocates a temporary loopback port and temporary directory, uses only synthetic fixture data, and terminates the service before cleanup. It must not be pointed at a formal service or formal data path.
