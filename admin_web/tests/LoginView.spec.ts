import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const authMocks = vi.hoisted(() => ({ login: vi.fn(), logout: vi.fn() }))
vi.mock('../src/auth/session', () => ({ useAdminSession: () => ({ login: authMocks.login, logout: authMocks.logout }) }))
import LoginView from '../src/views/LoginView.vue'

const mountLogin = async () => {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/login', component: LoginView }, { path: '/overview', component: { template: '<div>overview</div>' } },
    { path: '/change-password', component: { template: '<div>change password</div>' } },
  ] })
  await router.push('/login'); await router.isReady()
  return { router, wrapper: mount(LoginView, { global: { plugins: [router] } }) }
}

describe('admin LoginView', () => {
  beforeEach(() => { authMocks.login.mockReset(); authMocks.logout.mockReset() })
  it('admits a server-authorized operator', async () => {
    authMocks.login.mockResolvedValue({ permissions: ['product.manage'], must_change_password: false })
    const { router, wrapper } = await mountLogin()
    await wrapper.get('input[autocomplete="username"]').setValue('operator.one')
    await wrapper.get('input[autocomplete="current-password"]').setValue('password-value')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(authMocks.login).toHaveBeenCalledWith('operator.one', 'password-value')
    expect(router.currentRoute.value.path).toBe('/overview')
  })
  it('rejects a customer-service-only account from Admin', async () => {
    authMocks.login.mockResolvedValue({ permissions: ['workspace.access'], must_change_password: false })
    const { wrapper } = await mountLogin()
    await wrapper.get('input[autocomplete="username"]').setValue('support.one')
    await wrapper.get('input[autocomplete="current-password"]').setValue('password-value')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(authMocks.logout).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('当前账号没有运营管理权限')
  })
  it('routes an initialization credential to password replacement', async () => {
    authMocks.login.mockResolvedValue({ permissions: ['product.manage'], must_change_password: true })
    const { router, wrapper } = await mountLogin()
    await wrapper.get('input[autocomplete="username"]').setValue('江')
    await wrapper.get('input[autocomplete="current-password"]').setValue('temporary-value')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(router.currentRoute.value.path).toBe('/change-password')
  })
})
