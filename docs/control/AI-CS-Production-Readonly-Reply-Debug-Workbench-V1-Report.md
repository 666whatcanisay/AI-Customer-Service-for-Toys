# AI-CS Production Readonly Reply Debug Workbench V1

Date: 2026-08-14
Gate: `PASS / AI_CS_PUBLISHED_REPLY_DEBUG_WORKBENCH_READY / SOURCE_ONLY`

## Outcome

AI-CS now provides an operator workbench under `/reply-readiness` for evaluating one customer message through the current published `ReplyRouter`, fixed-rule snapshot, Published RAG, Quality Gate and Evidence path. The result is explanatory only and is permanently marked `production_usable=false` and `allow_auto_send=false`.

The existing 36-question readiness path remains the default `READINESS_SANDBOX` mode. The new `PUBLISHED_ROUTER_DEBUG` mode reuses the existing A endpoint `POST /api/admin/ai/reply-readiness/evaluate`; no second Router implementation or A debug route was created.

## Implementation

- C exposes the thin IAM- and scope-protected `POST /api/v1/admin/reply-readiness/debug` endpoint. It validates Store/Product/SKU through the existing catalog resolver, builds one in-memory question and calls the existing A client without creating a run, context-resolution row or transaction.
- C passes publication/index/Collection facts to A but does not reject an unpublished product before routing. A fixed rule can therefore answer without RAG; RAG and composite paths fail closed with explicit knowledge/Collection blockers.
- A injects a narrow read-only adapter over the already-running `RAGService`. It exposes only runtime identity, product visibility and query capabilities; it does not open Chroma or SQLite paths directly and does not publish, rebuild, switch or write a Collection.
- The published debug result records the actual Router source-build fingerprint, ReplyRule snapshot, RAG Collection, knowledge publication fingerprint/status, model/prompt identity, evaluation time and actual dependency usage.
- Drift blocking is dependency-sensitive: fixed rules use Router/ReplyRule; RAG uses Router/Collection/knowledge/model; composite uses all participating dependencies. Changes in unused dependencies are diagnostics only.
- Admin provides `36题风险池 / 单条消息调试` tabs, business-first results and collapsible production-version detail. Debug state is a module-level Vue reactive singleton only; it is cleared on logout and is not persisted in browser storage or on the server.

## Zero-side-effect boundary

The debug path does not create readiness runs, conversation resolutions, Feedback, Observation, Approval, Authorization, Execution or Sender work. It does not publish or mutate knowledge/rules/model configuration. A may retain only the existing aggregate, content-free RAG latency/error metrics when RAG is actually queried.

Automated C verification spies on `Session.add()` and `Session.commit()` and confirms zero calls for the debug request. The A Router/Readiness modules have no Sender dependency.

## Verification

- A task scope: `99 passed` across Readiness, Router, candidate contracts, rule publication and Gateway tests.
- C task scope: `31 passed` across Readiness API/candidate/migration, Store Context and ReplyRule governance/publication migrations.
- Admin full suite: `38 files / 107 tests passed`; typecheck and production build passed.
- Candidate export drift check passed.
- Formal `contracts/version.json` remains `0.14.0 / coordinated`.
- Gateway Wire remains `1.0`; raw schema SHA-256 remains `fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`; canonical JSON SHA-256 remains `e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`.

## Runtime and release status

This Gate is source-only. No service was started or restarted; no formal port, database, vector store, DataRoot, PDD Profile or sender was accessed. Deployment and an authenticated operator smoke against the formal read-only A/RAG service require a separate maintenance/release action and do not change the real-send Gate.
