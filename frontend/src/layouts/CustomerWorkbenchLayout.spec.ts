import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authSessionTestControl } from '@/auth/authSession'
import CustomerWorkbenchLayout from './CustomerWorkbenchLayout.vue'

const healthMocks = vi.hoisted(() => ({ rag: vi.fn(), platform: vi.fn() }))
vi.mock('@/api/ragClient', () => ({ ragClient: { getHealth: healthMocks.rag } }))
vi.mock('@/api/platformClient', () => ({ platformClient: { getHealth: healthMocks.platform } }))

const mountLayout = async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      '/', '/workspace', '/ai-chat', '/experience-cases', '/feedback', '/suggestions', '/suggestions/mine', '/store-selection'
    ].map((path) => ({ path, component: { template: '<div>页面内容</div>' } }))
  })
  await router.push('/')
  await router.isReady()
  return mount(CustomerWorkbenchLayout, { attachTo: document.body, global: { plugins: [router, ElementPlus] } })
}

describe('CustomerWorkbenchLayout', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    document.body.innerHTML = ''
    authSessionTestControl.setUser({
      id: '11111111-1111-4111-8111-111111111111', username: 'support.one',
      display_name: '小木', status: 'ACTIVE', roles: ['CUSTOMER_SERVICE'],
      permissions: ['workspace.access', 'ai.reply', 'feedback.submit'],
      stores: [{ id: 1, store_id: 1, store_code: 'PDD-SM', store_name: '玩趣乐园积木店', platform: 'pdd', is_default: false }],
      must_change_password: false, all_store_access: false,
      created_at: '2026-08-06T00:00:00Z', updated_at: '2026-08-06T00:00:00Z'
    })
    healthMocks.rag.mockResolvedValue({ ready: true })
    healthMocks.platform.mockResolvedValue({ status: 'ok' })
  })

  it('shows the unified product navigation, honest status labels and safety banner', async () => {
    const wrapper = await mountLayout()
    await flushPromises()
    expect(wrapper.get('nav').text()).toContain('首页')
    expect(wrapper.get('nav').text()).toContain('AI 客服')
    expect(wrapper.get('nav').text()).toContain('我的案例')
    expect(wrapper.get('nav').text()).toContain('问题反馈')
    expect(wrapper.text()).toContain('AI客服平台')
    expect(wrapper.get('[data-testid="global-system-status"]').text()).toContain('AI 可用')
    expect(wrapper.get('[data-testid="global-system-status"]').text()).toContain('平台 可用')
    expect(wrapper.get('[data-testid="global-system-status"]').text()).toContain('客服 当前页面')
    expect(wrapper.get('[data-testid="global-test-banner"]').text()).toContain('AI 生成建议须由客服确认后发送')
    expect(wrapper.text()).toContain('AI客服工作台')
    expect(wrapper.text()).toContain('AI 生成建议需人工确认')
    expect(wrapper.get('[data-testid="tester-summary"]').text()).toContain('小木')
    expect(wrapper.get('[data-testid="tester-summary"]').text()).toContain('玩趣乐园积木店')
    expect(wrapper.text()).not.toContain('测试工作台')
    expect(wrapper.text()).not.toContain('不是正式登录系统')
    expect(wrapper.find('[data-testid="product-technical-details"]').exists()).toBe(false)
    await wrapper.get('[data-testid="product-technical-toggle"]').trigger('click')
    expect(wrapper.get('[data-testid="product-technical-details"]').text()).toContain('Git Commit')
    wrapper.unmount()
  })

  it('uses the authenticated server identity and has no local identity editor', async () => {
    const wrapper = await mountLayout()
    await flushPromises()
    expect(document.body.textContent).not.toContain('设置客服工作台身份')
    expect(document.body.textContent).not.toContain('不是登录或权限认证')
    expect(wrapper.get('[data-testid="customer-logout"]').text()).toBe('退出')
    wrapper.unmount()
  })

  it('shows the test guide once for a known tester and records dismissal', async () => {
    const wrapper = await mountLayout()
    await flushPromises()

    expect(document.body.textContent).toContain('AI客服助手')
    expect(document.body.textContent).toContain('选择商品 / SKU')
    expect(document.body.textContent).toContain('人工确认后复制发送')
    expect(document.body.textContent).toContain('AI 建议需要人工确认')

    await wrapper.get('[data-testid="pilot-guide-start"]').trigger('click')
    await flushPromises()
    expect(localStorage.getItem('mumu-customer-workspace:pilot-guide-seen')).toBe('true')
    wrapper.unmount()
  })
})
