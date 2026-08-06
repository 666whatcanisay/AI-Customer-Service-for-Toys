# AI-CS Customer Desktop Workflow Integration V1 Task Card

- Requirement: `R022`
- Date: `2026-08-06`
- Owner: AI-CS Customer Workflow Integration Engineer
- Target: `AI_CS_CUSTOMER_DESKTOP_WORKFLOW_READY`
- Execution boundary: AI-CS source only; no Channel Engine, PDD, Gateway, automatic-send, RAG, Prompt or model change.

## Objective

Connect the authenticated Customer Workspace to the existing Channel Agent identity/status boundary so a customer-service user can see the device associated with the current user and effective Store, request a controlled one-time enrollment grant for an already registered unbound device, and receive explicit offline, upstream-unreachable and permission-invalid states.

## Contract and ownership

- C owns the authenticated `/api/v1/workspace/desktop-agent/**` facade, Store/user scope checks, upstream credential isolation and minimized audit persistence.
- B consumes only the shared AI-CS desktop-workflow contract; it never receives the Channel Engine operator session reference and never treats a hidden button as authorization.
- Channel Engine remains authoritative for Agent registration, device identity, heartbeat, enrollment, activation and online-state calculation. Its source and protocol are read-only inputs to this task.
- Enrollment remains one-time and device-bound. `BOUND` is not `ACTIVE`; independent activation is not bypassed.

## Acceptance criteria

1. Workspace displays current customer-service user, effective Store, Agent/device identity, Agent version and last heartbeat.
2. An already registered `UNBOUND` Agent can receive a one-time grant scoped by C to the authenticated user and authorized Store set; the grant is never logged or persisted by AI-CS.
3. Offline/Degraded, Channel Engine unreachable/not configured and upstream operator permission invalid states have distinct UI and API error handling.
4. C records successful login plus minimized binding-grant and observed Agent status changes; no password, session token, binding code or customer conversation content enters audit rows.
5. Tests cover login audit, Agent status, Workspace association, Store/role authorization and exceptional states.
6. Gateway Contract V1 canonical schema, Channel Engine source, PDD, automatic-send, A `/api/chat`, RAG and business knowledge behavior remain unchanged.

## Verification plan

- C focused and full pytest suites.
- B focused and full Vitest suites, typecheck and production build.
- Shared contract tests and JSON schema validation.
- A/Admin regression as cross-line protection; `git diff --check`; Gateway canonical hash and forbidden-scope diff audit.
- Runtime remains stopped because the formal database is still at `0013` while current source includes undeployed `0014` plus this task's additive migration.
