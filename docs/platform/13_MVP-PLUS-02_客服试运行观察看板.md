# MVP-PLUS-02 customer-service pilot operations dashboard

Status: C-line implementation and local verification passed on `agent/platform-mvp-plus-02`. Draft PR #32 targets `agent/platform-mvp-plus-01` because the experience-case persistence in parent Draft PR #30 is the required data source.

## Purpose and boundary

This is an observation-only internal-test/pilot dashboard. It is not a new business workflow, a formal operations report, production telemetry, or an authorization system. It does not create/update cases, change review state, change prompts, publish knowledge, train a model, send customer messages, modify orders, or write ERP data.

## C-owned API

`GET /api/v1/admin/pilot-operation-dashboard` reads existing `CustomerExperienceCase` rows and returns:

- today's case submissions;
- today's case-linked AI-answer count as the explicitly named `CASE_AI_ANSWER_PROXY` for AI calls;
- pending review (`NEW` plus `REVIEWING`), approved, and evaluated case counts;
- all-case counts for `NEW`, `REVIEWING`, `APPROVED`, and `EVALUATED`;
- the ten most frequent exact question texts by case count.

The response sets `data_mode=TEST_OR_PILOT` and `official_operation_report=false`. The service day is UTC because the local baseline has no frozen operational-timezone configuration. Frequent questions use only exact string grouping, with no semantic clustering, model inference, or complex analytics.

## Privacy and reporting caveat

The dashboard reads case question text only for the C internal-test administration page and does not log it. `v1-reminder-only` still is not automatic redaction, and no formal authorization is present. Do not load real customer content or treat the numbers as production operational telemetry before separate privacy, authorization, retention, audit, and reporting definitions are approved.
