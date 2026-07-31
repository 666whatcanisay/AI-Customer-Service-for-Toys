import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  getAdminOverview: vi.fn(),
  getHealth: vi.fn(),
  getAiControlCenterOverview: vi.fn()
}))

vi.mock('./api/client', () => apiMocks)

import App from './App.vue'

const createTestRouter = () => createRouter({
  history: createMemoryHistory(),
  routes: [
    '/overview', '/knowledge-center', '/knowledge-editor', '/knowledge-review', '/knowledge-gaps', '/import-center', '/store-management', '/customer-operations', '/experience-cases', '/ai-feedback-optimization-pool', '/ai-issues', '/suggestions',
    '/stores', '/products', '/faqs', '/safety-rules', '/sources', '/conflicts',
    '/ai-capabilities', '/ai-optimization-pool', '/knowledge-materials', '/knowledge-quality-pool',
    '/system-status', '/imports', '/test-data-packages'
  ].map((path) => ({ path, component: { template: '<div>运营页面内容</div>' } }))
})

describe('App product shell', () => {
  beforeEach(() => {
    apiMocks.getAdminOverview.mockResolvedValue({ test_data_mode: true, production_usable: false })
    apiMocks.getHealth.mockResolvedValue({ status: 'ok', service: 'platform', version: '0.1.0', request_id: 'request-1' })
    apiMocks.getAiControlCenterOverview.mockResolvedValue({
      service: { status: 'RUNNING', ready: true, modelConfigured: true },
    })
  })

  it('shows grouped navigation and only reveals technical details on demand', async () => {
    const router = createTestRouter()
    await router.push('/overview')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('AI客服平台')
    expect(wrapper.text()).toContain('首页')
    expect(wrapper.text()).toContain('AI运营概览')
    expect(wrapper.text()).toContain('客服运营')
    expect(wrapper.text()).toContain('商品知识中心')
    expect(wrapper.text()).toContain('店铺管理')
    expect(wrapper.text()).toContain('商品知识维护')
    expect(wrapper.text()).toContain('知识审核队列')
    expect(wrapper.text()).toContain('知识缺口')
    expect(wrapper.text()).toContain('知识资料')
    expect(wrapper.text()).toContain('FAQ管理')
    expect(wrapper.text()).toContain('安全规则')
    expect(wrapper.text()).toContain('导入中心')
    expect(wrapper.text()).toContain('AI问题中心')
    expect(wrapper.text()).toContain('后续能力')
    expect(wrapper.text()).not.toContain('Stores')
    expect(wrapper.text()).not.toContain('Products and SKUs')
    expect(wrapper.text()).not.toContain('Source evidence')
    expect(wrapper.text()).not.toContain('SHA')
    expect(wrapper.get('[data-testid="admin-service-statuses"]').text()).toContain('平台 可用')
    expect(wrapper.get('[data-testid="admin-service-statuses"]').text()).toContain('AI 可用')
    expect(wrapper.get('[data-testid="admin-service-statuses"]').text()).toContain('客服 未检测')
    expect(wrapper.text()).toContain('内部生产就绪')
    expect(wrapper.text()).toContain('AI-CS V1.0.0 已进入内部生产使用')
    expect(wrapper.find('[data-testid="admin-technical-details"]').exists()).toBe(false)

    await wrapper.get('[data-testid="admin-technical-toggle"]').trigger('click')
    expect(wrapper.get('[data-testid="admin-technical-details"]').text()).toContain('Git Commit')
    expect(wrapper.get('[data-testid="admin-technical-details"]').text()).toContain('客服入口未检测')
  })
})
