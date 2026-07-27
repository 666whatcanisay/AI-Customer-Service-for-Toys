import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import App from '../src/App.vue'
import { getAdminOverview, getHealth, listAiModules } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  getAdminOverview: vi.fn(),
  getHealth: vi.fn(),
  listAiModules: vi.fn(),
}))

describe('App', () => {
  it('groups the product navigation and identifies planning-only business entries', async () => {
    vi.mocked(getAdminOverview).mockResolvedValue({
      counts: { stores: 0, products: 0, skus: 0, faqs: 0, safety_rules: 0, sources: 0, conflicts: 0, import_batches: 0, suggestions: { submitted: 0, reviewing: 0, planned: 0, done: 0, rejected: 0 } },
      recent_imported_at: null, test_data_mode: true, production_usable: false,
    })
    vi.mocked(getHealth).mockResolvedValue({ status: 'ok', service: 'platform-backend', version: '0.1.0', request_id: 'health-1' })
    vi.mocked(listAiModules).mockResolvedValue([])

    const wrapper = mount(App, { global: { stubs: { RouterLink: { props: ['to'], template: '<a><slot /></a>' }, RouterView: { template: '<div />' } } } })
    await flushPromises()

    expect(wrapper.text()).toContain('客服运营')
    expect(wrapper.text()).toContain('商品知识中心')
    expect(wrapper.text()).toContain('AI 管理')
    expect(wrapper.text()).toContain('ERP 镜像（规划）')
    expect(wrapper.text()).toContain('退款风险（规划）')
    expect(wrapper.text()).toContain('正式权限与审计能力尚未启用')
  })
})
