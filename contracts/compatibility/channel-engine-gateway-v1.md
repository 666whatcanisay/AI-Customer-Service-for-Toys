# AI-CS Production Gateway Contract V1 compatibility

## Scope

Contracts `0.6.0` adds, without replacing any existing endpoint:

- `POST /gateway/v1/decisions`
- `GET /gateway/v1/health`

Both routes use the production-frozen Gateway wire `contract_version=1.0`.
The canonical specification is
`contracts/AI-CS-Production-Gateway-Contract-V1.md`; the server schema is
`contracts/schemas/channel-engine-gateway-server.v1.schema.json`. Its canonical
SHA-256 is
`e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`.

Execution Receipt and Event ingestion are not part of Production V1.
No production Channel Engine address or credential is configured or called.

## AI-CS scope profile

The frozen DecisionRequest permits extension data under `context`. AI-CS uses
the following additive profile:

```json
{
  "context": {
    "channel_name": "synthetic-channel",
    "locale": "zh-CN",
    "ai_cs_scope": {
      "tenant_id": "TENANT-SYNTHETIC",
      "platform": "pdd",
      "store_code": "STORE-SYNTHETIC",
      "product_id": "PRODUCT-SYNTHETIC",
      "sku_id": null
    }
  }
}
```

Repository contract `0.14.0` additionally accepts bounded `product`,
`transaction`, `conversation_history` and `visible_conversation_history`
members beside `ai_cs_scope`. AI-CS validates their product/SKU alignment,
rejects payment/address flags, keeps at most twenty recent entries, and does
not place customer content in Gateway metadata or logs.

Successful Decision metadata may now contain bounded `citations` descriptors
(`reference`, `title`, `product_id`, `sku_id`, `source_kind`). This is an
additive use of the existing flexible metadata object and does not change the
Gateway `1.0` schema or required approval flag.

`ai_cs_scope` is mandatory for a real AI-CS Decision. Missing or invalid scope
returns `422 SCHEMA_VALIDATION_FAILED`. The server never calls the legacy
unscoped `message` path.

## Media type compatibility

The normative vendor media type is
`application/vnd.ai-cs.channel-engine.gateway-v1+json`. During the documented
Channel Engine adapter compatibility window, the server also accepts
`application/json`, which is what the current adapter signs. Responses always
use the vendor media type. Any other request media type returns
`415 UNSUPPORTED_MEDIA_TYPE`.

## Health adapter boundary

The frozen health response exposes `status`, implementation `version`,
`capabilities` and `timestamp`, together with service/reachability fields. The
Channel Agent must sign `GET /gateway/v1/health`; AI-CS does not add an
anonymous alias.

## Decision mapping

| Existing A action | Gateway V1 action |
| --- | --- |
| `DIRECT_ANSWER`, `CONTROLLED_ANSWER`, `ASK_CLARIFY` | `SUGGEST_REPLY` |
| `REQUIRE_LOOKUP`, `TRANSFER_HUMAN`, `REFUSE` | `NO_ACTION` |

Every response fixes `requires_approval=true`. `NO_ACTION` always has
`proposed_content=null`. `risk_level` is a required top-level wire field with
`LOW`, `MEDIUM` or `HIGH`. RAG runtime/model unavailability returns a non-2xx
Gateway ErrorEnvelope and is never converted into a successful Decision.

All non-2xx bodies use `ErrorEnvelope.error.error_code`; the former wire label
`code` is accepted only as an internal model-validation compatibility alias and
is never serialized by the frozen V1 contract.

## Authentication and persistence

- All Production V1 routes require HMAC-SHA256; anonymous calls fail closed.
- The server validates timestamp skew, raw-body SHA-256, constant-time
  signature comparison and a durable ten-minute nonce replay window.
- Completed Decisions are stored by authenticated client and idempotency key
  for at least seven days. Same key/same canonical payload returns the stored
  response; same key/different payload returns `409 IDEMPOTENCY_CONFLICT`.
- The private SQLite state contains hashes and completed Gateway responses. It
  contains no HMAC secret, Authorization header, Prompt, source excerpt, vector
  or knowledge material and is excluded from Git.

## Affected-line review

- A: adds an isolated Gateway adapter over the existing answer service. RAG,
  Prompt, retrieval, product knowledge and `/api/chat` semantics are unchanged;
  the Gateway adapter validates bounded Host context and projects citations.
- B: no source or endpoint changes; it continues to call `/api/health` and
  `/api/chat` through `/rag-api`.
- C: adds Store-scoped Workspace facades for reply-policy read/change and
  human execution preparation. C enforces authenticated Store scope, requires
  explicit human confirmation for mutations, and calls Host through the
  existing signed service identity. Admin has no source or endpoint change.
- OPS: Gateway remains disabled until an approved runtime supplies an HMAC
  secret and private state path. TLS and production Channel Engine connectivity
  require a later deployment Gate.

## Deployment and rollback

Deploy A before enabling any Gateway client. With `GATEWAY_ENABLED=false`, the
new routes return a safe unavailable ErrorEnvelope and existing services run as
before. Rollback is disabling Gateway and restarting A; no B/C rollback, RAG
rebuild, knowledge republish or database migration is required.
