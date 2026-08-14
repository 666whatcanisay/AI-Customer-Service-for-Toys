# AI-CS Reply Router Card 1 Candidate Report V1

Date: 2026-08-13

Gate: `PASS / AI_CS_REPLY_ROUTER_CARD1_CANDIDATE_READY`

Coordination state: `CROSS_REPO_UNCOORDINATED`

## Delivered scope

- Added AI-CS-local strict candidate types for `ReplyTurnEnvelopeV1`,
  `ReplyRuleV1`, rule snapshot publication/receipt, `SubQuestionPlanV1` and
  `ReplyEvidenceBundleV1`.
- Added a fail-closed `context.ai_cs_reply_turn` parser. Missing, malformed,
  tampered or incomplete input returns `MANUAL_REQUIRED` and a stable blocker
  code.
- Added deterministic candidate JSON Schemas and synthetic fixtures under
  `contracts/candidates/reply-router-v1/`.
- Added complete Gateway V1 request/response vectors using the open `context`
  and `metadata` maps.
- Added the Engine producer/AI-CS consumer handoff at
  `docs/control/interfaces/AI-CS-Reply-Router-V1-Cross-Repo-Handoff.md`.

The formal Gateway runtime path does not consume these types yet. That is
intentional: Engine can implement the producer later without blocking Router
Fixture development, while real requests without a valid envelope remain
ineligible for future automatic-candidate handling.

## Contract and compatibility evidence

| Check | Result |
| --- | --- |
| AI-CS Gateway raw schema SHA-256 | `fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80` |
| Engine Gateway raw schema SHA-256 | same |
| Raw schema bytes | equal |
| AI-CS canonical JSON SHA-256 | `e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5` |
| Engine canonical JSON SHA-256 | same |
| Gateway Wire and approval flag | `1.0`; `requires_approval=true` unchanged |
| Existing Engine `DecisionResponse` parser | accepted the synthetic V1 response and preserved `metadata.reply_evidence_bundle` |
| Repository contract version | `0.14.0 / coordinated` unchanged |
| Candidate schema status | `UNCOORDINATED_CANDIDATE` |

No shared contract version, formal schema, changelog or compatibility freeze
was created. Formal coordination is deferred until the Engine consumer is
implemented and both repositories run the shared vectors.

## Card 1 Change Gate

Command:

```powershell
cd backend
$env:PYTHONPATH='.'
python -m pytest tests/test_reply_router_candidate_contracts.py tests/test_gateway_contract.py -q
python scripts/export_reply_router_contract_candidates.py --check
```

Result at delivery: `22 passed`; candidate drift check passed. A read-only run
of the existing Engine `DecisionResponse` parser also accepted the synthetic
Gateway response and preserved the complete evidence namespace. Inputs are
synthetic and contain no real PDD or customer data.

Covered behavior includes:

- frozen Gateway raw and canonical hashes;
- strict candidate schema drift;
- valid fixtures validated directly against every checked-in candidate schema;
- valid multi-message boundaries and hashes;
- missing, overlapping, incomplete and tampered Turn envelopes;
- rule and publication fingerprints;
- evidence hash, scope, exact sub-question coverage and content ranges;
- Gateway V1 additive extension compatibility;
- evidence metadata does not duplicate customer or knowledge text.

## Safety and data boundary

- No Engine source, B, C, Admin, database, migration, Runtime configuration,
  RAG collection, Prompt, model or knowledge data was changed.
- No service was started or stopped.
- No knowledge sync, publication, clear, rebuild, re-slice or embedding action
  was executed.
- Candidate fixtures use synthetic identities and text only.
- Evidence is not authorization and cannot change the frozen human-approval
  flag.

## Next task

Card 2 may implement C-owned fixed reply rule governance only after a
`Reuse First` audit of the existing review, version, publication, audit, IAM and
Admin capabilities. Card 1 does not sign `AI_CS_AUTOREPLY_READY`.
