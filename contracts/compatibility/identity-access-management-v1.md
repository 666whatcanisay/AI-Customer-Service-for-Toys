# Identity & Access Management V1 compatibility notes

## Scope

Repository contract `0.10.0` coordinates C-owned browser-user identity, Bearer
sessions, RBAC, first-login password replacement, and Store bindings across B,
C and Admin. It supersedes the 0.9 unique-default-Store client assumption. A
answer semantics, Gateway wire `1.0`, Channel Engine, PDD adapters, R006/R009
data semantics, Prompt, and RAG remain unchanged.

## Production endpoints

- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/change-password`
- `GET /api/v1/auth/store-options`
- `PUT /api/v1/auth/store-bindings`
- `GET|POST /api/v1/admin/users`
- `GET|PATCH|DELETE /api/v1/admin/users/{user_id}`
- `PUT /api/v1/admin/users/{user_id}/roles`
- `PUT /api/v1/admin/users/{user_id}/store-bindings`
- `POST /api/v1/workspace/ai-replies`
- `GET /api/v1/workspace/ai-health`

`DELETE` deactivates a user and revokes active sessions; it does not erase the
identity or its historical references. The workspace AI response remains the
existing A `/api/chat` success envelope. C validates the authenticated user's
permission and Store scope before forwarding to loopback A.

## Role mapping

- `CUSTOMER_SERVICE`: `workspace.access`, `ai.reply`, `feedback.submit`,
  `customer_service.manage`; may bind one or more enabled customer Stores.
- `OPERATOR`: `product.manage`, `sku.manage`, `knowledge.manage`, `faq.manage`,
  `ai_quality.view`, `store.view`, `feedback.view`; all-Store scope.
- `ADMIN`: every V1 permission, including `user.manage`.

Frontend navigation is presentation only. C Platform API is the enforcement
point. Customer Store catalog and workspace calls are restricted to the
authenticated user's bindings; ADMIN has explicit all-Store scope.

## Session and credential boundary

- Passwords are stored only as versioned, salted strong hashes.
- New/reset accounts may receive an 8–128 character temporary credential only
  when `must_change_password=true`. Business permission checks fail with
  `PASSWORD_CHANGE_REQUIRED` until the user replaces it with a 12–128
  character password; the replacement revokes existing sessions.
- Login returns an opaque random Bearer token once. Persistence stores only its
  SHA-256 digest, expiry, revocation state, and user reference.
- Browser clients keep the opaque token in `sessionStorage`, attach it to C API
  requests, clear it on logout/401, and never put it in URLs or logs.
- TLS remains a deployment prerequisite outside loopback or a trusted LAN.

## Compatibility and affected-line review

- B: after login, routes initialization credentials to mandatory password
  replacement and an unbound CUSTOMER_SERVICE user to enabled-Store
  multi-selection. Workspace Store choice is no longer a fixed default. Chat
  stays on the authenticated C facade with unchanged AI/human-review fields.
- C: adds the IAM migration, auth/RBAC enforcement, user administration, and
  Store-scoped catalog access. Existing Store rows are reused. OPERATOR and
  ADMIN obtain all-Store scope from their roles rather than binding rows.
- A: `/api/chat` is unchanged and remains loopback. Browser-reachable
  `/api/admin/ai/**` routes validate the Bearer session and operations
  permission through C `/api/v1/auth/me` and also fail closed while
  `must_change_password=true`; the two loopback-only R006 knowledge
  publication routes retain their service boundary. Existing operator-triggered
  A-to-C analysis bridges forward the initiating credential. Model, Prompt,
  RAG behavior, and response fields do not change.
- Gateway/Channel/PDD: no route, schema, secret, signature, or runtime change.

0.10 requires a coordinated B/C/Admin deployment because the 0.9 B consumer
cannot operate without a unique default Store. Rollback must restore the 0.9
provider and clients together. Do not downgrade while user/session rows are
required for operations.
