import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CustomerEfficiencyDashboardView from '../src/views/CustomerEfficiencyDashboardView.vue'
import { getAdminCustomerEfficiencySummary } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  getAdminCustomerEfficiencySummary: vi.fn(),
  apiErrorMessage: vi.fn(() => 'Could not load customer efficiency'),
}))

const mockedSummary = vi.mocked(getAdminCustomerEfficiencySummary)

describe('CustomerEfficiencyDashboardView', () => {
  beforeEach(() => mockedSummary.mockReset())

  it('renders aggregate efficiency metrics and no employee ranking or performance view', async () => {
    mockedSummary.mockResolvedValue({
      summary_version: 'customer-efficiency.v1', generated_at: '2026-07-27T10:00:00Z',
      window_start: '2026-07-27T00:00:00Z', window_end: '2026-07-27T10:00:00Z',
      ai_request_count: 8, direct_adoption_count: 2, edited_adoption_count: 2,
      not_adopted_count: 3, adoption_rate: 0.5,
    })

    const wrapper = mount(CustomerEfficiencyDashboardView)
    await flushPromises()

    expect(wrapper.text()).toContain('AI 请求次数')
    expect(wrapper.text()).toContain('8')
    expect(wrapper.text()).toContain('50.0%')
    expect(wrapper.text()).toContain('customer-efficiency.v1')
    expect(wrapper.text()).toContain('不展示员工身份、排名或绩效评价')
  })
})
