# Customer Desktop Workflow V1 compatibility notes

## Scope and routes

Repository contract `0.12.0` adds an authenticated C facade over the existing
Channel Agent V1 Admin API:

- `GET /api/v1/workspace/desktop-agent?store_id={id}`
- `POST /api/v1/workspace/desktop-agent/binding-grants`
- `GET /api/v1/admin/desktop-workflow/audit`

The Channel Agent protocol remains `1.0`; Channel Engine source, routes, RBAC,
registration, heartbeat, enrollment and activation behavior are unchanged.
Gateway Contract V1 is byte-unchanged.

## Security and privacy boundary

C authenticates the browser with the existing opaque AI-CS Bearer session,
derives the user ID server-side and verifies the requested Store against the
existing Workspace scope. The Channel Engine operator session reference is read
only from an external secret file and is never returned to B. Non-loopback HTTP
upstreams are rejected; LAN/remote upstreams require HTTPS.

Self-service can request a short-lived, one-time enrollment grant only for an
already registered `UNBOUND` Agent/device pair. C fixes the grant's user
reference to the authenticated user and Store references to C-authorized Store
codes. `BOUND` does not become `ACTIVE`; the existing independent activation
step remains mandatory. AI-CS does not persist or log the binding code.

Audit rows contain user, Agent/device and Store identifiers plus state/outcome
and timestamp. They exclude passwords, password hashes, session tokens,
operator session references, binding codes, customer messages, AI responses,
knowledge content and host filesystem paths.

## Compatibility and deployment

This contract is additive. Older B clients ignore the new routes and retain the
R021 Workspace behavior. The integration is disabled by default; a missing
configuration, unreachable upstream, invalid upstream permission or invalid
response returns a distinct non-2xx ErrorEnvelope and never reports an Agent as
online.

C migration `0015_customer_desktop_workflow_v1` adds only the minimized audit
table after `0014_store_context_resolver_v1`. Deploy C and migrate before B if
the device panel is enabled. Rolling B back is data-safe. Rolling C back to
0014 drops only the new audit table; it does not alter users, sessions, Store
bindings, Store Context records, products, knowledge or RAG data.

## Affected-line review

- B: consumes the new C projection, displays device/Agent status and performs a
  user-confirmed one-time grant request. No management secret or direct Channel
  Engine call enters the browser.
- C: owns user/Store authorization, upstream credential isolation, response
  validation, minimal audit and error mapping.
- Admin: may read minimized audit events through the ADMIN-only route; no new
  page is required by V1.
- A/RAG: no code, route, Prompt, model or knowledge behavior change.
- Channel Engine/PDD/Gateway: no source, contract, connection behavior or
  automatic-send change.
