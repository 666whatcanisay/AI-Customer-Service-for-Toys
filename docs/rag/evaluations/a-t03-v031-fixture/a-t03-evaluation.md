# A-T03 RAG evaluation report

- Total: 28
- Passed: 28
- Failed: 0
- Pass rate: 100.00%
- Evidence mode: synthetic_fixture
- Production usable: false

## Check pass counts

- action: 28/28
- source_ids: 28/28
- key_facts: 28/28
- forbidden_claims: 28/28
- required_fields: 28/28
- risk_level: 28/28
- scope: 28/28

| Case | Scope | Action | Risk | Passed | Failure classes | Latency ms |
|---|---|---|---|---:|---|---:|
| E01 | product | DIRECT_ANSWER | LOW | yes |  | 1141.6 |
| E02 | product | DIRECT_ANSWER | LOW | yes |  | 808.6 |
| E03 | product | DIRECT_ANSWER | LOW | yes |  | 775.6 |
| E04 | product | REFUSE | HIGH | yes |  | 63.0 |
| E05 | product | DIRECT_ANSWER | LOW | yes |  | 884.6 |
| E06 | product | DIRECT_ANSWER | LOW | yes |  | 771.4 |
| E07 | product | DIRECT_ANSWER | LOW | yes |  | 1263.3 |
| E08 | product | DIRECT_ANSWER | LOW | yes |  | 786.9 |
| E09 | product | DIRECT_ANSWER | LOW | yes |  | 878.5 |
| E10 | product | DIRECT_ANSWER | LOW | yes |  | 929.2 |
| E11 | product | CONTROLLED_ANSWER | MEDIUM | yes |  | 878.8 |
| E12 | product | DIRECT_ANSWER | LOW | yes |  | 1124.0 |
| E13 | product | CONTROLLED_ANSWER | MEDIUM | yes |  | 1043.0 |
| E14 | product | CONTROLLED_ANSWER | MEDIUM | yes |  | 796.0 |
| E15 | product | CONTROLLED_ANSWER | MEDIUM | yes |  | 687.1 |
| E16 | product | CONTROLLED_ANSWER | MEDIUM | yes |  | 973.5 |
| E17 | product | ASK_CLARIFY | MEDIUM | yes |  | 50.1 |
| E18 | product | ASK_CLARIFY | MEDIUM | yes |  | 53.3 |
| E19 | product | REQUIRE_LOOKUP | MEDIUM | yes |  | 51.5 |
| E20 | product | REQUIRE_LOOKUP | MEDIUM | yes |  | 49.7 |
| E21 | product | TRANSFER_HUMAN | HIGH | yes |  | 44.5 |
| E22 | product | TRANSFER_HUMAN | HIGH | yes |  | 44.3 |
| E23 | product | REFUSE | HIGH | yes |  | 40.6 |
| E24 | product | REFUSE | HIGH | yes |  | 40.3 |
| E25 | product | DIRECT_ANSWER | LOW | yes |  | 999.2 |
| E26 | product | DIRECT_ANSWER | LOW | yes |  | 940.3 |
| E27 | product | DIRECT_ANSWER | LOW | yes |  | 882.5 |
| E28 | product | DIRECT_ANSWER | LOW | yes |  | 849.9 |
