import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const authMocks = vi.hoisted(() => ({ login: vi.fn(), logout: vi.fn() }))
vi.mock('../auth/session', () => ({
  useAdminSession: () => ({ login: authMocks.login, logout: authMocks.logout })
}))

import LoginView from './LoginView.vue'

describe('admin LoginView', () => {
  beforeEach(() => {
    authMocks.login.mockReset()
    authMocks.logout.mockReset()
  })

  it('renders the server cooldown state returned by the IAM contract', async () => {
    authMocks.login.mockRejectedValue({
      response: { data: { error: { code: 'AUTHENTICATION_RATE_LIMITED' } } }
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/login', component: LoginView },
        { path: '/overview', component: { template: '<div>overview</div>' } },
        { path: '/change-password', component: { template: '<div>password</div>' } },
      ]
    })
    await router.push('/login')
    await router.isReady()
    const wrapper = mount(LoginView, { global: { plugins: [router] } })
    await wrapper.get('input[autocomplete="username"]').setValue('admin')
    await wrapper.get('input[autocomplete="current-password"]').setValue('wrong-password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('冷却时间结束后重试')
  })
})
