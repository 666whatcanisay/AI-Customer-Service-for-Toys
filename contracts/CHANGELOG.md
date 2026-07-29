# Contract changelog

## 0.2.0 - 2026-07-29

- Added the B-to-C `ai-interaction-event.v1` create and receipt schemas for
  direct acceptance, edited acceptance, and rejection.
- Added deployment order, rollback behavior, affected-line review, data
  minimization, and compatibility notes for Customer Feedback Loop V1.
- Carries forward the additive A-to-C AI Control Center product projection
  introduced in 0.1.1; all original 0.1.0 schemas remain unchanged.

## 0.1.1 - 2026-07-28

- Added the additive `ai-control-center-product.schema.json` contract for the
  read-only `GET /api/admin/ai/control-center/product-overview` projection.
- The projection is aggregate-only and contains no customer content, raw
  errors, Prompt text, secrets, platform URLs, individual feedback/evaluation
  records, model calls, or business writes.
- Compatibility: existing 0.1.0 schemas and A endpoints are unchanged. C/Admin
  may add this endpoint as an optional new consumer and must treat
  `NOT_AVAILABLE` as an explicit absence of data, not as zero or a fallback.

## 0.1.0 - 2026-07-21

- Added the initial stable request, response, feedback, and knowledge publishing schemas.
