# AI-CS Reply Rule Snapshot Publication Card 3 Report V1

Date: 2026-08-14

Gate: `PASS / AI_CS_REPLY_RULE_PUBLICATION_CARD3_READY / SOURCE_ONLY`

Coordination: `CROSS_REPO_UNCOORDINATED_CANDIDATE`

## Outcome

Card 3 implements the AI-CS repository side of governed fixed-reply snapshot publication. C publishes one complete effective snapshot per tenant/platform scope to A. A validates the strict candidate contract and atomically replaces only that scope after all checks pass. A failure leaves the last valid A snapshot and the last C-published revision intact.

This is source capability only. It does not deploy migration 0021, enable the Router, authorize automatic replies, connect Engine/PDD or send a customer message.

## Reuse-first implementation

- C reuses the existing `knowledge.manage` permission, reviewed Knowledge Material checks, server-derived Principal, internal service token, publication lease, idempotency and receipt patterns.
- C adds only the rule-snapshot publication state, minimized receipts and idempotency records required by this capability. It does not create another IAM, review system, database or Admin application.
- A stores snapshots beneath the existing Git-ignored vector database root in a dedicated atomic JSON projection. It does not add SQLite or modify the RAG collection.

## Interfaces and semantics

- C operator API: `POST /api/v1/admin/reply-rules/publications`, with mandatory `Idempotency-Key`.
- C receipt API: `GET /api/v1/admin/reply-rules/publication-receipts?tenant_id=&platform=`.
- C withdrawal API: `POST /api/v1/admin/reply-rules/{rule_id}/versions/{rule_version}/withdraw`, with mandatory `Idempotency-Key`.
- A loopback internal API: `POST /api/admin/ai/reply-rule-publications`, protected by the existing internal service identity.

C selects the latest currently effective, publishable `APPROVED` or `PUBLISHED` version for each rule ID in the exact tenant/platform scope. The payload carries only published rule projections and review evidence. A validates rule fingerprints, snapshot fingerprint, scope, revision continuity, size and idempotency before atomic replacement.

Withdrawal is also a complete-snapshot publication. C marks a rule `WITHDRAWN` only after A returns an exact valid Receipt. Removing the final rule publishes a valid empty snapshot with the next revision.

## Failure and privacy properties

- A rejects stale, skipped or conflicting revisions, duplicate publication identities, altered idempotent requests, invalid fingerprints, unknown fields and oversized/corrupt state.
- Retrying the same semantic publication may have a different `produced_at`; it replays the original receipt. Identity, content, scope, publisher or revision drift conflicts.
- C validates every Receipt field, including zero accepted rules. Transport failures or mismatched receipts set local publication state to `SYNC_FAILED` while preserving the prior revision, fingerprint, rule states and Receipt.
- Publication events and receipts contain identities, hashes, lifecycle state and operator evidence; they do not copy customer messages, canonical questions, aliases or fixed-reply text into audit records.

## Database and compatibility

- Source migration head: `0021_reply_rule_snapshot_publication_v1`.
- Controlled RC5 Runtime: remains `0019_runtime_database_identity_v1`; no migration or service operation was performed.
- Gateway Wire: remains `1.0`; frozen raw and canonical hashes are unchanged.
- Shared contract: remains `0.14.0 / coordinated`.
- `reply-rule-publication.v1` remains under `contracts/candidates/` as `UNCOORDINATED_CANDIDATE`; AI-CS does not unilaterally freeze the next shared version.

## Verification

- A Card 3 plus candidate/Gateway targeted gate: `27 passed`.
- A full regression: `173 passed, 3 skipped` (real opt-in E2E remains skipped).
- C Card 2/3 plus migration targeted gate: `11 passed`.
- C full regression: `191 passed`.
- Every C test publication payload is parsed in an isolated process by A's strict `ReplyRulePublicationV1`, covering both populated and empty snapshots.
- Migration 0021 upgrade/downgrade/upgrade and the repository single-head migration path passed in isolated SQLite databases.

## Rollback

Before any deployment, back up the controlled database. Source rollback removes the A snapshot endpoint/store and C publication endpoints/service, then downgrades only a non-production copy from 0021 to 0020. Existing A snapshot files may be retained as inert recovery evidence or removed through a separately approved Runtime cleanup. Do not modify the controlled RC5 Runtime as part of source rollback.

## Next card

Card 4 may consume the last valid A snapshot to implement the safe Reply Router, fixed-rule matching, RAG fallback and composite reply generation. It must keep `ReplyTurnEnvelopeV1` fail-closed behavior and must not implement automatic sending.
