import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import OperationsOverviewView from '../src/views/OperationsOverviewView.vue'
import {
  getAdminOverview,
  getHealth,
  listAiFeedbackAnalysisResults,
  listKnowledgeMaterials,
  listKnowledgeQualityAssessments,
} from '../src/api/client'

vi.mock('../src/api/client', () => ({
  getAdminOverview: vi.fn(),
  getHealth: vi.fn(),
  listKnowledgeMaterials: vi.fn(),
  listKnowledgeQualityAssessments: vi.fn(),
  listAiFeedbackAnalysisResults: vi.fn(),
  apiErrorMessage: vi.fn(() => '运营概览请求失败'),
}))

const mockedOverview = vi.mocked(getAdminOverview)
const mockedHealth = vi.mocked(getHealth)
const mockedMaterials = vi.mocked(listKnowledgeMaterials)
const mockedQuality = vi.mocked(listKnowledgeQualityAssessments)
const mockedFeedback = vi.mocked(listAiFeedbackAnalysisResults)

describe('OperationsOverviewView', () => {
  beforeEach(() => {
    mockedOverview.mockReset()
    mockedHealth.mockReset()
    mockedMaterials.mockReset()
    mockedQuality.mockReset()
    mockedFeedback.mockReset()
  })

  it('renders API-backed C facts and marks a failed native dataset as unavailable instead of zero', async () => {
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
    mockedMaterials.mockResolvedValue({ items: [], total: 4, page: 1, size: 1 })
    mockedQuality.mockRejectedValue(new Error('quality unavailable'))
    mockedFeedback.mockResolvedValue({ items: [], total: 3 })

    const wrapper = mount(OperationsOverviewView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    expect(wrapper.text()).toContain('18')
    expect(wrapper.text()).toContain('4')
    expect(wrapper.text()).toContain('暂无法读取')
    expect(wrapper.text()).toContain('AI 控制中心')
    expect(wrapper.find('.service-status').text()).toContain('C 平台')
  })
})
