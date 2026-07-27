import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AiFeedbackOptimizationPoolView from '../src/views/AiFeedbackOptimizationPoolView.vue'
import { listAiFeedbackAnalysisResults } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  listAiFeedbackAnalysisResults: vi.fn(),
  apiErrorMessage: vi.fn(() => 'AI feedback analysis request failed'),
}))

const mockedList = vi.mocked(listAiFeedbackAnalysisResults)

describe('AiFeedbackOptimizationPoolView', () => {
  beforeEach(() => mockedList.mockReset())

  it('renders completed analysis evidence as read-only detail without action controls', async () => {
    mockedList.mockResolvedValue({
      items: [{
        feedback_id: 'ARF-TEST-1', revision: 1, content_hash: 'sha256:test', feedback_type: 'MISSING_INFO',
        analysis_run_id: 'AQR-TEST-1', analysis_status: 'ANALYZED', model_version: 'model-v1',
        prompt_version: 'prompt-v1', analysis: { summary: 'Missing lower-age safety limit.' },
        suggestions: [{ category: 'PROMPT_HYPOTHESIS' }], created_at: '2026-07-27T08:00:00Z',
        question: 'What age is this toy for?', ai_answer: 'Ages six to twelve.',
        final_answer: 'Ages six to twelve, with adult supervision.',
      }],
      total: 1,
    })

    const wrapper = mount(AiFeedbackOptimizationPoolView)
    await flushPromises()

    expect(wrapper.text()).toContain('What age is this toy for?')
    expect(wrapper.text()).toContain('信息缺失')
    await wrapper.get('.link-button').trigger('click')
    expect(wrapper.text()).toContain('Missing lower-age safety limit.')
    expect(wrapper.text()).toContain('sha256:test')
    expect(wrapper.find('.detail button').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Publish knowledge')
  })
})
