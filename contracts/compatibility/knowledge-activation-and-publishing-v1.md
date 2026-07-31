# Knowledge Activation & AI Publishing V1 compatibility

Contract version: `0.4.0` (additive over `0.3.0`).

## Ownership and flow

- C owns approved business knowledge, customer-service activation and the
  publication ledger. C is the only actor allowed to request publication.
- A accepts the explicit tenant/platform/store/product context from C, produces
  chunks and embeddings in the configured active collection, and returns
  product-level evidence. A does not decide whether a product may enter B.
- B continues to consume only C's final customer-service catalog. For an
  already projected product, B may read
  `/api/v1/customer-service/catalog/products/{product_id}/ai-knowledge` and
  display C's final publication status, receipt presence and chunk evidence.
  B does not infer catalog eligibility from that evidence.

## Independent state machines

`APPROVED`, `customer_service_status=ENABLED` and `AI knowledge=PUBLISHED` are
three independent states. No state transition implicitly triggers another.
Only approved products may be enabled or published.

## Incremental and failure semantics

- Publication upserts a new fingerprint-scoped product version, verifies chunk
  and embedding counts, then removes only the old version of that same product.
- No full collection rebuild is permitted. Customer-service status-only changes
  do not change the knowledge fingerprint and do not re-embed.
- Failed publication reports `SYNC_FAILED`; the prior published version remains
  intact. Content changes after publication report `NEED_RESYNC`.
- All write requests are idempotent. Each successful state change produces an
  immutable receipt.

## Compatibility, deployment and rollback

- No 0.3.0 schema, R009 import contract or Prompt contract changes. The new B
  read endpoint is additive and old clients may ignore it.
- Deploy A publication endpoints, then C migration/provider, then Admin. Roll
  back Admin, then C, then A. Database downgrade requires a backup and discards
  only the additive publication ledger; it never deletes Chroma data.
