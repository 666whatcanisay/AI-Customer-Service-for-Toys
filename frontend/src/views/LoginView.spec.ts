import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const authMocks = vi.hoisted(() => ({ login: vi.fn(), logout: vi.fn() }))
vi.mock('@/auth/authSession', () => ({
  useAuthSession: () => ({ login: authMocks.login, logout: authMocks.logout })
}))

import LoginView from './LoginView.vue'

const mountView = async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', component: LoginView },
      { path: '/workspace', component: { template: '<div>workspace</div>' } },
      { path: '/change-password', component: { template: '<div>change password</div>' } },
      { path: '/store-selection', component: { template: '<div>store selection</div>' } },
    ]
  })
  await router.push('/login?redirect=/workspace')
  await router.isReady()
  return { router, wrapper: mount(LoginView, { global: { plugins: [router] } }) }
}

describe('customer LoginView', () => {
  beforeEach(() => {
    authMocks.login.mockReset()
    authMocks.logout.mockReset()
  })

  it('logs in with account credentials and enters the permitted workspace', async () => {
    authMocks.login.mockResolvedValue({ permissions: ['workspace.access'], roles: ['CUSTOMER_SERVICE'], stores: [{ store_id: 1, is_default: true }], must_change_password: false })
    const { router, wrapper } = await mountView()
    await wrapper.get('input[autocomplete="username"]').setValue('support.one')
    await wrapper.get('input[autocomplete="current-password"]').setValue('secret-password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(authMocks.login).toHaveBeenCalledWith('support.one', 'secret-password')
    expect(router.currentRoute.value.path).toBe('/workspace')
  })

  it('does not enter the workspace when the server projection lacks permission', async () => {
    authMocks.login.mockResolvedValue({ permissions: ['product.manage'], roles: ['OPERATOR'], stores: [], must_change_password: false })
    const { wrapper } = await mountView()
    await wrapper.get('input[autocomplete="username"]').setValue('operator.one')
    await wrapper.get('input[autocomplete="current-password"]').setValue('secret-password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(authMocks.logout).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('当前账号没有客服工作台权限')
  })

  it('routes a temporary credential to mandatory password replacement', async () => {
    authMocks.login.mockResolvedValue({ permissions: ['workspace.access'], roles: ['CUSTOMER_SERVICE'], stores: [], must_change_password: true })
    const { router, wrapper } = await mountView()
    await wrapper.get('input[autocomplete="username"]').setValue('Wa')
    await wrapper.get('input[autocomplete="current-password"]').setValue('temporary-value')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/change-password')
  })

  it('renders the server cooldown state without treating it as another password failure', async () => {
    authMocks.login.mockRejectedValue({ response: { status: 429, data: { error: { code: 'AUTHENTICATION_RATE_LIMITED' } } } })
    const { wrapper } = await mountView()
    await wrapper.get('input[autocomplete="username"]').setValue('Wa')
    await wrapper.get('input[autocomplete="current-password"]').setValue('wrong-password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('冷却时间结束后重试')
  })

  it('does not misreport an upstream 503 as a password failure', async () => {
    authMocks.login.mockRejectedValue({ response: { status: 503, data: { detail: 'AI-CS platform is unavailable' } } })
    const { wrapper } = await mountView()
    await wrapper.get('input[autocomplete="username"]').setValue('support.one')
    await wrapper.get('input[autocomplete="current-password"]').setValue('value')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('AI-CS服务暂时不可用（HTTP 503）')
    expect(wrapper.get('[role="alert"]').text()).not.toContain('密码错误')
  })

  it('explains an expired local security session instead of issuing a generic fault id', async () => {
    authMocks.login.mockRejectedValue({
      response: { status: 403, data: { error: { code: 'LOCAL_SESSION_OR_CSRF_INVALID' } } }
    })
    const { wrapper } = await mountView()
    await wrapper.get('input[autocomplete="username"]').setValue('support.one')
    await wrapper.get('input[autocomplete="current-password"]').setValue('value')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    const message = wrapper.get('[role="alert"]').text()
    expect(message).toContain('本地安全会话已失效')
    expect(message).toContain('不是账号或密码错误')
    expect(message).not.toContain('LOGIN-')
  })

  it('explains a failed bootstrap handoff as a local session issue', async () => {
    authMocks.login.mockRejectedValue(new Error('CHANNEL_AGENT_BOOTSTRAP_401'))
    const { wrapper } = await mountView()
    await wrapper.get('input[autocomplete="username"]').setValue('support.one')
    await wrapper.get('input[autocomplete="current-password"]').setValue('value')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('本地安全会话已失效')
    expect(wrapper.get('[role="alert"]').text()).not.toContain('LOGIN-')
  })
})
