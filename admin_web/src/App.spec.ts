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
    localStorage.clear()
    apiMocks.getAdminOverview.mockResolvedValue({ test_data_mode: true, production_usable: false })
    apiMocks.getHealth.mockResolvedValue({ status: 'ok', service: 'platform', version: '0.1.0', request_id: 'request-1' })
    apiMocks.getAiControlCenterOverview.mockResolvedValue({
      service: { status: 'RUNNING', ready: true, modelConfigured: true },
    })
  })

  it('defaults to six simple navigation entries and only reveals technical details on demand', async () => {
    const router = createTestRouter()
    await router.push('/overview')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('AI客服平台')
    expect(wrapper.findAll('[data-testid="simple-navigation-item"]')).toHaveLength(6)
    expect(wrapper.text()).toContain('运营工作台')
    expect(wrapper.text()).toContain('商品')
    expect(wrapper.text()).toContain('知识')
    expect(wrapper.text()).toContain('导入')
    expect(wrapper.text()).toContain('客服运营')
    expect(wrapper.text()).toContain('AI状态')
    expect(wrapper.find('[data-testid="advanced-navigation-label"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="advanced-navigation-item"]')).toHaveLength(0)
    expect(wrapper.text()).not.toContain('手工补充知识')
    expect(wrapper.text()).not.toContain('资料上传与审核')
    expect(wrapper.text()).not.toContain('后续能力')
    expect(wrapper.get('[data-testid="navigation-mode-simple"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.text()).toContain('模式只改变导航显示，不改变页面权限')
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

  it('shows every former navigation destination in advanced mode and persists the display preference', async () => {
    const router = createTestRouter()
    await router.push('/overview')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    await wrapper.get('[data-testid="navigation-mode-advanced"]').trigger('click')

    expect(wrapper.findAll('[data-testid="simple-navigation-item"]')).toHaveLength(6)
    expect(wrapper.findAll('[data-testid="advanced-navigation-group"]')).toHaveLength(3)
    expect(wrapper.findAll('[data-testid="advanced-navigation-item"]')).toHaveLength(8)
    expect(wrapper.get('[data-testid="advanced-navigation-label"]').text()).toBe('高级功能')
    expect(wrapper.text()).toContain('知识治理')
    expect(wrapper.text()).toContain('运营复盘')
    expect(wrapper.text()).toContain('系统诊断')
    expect(wrapper.text()).toContain('手工补充知识')
    expect(wrapper.text()).toContain('资料上传与审核')
    expect(wrapper.text()).toContain('知识审核队列')
    expect(wrapper.text()).toContain('知识缺口')
    expect(wrapper.text()).toContain('FAQ管理')
    expect(wrapper.text()).toContain('安全规则')
    expect(wrapper.text()).toContain('AI问题中心')
    expect(wrapper.text()).toContain('服务状态')
    expect(wrapper.text()).toContain('后续能力')
    expect(localStorage.getItem('ai-cs-admin-navigation-mode-v1')).toBe('advanced')

    wrapper.unmount()
    const restored = mount(App, { global: { plugins: [router] } })
    await flushPromises()
    expect(restored.get('[data-testid="navigation-mode-advanced"]').attributes('aria-pressed')).toBe('true')
    expect(restored.findAll('[data-testid="advanced-navigation-item"]')).toHaveLength(8)
  })
})
