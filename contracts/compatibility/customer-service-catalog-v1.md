# Customer Available Catalog V1 compatibility

Contract version: `0.3.0`

## Change

- Adds C-owned read projections at `/api/v1/customer-service/catalog/**` with
  schema version `pilot-business-catalog.v1.1`.
- Adds explicit Store/Product `customer_service_status` changes with required
  `Idempotency-Key` and immutable activation receipts.
- Store owns `data_source`; Product inherits it from Store. SKU inherits Product
  availability and deliberately has no independent switch.

## Compatibility

- This release is additive over `0.2.0`. No 0.2.0 schema, endpoint or payload is
  removed or changed. `/api/v1/test-catalog/**` remains available during the
  compatibility period with its original meaning.
- C is affected as the owner and provider. B is affected as a consumer and must
  deploy after C. A has no request, response or runtime change.
- A 0.3.0 B consumer calls only the new catalog paths and does not inspect
  `test_data_mode`, `production_usable`, `publishable`, or other legacy fields
  to decide business availability.
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
- A: reviewed as unaffected; the existing tenant/store/product/SKU context and
  all A endpoints are unchanged.
