# Store Context Resolver V1 compatibility notes

## Scope

Repository contract `0.11.0` adds the C-owned default-Store workflow and
conversation context resolution used by the B Customer Workspace and C Admin.
It is additive over IAM V1 and the customer-service catalog. C remains the
authority for identity, Store authorization and customer-available
Product/SKU projections.

## Production endpoints

- `PUT /api/v1/auth/default-store`
- `GET /api/v1/workspace/context`
- `POST /api/v1/workspace/context-resolutions`
- `POST /api/v1/workspace/ai-replies`
- `GET /api/v1/admin/store-context/resolutions`

`PUT /api/v1/auth/store-bindings` remains supported and accepts an optional
`default_store_id`. If an older client omits it, C retains an authorized
existing default or chooses the first requested Store deterministically.
CUSTOMER_SERVICE projections with bindings therefore contain exactly one
default Store. ADMIN and OPERATOR retain role-derived all-Store scope.

## Resolution rules

- The resolver never searches outside the effective authorized Store.
- Product/SKU identifiers, codes, official names and display names are matched
  after NFKC/case-fold/whitespace normalization against transient conversation
  content.
- One Product candidate resolves automatically; multiple candidates require
  human confirmation; no candidate is `UNKNOWN`.
- After Product resolution, no SKU yields `sku_id=null`, one SKU resolves
  automatically, and multiple possible SKUs require human confirmation.
- A confirmed Product/SKU is revalidated against the authorized customer-
  available catalog. Client-provided names or availability flags are never
  trusted.

The response carries stable IDs and display labels for human confirmation.
The stored audit row contains only user/Store/entity IDs, candidate ID arrays,
a normalized conversation SHA-256, status, reason code and timestamp. It never
contains customer text, AI answers, credentials, session tokens or knowledge
content.

## AI context injection and compatibility

B sends `resolution_id` to the authenticated C Workspace facade after a
`RESOLVED` result. C reloads that resolution for the same user, revalidates
Store/Product/SKU scope and constructs the existing A chat context. A receives
the unchanged `{question, context}` request and its response remains unchanged.
The legacy explicit `context` form is retained for compatibility and remains
server-authorized.

Operational RAG or LLM failures are not AI answers. C maps A's explicit
`RAG_RUNTIME_ERROR` or `LLM_REQUEST_FAILED` warning to HTTP 503
`AI_SERVICE_UNAVAILABLE`; an A-side non-2xx response is also preserved as a
non-2xx platform ErrorEnvelope. Successful assistant response fields remain
unchanged.

## Affected-line review

- B: consumes C-owned Workspace context/resolution objects, persists default
  Store switches through C and requests manual confirmation only for ambiguous
  Product/SKU candidates. No auto-send is added.
- C: owns default Store persistence, resolver rules, minimal resolution audit,
  AI context reconstruction and ADMIN-only audit projection.
- Admin: shows Store defaults/scope and the minimized resolution records.
- A: no route, request schema, answer behavior, Prompt, RAG or model change.
- Gateway/Channel/PDD: no route, schema, signature, secret, adapter or runtime
  change. The frozen Gateway Contract V1 canonical schema must retain its
  pre-R020 SHA-256.

Deploy C before or together with B/Admin. An older B client continues to use
the legacy Workspace chat request. Rolling B/Admin back does not require data
rollback. Rolling C below 0.11 leaves the additive 0014 audit table unused; the
0014 downgrade removes only that table and does not alter users, bindings,
catalog data, RAG data or customer content.
