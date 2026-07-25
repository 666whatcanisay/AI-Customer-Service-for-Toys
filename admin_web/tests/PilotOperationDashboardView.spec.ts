import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import PilotOperationDashboardView from '../src/views/PilotOperationDashboardView.vue'
import { getPilotOperationDashboard } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  getPilotOperationDashboard: vi.fn(),
  apiErrorMessage: vi.fn(() => 'Pilot dashboard request failed'),
}))

const mockedDashboard = vi.mocked(getPilotOperationDashboard)

describe('PilotOperationDashboardView', () => {
  beforeEach(() => mockedDashboard.mockReset())

  it('renders API-backed pilot counts, question ranks, and the non-official report warning', async () => {
    mockedDashboard.mockResolvedValue({
      generated_at: '2026-07-25T08:00:00Z', data_mode: 'TEST_OR_PILOT', official_operation_report: false,
      ai_call_measurement: 'CASE_AI_ANSWER_PROXY',
      today: { ai_call_count: 8, case_submission_count: 5, pending_review_count: 3, approved_case_count: 2, evaluated_case_count: 1 },
      experience_cases: { new: 2, reviewing: 1, approved: 2, evaluated: 1 },
      frequent_questions: [{ question: 'What age range is appropriate?', case_count: 4 }],
    })
    const wrapper = mount(PilotOperationDashboardView)
    await flushPromises()

    expect(wrapper.text()).toContain('Test / pilot data only.')
    expect(wrapper.text()).toContain('AI calls')
    expect(wrapper.text()).toContain('8')
    expect(wrapper.text()).toContain('What age range is appropriate?')
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
  })
})
