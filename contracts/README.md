# Shared contracts

This directory is jointly owned by all three development lines. Schemas are the
versioned compatibility boundary; do not make breaking changes without updating
`version.json`, `CHANGELOG.md`, and the compatibility notes in the pull request.

Current coordinated baseline: `0.10.0`. Customer-service catalog consumers must use
the C-owned `pilot-business-catalog.v1.1` projection and must not derive
availability from legacy test or publication fields.

R006.1 adds C-to-A incremental product-knowledge publication and visibility
evidence, plus C-owned batch customer-service activation. Publication and
customer-service activation remain independent, explicit operator actions. B
reads the additive C-owned product AI knowledge status projection solely for
display; it does not use publication evidence to decide catalog eligibility.

`0.5.0` adds `INITIAL_IMPORT` as the formal current source label for eligible
historical initialization records. `TEST` remains accepted for historical
receipts, fixtures and compatibility reads. C-to-A publication accepts the same
additive label; the canonical knowledge fingerprint is unchanged, so this
transition does not rebuild RAG or alter automatic-action boundaries.

`0.6.0` adds an opt-in Channel Engine Gateway Server boundary. It does not
replace the B-facing `/api/chat` contract. Gateway decisions require HMAC,
strict Contract V1 objects, durable idempotency, `requires_approval=true`, and
the additive `context.ai_cs_scope` profile; real Channel Engine production
connectivity is outside this foundation.

Production Gateway wire `1.0` is frozen by
[`AI-CS-Production-Gateway-Contract-V1.md`](AI-CS-Production-Gateway-Contract-V1.md).
The Server and Agent schemas must remain byte-semantically equal after canonical
JSON serialization and match SHA-256
`e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`.
Receipt ingestion, Event synchronization, Agent registry, multi-tenancy and
multi-instance scheduling are explicitly deferred from Production V1.

`0.7.0` adds the read-only `ai-cs.server-runtime-console.v1` projection for the
local Operations Console. It reports Server/Gateway state, implementation
versions, runtime mode and the frozen Gateway Contract version. It never
contains a credential, secret reference, state path or request content. This
additive console contract does not change Gateway wire `1.0`, `/api/chat`, or
any B/C business contract.

`0.8.0` adds the optional `server.network_mode` (`LOCAL` or `LAN`, default
`LOCAL`) to that read-only Console projection. It reports the selected runtime
exposure mode without disclosing a bind address, allowed CIDR, credential or
secret reference. The frozen Gateway wire schema and Contract `1.0` are
unchanged.

`0.9.0` adds C-owned browser-user authentication, opaque Bearer sessions,
three fixed roles, server-enforced permissions, and bindings to the existing
Store model. B enters the authenticated user's default Store automatically and
uses the C workspace facade for the unchanged A chat envelope. C Admin adds
ADMIN-only user management; OPERATOR and CUSTOMER_SERVICE permissions are
enforced by C, not by hidden buttons. A AI-admin routes validate the same Bearer
session and operations permission through C; A stores no identity or token.
Gateway wire `1.0`, Channel Engine, PDD, R006/R009, Prompt, RAG, and A
`/api/chat` semantics remain unchanged.

`0.10.0` is a coordinated IAM policy revision. It supports Unicode internal
usernames and temporary 8-character initialization credentials, but marks every
new or reset credential for mandatory first-login replacement with a 12+
character password. CUSTOMER_SERVICE selects one or more enabled Stores and no
longer depends on a unique default; OPERATOR and ADMIN have server-derived
all-Store scope. B, C and Admin must deploy this revision together. No password
value is part of the contract or source tree.
