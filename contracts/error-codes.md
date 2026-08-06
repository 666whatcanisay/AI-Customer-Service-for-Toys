# Error codes

| Code | Meaning | Client action |
| --- | --- | --- |
| `INVALID_REQUEST` | Request does not conform to the contract. | Correct fields and retry. |
| `RISK_REVIEW_REQUIRED` | Answer needs controlled handling. | Follow the returned action. |
| `INTERNAL_ERROR` | Service failed unexpectedly. | Retry or transfer to a human. |

## Identity & Access Management V1

- `AUTHENTICATION_REQUIRED`: a Bearer credential is missing or malformed.
- `AUTHENTICATION_FAILED`: username/password or Bearer token is invalid.
- `AUTHENTICATION_RATE_LIMITED`: the minimized username or source failure
  bucket is cooling down after repeated failed logins. The response is HTTP
  429 and carries `Retry-After`; clients must not retry before that interval.
- `SESSION_EXPIRED`: the authenticated session is expired or revoked.
- `PASSWORD_CHANGE_REQUIRED`: the authenticated account is using an
  initialization/reset credential and must replace it before business APIs are
  authorized.
- `AUTHORIZATION_DENIED`: the authenticated user lacks a server-side permission
  or Store binding.
- `USER_NOT_FOUND`: the target user does not exist.
- `USERNAME_CONFLICT`: the normalized username is already registered.
- `ROLE_INVALID`: one or more assigned roles are outside the fixed V1 set.
- `STORE_BINDING_INVALID`: a Store does not exist, is duplicated, or is outside
  the allowed binding shape.
- `DEFAULT_STORE_REQUIRED`: a bound CUSTOMER_SERVICE account has no unique
  default Store. An unbound first-login account remains valid and must complete
  Store selection before entering the Workspace.

## Store Context Resolver V1

- `STORE_CONTEXT_UNAVAILABLE`: the requested authorized Store is no longer in
  the customer-service available projection.
- `PRODUCT_CONFIRMATION_INVALID`: the confirmed Product is outside the
  effective Store's customer-service catalog.
- `SKU_CONFIRMATION_INVALID`: the confirmed SKU is outside the resolved
  Product's customer-service catalog.
- `RESOLUTION_NOT_FOUND`: the resolution does not exist or belongs to another
  authenticated user.
- `RESOLUTION_NOT_READY`: the resolution still needs human confirmation or its
  catalog context is no longer customer-service available.

## Customer Desktop Workflow V1

- `CHANNEL_AGENT_INTEGRATION_NOT_CONFIGURED`: the opt-in C integration or its
  server/secret-file reference is absent or unsafe.
- `CHANNEL_AGENT_SERVER_UNREACHABLE`: C cannot reach the configured Channel
  Agent server within the bounded timeout.
- `CHANNEL_AGENT_OPERATOR_PERMISSION_INVALID`: the external operator session
  reference is rejected or no longer authorized.
- `CHANNEL_AGENT_RESPONSE_INVALID`: the upstream response does not conform to
  Channel Agent protocol `1.0`.
- `CHANNEL_AGENT_REQUEST_REJECTED`: Channel Engine rejected the bounded facade
  request for a non-authentication reason.
- `CHANNEL_AGENT_NOT_REGISTERED`: the submitted Agent/device pair is not in the
  server-authoritative registry.
- `CHANNEL_AGENT_BINDING_INVALID`: the Agent is not `UNBOUND` or already carries
  identity/Store references and cannot receive a self-enrollment grant.

## Channel Engine Gateway Server Foundation V1

All `/gateway/v1/**` non-2xx responses use the frozen Gateway ErrorEnvelope.
Phase 1 implements:

- `INVALID_REQUEST`
- `AUTHENTICATION_REQUIRED`
- `AUTHENTICATION_FAILED`
- `RESOURCE_NOT_FOUND`
- `METHOD_NOT_ALLOWED`
- `UNSUPPORTED_CONTRACT_VERSION`
- `IDEMPOTENCY_IN_PROGRESS`
- `IDEMPOTENCY_CONFLICT`
- `PAYLOAD_TOO_LARGE`
- `UNSUPPORTED_MEDIA_TYPE`
- `SCHEMA_VALIDATION_FAILED`
- `INTERNAL_ERROR`
- `SERVICE_UNAVAILABLE`

Only `IDEMPOTENCY_IN_PROGRESS`, `INTERNAL_ERROR` and `SERVICE_UNAVAILABLE` are
retryable among the Phase-1 responses currently emitted. Authentication,
schema, version, media-type and idempotency-conflict failures require correction
and must not be retried unchanged.

