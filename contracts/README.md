# Shared contracts

This directory is jointly owned by all three development lines. Schemas are the
versioned compatibility boundary; do not make breaking changes without updating
`version.json`, `CHANGELOG.md`, and the compatibility notes in the pull request.

Current additive baseline: `0.5.0`. Customer-service catalog consumers must use
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
