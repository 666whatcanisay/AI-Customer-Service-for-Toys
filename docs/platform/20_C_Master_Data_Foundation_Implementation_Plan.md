# C Master Data Foundation Implementation Plan

> **Task:** Phase 4.1 C Master Data Foundation
> **Owner:** C Platform / Data
> **Canonical code base:** `origin/develop@671c9a293f1e5e0f462522ad2c7e114c7919c388`
> **Development branch:** `agent/platform-master-data-foundation-v1`
> **Current migration head:** `0007_target_mode_v2_knowledge_quality_loop`
> **Status:** baseline prepared; implementation remains subject to the Interface Owner Gate

## 1. Objective

Phase 4.1 establishes C-owned master-data persistence for Store, canonical Product/SKU, store listings, external identity mappings and versioned promotion evidence. It prepares a reproducible data foundation without changing B customer workflow, A RAG behavior, existing shared contracts or automatic business boundaries.

This plan is an implementation guide, not an assertion that the models, migrations, APIs, authentication or production controls already exist.

## 2. Governing decisions

- Architecture: [AI-CS Business Data Architecture ADR V1.1](../control/architecture/AI-CS-Business-Data-Architecture-ADR-V1.1.md).
- Interface governance: [AI-CS master-data.v1 Interface Freeze Plan](../control/interfaces/AI-CS-master-data-v1-Interface-Freeze-Plan.md).
- C owns business truth and persistence; B consumes authorized catalog projections; A consumes approved serving snapshots and never writes master data.
- Existing `CustomerSuggestion`, `CustomerExperienceCase`, `AIResponseFeedback`, `CustomerEfficiencyEvent`, test catalog and knowledge material entities remain separate.
- No ERP write, automatic knowledge publication, automatic Prompt/model change, automatic training, customer-message send, order, refund or after-sales action is introduced.

## 3. Authorized Phase 4.1 scope

Allowed implementation paths after Gate authorization:

- `platform_backend/**` for C-owned models, repository/service logic and tests;
- `platform_backend/migrations/**` for one new linear migration after the canonical head;
- `docs/platform/**` for C delivery and migration evidence;
- C-only Admin support may be planned separately, but B/A cross-line consumption is not part of the first persistence slice.

Protected paths:

- `backend/**`, `frontend/**`, `extension/**`, `contracts/**`, `scripts/windows/**`;
- existing released migrations `0001` through `0007_target_mode_v2_knowledge_quality_loop`;
- user databases, runtime records, test packages and knowledge/vector data.

## 4. Repository and migration rules

1. Development starts only from this branch and its canonical base lineage; the historical `agent/platform-admin-ui-productization-v1` branch is not merged or rebased into Phase 4.1.
2. The first Phase 4.1 migration must have `down_revision = "0007_target_mode_v2_knowledge_quality_loop"` and must leave Alembic with exactly one head.
3. The old feature-branch revisions `0007_p0_customer_efficiency_events`, `0008_pilot_store_center` and `0009_pilot_trial_governance` are not copied or renumbered into this branch without a separate review.
4. A filename rename is not migration recovery. Revision ID, parent, upgrade, downgrade and database state must all be verified.
5. Before creating a migration, OPS/QA must inventory the `alembic_version` of every maintained database. If any persistent database is stamped on the old branch chain, implementation stops for a dedicated bridge/rebuild decision.
6. Migration evidence must cover empty-database upgrade, canonical-old-database upgrade, downgrade to the prior canonical head, re-upgrade and a unique-head check.

## 5. Planned C-owned persistence slice

The first slice may define the following internal entities after field-level review:

| Entity | Purpose | Required boundary |
| --- | --- | --- |
| Store master | Stable C-owned Store identity within an authenticated Tenant/channel scope | External store codes are mappings, not global primary keys |
| Canonical Product | Stable product identity independent of a specific store listing | Does not absorb order, inventory or ERP domains |
| Canonical SKU | Stable sellable variant identity under a canonical Product | Must enforce Product/SKU parent consistency |
| Store Product Listing | Maps an authorized Store listing to a canonical Product | `ACTIVE` only after human-controlled promotion |
| Store SKU Listing | Maps a Store listing SKU to a canonical SKU | Cannot cross Store/Product parent scope |
| External Identity Mapping | Records source system, external ID, subject, status and evidence | Ambiguity remains `REVIEW_REQUIRED`; no AI auto-merge |
| Catalog Revision / Promotion Audit | Records immutable revision, actor, reason, source and lifecycle transition | Historical evidence is append-only and not delete-rewritten |

Final column names, lengths, nullability, enumerations, indexes and transport projections must come from the approved interface/schema artefacts. Implementation Agents must not infer missing fields from this summary.

## 6. Delivery phases

### 4.1.0 Baseline Gate

- Confirm branch, base SHA, clean worktree and unique canonical migration head.
- Confirm ADR, Interface Freeze and this plan are tracked in the same Git history.
- Confirm no persistent database is on the abandoned migration branch.

### 4.1.1 Persistence model review

- Produce the entity relationship, key strategy, uniqueness constraints, lifecycle fields and tenant/store isolation tests.
- Review existing test catalog, staged import and knowledge-material references; do not silently replace their semantics.

### 4.1.2 Linear migration

- Add one canonical migration after the approved head.
- Provide upgrade/downgrade/re-upgrade and clean-database evidence.
- Do not import the old branch migrations.

### 4.1.3 C-internal repository/service rules

- Implement stable identity, mapping conflict detection, revision and human promotion rules.
- Keep uncertain mappings out of active customer/AI projections.
- Do not add B/A consumers in this slice.

### 4.1.4 Controlled C read projections

- Only after the corresponding schema and transport binding are frozen, expose C-owned read projections.
- Existing test-catalog and Productization V2 endpoints remain backward compatible.

### 4.1.5 Integration handoff

- B and A receive separate tasks only after Provider tests, compatibility evidence and Interface Owner approval.
- QA verifies tenant/store isolation, parent-child integrity, revision replay and failure behavior before any runtime or pilot claim.

## 7. Minimum verification

- Git diff contains only the authorized C/documentation paths.
- Alembic reports exactly one head.
- Empty SQLite database upgrades to head.
- A database at `0007_target_mode_v2_knowledge_quality_loop` upgrades to the new head.
- Downgrade returns to the canonical prior head and re-upgrade succeeds.
- Duplicate external identifiers do not overwrite active identities.
- Cross-tenant, cross-store and invalid Product/SKU/Listing parent references are rejected.
- Uncertain mappings remain non-active and invisible to B/A projections.
- Existing platform pytest, Admin compatibility tests if affected, and `git diff --check` pass.
- No `.runtime`, database, log, source material, secret, dependency or build artefact is committed.

## 8. Stop conditions

Stop Phase 4.1 immediately if:

- more than one Alembic head appears;
- a maintained database is found on the old `0007_p0 → 0008 → 0009` chain without a recovery decision;
- the implementation requires changing B/A fields before the relevant interface family is frozen;
- authentication scope, tenant ownership, identifier semantics or migration rollback is ambiguous;
- a change would modify existing released migrations or import old C branch commits wholesale.

## 9. Authorization Gate

Branch preparation and documentation synchronization do not by themselves authorize model or migration development. Implementation is authorized only when the Interface Owner artefacts required by the freeze plan are complete and its Gate is changed from `INTERFACE_FREEZE_REQUIRED` to an approved implementation state.

Until then, this branch is a reproducible Phase 4.1 baseline with development status `BLOCKED_AT_INTERFACE_GATE`.
