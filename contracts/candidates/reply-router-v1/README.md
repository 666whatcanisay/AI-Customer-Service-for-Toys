# AI-CS Reply Router V1 contract candidates

Status: `UNCOORDINATED_CANDIDATE`

This directory contains AI-CS-local candidate schemas and synthetic fixtures
for the post-RC5 reply Router handoff. It is deliberately outside
`contracts/schemas/` and does not change the coordinated repository contract
version.

Cards 2–5 now implement C-local rule governance, C-to-A complete-snapshot
publication, A's safe Router and A's runtime Quality/Evidence projection
against these candidate models. That implementation does not promote this
directory to a coordinated shared contract and does not claim Engine support
or send authority.

Card 6 audited the complete chain. The AI-CS component is source-ready, but
the current Engine does not yet produce the turn extension, consume the
evidence extension or bind either one into AutoPolicyAuthorizationV2.
`AI_CS_AUTOREPLY_READY` therefore remains failed/not signed; see the Card 6
acceptance report and cross-repository handoff.

## Compatibility boundary

- Gateway Wire remains `1.0`.
- `contracts/version.json` remains the last cross-line coordinated version.
- The frozen Gateway schema is not regenerated or edited.
- `context.ai_cs_reply_turn` is an Engine-to-AI-CS extension point.
- `metadata.reply_evidence_bundle` is evidence only. It does not authorize
  execution and does not change `requires_approval=true`.
- A emits the bundle only after its local Quality Gate passes. Missing,
  tampered, unknown-version, oversized, structurally invalid or request-scope
  mismatched evidence fails closed to Gateway `NO_ACTION`.
- Evidence source scope may equal the frozen scope or be its governed ancestor
  (`TENANT`, `STORE`, `PRODUCT`, then exact `SKU`). Cross-tenant, cross-store,
  cross-product and cross-SKU evidence remains invalid.
- Fixed-rule evidence binds the exact reviewed material revision, content
  SHA-256, review identity, source scope, rule content fingerprint and complete
  snapshot revision/fingerprint. It carries no material text or filename.
- Facts must remain inside their segment, cite only that segment's sources and
  cover every non-whitespace character of the proposed reply without overlap.
- Engine support is not claimed until both repositories coordinate the next
  additive contract version.

## Candidate change history

- Card 1: introduced strict local turn, rule, split-plan and evidence models
  plus synthetic compatibility vectors.
- Cards 2–3: exercised governed rule lifecycle and complete-snapshot
  publication without promoting the candidate.
- Card 4: connected the strict turn input to A's approval-required Router.
- Card 5: enabled runtime evidence generation, added semantic ancestor-scope
  validation and strengthened fact/source/range completeness. The coordinated
  version remains `0.14.0`; formal version selection is deferred to Engine
  consumer coordination.
- Card 6 audit: completed the AI-CS source-capability review and recorded the
  Engine producer/consumer/authorization gaps. The audit itself selected no
  coordinated version.
- Card 6 remediation harness: added a strict Engine acceptance artifact,
  synthetic PASS fixture and AI-CS read-only wrapper. This changes only the
  uncoordinated candidate set; the formal shared version remains `0.14.0`.
- Fixed-rule source-evidence hardening: sealed exact reviewed source revisions
  in C, rejected narrower-source generalization, carried provenance through the
  complete snapshot and bound it into A's fixed-rule evidence. Pre-hardening
  candidate snapshots fail closed; no formal version was selected.

## Contents

- `schemas/`: strict JSON Schema candidates exported from AI-CS-local Pydantic
  types.
- `fixtures/`: synthetic valid and fail-closed vectors. They contain no real
  customer, Store, Product, order or source-material data.
- `engine-autoreply-v2-acceptance.v1.candidate.schema.json` and its synthetic
  fixture define the test-only Engine evidence consumed by the Card 6 wrapper;
  they do not authorize execution.

Regenerate or verify from `backend/`:

```powershell
$env:PYTHONPATH='.'
python scripts/export_reply_router_contract_candidates.py
python scripts/export_reply_router_contract_candidates.py --check
python scripts/verify_engine_autoreply_v2_readiness.py --engine-root <engine-root>
```

The cross-repository producer/consumer rules are recorded in
`docs/control/interfaces/AI-CS-Reply-Router-V1-Cross-Repo-Handoff.md`.
