# AI-CS Server Runtime Console V1 compatibility

`GET /api/admin/server-runtime` is an additive, read-only A-to-C Operations
Console projection with schema version `ai-cs.server-runtime-console.v1`.

It is not a Channel Engine production route and is not part of frozen Gateway
wire `1.0`. Channel Engine clients continue to use only authenticated
`POST /gateway/v1/decisions` and `GET /gateway/v1/health`.

## Compatibility boundary

- A owns the runtime facts and returns Server state/version/runtime mode plus
  Gateway enablement/state/version/Contract version/configuration state.
- C Admin consumes the projection only on the existing local `/ai-api` proxy
  and displays it on the read-only System Status page.
- B does not call this route. `/api/chat`, the B customer workflow and customer
  catalog behavior are unchanged.
- The response excludes credentials, secret references, filesystem/database
  paths, request/response content, nonces and idempotency records.
- Unknown response fields remain forbidden by the checked-in schema. Additive
  evolution requires a new repository contract version and affected-line
  review; breaking changes require a new schema version.

## Affected-line review

| Line | Effect | Review result |
| --- | --- | --- |
| A | New read-only projection; no model/RAG/Prompt call and no business write | Compatible |
| B | No consumer or route semantic change | Unaffected |
| C | System Status adds a typed read-only consumer; R006/R009 pages unchanged | Compatible |
| Gateway Contract V1 | Production routes, objects, HMAC and canonical SHA unchanged | Unaffected |
