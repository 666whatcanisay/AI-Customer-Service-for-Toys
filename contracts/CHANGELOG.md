# Contract changelog

## 0.7.0 - 2026-08-05

- Added the read-only `ai-cs.server-runtime-console.v1` schema consumed by the
  local Operations Console at `GET /api/admin/server-runtime`.
- The projection contains only Server state/version/runtime mode and Gateway
  enablement/state/version/Contract version/configuration state. Credentials,
  secret references, local paths, request content and idempotency data are
  excluded.
- This is additive over 0.6.0. Frozen Gateway wire `1.0`, canonical schema SHA,
  `/api/chat`, R006/R009, RAG, Prompt and all existing B/C contracts are
  unchanged.

## 0.6.0 Production Gateway V1 freeze - 2026-08-05

- Froze the AI-CS Server/Channel Agent Gateway wire at `1.0` with canonical
  Decision, Health, Error and HMAC authentication objects.
- Promoted `risk_level` to a required DecisionResponse field; normalized Health
  to `status`, `version`, `capabilities` and `timestamp`; normalized the stable
  error discriminator to `error_code`.
- Locked both repositories to the same canonical JSON Schema SHA-256:
  `e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`.
- Explicitly deferred Execution Receipt ingestion, Event synchronization, Agent
  registration, multi-tenancy and multi-instance scheduling from Production
  V1. Internal Channel Engine Receipt/Event domain models are unchanged.
- This is a Gateway boundary freeze only. Existing AI decision, RAG, B/C APIs,
  Channel execution and database behavior are unchanged.

## 0.6.0 - 2026-08-04

- Added the isolated Channel Engine Gateway Server Foundation V1 schema for
  authenticated `POST /gateway/v1/decisions` and `GET /gateway/v1/health`.
- Gateway wire objects use frozen `contract_version=1.0`, strict unknown-field
  rejection, `requires_approval=true`, stable ErrorEnvelope codes, HMAC request
  identity, and durable Decision idempotency.
- AI-CS requires the additive `context.ai_cs_scope` compatibility profile with
  tenant, platform, store, product and optional SKU identifiers. Missing scope
  fails closed; the Gateway never falls back to the legacy unscoped `message`
  request.
- Existing `/api/chat`, `/api/health`, A answer schemas, C APIs and all B
  consumers are unchanged. The Gateway is opt-in and production Channel Engine
  connectivity remains disabled.

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
