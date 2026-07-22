# A-T03 RAG evaluation report

- Total: 28
- Passed: 0
- Failed: 28
- Pass rate: 0.00%
- Evidence mode: live_c_api
- Production usable: false

## Check pass counts

- action: 19/28
- source_ids: 19/28
- key_facts: 1/28
- forbidden_claims: 28/28
- required_fields: 2/28
- risk_level: 18/28
- scope: 28/28

| Case | Scope | Action | Risk | Passed | Failure classes | Latency ms |
|---|---|---|---|---:|---|---:|
| CASE-PDD-SM-001 | product | DIRECT_ANSWER | LOW | no | model, rule | 1389.0 |
| CASE-PDD-SM-002 | product | CONTROLLED_ANSWER | MEDIUM | no | model, retrieval, rule | 1044.4 |
| CASE-PDD-SM-003 | product | CONTROLLED_ANSWER | MEDIUM | no | model, rule | 1348.5 |
| CASE-PDD-SM-004 | product | DIRECT_ANSWER | LOW | no | model, rule | 1033.9 |
| CASE-PDD-SM-005 | product | CONTROLLED_ANSWER | MEDIUM | no | model, rule | 1006.7 |
| CASE-PDD-SM-006 | product | CONTROLLED_ANSWER | LOW | no | rule | 851.5 |
| CASE-PDD-SM-007 | product | ASK_CLARIFY | HIGH | no | model, rule | 73.2 |
| CASE-PDD-SM-008 | product | DIRECT_ANSWER | LOW | no | model, rule | 917.7 |
| CASE-PDD-SM-009 | product | DIRECT_ANSWER | LOW | no | model, retrieval, rule | 1173.8 |
| CASE-PDD-SM-010 | product | CONTROLLED_ANSWER | MEDIUM | no | model, rule | 1050.4 |
| CASE-PDD-SM-011 | product | CONTROLLED_ANSWER | MEDIUM | no | model, retrieval, rule | 1221.9 |
| CASE-PDD-SM-012 | product | CONTROLLED_ANSWER | MEDIUM | no | model, rule | 1625.1 |
| CASE-PDD-SM-013 | product | DIRECT_ANSWER | LOW | no | model, rule | 911.3 |
| CASE-PDD-SM-014 | product | CONTROLLED_ANSWER | LOW | no | model, rule | 1149.5 |
| CASE-PDD-SM-015 | store | TRANSFER_HUMAN | HIGH | no | model, rule | 68.3 |
| CASE-PDD-SM-016 | store | REQUIRE_LOOKUP | HIGH | no | model, rule | 59.6 |
| CASE-PDD-SM-017 | store | TRANSFER_HUMAN | HIGH | no | model, rule | 61.9 |
| CASE-PDD-SM-018 | store | REQUIRE_LOOKUP | HIGH | no | model, rule | 60.9 |
| CASE-PDD-SM-019 | product | REFUSE | HIGH | no | model, retrieval, rule | 72.6 |
| CASE-PDD-SM-020 | product | DIRECT_ANSWER | LOW | no | model, rule | 851.4 |
| CASE-PDD-SM-021 | product | CONTROLLED_ANSWER | MEDIUM | no | model, retrieval, rule | 1875.7 |
| CASE-PDD-SM-022 | product | CONTROLLED_ANSWER | MEDIUM | no | model, retrieval, rule | 1843.5 |
| CASE-PDD-SM-023 | product | CONTROLLED_ANSWER | MEDIUM | no | model, retrieval, rule | 1139.1 |
| CASE-PDD-SM-024 | product | TRANSFER_HUMAN | HIGH | no | model, retrieval, rule | 74.7 |
| CASE-PDD-SM-025 | store | REQUIRE_LOOKUP | HIGH | no | model, rule | 84.3 |
| CASE-PDD-SM-026 | product | CONTROLLED_ANSWER | MEDIUM | no | model, retrieval, rule | 1816.8 |
| CASE-PDD-SM-027 | product | DIRECT_ANSWER | LOW | no | model, rule | 1783.8 |
| CASE-PDD-SM-028 | product | REQUIRE_LOOKUP | HIGH | no | model, rule | 83.2 |
