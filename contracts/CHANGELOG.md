# Contract changelog

## 0.5.0 - 2026-07-31

- Added `INITIAL_IMPORT` to the additive C-owned customer-service catalog,
  activation-receipt, and C-to-A knowledge-publication source enums. It is the
  formal current label for a Store
  whose existing provenance proves it was initialized from the retained
  `IMPORTED_TEST_ONLY + 0.3.1-test` package.
- `TEST` remains valid for prior immutable activation receipts, historical
  reads, test fixtures and compatibility consumers. No schema version, endpoint
  or availability rule is removed or changed.
- C remains the only data-source and catalog-projection owner. B continues to
  consume the final projection and must not infer availability from a source
  label, legacy test flags, publication evidence or local fallback rules. A
  accepts the additive source label without changing publication behavior.

## 0.4.0 - 2026-07-31

- Added the C-owned `customer-product-ai-knowledge-status.v1` read projection
  used by B to display actual AI publication status, immutable receipt presence,
  and product-level chunk/embedding counts. It does not change catalog
  availability or authorize B to infer business eligibility.
- Added the C-to-A `ai-product-knowledge-publication.v1` incremental publishing
  request and immutable publication receipt. A accepts business context from C
  and does not decide product permissions.
- Added `ai-product-knowledge-visibility.v1` product-level chunk, embedding,
  fingerprint, collection and publication-state evidence.
- Added the C-owned `pilot-business-catalog-batch-activation.v1` response for
  operator-confirmed batch enablement of approved products. Each changed item
  retains its existing immutable activation receipt.
- Additive over 0.3.0: the B catalog projection, R009 import interfaces and all
  earlier schemas remain unchanged. No full RAG rebuild is introduced.

## 0.3.0 - 2026-07-31

- Added the C-owned `pilot-business-catalog.v1.1` projection consumed by B at
  `/api/v1/customer-service/catalog/**`.
- Added the operator-controlled Store/Product activation request, response and
  immutable receipt schemas. SKU availability is inherited from Product and
  has no independent activation command.
- Removed no existing schema or endpoint. Contract 0.2.0 payloads and the
  compatibility-period `/api/v1/test-catalog/**` routes remain unchanged.
- C is the only business-data owner and projector. B consumes final projected
  items and must not infer availability from `test_data_mode`,
  `production_usable`, or `publishable`. A is unaffected.

## 0.2.0 - 2026-07-29

- Added the B-to-C `ai-interaction-event.v1` create and receipt schemas for
  direct acceptance, edited acceptance, and rejection.
- Added deployment order, rollback behavior, affected-line review, data
  minimization, and compatibility notes for Customer Feedback Loop V1.
- Carries forward the additive A-to-C AI Control Center product projection
  introduced in 0.1.1; all original 0.1.0 schemas remain unchanged.

## 0.1.1 - 2026-07-28

- Added the additive `ai-control-center-product.schema.json` contract for the
  read-only `GET /api/admin/ai/control-center/product-overview` projection.
- The projection is aggregate-only and contains no customer content, raw
  errors, Prompt text, secrets, platform URLs, individual feedback/evaluation
  records, model calls, or business writes.
- Compatibility: existing 0.1.0 schemas and A endpoints are unchanged. C/Admin
  may add this endpoint as an optional new consumer and must treat
  `NOT_AVAILABLE` as an explicit absence of data, not as zero or a fallback.

## 0.1.0 - 2026-07-21

- Added the initial stable request, response, feedback, and knowledge publishing schemas.
