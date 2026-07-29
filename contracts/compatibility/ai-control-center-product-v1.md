# AI Control Center Product Projection V1 compatibility

Contract introduced in `0.1.1` and carried forward unchanged in `0.2.0`.

## Change

- Adds the read-only `GET /api/admin/ai/control-center/product-overview` A
  provider projection and `ai-control-center-product.schema.json`.
- The projection reports aggregate service, model, knowledge, usage, quality,
  and runtime availability. It performs no model call and no business write.

## Affected-line review

- A is the provider and owns the endpoint implementation.
- C may consume the endpoint as an optional Admin projection.
- B is not affected.

## Compatibility and rollout

- The change is additive; all `0.1.0` schemas and endpoints remain unchanged.
- Deploy A before enabling a C consumer. A C consumer must treat
  `NOT_AVAILABLE` as explicit absence and must not convert it to zero or a
  synthetic success.
- Roll back the C consumer first. Removing the optional A endpoint afterward
  does not require a data migration because the projection is read-only.

## Data boundary

The projection excludes customer content, raw errors, Prompt text, secrets,
platform URLs, individual feedback/evaluation records, source knowledge, and
model output. Runtime identity is exposed only when explicitly configured.
