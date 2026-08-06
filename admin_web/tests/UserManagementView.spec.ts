import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  apiErrorMessage: vi.fn(() => '请求失败'), assignUserRoles: vi.fn(), assignUserStores: vi.fn(),
  createUser: vi.fn(), deactivateUser: vi.fn(), listOperationStores: vi.fn(),
  listStoreContextResolutions: vi.fn(), listUsers: vi.fn(),
}))
vi.mock('../src/api/client', () => apiMocks)
import UserManagementView from '../src/views/UserManagementView.vue'

const user = {
  id: '11111111-1111-4111-8111-111111111111', username: 'support.one', display_name: '张三',
  status: 'ACTIVE' as const, roles: ['CUSTOMER_SERVICE'] as const,
  permissions: ['workspace.access', 'ai.reply', 'feedback.submit', 'customer_service.manage'],
  stores: [{ id: 1, store_id: 8, store_code: 'PDD-SM', store_name: '玩趣乐园积木店', platform: 'pdd', is_default: true }],
  must_change_password: true, all_store_access: false,
  created_at: '2026-08-06T00:00:00Z', updated_at: '2026-08-06T00:00:00Z',
}
const store = { store_ref: 8, store_name: '玩趣乐园积木店', platform_name: '拼多多', status: 'ACTIVE', status_name: '正常', product_count: 3, created_at: '2026-08-06T00:00:00Z', remarks: '', data_source: 'PILOT', customer_service_status: 'ENABLED', customer_service_status_updated_at: null, customer_service_status_updated_by: null }

describe('UserManagementView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.listUsers.mockResolvedValue({ schema_version: 'ai-cs.iam.v1', items: [user], total: 1 })
    apiMocks.listOperationStores.mockResolvedValue({ items: [store], total: 1 })
    apiMocks.listStoreContextResolutions.mockResolvedValue({ schema_version: 'ai-cs.store-context.v1', items: [], total: 0 })
    apiMocks.createUser.mockResolvedValue(user)
    apiMocks.assignUserStores.mockResolvedValue(user)
    apiMocks.assignUserRoles.mockResolvedValue(user)
  })
  it('lists real users and creates a customer-service user with multiple optional Stores', async () => {
    const wrapper = mount(UserManagementView)
    await flushPromises()
    expect(wrapper.text()).toContain('张三')
    expect(wrapper.text()).toContain('玩趣乐园积木店')
    const inputs = wrapper.findAll('form[data-testid="create-user-form"] input')
    await inputs[0].setValue('support.two'); await inputs[1].setValue('李四'); await inputs[2].setValue('Long-password-42!')
    const storeChoice = wrapper.findAll('form[data-testid="create-user-form"] input[type="checkbox"]').at(3)!
    await storeChoice.setValue(true)
    const defaultChoice = wrapper.get('form[data-testid="create-user-form"] input[type="radio"]')
    await defaultChoice.setValue(true)
    await wrapper.get('form[data-testid="create-user-form"]').trigger('submit'); await flushPromises()
    expect(apiMocks.createUser).toHaveBeenCalledWith(expect.objectContaining({
      username: 'support.two', display_name: '李四', roles: ['CUSTOMER_SERVICE'],
      store_bindings: [{ store_id: 8, is_default: true }],
    }))
    expect(wrapper.text()).toContain('首次登录需修改')
  })
  it('allows an unbound customer-service account to enter first-login Store selection', async () => {
    const wrapper = mount(UserManagementView); await flushPromises()
    const inputs = wrapper.findAll('form[data-testid="create-user-form"] input')
    await inputs[0].setValue('support.two'); await inputs[1].setValue('李四'); await inputs[2].setValue('Long-password-42!')
    await wrapper.get('form[data-testid="create-user-form"]').trigger('submit'); await flushPromises()
    expect(apiMocks.createUser).toHaveBeenCalledWith(expect.objectContaining({ store_bindings: [] }))
  })
  it('assigns operator all-store role and clears obsolete customer Store bindings', async () => {
    const wrapper = mount(UserManagementView); await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '分配')!.trigger('click')
    const assignment = wrapper.get('form[data-testid="user-assignment-form"]')
    const roleInputs = assignment.findAll('input[type="checkbox"]')
    await roleInputs[1].setValue(true)
    await roleInputs[2].setValue(false)
    const storeChoice = assignment.findAll('input[type="checkbox"]').at(3)!
    await storeChoice.setValue(false)
    await assignment.trigger('submit'); await flushPromises()
    expect(apiMocks.assignUserRoles).toHaveBeenCalledWith(user.id, ['OPERATOR'])
    expect(apiMocks.assignUserStores).toHaveBeenCalledWith(user.id, [])
    expect(apiMocks.assignUserRoles.mock.invocationCallOrder[0])
      .toBeLessThan(apiMocks.assignUserStores.mock.invocationCallOrder[0])
  })
})
