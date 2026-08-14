# AI-CS Reply Router Card 4 Report V1

Date: 2026-08-14

Gate: `PASS / AI_CS_REPLY_ROUTER_CARD4_READY / SOURCE_ONLY`

Coordination: `CROSS_REPO_UNCOORDINATED_CANDIDATE`

## Outcome

Card 4 implements the AI-CS repository side of the safe Reply Router. The enabled Gateway request path now consumes Engine's strict `context.ai_cs_reply_turn`, validates exact message hashes and code-point ranges, conservatively plans sub-questions, routes each confirmed source fragment to the best governed fixed rule or the existing scoped RAG service, and preserves reply order when composing the result.

This is still an approval-required suggestion capability. Gateway V1 continues to return `requires_approval=true`. Card 4 does not add Quality Gate authorization, policy authorization, automatic sending, Receipt generation, Engine changes, PDD access or production rollout.

## Safe turn and split behavior

- A missing, malformed, hash-mismatched or range-mismatched Reply Turn Envelope fails closed before RAG is called.
- Splits retain exact original Unicode code-point ranges and hashes. Hard punctuation is deterministic; comma splitting is allowed only when every fragment has one distinct recognized intent.
- Multiple intents in one unsafely separable fragment, unresolved references, multiple product/SKU references, scope mismatches, coverage gaps, overlaps or more than eight sub-questions route the whole turn to manual handling.
- Fixed rules match only original source fragments. No model rewrite is used as a matching input.
- Every confirmed sub-question produces exactly one ordered answer segment. Any failed segment makes the whole turn manual/no-action.

## Fixed-rule routing

- Router reads only the last atomically accepted A snapshot for the exact tenant/platform.
- Matching permits only NFKC full/half-width normalization, whitespace removal and a bounded approved synonym table.
- Priority is `SKU > PRODUCT > STORE > TENANT`; within one scope the longest normalized alias wins. Equal-priority/equal-length rules fail closed.
- Rules must be `PUBLISHED`, currently effective and in the exact store/product/SKU scope.
- Fixed templates may use only declared approved variables. Required context, template syntax and prohibited-claim checks are revalidated at decision time.
- Fixed matches do not call RAG. `allow_auto_candidate` is retained as governance data but does not grant sending authority in this card.

## RAG fallback and composition

- Only clear fixed-rule misses call the existing `RAGService.query` path.
- Each RAG call receives the original sub-question plus the complete aggregate customer turn as a bounded verified conversation entry; no truncation of that turn is accepted.
- Empty, unavailable, high-risk, non-suggestion, warning-bearing, missing-source or cross-product/SKU results fail closed.
- A product-scoped reply must contain at least one source proving the current product scope; every explicit source product/SKU identifier is rechecked.
- Fixed and RAG segments are combined in original order with a stable newline separator. Aggregate action and risk are the most conservative accepted segment values.
- Successful results retain `SUGGESTION_ONLY` and `AUTO_SEND_DISABLED`.

## Gateway compatibility

`GatewayServer` now has an optional request-aware decision provider. Existing two-argument providers remain supported, so existing Gateway unit fixtures and non-Router consumers are unchanged. The formal application enables the request-aware provider and passes the complete frozen request context to `ReplyRouter`.

Missing/invalid turn input becomes a successful Gateway `NO_ACTION` decision with stable manual-routing codes; it is not treated as an AI answer and it does not invoke RAG. Valid low-risk Router output remains `SUGGEST_REPLY` with human approval required.

No Gateway V1 top-level field, schema, media type, HMAC behavior or response approval invariant changed.

## Privacy and data boundaries

- No customer message, reply text, source excerpt, Prompt, secret or exception text is added to audit logs by the Router.
- Router trace is a local in-memory structure used for the next Quality/Evidence card; Gateway V1 does not yet publish a `reply_evidence_bundle` from runtime decisions.
- No source knowledge, vector, database, log, model or customer data file was created or modified.
- `backend/vector_db/chroma.sqlite3` remains 188416 bytes with SHA-256 `0c6ca2e39618dd81ad764e7063ec787cc441316415a3d857de86d4b47fb41417`.
- `backend/knowledge_base/README.md` remains 124 bytes with SHA-256 `c215ab851a5d78ab82840ba0e2108b0755c4abb5efe05c4810fac4e36361e456`.

## Contract and version boundary

- Gateway Wire remains `1.0`.
- Frozen Gateway raw schema remains 16001 bytes with SHA-256 `fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`.
- Shared contract remains `0.14.0 / coordinated`.
- Reply Router candidates remain under `contracts/candidates/` and their export drift check passes. AI-CS does not select or freeze the next shared version.
- Engine remains the only production owner of the four-second buffer and `ReplyTurnEnvelopeV1`; this card does not modify or wait on Engine.

## Verification

- Router plus Gateway targeted gate: `39 passed` (`19` Router and `20` Gateway).
- A full regression: `192 passed, 3 skipped`; the skipped tests are the existing explicit real external E2E gates.
- Deterministic offline RAG/Gateway baseline: `81 passed`, the same suite passed both before and after Card 4.
- Candidate contract export: `--check` passed with zero drift.
- `git diff --check`: passed.

The historical real 28-question report was not regenerated. Card 4 does not modify RAG retrieval, Prompt, model or knowledge, and the evaluator writes durable reports. Its existing `19/28` historical status is neither improved nor overridden by this Router gate.

## Rollback

Source rollback removes the optional request-aware provider wiring and `ReplyRouter`, returning the enabled Gateway application to its previous direct scoped-RAG provider. Rule snapshots remain inert data and do not require deletion. Do not change the controlled Runtime, RAG collection or C database as part of source rollback.

## Next card

Card 5 may convert the local trace into strict evidence, run the unified Quality Gate and emit the bounded `metadata.reply_evidence_bundle` candidate while keeping `requires_approval=true`. It must not implement Engine policy authorization, RC5 sending or automatic customer replies.
