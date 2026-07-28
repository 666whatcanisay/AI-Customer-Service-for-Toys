import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AiOptimizationPoolView from '../src/views/AiOptimizationPoolView.vue'
import { listAiOptimizationCases } from '../src/api/client'

vi.mock('../src/api/client', () => ({ listAiOptimizationCases: vi.fn(), apiErrorMessage: vi.fn(() => '评测服务暂不可用') }))
const mockedList = vi.mocked(listAiOptimizationCases)

describe('AiOptimizationPoolView', () => {
  beforeEach(() => mockedList.mockReset())
  it('uses business summaries for evaluations and hides raw evidence by default', async () => {
    mockedList.mockResolvedValue({ items: [{ case_id: 'CEC-TEST-2', revision: 1, store_code: 'STORE-1', product_id: 'PRODUCT-1', sku_id: 'SKU-1', question: '适用年龄？', ai_answer: '6 岁以上。', final_answer: '6 岁以上，成人陪同。', feedback_type: 'CORRECTION', export_revision: 'CEC-TEST-2-r1-e1', content_hash: 'sha256:test', evaluation_status: 'EVALUATED', latest_evaluation_run_id: 'AEC-1', latest_evaluation: { evaluation_run_id: 'AEC-1', case_id: 'CEC-TEST-2', revision: 1, export_revision: 'CEC-TEST-2-r1-e1', evaluation_status: 'EVALUATED', model_version: 'model-v1', prompt_version: 'prompt-v1', result: { summary: '需要补充监护提醒。' }, suggestions: [{ action: '补充监护提醒。' }], recorded_at: '2026-07-25T08:00:00Z' } }], page: 1, size: 20, total: 1 })
    const wrapper = mount(AiOptimizationPoolView); await flushPromises(); expect(wrapper.text()).toContain('评测结论'); expect(wrapper.text()).toContain('需要补充监护提醒。'); expect(wrapper.find('pre').exists()).toBe(false)
    await wrapper.get('.link-button').trigger('click'); expect(wrapper.text()).toContain('建议动作'); expect(wrapper.find('details').attributes('open')).toBeUndefined()
  })
})
