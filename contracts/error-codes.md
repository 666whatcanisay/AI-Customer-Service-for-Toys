# Error codes

| Code | Meaning | Client action |
| --- | --- | --- |
| `INVALID_REQUEST` | Request does not conform to the contract. | Correct fields and retry. |
| `RISK_REVIEW_REQUIRED` | Answer needs controlled handling. | Follow the returned action. |
| `INTERNAL_ERROR` | Service failed unexpectedly. | Retry or transfer to a human. |
