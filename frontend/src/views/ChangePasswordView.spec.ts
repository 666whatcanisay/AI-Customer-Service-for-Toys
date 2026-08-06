import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

const changePassword = vi.fn()
vi.mock('@/auth/authSession', () => ({ useAuthSession: () => ({ changePassword }) }))
import ChangePasswordView from './ChangePasswordView.vue'

describe('customer ChangePasswordView', () => {
  it('replaces the initialization password and returns to login', async () => {
    changePassword.mockResolvedValue(undefined)
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/change-password', component: ChangePasswordView },
      { path: '/login', component: { template: '<div>login</div>' } },
    ] })
    await router.push('/change-password'); await router.isReady()
    const wrapper = mount(ChangePasswordView, { global: { plugins: [router] } })
    const fields = wrapper.findAll('input')
    await fields[0].setValue('temporary-value')
    await fields[1].setValue('replacement-password-value')
    await fields[2].setValue('replacement-password-value')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(changePassword).toHaveBeenCalledWith('temporary-value', 'replacement-password-value')
    expect(router.currentRoute.value.path).toBe('/login')
  })
})
