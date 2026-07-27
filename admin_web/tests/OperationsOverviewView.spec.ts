import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import OperationsOverviewView from '../src/views/OperationsOverviewView.vue'
import { getAdminOperationsToday, getHealth, listAiModules } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  getAdminOperationsToday: vi.fn(),
  getHealth: vi.fn(),
  listAiModules: vi.fn(),
  apiErrorMessage: vi.fn(() => 'Could not load operations snapshot'),
}))

const mockedOperations = vi.mocked(getAdminOperationsToday)
const mockedHealth = vi.mocked(getHealth)
const mockedModules = vi.mocked(listAiModules)

describe('OperationsOverviewView', () => {
  beforeEach(() => {
    mockedOperations.mockReset()
    mockedHealth.mockReset()
    mockedModules.mockReset()
  })

  it('renders one API-backed UTC-day snapshot and does not turn unavailable AI into a metric', async () => {
    mockedOperations.mockResolvedValue({
      today: {
        generated_at: '2026-07-27T10:00:00Z', window_start: '2026-07-27T00:00:00Z', window_end: '2026-07-27T10:00:00Z',
        ai_request_count: 8, direct_adoption_count: 2, edited_adoption_count: 2, not_adopted_count: 3, adoption_rate: 0.5,
        experience_case_submission_count: 4, ai_feedback_submission_count: 2, completed_ai_analysis_count: 1,
      },
      work_queue: { pending_experience_review_count: 3, pending_ai_analysis_count: 1, open_knowledge_conflict_count: 5 },
      knowledge: { store_count: 1, product_count: 5, sku_count: 18, faq_count: 16, safety_rule_count: 8, recent_imported_at: '2026-07-25T08:00:00Z' },
      test_data_mode: true, production_usable: false,
    })
    mockedHealth.mockResolvedValue({ status: 'ok', service: 'platform-backend', version: '0.1.0', request_id: 'health-1' })
    mockedModules.mockRejectedValue(new Error('A unavailable'))

    const wrapper = mount(OperationsOverviewView, {
      global: { stubs: { RouterLink: { props: ['to'], template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('今日 AI 使用')
    expect(wrapper.text()).toContain('8 次')
    expect(wrapper.text()).toContain('50.0%')
    expect(wrapper.text()).toContain('今日案例')
    expect(wrapper.text()).toContain('4 件')
    expect(wrapper.text()).toContain('待审核经验案例')
    expect(wrapper.text()).toContain('平台可用 · AI 待连接')
    expect(mockedOperations).toHaveBeenCalledTimes(1)
  })

  it('labels zero-valued real sources as insufficient samples rather than a fabricated operating result', async () => {
    mockedOperations.mockResolvedValue({
      today: {
        generated_at: '2026-07-27T10:00:00Z', window_start: '2026-07-27T00:00:00Z', window_end: '2026-07-27T10:00:00Z',
        ai_request_count: 0, direct_adoption_count: 0, edited_adoption_count: 0, not_adopted_count: 0, adoption_rate: 0,
        experience_case_submission_count: 0, ai_feedback_submission_count: 0, completed_ai_analysis_count: 0,
      },
      work_queue: { pending_experience_review_count: 0, pending_ai_analysis_count: 0, open_knowledge_conflict_count: 0 },
      knowledge: { store_count: 0, product_count: 0, sku_count: 0, faq_count: 0, safety_rule_count: 0, recent_imported_at: null },
      test_data_mode: true, production_usable: false,
    })
    mockedHealth.mockRejectedValue(new Error('offline'))
    mockedModules.mockRejectedValue(new Error('offline'))

    const wrapper = mount(OperationsOverviewView, {
      global: { stubs: { RouterLink: { props: ['to'], template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('样本不足')
    expect(wrapper.text()).toContain('待启用')
    expect(wrapper.text()).toContain('平台待连接 · AI 待连接')
  })
})
