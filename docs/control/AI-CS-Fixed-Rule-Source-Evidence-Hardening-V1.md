# AI-CS Fixed Rule Source Evidence Hardening V1

Date: 2026-08-14

Gate: `PASS / AI_CS_FIXED_RULE_SOURCE_EVIDENCE_READY / SOURCE_ONLY`

Global Gate: `FAIL / AI_CS_AUTOREPLY_READY_NOT_ACHIEVED`

Coordination: `CROSS_REPO_UNCOORDINATED_CANDIDATE`

## Architecture finding

The Card 2–5 implementation validated reviewed C knowledge while approving and
publishing a fixed reply, but the C-to-A snapshot retained only the rule ID,
version and semantic content fingerprint. It discarded the exact source
material revision, content hash, review identity and source scope. A therefore
could prove that a rule was current, but could not prove which reviewed source
revision supported the fixed answer.

The prior C scope check also allowed a source narrower than the rule. For
example, one SKU-specific material could support a product-level rule. That
would incorrectly generalize a local fact to every SKU of the product.

Both defects are P0 for future automatic authorization. Passing tests or a
valid rule version cannot substitute for fact-level provenance.

## Implemented closure

- C seals a content-free source evidence list at rule approval: material ID,
  exact revision, lowercase content SHA-256, `REVIEWED_VALID`, governed scope,
  reviewer identity and review time.
- Migration `0022_reply_rule_source_evidence_v1` adds only the evidence JSON to
  the existing `reply_rules` entity. It does not create another knowledge,
  review, IAM or publication system.
- Publication recomputes the latest reviewed evidence and requires an exact
  match with the approval-time binding. New revisions, changed hashes, invalid
  review state, malformed evidence or scope drift make the rule ineligible.
- Source scope must be equal to or broader than the rule scope. Product
  evidence may support an exact product or its SKU; SKU evidence may support
  only that exact SKU. The current Knowledge Material model cannot represent
  tenant/store evidence, so it fails closed instead of promoting a product
  source to tenant/store scope.
- The complete C-to-A snapshot now carries `source_materials`. Its snapshot
  fingerprint therefore changes whenever provenance changes, while the rule's
  semantic content fingerprint remains stable for unchanged answer content.
- A validates the strict source evidence and embeds the rule content
  fingerprint, snapshot revision/fingerprint and exact source materials in the
  fixed-rule `EvidenceSourceV1`. The evidence bundle still contains no question,
  answer, source text, filename or uploaded binary.
- A re-reads the current atomic snapshot during Quality Gate evaluation. Missing
  or malformed legacy snapshots fail closed as unavailable; they do not fall
  back to RAG after a fixed answer has been selected.

## Failure vectors

- A SKU source bound to a product rule is rejected with
  `REPLY_RULE_SOURCE_SCOPE_TOO_NARROW`.
- A newer source revision after approval causes the stale rule to be removed
  from the next complete snapshot; the old answer is not silently re-approved.
- Missing fixed-rule source revisions, missing snapshot identity and
  cross-scope source evidence are rejected by the strict candidate model.
- Existing pre-0022 reviewed rules have no sealed evidence. They must receive a
  new rule revision and review before publication; the migration does not
  fabricate historical proof.

## Verification

- A full regression: `213 passed, 3 skipped`; the skipped cases are the existing
  explicit real external E2E gates.
- C full regression: `194 passed`.
- Fixed-rule/Router/candidate/Gateway A gate: `76 passed`.
- Rule governance/publication/migration C gate: `14 passed`.
- Card 6 verifier/candidate gate: `24 passed`.
- Formal shared contracts: `16 passed`.
- Alembic has one source head: `0022_reply_rule_source_evidence_v1`; isolated
  `0021 -> 0022 -> 0021 -> 0022` and `0013 -> head -> 0013 -> head` passed.
- Candidate export drift check passed.

## Remaining architecture constraints

- Engine still does not produce `ReplyTurnEnvelopeV1`, consume the strengthened
  evidence, create `AutoPolicyAuthorizationV2`, or bind it to Sender/Receipt.
  The read-only verifier therefore correctly remains
  `FAIL / ENGINE_ACCEPTANCE_ADAPTER_MISSING`.
- The controlled RC5 Runtime remains at migration 0019. Source head 0022 is not
  deployed by this task; deployment requires a separate backup/migration Gate.
- The historical real RAG evaluation remains `19/28`. This hardening does not
  change retrieval, Prompt, model, knowledge or that independent quality Gate.
- The A snapshot store remains a single-instance atomic-file projection. A
  future multi-worker/multi-host deployment requires a coordinated durable CAS
  store; this task does not broaden the current single-instance runtime.

No Engine, PDD, Runtime, vector, knowledge content, model, Prompt or formal
shared-contract version was modified. Gateway Wire remains `1.0` and
`requires_approval=true`.
