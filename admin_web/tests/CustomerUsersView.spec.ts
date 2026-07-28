import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  apiErrorMessage: vi.fn(() => '操作失败'),
  createCustomerUser: vi.fn(),
  listCatalogStores: vi.fn(),
  listCustomerUsers: vi.fn(),
  updateCustomerUser: vi.fn(),
  updateCustomerUserStatus: vi.fn(),
}))

vi.mock('../src/api/client', () => apiMocks)

import CustomerUsersView from '../src/views/CustomerUsersView.vue'

const user = {
  user_id: 'CSU-TEST-1',
  display_name: '小林',
  role: 'CUSTOMER_SERVICE' as const,
  status: 'ACTIVE' as const,
  default_store_code: 'STORE-ONE',
  store_bindings: [{ store_code: 'STORE-ONE', is_default: true }],
  created_at: '2026-07-28T00:00:00Z',
  updated_at: '2026-07-28T00:00:00Z',
}

describe('CustomerUsersView', () => {
  beforeEach(() => {
    apiMocks.listCustomerUsers.mockResolvedValue({ items: [user], total: 1 })
    apiMocks.listCatalogStores.mockResolvedValue([{ store_code: 'STORE-ONE', store_name: '汕明测试店' }])
    apiMocks.updateCustomerUser.mockResolvedValue(user)
    apiMocks.updateCustomerUserStatus.mockResolvedValue({ ...user, status: 'DISABLED' })
  })

  it('shows Chinese trial-boundary guidance and edits a selected customer user', async () => {
    const wrapper = mount(CustomerUsersView)
    await flushPromises()

    expect(wrapper.text()).toContain('客服用户')
    expect(wrapper.text()).toContain('试运行边界')
    expect(wrapper.text()).toContain('小林')
    await wrapper.get('button.link-button').trigger('click')
    expect(wrapper.text()).toContain('编辑客服用户')
    await wrapper.get('input[placeholder="例如：小林"]').setValue('小林（晚班）')
    await wrapper.get('[data-testid="customer-user-save"]').trigger('click')
    await flushPromises()

    expect(apiMocks.updateCustomerUser).toHaveBeenCalledWith('CSU-TEST-1', {
      display_name: '小林（晚班）',
      role: 'CUSTOMER_SERVICE',
      store_codes: ['STORE-ONE'],
      default_store_code: 'STORE-ONE',
    })
  })

  it('does not use an empty state to hide an API error', async () => {
    apiMocks.listCustomerUsers.mockRejectedValueOnce(new Error('offline'))
    const wrapper = mount(CustomerUsersView)
    await flushPromises()

    expect(wrapper.text()).toContain('客服用户资料暂时无法读取')
    expect(wrapper.text()).not.toContain('还没有客服用户。请先新增')
  })
})
