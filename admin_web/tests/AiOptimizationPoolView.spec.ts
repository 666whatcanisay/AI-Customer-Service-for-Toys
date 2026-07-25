import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AiOptimizationPoolView from '../src/views/AiOptimizationPoolView.vue'
import { listAiOptimizationCases } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  listAiOptimizationCases: vi.fn(),
  apiErrorMessage: vi.fn(() => 'Optimization-pool request failed'),
}))

const mockedList = vi.mocked(listAiOptimizationCases)

describe('AiOptimizationPoolView', () => {
  beforeEach(() => mockedList.mockReset())

  it('renders approved cases and their returned evaluation evidence without action controls', async () => {
    mockedList.mockResolvedValue({
      items: [{
        case_id: 'CEC-TEST-2', revision: 1, store_code: 'STORE-1', product_id: 'PRODUCT-1', sku_id: 'SKU-1',
        question: 'Question', ai_answer: 'AI answer', final_answer: 'Final answer', feedback_type: 'CORRECTION',
        export_revision: 'CEC-TEST-2-r1-e1', content_hash: 'sha256:test', evaluation_status: 'EVALUATED',
        latest_evaluation_run_id: 'AEC-1', latest_evaluation: {
          evaluation_run_id: 'AEC-1', case_id: 'CEC-TEST-2', revision: 1, export_revision: 'CEC-TEST-2-r1-e1',
          evaluation_status: 'EVALUATED', model_version: 'model-v1', prompt_version: 'prompt-v1',
          result: { outcome: 'NEEDS_REVIEW' }, suggestions: [{ category: 'PROMPT_HYPOTHESIS' }],
          recorded_at: '2026-07-25T08:00:00Z',
        },
      }],
      page: 1, size: 20, total: 1,
    })
    const wrapper = mount(AiOptimizationPoolView)
    await flushPromises()

    expect(wrapper.text()).toContain('CEC-TEST-2')
    await wrapper.get('.link-button').trigger('click')
    expect(wrapper.text()).toContain('NEEDS_REVIEW')
    expect(wrapper.find('.detail button').exists()).toBe(false)
  })
})
