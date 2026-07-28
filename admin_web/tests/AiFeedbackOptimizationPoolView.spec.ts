import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AiFeedbackOptimizationPoolView from '../src/views/AiFeedbackOptimizationPoolView.vue'
import { listAiFeedbackAnalysisResults } from '../src/api/client'

vi.mock('../src/api/client', () => ({ listAiFeedbackAnalysisResults: vi.fn(), apiErrorMessage: vi.fn(() => '分析服务暂不可用') }))
const mockedList = vi.mocked(listAiFeedbackAnalysisResults)
const analysis = { summary: '缺少适用年龄说明。', ai_human_difference: '人工回复补充了监护提醒。', risk_judgement: '需要补充安全信息。' }

describe('AiFeedbackOptimizationPoolView', () => {
  beforeEach(() => mockedList.mockReset())
  it('renders Chinese evidence summary and keeps raw JSON folded', async () => {
    mockedList.mockResolvedValue({ items: [{ feedback_id: 'ARF-TEST-1', revision: 1, content_hash: 'sha256:test', feedback_type: 'MISSING_INFO', analysis_run_id: 'AQR-TEST-1', analysis_status: 'ANALYZED', model_version: 'model-v1', prompt_version: 'prompt-v1', analysis, suggestions: [{ action: '补充适用年龄和监护提醒。' }], created_at: '2026-07-27T08:00:00Z', question: '适用年龄是多少？', ai_answer: '6 到 12 岁。', final_answer: '6 到 12 岁，建议成人陪同。' }], total: 1 })
    const wrapper = mount(AiFeedbackOptimizationPoolView); await flushPromises()
    expect(wrapper.text()).toContain('客户问题'); expect(wrapper.text()).toContain('缺少适用年龄说明。'); expect(wrapper.find('pre').exists()).toBe(false)
    await wrapper.get('.link-button').trigger('click'); expect(wrapper.text()).toContain('AI 与人工差异'); expect(wrapper.text()).toContain('补充适用年龄和监护提醒。'); expect(wrapper.find('details').attributes('open')).toBeUndefined()
    await wrapper.get('.technical-details summary').trigger('click'); expect(wrapper.text()).toContain('sha256:test'); expect(wrapper.find('.detail button').exists()).toBe(false)
  })
})
