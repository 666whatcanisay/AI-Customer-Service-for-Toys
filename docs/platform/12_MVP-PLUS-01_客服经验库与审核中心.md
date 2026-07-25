# MVP-PLUS-01 customer experience case center

Status: C-line implementation ready for review on `agent/platform-mvp-plus-01`, based on `origin/develop@271c15520dd7bf91ad8bfa26cad784d3b780e376`.

The implementation follows the frozen task interface in `docs/control/interfaces/experience-case.v1-draft.md`. This document records the C-owned implementation and does not alter `contracts/**` or re-specify the frozen contract.

## Data lifecycle

`CustomerExperienceCase` is independent of `CustomerSuggestion`. Each submitted case starts at revision `1` with:

- `source_type=CUSTOMER_SERVICE_SUBMITTED`
- `review_status=NEW`
- `redaction_version=v1-reminder-only`
- `evaluation_status=NOT_EXPORTED`

The only review transitions are `NEW -> REVIEWING`, `NEW -> REJECTED`, `REVIEWING -> APPROVED`, and `REVIEWING -> REJECTED`. An approved revision cannot be changed through the review API. Approval creates one immutable `CustomerExperienceCaseExport` snapshot with an `export_revision` and a SHA-256 hash over the governed snapshot contents. `CustomerExperienceEvaluation` is append-only evidence tied to the exact case ID, revision, export revision, and content hash.

`v1-reminder-only` is not an automatic-redaction claim. The service preserves submitted content, does not log the case text in these modules, and requires a separate frozen privacy/access design before real customer data can be used.

## Frozen paths implemented by C

- `POST /api/v1/customer-experience-cases` accepts only B submission fields and forces C-owned lifecycle/governance values.
- `GET /api/v1/customer-experience-cases?created_by=&review_status=` returns only the submitter's status projection, without review notes or evaluation evidence.
- `GET /api/v1/admin/ai-optimization/cases/export` returns only approved immutable snapshots. It includes the frozen `export_revision`, context identifiers, content hash, and redaction version in addition to the required answer content.
- `POST /api/v1/admin/ai-optimization/evaluation-results` stores an A evaluation only if the case ID, revision, export revision, and content hash match the frozen snapshot. It never calls a prompt, knowledge, model-training, customer-message, order, or ERP action.

C-owned internal administration endpoints provide case listing/detail/review and approved-pool/evaluation viewing for the internal-test portal. They use the established C error envelope. New experience-case validation uses `EXPERIENCE_CASE_VALIDATION_FAILED`; lifecycle, immutable revision, exportability, and snapshot-mismatch errors use the frozen error codes.

## Cross-line compatibility

The affected consumers are B for submission/status projection and A for controlled export/evaluation evidence. These are additive paths explicitly frozen for MVP-PLUS-01; no existing endpoint, field, error code, or shared-contract version is renamed or removed. `contracts/version.json` remains `0.1.0`.

This does not grant browser clients direct database access, enable A to consume drafts, or enable C to apply A suggestions automatically. Any promotion to a shared versioned contract requires a separate schema, version, changelog, compatibility analysis, A/B/C review, and rollback plan.

## Administration portal

`/experience-cases` provides store, product, SKU, status, and submitter filters; detailed submitted/AI/final answers; and start-review, approve, and reject operations. The operator identifier is visibly labelled as an unverified test identity because formal authorization is absent.

`/ai-optimization-pool` displays approved snapshots, evaluation status, and recorded result/suggestion evidence. It has no Prompt editing, knowledge publishing, model training, ERP, order, or message-send control.
