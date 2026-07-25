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
    routes: [{ path: '/', component: { template: '<div>首页内容</div>' } }]
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

  it('shows the platform navigation, global status and safety banner', async () => {
    localStorage.setItem(TESTER_IDENTITY_STORAGE_KEY, JSON.stringify({ reporterId: 'TESTER-ONE', reporterName: '小木', defaultStoreCode: 'PDD-SM' }))
    const wrapper = await mountLayout()
    await flushPromises()
    expect(wrapper.get('nav').text()).toContain('工作台首页')
    expect(wrapper.get('nav').text()).toContain('AI 客服')
    expect(wrapper.get('nav').text()).toContain('我的建议')
    expect(wrapper.get('nav').text()).toContain('我的案例')
    expect(wrapper.get('[data-testid="global-system-status"]').text()).toContain('AI 可用')
    expect(wrapper.get('[data-testid="global-test-banner"]').text()).toContain('禁止填写真实客户隐私')
    wrapper.unmount()
  })

  it('asks a first-time tester for a display name without claiming authentication', async () => {
    const wrapper = await mountLayout()
    await flushPromises()
    expect(document.body.textContent).toContain('设置测试客服身份')
    expect(document.body.textContent).toContain('不是登录或权限认证')
    wrapper.unmount()
  })
})
