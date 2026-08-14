# PDD Reply Readiness V1 candidate

Status: `UNCOORDINATED_CANDIDATE`.

This directory contains the proposed A/C handoff types for Task Cards 7–8:

- `PddReplyReadinessQuestionV1`
- `PddReplyReadinessInputV1`
- `PddReplyReadinessItemResultV1`
- `PddReplyReadinessResultV1`
- `PddReplyReadinessPublishedDebugResultV1`

Compatibility rules:

- `contracts/version.json` remains `0.14.0 / coordinated`; this candidate does not freeze a next shared version.
- Gateway Wire remains `1.0`; no Gateway request/response field or frozen schema is changed.
- C owns the question-set projection, immutable knowledge revision, run ledger, idempotency and store access checks.
- Card 8 adds optional `knowledge_sources[]` to freeze the automatically aggregated latest reviewed PRODUCT/exact-SKU/FAQ/safety revisions. The existing singular `knowledge_snapshot` remains valid for legacy fixtures; sending both shapes is rejected.
- Each multi-source entry carries optional store/product/SKU scope identity. New C producers populate it, and A fails closed on scope, status, template, or duplicate-material drift.
- `material_id/material_revision` on the run projection remains the one explicit draft overlay; `knowledge_source_count` is a read-only C projection. No `KnowledgeMaterial` column or task table is added.
- A validates the strict input, rechecks the exact ReplyRule snapshot, uses `ReplyRouter.decide()` with an in-memory replay provider, and returns a content-hashed result.
- The input is always `test_data_mode=true`, `production_usable=false`, `allow_auto_send=false`, and the sandbox vector identity must begin with `in-memory-replay:`.
- V1 adds `execution_mode` with a backward-compatible `READINESS_SANDBOX` default. `PUBLISHED_ROUTER_DEBUG` is limited to exactly one operator-provided question, forbids sandbox/draft knowledge, and reuses the current published Router/RAG runtime without any publish, ledger, conversation, approval, authorization, execution, or send side effect.
- Published debug results freeze the non-secret Router, ReplyRule, Collection, knowledge-publication and model/prompt identities observed for that request. The Router build identity hashes the running Router/contracts/publication-store source components rather than reusing the static contract-name hash. `dependency_usage` makes drift blocking source-sensitive; changes in unused components remain diagnostic only.
- Browser clients call only C Admin endpoints. They do not construct or forward this evidence contract to A.
- Unknown versions, extra fields, hash drift, snapshot drift, missing results, or evaluator failure fail closed.
- `pdd-reply-readiness-input.valid.json` demonstrates the new aggregate form; `pdd-reply-readiness-input.legacy-single.valid.json` protects the old single-source form.
- `pdd-reply-readiness-input.published-debug.valid.json` and its paired result demonstrate the read-only production-Router debug shape with synthetic content only.

Affected-line review:

- A: additive internal endpoint and local strict types; production RAG publication and Gateway schemas are unchanged.
- C: additive internal client/Admin projection and task-specific tables; `KnowledgeMaterial` core columns are unchanged.
- Admin: additive `/reply-readiness` view and knowledge-history controls.
- Engine/CE: no implementation dependency; only the deferred entry-context handoff applies later.

Fixtures are synthetic and contain no customer, merchant, source-document, or real product data.
