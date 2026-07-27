import { describe, expect, it } from 'vitest'
import { RagAdapterError } from './ragAdapter'
import { adaptAiOperationsOverviewResponse, adaptAiQualityBaselineResponse } from './aiControlCenterAdapter'

describe('AI control center V2 adapters', () => {
  it('adapts the published read-only operational snapshot without inventing Badcase counts', () => {
    const snapshot = adaptAiOperationsOverviewResponse({
      success: true,
      message: 'AI operations overview',
      data: {
        schema_version: 'ai-operations.v1', generated_at: '2026-07-27T09:00:00Z', raw_content_exposed: false,
        answer_volume: { status: 'AVAILABLE', metrics_scope: 'since_start', processed_request_count: 5, direct_answer_count: 3, controlled_answer_count: 1, transfer_human_count: 1, other_outcome_count: 0, durable: false, explanation: 'process aggregate' },
        answer_quality: { status: 'AVAILABLE', evaluation_id: 'a-t03-v031-live', evaluated_case_count: 28, passed_case_count: 19, pass_rate_percent: 67.86, measured_at: 'NOT_AVAILABLE', explanation: 'saved evaluation' },
        knowledge_coverage: { status: 'AVAILABLE', indexed_chunk_count: 47, source_attribution_checked_case_count: 28, source_attribution_pass_rate_percent: 75, explanation: 'coverage aggregate' },
        badcase: { status: 'NOT_AVAILABLE', categories: [{ category: 'FACT_ERROR', count: null }, { category: 'MISSING_INFO', count: null }, { category: 'STYLE_ISSUE', count: null }, { category: 'RISK_ISSUE', count: null }], explanation: 'No published aggregate.', raw_content_exposed: false },
        model_status: { status: 'CONFIGURED', provider: 'ollama', model_version: 'qwen3.5:9b', service_ready: true, availability_probed: false, average_latency_ms: null, error_count: 0, last_error_category: null, explanation: 'configured only' },
        external_data: [{ source_id: 'feedback', status: 'NOT_CONFIGURED', read_attempted: false, explanation: 'not configured', operator_action: 'configure manually' }],
        notices: [{ code: 'MODEL_CONFIGURED', severity: 'INFO', message: 'configured', operator_action: 'observe', automatic_action_taken: false }]
      }
    })

    expect(snapshot.modelStatus.modelVersion).toBe('qwen3.5:9b')
    expect(snapshot.answerQuality.passRatePercent).toBe(67.86)
    expect(snapshot.badcase.categories.map((item) => item.count)).toEqual([null, null, null, null])
    expect(snapshot.rawContentExposed).toBe(false)
  })

  it('adapts the saved live evaluation summary and rejects unsafe content flags', () => {
    const response = {
      success: true,
      message: 'AI quality baseline diagnosis',
      data: {
        schema_version: 'ai-quality-baseline.v1', status: 'AVAILABLE', raw_content_exposed: false, model_or_prompt_changed: false,
        summary: {
          evaluation_id: 'a-t03-v031-live', executed_at: 'NOT_AVAILABLE', dataset_version: 'NOT_AVAILABLE', total_case_count: 28, passed_case_count: 19, failed_case_count: 9, pass_rate_percent: 67.86,
          checks: [{ check: 'action', passed_case_count: 28 }, { check: 'source_ids', passed_case_count: 21 }, { check: 'key_facts', passed_case_count: 23 }, { check: 'forbidden_claims', passed_case_count: 28 }, { check: 'required_fields', passed_case_count: 28 }, { check: 'risk_level', passed_case_count: 27 }, { check: 'scope', passed_case_count: 28 }]
        },
        failed_cases: [{ case_id: 'CASE-PDD-SM-001', categories: ['DATA_PROBLEM'], evaluator_failure_classes: ['metadata_loss'], failed_checks: ['source_ids'], expected_source_count: 1, missing_expected_source_count: 1, expected_fact_count: 1, suggested_verifications: ['Verify test data metadata.'] }],
        cause_findings: [{ category: 'DATA_PROBLEM', affected_case_count: 9, evidence: 'DIRECT_EVALUATOR_SIGNAL', conclusion: 'metadata is incomplete', recommended_verification: 'Check test metadata', automatic_change_allowed: false }],
        recommendations: [{ priority: 'P0', category: 'DATA_PROBLEM', recommendation: 'Repair data metadata.', rationale: 'Direct evaluator signals.', automatic_change_allowed: false }]
      }
    }

    expect(adaptAiQualityBaselineResponse(response).summary?.failedCaseCount).toBe(9)
    expect(() => adaptAiQualityBaselineResponse({ ...response, data: { ...response.data, raw_content_exposed: true } })).toThrow(RagAdapterError)
  })
})
