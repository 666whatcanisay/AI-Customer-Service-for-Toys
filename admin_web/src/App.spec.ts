import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  getAdminOverview: vi.fn(),
  getHealth: vi.fn(),
  getAiRuntimeStatus: vi.fn()
}))

vi.mock('./api/client', () => apiMocks)

import App from './App.vue'

const createTestRouter = () => createRouter({
  history: createMemoryHistory(),
  routes: [
    '/overview', '/experience-cases', '/ai-feedback-optimization-pool', '/suggestions',
    '/stores', '/products', '/faqs', '/safety-rules', '/sources', '/conflicts',
    '/ai-capabilities', '/ai-optimization-pool', '/system-status', '/imports', '/test-data-packages'
  ].map((path) => ({ path, component: { template: '<div>运营页面内容</div>' } }))
})

describe('App product shell', () => {
  beforeEach(() => {
    apiMocks.getAdminOverview.mockResolvedValue({ test_data_mode: true, production_usable: false })
    apiMocks.getHealth.mockResolvedValue({ status: 'ok', service: 'platform', version: '0.1.0', request_id: 'request-1' })
    apiMocks.getAiRuntimeStatus.mockResolvedValue({ ready: true, modelConfigured: true, initializationError: null })
  })

  it('shows grouped navigation and only reveals technical details on demand', async () => {
    const router = createTestRouter()
    await router.push('/overview')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('AI 客服平台')
    expect(wrapper.text()).toContain('客服运营')
    expect(wrapper.text()).toContain('商品资料')
    expect(wrapper.text()).toContain('AI 控制中心')
    expect(wrapper.text()).toContain('业务扩展 · 规划中')
    expect(wrapper.get('[data-testid="admin-service-statuses"]').text()).toContain('平台 可用')
    expect(wrapper.get('[data-testid="admin-service-statuses"]').text()).toContain('AI 可用')
    expect(wrapper.get('[data-testid="admin-service-statuses"]').text()).toContain('客服 未接入检测')
    expect(wrapper.text()).toContain('测试环境')
    expect(wrapper.find('[data-testid="admin-technical-details"]').exists()).toBe(false)

    await wrapper.get('[data-testid="admin-technical-toggle"]').trigger('click')
    expect(wrapper.get('[data-testid="admin-technical-details"]').text()).toContain('Git Commit')
    expect(wrapper.get('[data-testid="admin-technical-details"]').text()).toContain('未接入检测')
  })
})
