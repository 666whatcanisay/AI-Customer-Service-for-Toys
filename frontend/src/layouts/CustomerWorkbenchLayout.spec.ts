import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TESTER_IDENTITY_STORAGE_KEY } from '@/workspace/testerIdentity'
import CustomerWorkbenchLayout from './CustomerWorkbenchLayout.vue'

const healthMocks = vi.hoisted(() => ({ rag: vi.fn(), platform: vi.fn() }))
vi.mock('@/api/ragClient', () => ({ ragClient: { getHealth: healthMocks.rag } }))
vi.mock('@/api/platformClient', () => ({ platformClient: { getHealth: healthMocks.platform } }))

const mountLayout = async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      '/', '/ai-chat', '/experience-cases', '/feedback', '/suggestions', '/suggestions/mine'
    ].map((path) => ({ path, component: { template: '<div>页面内容</div>' } }))
  })
  await router.push('/')
  await router.isReady()
  return mount(CustomerWorkbenchLayout, { attachTo: document.body, global: { plugins: [router, ElementPlus] } })
}

describe('CustomerWorkbenchLayout', () => {
  beforeEach(() => {
    localStorage.clear()
    document.body.innerHTML = ''
    healthMocks.rag.mockResolvedValue({ ready: true })
    healthMocks.platform.mockResolvedValue({ status: 'ok' })
  })

  it('shows the unified product navigation, honest status labels and safety banner', async () => {
    localStorage.setItem(TESTER_IDENTITY_STORAGE_KEY, JSON.stringify({ reporterId: 'TESTER-ONE', reporterName: '小木', defaultStoreCode: 'PDD-SM' }))
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
    expect(wrapper.get('[data-testid="global-test-banner"]').text()).toContain('禁止填写真实客户隐私')
    expect(wrapper.find('[data-testid="product-technical-details"]').exists()).toBe(false)
    await wrapper.get('[data-testid="product-technical-toggle"]').trigger('click')
    expect(wrapper.get('[data-testid="product-technical-details"]').text()).toContain('Git Commit')
    wrapper.unmount()
  })

  it('asks a first-time tester for a display name without claiming authentication', async () => {
    const wrapper = await mountLayout()
    await flushPromises()
    expect(document.body.textContent).toContain('设置测试客服身份')
    expect(document.body.textContent).toContain('不是登录或权限认证')
    wrapper.unmount()
  })

  it('shows the test guide once for a known tester and records dismissal', async () => {
    localStorage.setItem(
      TESTER_IDENTITY_STORAGE_KEY,
      JSON.stringify({ reporterId: 'TESTER-ONE', reporterName: '小木', defaultStoreCode: 'PDD-SM' })
    )
    const wrapper = await mountLayout()
    await flushPromises()

    expect(document.body.textContent).toContain('AI客服助手（测试版）')
    expect(document.body.textContent).toContain('选择商品 / SKU')
    expect(document.body.textContent).toContain('人工确认后复制发送')
    expect(document.body.textContent).toContain('AI 建议需要人工确认')

    await wrapper.get('[data-testid="pilot-guide-start"]').trigger('click')
    await flushPromises()
    expect(localStorage.getItem('mumu-customer-workspace:pilot-guide-seen')).toBe('true')
    wrapper.unmount()
  })
})