## Customer Feedback Loop V1

- `AI_INTERACTION_EVENT_VALIDATION_FAILED`: event payload or required
  `Idempotency-Key` is invalid.
- `AI_INTERACTION_EVENT_IDEMPOTENCY_CONFLICT`: the idempotency key is already
  bound to a different event.
- `AI_INTERACTION_EVENT_NOT_FOUND`: a feedback reason referenced no saved
  rejected interaction.
- `AI_PROBLEM_NOT_FOUND`: the C-owned AI problem does not exist.
- `AI_PROBLEM_TYPE_REQUIRED`: confirmation omitted a controlled problem type.
- `AI_PROBLEM_STATUS_TRANSITION_INVALID`: the requested human lifecycle
  transition is out of order.
- `AI_PROBLEM_VERIFICATION_EVIDENCE_REQUIRED`: verification lacks a verified
  knowledge task.
- `KNOWLEDGE_OPTIMIZATION_TASK_NOT_FOUND`: the C-owned task does not exist.
- `KNOWLEDGE_OPTIMIZATION_TASK_EXISTS`: a problem already has its V1 task.
- `KNOWLEDGE_OPTIMIZATION_TASK_STATUS_TRANSITION_INVALID`: the requested task
  lifecycle transition is out of order.
- `KNOWLEDGE_OPTIMIZATION_TASK_NOT_READY_FOR_VERIFICATION`: the task is not
  complete.

## Customer Available Catalog V1

- `CUSTOMER_SERVICE_STATUS_INVALID`: the requested status, operator or request
  format is invalid.
- `CUSTOMER_SERVICE_ENTITY_NOT_FOUND`: the requested Store or Product does not
  exist.
- `CUSTOMER_SERVICE_ENTITY_QUARANTINED`: source provenance is unknown or
  conflicting, so the entity cannot be enabled.
- `CUSTOMER_SERVICE_STORE_NOT_ENABLED`: a Product cannot be enabled while its
  parent Store is not enabled.
- `CUSTOMER_SERVICE_ENTITY_INVALID`: required identity, name, platform or
  parent-scope data is invalid.
- `ACTIVATION_IDEMPOTENCY_CONFLICT`: an `Idempotency-Key` is already bound to a
  different activation request.
- `ACTIVATION_RECEIPT_NOT_FOUND`: the requested immutable activation receipt
  does not exist.

## Knowledge Activation & AI Publishing V1

- `CUSTOMER_SERVICE_PRODUCT_NOT_APPROVED`: only an approved Product may be
  enabled for customer-service use.
- `AI_KNOWLEDGE_IDEMPOTENCY_REQUIRED`: publication requires a valid
  `Idempotency-Key`.
- `AI_KNOWLEDGE_IDEMPOTENCY_CONFLICT`: a publication key is bound to a
  different product/version request.
- `AI_KNOWLEDGE_PRODUCT_NOT_FOUND`: the requested Product does not exist.
- `AI_KNOWLEDGE_NOT_APPROVED`: only approved Product knowledge may be published.
- `AI_KNOWLEDGE_SOURCE_UNCONFIRMED`: source provenance is not TEST, INITIAL_IMPORT, or PILOT.
- `AI_KNOWLEDGE_PUBLISH_FAILED`: incremental publication or receipt verification
  failed; the previous published product version remains intact.
- `AI_KNOWLEDGE_PUBLISH_IN_PROGRESS`: another caller holds the product-scoped
  publication lease; retry later with the same idempotency key.
- `AI_KNOWLEDGE_PUBLISH_LEASE_LOST`: the caller's bounded publication lease
  expired before its result could be committed; the newer owner remains
  authoritative.
- `AI_KNOWLEDGE_VISIBILITY_UNAVAILABLE`: product-level RAG evidence could not be
  checked; the client must not infer a published state.

## Production hardening service boundary

- `INTERNAL_SERVICE_AUTHENTICATION_FAILED`: a loopback A/C service call omitted
  or failed the constant-time service credential check.
- `INTERNAL_SERVICE_AUTH_UNAVAILABLE`: the server-side credential file
  reference is absent or invalid; operators must repair configuration.
- `AI_SERVICE_UNAVAILABLE`: C could not obtain a successful RAG/LLM result;
  Workspace returns a non-2xx response and must not display it as an answer.
- `AI_SERVICE_REQUEST_REJECTED`: loopback A rejected C's request before reply
  generation; the failure is not a successful Workspace response.
