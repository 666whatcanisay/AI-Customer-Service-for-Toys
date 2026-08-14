# AI-CS Reply Quality and Evidence Card 5 Report V1

Date: 2026-08-14

Gate: `PASS / AI_CS_REPLY_QUALITY_EVIDENCE_CARD5_READY / SOURCE_ONLY`

Coordination: `CROSS_REPO_UNCOORDINATED_CANDIDATE`

Hardening addendum (2026-08-14): fixed-rule evidence now also binds the exact
reviewed material revision/hash/scope and the complete rule-snapshot identity.
C rejects narrower-source generalization and stale source revisions before
publication. This closes a provenance gap without changing the historical Card
5 Gate, Gateway Wire or formal contract version. Current aggregate evidence is
recorded in [Fixed Rule Source Evidence Hardening V1](AI-CS-Fixed-Rule-Source-Evidence-Hardening-V1.md).

## Outcome

Card 5 implements A's unified local Quality Gate and runtime `reply_evidence_bundle.v1` generation. A successful fixed-rule, RAG or composite Router result now receives a deterministic evidence bundle only after its complete split plan, answer, action, risk, current rule state, governed RAG lineage, source scope, prohibited claims and fact-to-source mapping pass strict checks.

The enabled Gateway reparses and validates the bundle before placing it under `metadata.reply_evidence_bundle`. Every resulting Gateway decision still has `requires_approval=true`. This card does not implement `AutoPolicyAuthorizationV2`, Engine state/revision checks, RC5 Sender, Receipt, PDD access or automatic customer replies.

## Unified Quality Gate

Quality PASS requires all of the following:

- A valid `SINGLE` or `SPLIT_CONFIRMED` plan with no plan/trace blocker and exactly one ordered segment per sub-question.
- The proposed reply exactly equals the ordered segment composition; aggregate action and risk equal the most conservative segment values.
- No realtime order/logistics/refund/payment/compensation, authenticity or aftersales intent and no generic prohibited commitment.
- Fixed rules are still present in the latest atomically accepted snapshot, `PUBLISHED`, effective, in scope, marked `allow_auto_candidate`, and re-render to the exact segment answer.
- Fixed `DIRECT_ANSWER` is `LOW`; reviewed fixed `CONTROLLED_ANSWER` and approved fixed `ASK_CLARIFY` are `MEDIUM`. Clarification is limited to `product_id` or `sku_id` and uses the published fixed template.
- RAG segments are only `DIRECT_ANSWER + LOW`. Every RAG source has a lowercase SHA-256 knowledge publication fingerprint, bounded non-empty source lineage and a governed scope compatible with the frozen request.
- Direct/controlled answers have no missing fields. Approved clarification fields are recorded in the evidence bundle for later policy evaluation.

Any failed condition returns the whole turn to manual handling. No partial segment or stale fixed answer is retained as an automatic candidate.

## Evidence construction

The runtime bundle contains no customer text, reply text, source excerpt, canonical question, fixed template or Prompt. It contains only:

- the strict sub-question plan with source message IDs, ranges and hashes;
- frozen request scope and each source's governed scope;
- ordered reply segment ranges/hashes, actions, risks and source IDs;
- one evidence fact covering each entire segment and citing only that segment's sources;
- fixed rule ID/version/content fingerprint, rule snapshot identity and exact
  reviewed source-material revisions, or RAG knowledge
  reference/publication fingerprint;
- warning, missing-field and blocker projections; and
- deterministic canonical SHA-256.

Fact ranges must remain inside their segment, may not overlap and must cover every non-whitespace character of the proposed reply. The canonical bundle remains limited to 32 KiB.

Source scope is allowed to be the frozen scope or a governed ancestor. For example, a reviewed tenant/store rule may support a product reply and a product fact may support an exact SKU reply. Cross-tenant, cross-store, cross-product and cross-SKU evidence remains invalid.

## Gateway fail-closed behavior

Gateway validates evidence independently of the Router result:

- `quality_gate_status` and bundle must both be present for a declared PASS.
- Schema version, strict structure, canonical hash, size, proposed-content ranges and frozen request scope are revalidated.
- Missing, tampered, unknown-version, structurally invalid or cross-scope evidence becomes `NO_ACTION / HIGH / REPLY_EVIDENCE_INVALID`.
- Invalid evidence is not returned in metadata and its proposed reply, sources and required fields are discarded.
- Legacy two-argument Gateway providers that never declare Quality/Evidence remain backward-compatible for their existing approval-only behavior.

The nested metadata field is evidence only. Its presence never changes `requires_approval=true` and never grants execution authority.

## Contract and compatibility

- Gateway Wire remains `1.0`.
- Frozen Gateway schema remains 16001 bytes with raw SHA-256 `fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`.
- Shared contract remains `0.14.0 / coordinated`.
- The strengthened evidence schema remains an `UNCOORDINATED_CANDIDATE` under `contracts/candidates/reply-router-v1/`; its candidate change history and cross-line affected review are updated.
- Engine source is unchanged. Formal additive version selection remains deferred until the Engine producer/consumer is implemented and both repositories run the same vectors.

## Privacy and data integrity

- Evidence and stable error projections contain no customer or knowledge正文 and no exception text.
- No secret, customer data, source knowledge, vector, database, log, dependency, model or build artifact was added to Git.
- `backend/vector_db/chroma.sqlite3` remains 188416 bytes with SHA-256 `0c6ca2e39618dd81ad764e7063ec787cc441316415a3d857de86d4b47fb41417`.
- `backend/knowledge_base/README.md` remains 124 bytes with SHA-256 `c215ab851a5d78ab82840ba0e2108b0755c4abb5efe05c4810fac4e36361e456`.

## Verification

- Card 5 Router/contract/Gateway targeted gate: `70 passed` (`26` Router, `19` candidate contract and `25` Gateway).
- A full regression: `208 passed, 3 skipped`; skipped tests remain the existing explicit real external E2E gates.
- Current deterministic RAG/API/Gateway suite: `86 passed`; it includes and preserves the prior 81-test Card 4 baseline plus five Card 5 Gateway evidence cases.
- Candidate export `--check`: passed with zero drift.
- `git diff --check`: passed.
- Gateway, vector and knowledge-placeholder fingerprints are unchanged.

The historical real 28-question RAG report was not regenerated because Card 5 changes neither retrieval, Prompt, model nor knowledge and that evaluator writes durable reports. Its separate `19/28` historical status remains unchanged.

## Remaining execution-time checks

A proves generation-time evidence only. It cannot prove that Engine's Agent/device/store/customer/conversation/message/revision, selector state, page state or latest customer message remains current at execution time. It also cannot grant a nonce, signature or sender permit. Those checks belong to the Engine-side policy authorization and must fail closed immediately before any send.

## Next card

Card 6 may audit Cards 1–5 against the complete AI-CS side of `AI_CS_AUTOREPLY_READY`, finalize the Engine handoff and state exactly which automatic-authorization/sending capabilities remain external. It must not claim real PDD, Pilot or Production readiness and must not modify Engine.
