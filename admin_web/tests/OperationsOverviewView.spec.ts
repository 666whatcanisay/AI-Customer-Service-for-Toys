import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import OperationsOverviewView from '../src/views/OperationsOverviewView.vue'
import { getAdminOverview, getAiKnowledgeStatistics, getAiRuntimeStatus, getHealth } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  getAdminOverview: vi.fn(), getHealth: vi.fn(), getAiRuntimeStatus: vi.fn(), getAiKnowledgeStatistics: vi.fn(),
  apiErrorMessage: vi.fn(() => 'Could not load overview'),
}))

const mockedOverview = vi.mocked(getAdminOverview)
const mockedHealth = vi.mocked(getHealth)
const mockedRuntime = vi.mocked(getAiRuntimeStatus)
const mockedKnowledge = vi.mocked(getAiKnowledgeStatistics)

describe('OperationsOverviewView', () => {
  beforeEach(() => {
    mockedOverview.mockReset(); mockedHealth.mockReset(); mockedRuntime.mockReset(); mockedKnowledge.mockReset()
  })

  it('renders API-backed counts and a real unavailable A state without fabricated data', async () => {
    mockedOverview.mockResolvedValue({
      counts: {
        stores: 1, products: 5, skus: 18, faqs: 16, safety_rules: 8, sources: 37,
        conflicts: 13, import_batches: 1,
        suggestions: { submitted: 2, reviewing: 1, planned: 0, done: 0, rejected: 0 },
      },
      recent_imported_at: '2026-07-25T08:00:00Z', test_data_mode: true, production_usable: false,
    })
    mockedHealth.mockResolvedValue({ status: 'ok', service: 'platform-backend', version: '0.1.0', request_id: 'health-1' })
    mockedRuntime.mockRejectedValue(new Error('A unavailable'))
    mockedKnowledge.mockRejectedValue(new Error('A unavailable'))

    const wrapper = mount(OperationsOverviewView, {
      global: { stubs: { RouterLink: { props: ['to'], template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('18')
    expect(wrapper.text()).toContain('13')
    expect(wrapper.text()).toContain('AI 服务不可读取')
    expect(wrapper.text()).toContain('AI 运行信息暂时不可读取')
  })
})
