# Error codes

| Code | Meaning | Client action |
| --- | --- | --- |
| `INVALID_REQUEST` | Request does not conform to the contract. | Correct fields and retry. |
| `RISK_REVIEW_REQUIRED` | Answer needs controlled handling. | Follow the returned action. |
| `INTERNAL_ERROR` | Service failed unexpectedly. | Retry or transfer to a human. |

## Identity & Access Management V1

- `AUTHENTICATION_REQUIRED`: a Bearer credential is missing or malformed.
- `AUTHENTICATION_FAILED`: username/password or Bearer token is invalid.
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
- `DEFAULT_STORE_REQUIRED`: retained for 0.9 compatibility; 0.10 no longer
  emits it because CUSTOMER_SERVICE may start unbound and select multiple
  enabled Stores.

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
- `AI_KNOWLEDGE_VISIBILITY_UNAVAILABLE`: product-level RAG evidence could not be
  checked; the client must not infer a published state.
