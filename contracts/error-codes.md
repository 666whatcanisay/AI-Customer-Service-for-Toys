# Error codes

| Code | Meaning | Client action |
| --- | --- | --- |
| `INVALID_REQUEST` | Request does not conform to the contract. | Correct fields and retry. |
| `RISK_REVIEW_REQUIRED` | Answer needs controlled handling. | Follow the returned action. |
| `INTERNAL_ERROR` | Service failed unexpectedly. | Retry or transfer to a human. |

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
