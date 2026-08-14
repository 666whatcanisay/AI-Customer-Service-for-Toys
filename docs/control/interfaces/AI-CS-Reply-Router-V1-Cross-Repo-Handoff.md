# AI-CS Reply Router V1 Cross-Repo Handoff

Status: `CROSS_REPO_HANDOFF_REQUIRED / UNCOORDINATED_CANDIDATE`

Date: 2026-08-14

AI-CS implementation note: Cards 2–5 now provide C-local governed reply rules,
C-to-A complete-snapshot publication, A's source-only Reply Router and A's
runtime Quality/Evidence projection. A emits the candidate evidence bundle
only after local quality PASS and maps invalid input/evidence to manual
`NO_ACTION`. This remains an AI-CS-local candidate and does not change Engine
ownership, grant send authority or select the shared version below.

Card 6 acceptance note: the AI-CS component is source-ready, but read-only
inspection of the current Engine shows that it does not produce
`ai_cs_reply_turn`, consume `reply_evidence_bundle`, or implement
`AutoPolicyAuthorizationV2`. Therefore `AI_CS_AUTOREPLY_READY` is not signed.
The remedial Engine integration requirements are listed in section 9 and in
the Card 6 acceptance report.

## 1. Ownership and non-blocking development

`context.ai_cs_reply_turn` is produced by Channel Engine and consumed by
AI-CS. Engine owns the four-second Buffer, original platform message IDs,
aggregation order and source ranges. AI-CS owns strict parsing, fail-closed
handling, Router use and evidence generation.

This AI-CS task does not change the Engine repository. Until Engine implements
the producer, AI-CS tests the implemented Router with checked-in synthetic
fixtures. A missing or invalid envelope is `MANUAL_REQUIRED` internally and a
Gateway `NO_ACTION`; it does not call RAG and must never become an
automatic-reply candidate.

## 2. Frozen Gateway boundary

No Gateway V1 top-level field is added.

- Request extension: `DecisionRequest.context.ai_cs_reply_turn`
- Response extension: `DecisionResponse.metadata.reply_evidence_bundle`
- Gateway Wire: `1.0`
- `requires_approval`: remains `true`
- Raw schema file SHA-256:
  `fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`
- Canonical JSON SHA-256:
  `e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`

The candidates do not update `contracts/version.json`. The next additive
shared version must be selected only when the Engine consumer is implemented
and both repositories run the same vectors.

## 3. `ReplyTurnEnvelopeV1` producer rules

Candidate schema:
`contracts/candidates/reply-router-v1/schemas/ai-cs-reply-turn.v1.candidate.schema.json`

Engine must produce the envelope from the exact string placed in Gateway
`customer_message`:

1. Order one to thirty-two original customer messages exactly as the Buffer
   orders them.
2. Join the privacy-filtered message strings with exactly one line feed
   (`U+000A`). Do not trim, rewrite or normalize them after range calculation.
3. Use zero-based, left-closed/right-open offsets measured in Unicode scalar
   values (`index_unit=UNICODE_CODE_POINT`). Python's normal `str` indexing is
   the reference behavior. UTF-8 byte offsets and UTF-16 code-unit offsets are
   not accepted.
4. The first message starts at zero. Each next start equals the prior end plus
   one separator. The final end equals `len(customer_message)` in Unicode code
   points.
5. Compute every `content_sha256` over the UTF-8 encoding of the exact message
   slice. Compute `aggregate_content_sha256` over the UTF-8 encoding of the
   complete `customer_message`.
6. Preserve the stable original platform message IDs. Do not use reply text,
   timestamp concatenation or a newly generated aggregate ID as an original
   message ID.
7. Do not copy customer text into the envelope.

The aggregate Gateway top-level `message_id` remains the existing Engine input
identity. It does not replace the original IDs in the envelope.

## 4. AI-CS consumer rules and error semantics

AI-CS parses the extension with strict types and validates it against the
actual `customer_message` before fixed-rule matching or RAG fallback.

