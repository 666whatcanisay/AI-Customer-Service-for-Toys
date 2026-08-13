import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  listUsers: vi.fn(), listOperationStores: vi.fn(), listStoreContextResolutions: vi.fn(),
  updateUser: vi.fn(), deactivateUser: vi.fn(), assignUserRoles: vi.fn(),
  assignUserStores: vi.fn(), createUser: vi.fn(), apiErrorMessage: vi.fn(() => 'error'),
}))
vi.mock('../api/client', () => api)

import UserManagementView from './UserManagementView.vue'

describe('UserManagementView account lifecycle', () => {
  beforeEach(() => {
    vi.stubGlobal('confirm', vi.fn(() => true))
    api.listUsers.mockResolvedValue({
      items: [{
        id: 'user-disabled', username: 'disabled', display_name: '停用客服', status: 'DISABLED',
        roles: ['CUSTOMER_SERVICE'], permissions: [], stores: [], all_store_access: false,
        created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z',
      }], total: 1,
    })
    api.listOperationStores.mockResolvedValue({ items: [], total: 0 })
    api.listStoreContextResolutions.mockResolvedValue({ items: [], total: 0 })
    api.updateUser.mockResolvedValue({})
  })

  it('can explicitly re-enable a disabled user through the existing update API', async () => {
    const wrapper = mount(UserManagementView, {
      global: { stubs: { UserStoreBindingFields: true } },
    })
    await flushPromises()
    await wrapper.get('[data-testid="enable-user-user-disabled"]').trigger('click')
    await flushPromises()
    expect(api.updateUser).toHaveBeenCalledWith('user-disabled', { status: 'ACTIVE' })
  })
})
