import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import OperationsOverviewView from '../src/views/OperationsOverviewView.vue'
import { getAdminCustomerEfficiencySummary, getAdminOverview, getHealth, listAdminExperienceCases, listAiFeedbackAnalysisResults, listAiModules } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  getAdminOverview: vi.fn(),
  getHealth: vi.fn(),
  listAiModules: vi.fn(),
  getAdminCustomerEfficiencySummary: vi.fn(),
  listAdminExperienceCases: vi.fn(),
  listAiFeedbackAnalysisResults: vi.fn(),
  apiErrorMessage: vi.fn(() => 'Could not load overview'),
}))

const mockedOverview = vi.mocked(getAdminOverview)
const mockedHealth = vi.mocked(getHealth)
const mockedModules = vi.mocked(listAiModules)
const mockedEfficiency = vi.mocked(getAdminCustomerEfficiencySummary)
const mockedCases = vi.mocked(listAdminExperienceCases)
const mockedIssues = vi.mocked(listAiFeedbackAnalysisResults)

describe('OperationsOverviewView', () => {
  beforeEach(() => {
    mockedOverview.mockReset()
    mockedHealth.mockReset()
    mockedModules.mockReset()
    mockedEfficiency.mockReset()
    mockedCases.mockReset()
    mockedIssues.mockReset()
  })

  it('renders API-backed operating data and marks missing AI connectivity without fabricated data', async () => {
    mockedOverview.mockResolvedValue({
      counts: {
        stores: 1, products: 5, skus: 18, faqs: 16, safety_rules: 8, sources: 37,
        conflicts: 13, import_batches: 1,
        suggestions: { submitted: 2, reviewing: 1, planned: 0, done: 0, rejected: 0 },
      },
      recent_imported_at: '2026-07-25T08:00:00Z',
      test_data_mode: true,
      production_usable: false,
    })
    mockedHealth.mockResolvedValue({ status: 'ok', service: 'platform-backend', version: '0.1.0', request_id: 'health-1' })
    mockedModules.mockRejectedValue(new Error('A unavailable'))
    mockedEfficiency.mockResolvedValue({ summary_version: 'customer-efficiency.v1', generated_at: '2026-07-27T10:00:00Z', window_start: '2026-07-27T00:00:00Z', window_end: '2026-07-27T10:00:00Z', ai_request_count: 8, direct_adoption_count: 2, edited_adoption_count: 2, not_adopted_count: 3, adoption_rate: 0.5 })
    mockedCases.mockResolvedValue({ items: [], page: 1, size: 1, total: 4 })
    mockedIssues.mockResolvedValue({ items: [], total: 2 })

    const wrapper = mount(OperationsOverviewView, {
      global: { stubs: { RouterLink: { props: ['to'], template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('客服效率')
    expect(wrapper.text()).toContain('50.0%')
    expect(wrapper.text()).toContain('案例数量')
    expect(wrapper.text()).toContain('4')
    expect(wrapper.text()).toContain('AI 服务状态')
    expect(wrapper.text()).toContain('待启用')
  })
})
