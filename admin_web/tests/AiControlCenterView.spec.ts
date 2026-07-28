import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AiControlCenterView from '../src/views/AiControlCenterView.vue'
import { getAdminOperationsToday, getHealth, listAiFeedbackAnalysisResults, listAiModules, listAiOptimizationCases } from '../src/api/client'

vi.mock('../src/api/client', () => ({ getAdminOperationsToday: vi.fn(), getHealth: vi.fn(), listAiFeedbackAnalysisResults: vi.fn(), listAiModules: vi.fn(), listAiOptimizationCases: vi.fn() }))
const operations = vi.mocked(getAdminOperationsToday); const health = vi.mocked(getHealth); const feedback = vi.mocked(listAiFeedbackAnalysisResults); const modules = vi.mocked(listAiModules); const evaluations = vi.mocked(listAiOptimizationCases)
const operationsData = { today: { generated_at: '2026-07-28T08:00:00Z', window_start: '2026-07-28T00:00:00Z', window_end: '2026-07-28T08:00:00Z', ai_request_count: 0, direct_adoption_count: 0, edited_adoption_count: 0, not_adopted_count: 0, adoption_rate: 0, experience_case_submission_count: 0, ai_feedback_submission_count: 0, completed_ai_analysis_count: 0 }, work_queue: { pending_experience_review_count: 0, pending_ai_analysis_count: 0, open_knowledge_conflict_count: 0 }, knowledge: { store_count: 0, product_count: 0, sku_count: 0, faq_count: 0, safety_rule_count: 0, recent_imported_at: null }, test_data_mode: true, production_usable: false }

describe('AiControlCenterView', () => {
  beforeEach(() => { operations.mockReset(); health.mockReset(); feedback.mockReset(); modules.mockReset(); evaluations.mockReset() })
  it('says the interface is available but has no display data when A returns no modules', async () => {
    operations.mockResolvedValue(operationsData); health.mockResolvedValue({ status: 'ok', service: 'platform', version: '0.1.0', request_id: 'health-1' }); modules.mockResolvedValue([]); feedback.mockResolvedValue({ items: [], total: 0 }); evaluations.mockResolvedValue({ items: [], page: 1, size: 20, total: 0 })
    const wrapper = mount(AiControlCenterView); await flushPromises(); expect(wrapper.text()).toContain('接口可用，暂无可展示数据'); expect(wrapper.text()).toContain('样本不足'); expect(wrapper.get('details').attributes('open')).toBeUndefined()
  })
})
