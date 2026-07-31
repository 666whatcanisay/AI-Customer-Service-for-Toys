# Shared contracts

This directory is jointly owned by all three development lines. Schemas are the
versioned compatibility boundary; do not make breaking changes without updating
`version.json`, `CHANGELOG.md`, and the compatibility notes in the pull request.

Current additive baseline: `0.4.0`. Customer-service catalog consumers must use
the C-owned `pilot-business-catalog.v1.1` projection and must not derive
availability from legacy test or publication fields.

R006.1 adds C-to-A incremental product-knowledge publication and visibility
evidence, plus C-owned batch customer-service activation. Publication and
customer-service activation remain independent, explicit operator actions.
