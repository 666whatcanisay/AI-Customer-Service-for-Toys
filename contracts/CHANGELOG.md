# Contract changelog

## 0.13.0 - 2026-08-06

- Added HTTP 429 `AUTHENTICATION_RATE_LIMITED` plus `Retry-After` for persistent,
  privacy-minimized login failure buckets. Existing successful IAM objects are
  unchanged.
- Added non-2xx Workspace failure semantics for RAG/LLM operational errors and
  bounded product-publication concurrency error codes.
- Required a file-referenced service identity on every non-health legacy A
  service route and the existing A/C internal routes. The runtime-console route
  accepts either an authorized operations session or that service identity.
  The credential is never browser-readable, logged, or part of a wire schema.
- Gateway wire `1.0` and its canonical schema, Channel Engine, PDD Adapter,
  automatic-send, Prompt and successful A `/api/chat` semantics are unchanged.

## 0.12.0 - 2026-08-06

- Added the C-owned authenticated Customer Desktop Workflow projection,
  one-time self-enrollment grant request and minimized ADMIN audit objects.
- AI-CS derives the user and Store scope server-side and keeps the Channel
  Engine operator session reference outside the browser and source tree.
- Enrollment remains restricted to registered `UNBOUND` devices; independent
  Channel Agent activation is preserved. Integration is disabled by default
  and upstream configuration, reachability, permission and contract failures
  are distinct non-2xx responses.
- Channel Agent protocol `1.0`, Channel Engine source, Gateway wire `1.0`, PDD,
  automatic-send, A `/api/chat`, RAG, Prompt and model behavior are unchanged.

## 0.11.0 - 2026-08-06

- Added C-owned default-Store selection, Workspace context, conversation
  Product/SKU resolution and minimized ADMIN resolution-audit objects.
- CUSTOMER_SERVICE bindings now converge on exactly one default Store. The
  existing self-binding request remains compatible: an omitted
  `default_store_id` retains an authorized default or deterministically chooses
  the first requested Store.
- Added resolver-first AI context injection by `resolution_id` while retaining
  the legacy explicit Workspace chat context. A `/api/chat` and its response
  remain unchanged; ambiguous matches require human confirmation and no
  automatic send is introduced.
- Gateway wire `1.0`, Channel Engine RC1, PDD Adapter, R006/R009 semantics,
  Prompt, RAG and model behavior are unchanged.

## 0.10.0 - 2026-08-06

- Coordinated the C IAM provider, B Customer Workspace and C Admin around the
  internal account policy: 1–64 character Unicode usernames, 8–128 character
  temporary initialization credentials, and server-enforced first-login
  password replacement with a 12–128 character new credential.
- Added `must_change_password` and `all_store_access` to the IAM user
  projection, self-service password replacement, and CUSTOMER_SERVICE
  enabled-Store option/multi-binding objects. CUSTOMER_SERVICE no longer
  requires a fixed default Store.
- Expanded fixed permissions for customer-service self-management and explicit
  product/SKU/knowledge/FAQ/AI-quality/store operations. OPERATOR and ADMIN
  receive server-derived all-Store scope; only ADMIN receives user management.
- This is a coordinated pre-1.0 IAM revision because an old B consumer depends
  on a unique default Store. B, C and Admin must deploy together. A chat,
  Gateway wire `1.0`, Channel Engine, PDD Adapter, R006/R009, Prompt, RAG and
  model behavior are unchanged.

## 0.9.0 - 2026-08-06

- Added `ai-cs.iam.v1` login, current-user, user administration, fixed role,
  permission, Store-binding, and platform ErrorEnvelope objects.
- Added an authenticated C workspace facade that validates the user's Store
  scope before forwarding the unchanged A `/api/chat` request/response.
- A, B and C are affected. Frontend controls are presentation only; C remains
  the IAM authority and reuses the existing Store model. Browser-reachable A
  AI-admin routes validate the Bearer session and operations permission through
  C before serving the frozen control response.
- This is additive over 0.8.0. Gateway wire `1.0` and its canonical schema,
  Channel Engine RC1, PDD Adapter, R006/R009, Prompt, RAG, and A answer
  semantics are unchanged.

## 0.8.0 - 2026-08-05

- Added optional `server.network_mode` (`LOCAL` or `LAN`, default `LOCAL`) to
  the read-only `ai-cs.server-runtime-console.v1` projection so Operations can
  see the active Gateway exposure mode.
- No bind address, allowed network, firewall detail, credential, secret
  reference or request content is added to the shared response.
- This is additive over 0.7.0. Frozen Gateway wire `1.0`, its canonical schema,
  HMAC/nonce/timestamp/signature rules, `/api/chat`, R006/R009 and all business
  contracts are unchanged.

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
