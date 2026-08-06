# Production hardening V1 compatibility

Repository contract `0.13.0` coordinates security and failure semantics without
changing successful business payloads or the frozen Gateway wire contract.

## Authentication boundary

- A `/api/health` is the only unauthenticated A route.
- Existing A chat, retrieval, status, statistics and compatibility routes now
  require `X-AI-CS-Service-Token`. C resolves the token from a runtime file and
  injects it only on its loopback A call.
- A operations routes continue to require a C-validated operations Bearer
  session. `/api/admin/server-runtime` accepts either that operations identity
  or the runtime service identity so trusted status scripts remain usable.
- The production web proxy forwards browser `Authorization` but explicitly
  strips the service-token header, cookies and other non-allowlisted headers.
- C browser routes retain their existing IAM/RBAC and Store-scope checks. Login
  and health remain the only public C entry points; the frozen internal test
  knowledge projection requires the same service identity.

## Failure behavior

- Login throttling can add HTTP 429 `AUTHENTICATION_RATE_LIMITED` and a
  `Retry-After` response header. Successful login/session objects are unchanged.
- The authenticated Workspace facade maps A transport, RAG runtime and model
  failures to a non-2xx error envelope. The successful legacy A `/api/chat`
  payload remains unchanged for its trusted C caller.
- Concurrent publication for the same product returns HTTP 409
  `AI_KNOWLEDGE_PUBLISH_IN_PROGRESS`; an expired lease is recoverable.

## Affected-line review

- A owns service authentication, successful RAG behavior and Gateway isolation.
- B consumes only the authenticated C Workspace facade and handles login 429;
  no direct A credential is exposed to the browser.
- C owns IAM/session throttling, RBAC/Store authorization, service-token
  injection, publication leases and the error envelope.
- Admin uses its existing operations Bearer session and handles login 429.
- Gateway Contract V1 schema and HMAC behavior, Channel Engine, PDD Adapter,
  Prompt, automatic-send and human-confirm boundaries are unchanged.