| Condition | AI-CS result |
| --- | --- |
| Extension absent | `MANUAL_REQUIRED / REPLY_TURN_ENVELOPE_MISSING` |
| Wrong type, unknown field, duplicate ID, overlapping/gapped range | `MANUAL_REQUIRED / REPLY_TURN_ENVELOPE_INVALID` |
| Aggregate hash mismatch | `MANUAL_REQUIRED / REPLY_TURN_AGGREGATE_HASH_MISMATCH` |
| Final range does not cover the aggregate | `MANUAL_REQUIRED / REPLY_TURN_RANGE_COVERAGE_MISMATCH` |
| Message slice hash mismatch | `MANUAL_REQUIRED / REPLY_TURN_MESSAGE_HASH_MISMATCH` |
| Joiner mismatch | `MANUAL_REQUIRED / REPLY_TURN_SEPARATOR_MISMATCH` |

These failures are not retryable automatic-send decisions. They may produce an
internal human suggestion later, but they cannot grant policy authorization.

## 5. Evidence bundle boundary

`metadata.reply_evidence_bundle` uses the candidate
`reply-evidence-bundle.v1` type. It carries hashes, ranges, source identities,
scope and risk/action mappings. It must not duplicate customer questions,
knowledge text or source excerpts.

The canonical bundle size is limited to 32 KiB. `bundle_sha256` is lowercase
SHA-256 over UTF-8 canonical JSON after removing the `bundle_sha256` member;
canonical JSON sorts object keys, emits no insignificant whitespace, preserves
Unicode and rejects NaN/Infinity.

The bundle is a Quality Gate input only. Old Gateway V1 consumers may ignore
it. A future Engine consumer must validate its version, structure, hash, scope
and current local state and must not interpret its presence as send authority.

Card 5 emits this bundle from runtime Router decisions only when all segments
pass local quality checks. Gateway reparses the strict model, validates the
bundle hash and reply ranges, and compares the frozen bundle scope with the
actual request scope before adding it to metadata. Missing, tampered,
unknown-version, oversized, structurally invalid or cross-scope evidence is a
manual `NO_ACTION` and is not echoed back.

Source scope is semantic, not an assertion that every source was published at
SKU level. A source may be the frozen scope or one of its governed ancestors:
same tenant, same store, same product and then exact SKU. A tenant-level rule
may therefore support a product/SKU reply, while another tenant/store/product
or SKU never may. Every fact range must stay inside its segment, cite only that
segment's sources and cover all non-whitespace proposed content without
overlap.

Fixed-rule evidence additionally carries the rule semantic fingerprint, the
complete-snapshot revision/fingerprint and a content-free list of exact source
material revisions. Each material entry contains only ID, revision, content
SHA-256, `REVIEWED_VALID`, governed scope and review identity/time. A source
must be equal to or broader than the rule scope; SKU evidence cannot support a
product/store/tenant rule. C revalidates the latest material revision before
every publication, so a changed source requires a new rule revision and human
review. Missing legacy evidence fails closed.

The bundle still does not prove that the conversation revision, page, customer
message or knowledge state is current at execution time. A future Engine
consumer must revalidate those facts immediately before policy authorization.

## 6. Shared vectors

Synthetic vectors are checked in under
`contracts/candidates/reply-router-v1/fixtures/`:

- valid and invalid `ReplyTurnEnvelopeV1` examples;
- a candidate rule publication snapshot;
- a valid evidence bundle;
- a complete Gateway V1 request carrying `ai_cs_reply_turn`;
- a complete Gateway V1 response carrying `reply_evidence_bundle`.

Engine integration must consume the valid vectors and reproduce the same
hashes and ranges. It must also reject the tampered, overlapping and incomplete
vectors. Only after that review may both repositories coordinate a formal
additive contract version, changelog and compatibility note.

## 7. Affected-line review

- A: owns candidate types, parser, fixtures, Router, local Quality Gate and
  evidence generation. The enabled Gateway application uses the request-aware
  provider; legacy two-argument providers remain compatible and the frozen
  wire is unchanged.
- B: no API consumption or source change. Existing human-review behavior is
  unchanged.
