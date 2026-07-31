# Customer Available Catalog V1 compatibility

Contract version: `0.5.0`

## Change

- Adds C-owned read projections at `/api/v1/customer-service/catalog/**` with
  schema version `pilot-business-catalog.v1.1`.
- Adds explicit Store/Product `customer_service_status` changes with required
  `Idempotency-Key` and immutable activation receipts.
- Store owns `data_source`; Product inherits it from Store. SKU inherits Product
  availability and deliberately has no independent switch.
- `INITIAL_IMPORT` is an additive current source value for historical
  initialization records whose retained package provenance is
  `IMPORTED_TEST_ONLY + 0.3.1-test`. Existing `TEST` values remain valid for
  immutable activation receipts, historical reads, fixtures and compatibility.

## Compatibility

- This release is additive over `0.2.0`. No 0.2.0 schema, endpoint or payload is
  removed or changed. `/api/v1/test-catalog/**` remains available during the
  compatibility period with its original meaning.
- C is affected as the owner and provider. B is affected as a consumer and must
  deploy after C. A accepts `INITIAL_IMPORT` as an additive publication-request
  source without changing indexing, retrieval, or answer behavior.
- A 0.3.0 B consumer calls only the new catalog paths and does not inspect
  `test_data_mode`, `production_usable`, `publishable`, or other legacy fields
  to decide business availability.
- B 0.5.0 accepts `INITIAL_IMPORT` as a transport value but does not use it to
  decide business availability. C continues to provide only enabled final
  items; source labels are provenance, not a consumer-side eligibility rule.
- C-to-A publication accepts the same additive source values. The source-label
  transition does not change the canonical knowledge fingerprint, so existing
  publication receipts and chunks remain valid and are not rebuilt.
- Roll back B before C. C may retain additive availability columns and receipts;
  downgrade requires a normal database backup and approval to discard them.

## Projection behavior

- `COMPLETE` with zero items is the only authoritative empty catalog result.
- `PARTIAL` means C isolated malformed source rows and still returned all valid
  final items. Warnings contain aggregate counts only.
- Disabled entities are normal business filtering and do not generate warnings.
- `ENABLED` means selectable for human customer-service use only. It never
  authorizes automatic messages, refunds, orders, knowledge publication, RAG
  changes, Prompt changes or model training.

## Affected-line review

- C: reviewed as schema owner, persistence owner, projection provider and
  operator-action owner.
- B: reviewed as a strict consumer of final items; technical schema validation
  is retained, business trust inference is removed.
- A: reviewed as an additive request-enum consumer; existing
  tenant/store/product/SKU scoping, indexing, retrieval, and answer behavior are
  unchanged.
