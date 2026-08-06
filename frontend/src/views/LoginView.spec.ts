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
    authMocks.login.mockResolvedValue({ permissions: ['workspace.access'], roles: ['CUSTOMER_SERVICE'], stores: [{ store_id: 1 }], must_change_password: false })
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
})