- C: Cards 2–3 reuse existing IAM, reviewed knowledge, lease, idempotency and
  receipt infrastructure for governed rules and complete-snapshot publication.
  Source migration head is 0021 while the controlled Runtime remains 0019.
- Engine: future producer/consumer implementation only; no Engine source was
  changed by this task.

The fixed-rule evidence hardening moved C's source migration head to
`0022_reply_rule_source_evidence_v1`; the controlled Runtime remains 0019 and
was not migrated. The candidate change remains uncoordinated.

## 8. Rollback

Remove the AI-CS-local Router and optional request-aware provider wiring, then
remove candidates only if Cards 1–3 are also rolled back. Rule snapshots may
remain inert. No RAG collection, Gateway schema, runtime config or Engine
rollback is required.

## 9. Engine Autoreply V2 remedial task

This is an Engine-owned follow-up and is not authorization for AI-CS to edit
the Engine repository.

1. Produce the exact `ReplyTurnEnvelopeV1` from the four-second Buffer.
2. Strictly consume and re-hash `reply_evidence_bundle.v1` into a local V2
   package; all missing, unknown, tampered, oversized, stale or cross-scope
   input fails closed. Fixed sources must retain their rule content fingerprint,
   snapshot revision/fingerprint and exact reviewed material revision/hash/scope
   evidence; missing pre-hardening fixed evidence is not backward-filled.
3. Create a signed, short-lived, one-use `AutoPolicyAuthorizationV2` bound to
   the message/revision, final reply hash, evidence hash, quality/risk/store
   policy, selector evidence and activation permit.
4. Keep `Decision → PolicyAuthorization → Execution → Receipt` separate from
   the human-approval ledger. Automatic authorization must never imply
   `human_approval_verified=true`.
5. Revalidate the latest customer message, conversation revision, page,
   input, selector, knowledge state, rate policy and Kill Switch immediately
   before execution.
6. Connect the authorization to the RC5 Sender and immutable Receipt path;
   `UNKNOWN` is never auto-retried and rate-limited replies go to humans.
7. Run the shared candidate vectors and cross-repository end-to-end negative
   cases, then coordinate the next additive shared version. Gateway Wire 1.0
   and its frozen schema remain unchanged.

## 10. Executable Card 6 acceptance adapter

AI-CS provides a read-only wrapper at
`backend/scripts/verify_engine_autoreply_v2_readiness.py`. Engine owns the
future adapter at `scripts/verify_ai_cs_autoreply_v2.py`; AI-CS must not add it
to the Engine repository.

The wrapper supplies only synthetic candidate paths and hashes:

- `--candidate-root`
- `--candidate-manifest-sha256`
- `--gateway-schema`
- `--gateway-raw-sha256`
- `--gateway-canonical-sha256`
- `--engine-commit`
- `--offline-only`
- `--output`

The Engine adapter output must validate against
`engine-autoreply-v2-acceptance.v1.candidate.schema.json` and must contain all
fourteen named checks: Turn producer/negative vectors, Evidence
consumer/negative vectors, local V2 package, authorization V2, ledger
separation, execution-time revalidation, versioned rate policy, Kill Switch,
Sender binding, Receipt binding, UNKNOWN no-retry and cross-repository replay.

A PASS artifact must match the exact Engine commit, candidate manifest and
Gateway hashes and attest all four side effects as false: no Engine source
mutation by the verifier, no Runtime start, no PDD connection and no real send
attempt. It must also declare that it contains neither secrets nor customer
data. Missing, malformed, mismatched or incomplete evidence is FAIL.

The wrapper independently fingerprints the full Engine Git worktree before
and after adapter execution and sets the offline-only environment flag. Any
worktree change during acceptance fails even if the adapter claims otherwise.

The adapter protocol remains an `UNCOORDINATED_CANDIDATE`; it does not select
a repository contract version or change Gateway Wire 1.0. The current Engine
has no adapter, so the wrapper correctly returns
`ENGINE_ACCEPTANCE_ADAPTER_MISSING` with exit code 1.
