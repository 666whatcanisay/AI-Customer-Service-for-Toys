import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  apiErrorMessage: vi.fn(() => '请求失败'), assignUserRoles: vi.fn(), assignUserStores: vi.fn(),
  createUser: vi.fn(), deactivateUser: vi.fn(), listOperationStores: vi.fn(),
  listStoreContextResolutions: vi.fn(), listUsers: vi.fn(), updateUser: vi.fn(),
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
const unboundUser = {
  ...user,
  id: '22222222-2222-4222-8222-222222222222',
  username: 'support.two',
  display_name: '李四',
  stores: [],
}
const store = { store_ref: 8, store_name: '玩趣乐园积木店', platform_name: '拼多多', status: 'ACTIVE', status_name: '正常', product_count: 3, created_at: '2026-08-06T00:00:00Z', remarks: '', data_source: 'PILOT', customer_service_status: 'ENABLED', customer_service_status_updated_at: null, customer_service_status_updated_by: null }
const secondStore = { ...store, store_ref: 9, store_name: '汕明' }

describe('UserManagementView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.listUsers.mockResolvedValue({ schema_version: 'ai-cs.iam.v1', items: [user, unboundUser], total: 2 })
    apiMocks.listOperationStores.mockResolvedValue({ items: [store, secondStore], total: 2 })
    apiMocks.listStoreContextResolutions.mockResolvedValue({ schema_version: 'ai-cs.store-context.v1', items: [], total: 0 })
    apiMocks.createUser.mockResolvedValue(user)
    apiMocks.assignUserStores.mockResolvedValue(user)
    apiMocks.assignUserRoles.mockResolvedValue(user)
    apiMocks.updateUser.mockResolvedValue(user)
  })

  it('keeps the main page compact and opens user creation in a modal', async () => {
    const wrapper = mount(UserManagementView)
    await flushPromises()

    expect(wrapper.text()).toContain('共 2 人')
    expect(wrapper.find('[data-testid="create-user-form"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="store-context-audit"]').attributes('open')).toBeUndefined()

    await wrapper.get('[data-testid="open-create-user"]').trigger('click')
    expect(wrapper.find('[data-testid="create-user-modal"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="create-user-form"]').attributes('role')).toBe('dialog')
  })

  it('automatically makes the first selected customer Store the default when creating a user', async () => {
    const wrapper = mount(UserManagementView)
    await flushPromises()
    await wrapper.get('[data-testid="open-create-user"]').trigger('click')
    const form = wrapper.get('form[data-testid="create-user-form"]')
    const credentials = form.findAll('input').filter((input) => ['text', 'password'].includes(input.attributes('type') || 'text'))
    await credentials[0].setValue('support.three')
    await credentials[1].setValue('王五')
    await credentials[2].setValue('Long-password-42!')

    await form.get('[data-testid="create-store-8"]').setValue(true)
    await flushPromises()
    expect((form.get('input[name="create-default-store"]').element as HTMLInputElement).checked).toBe(true)

    await form.trigger('submit')
    await flushPromises()
    expect(apiMocks.createUser).toHaveBeenCalledWith(expect.objectContaining({
      username: 'support.three', display_name: '王五', roles: ['CUSTOMER_SERVICE'],
      store_bindings: [{ store_id: 8, is_default: true }],
    }))
  })

  it('allows an unbound customer-service account to enter first-login Store selection', async () => {
    const wrapper = mount(UserManagementView)
    await flushPromises()
    await wrapper.get('[data-testid="open-create-user"]').trigger('click')
    const form = wrapper.get('form[data-testid="create-user-form"]')
    const credentials = form.findAll('input').filter((input) => ['text', 'password'].includes(input.attributes('type') || 'text'))
    await credentials[0].setValue('support.three')
    await credentials[1].setValue('王五')
    await credentials[2].setValue('Long-password-42!')
    await form.trigger('submit')
    await flushPromises()
    expect(apiMocks.createUser).toHaveBeenCalledWith(expect.objectContaining({ store_bindings: [] }))
  })

  it('opens assignment in a modal and auto-selects a default Store for an unbound customer-service user', async () => {
    const wrapper = mount(UserManagementView)
    await flushPromises()
    await wrapper.get(`[data-testid="assign-user-${unboundUser.id}"]`).trigger('click')
    const assignment = wrapper.get('form[data-testid="user-assignment-form"]')

    expect(wrapper.find('[data-testid="user-assignment-modal"]').exists()).toBe(true)
    await assignment.get('[data-testid="edit-store-8"]').setValue(true)
    await flushPromises()
    expect((assignment.get('input[name="edit-default-store"]').element as HTMLInputElement).checked).toBe(true)

    await assignment.trigger('submit')
    await flushPromises()
    expect(apiMocks.assignUserRoles).toHaveBeenCalledWith(unboundUser.id, ['CUSTOMER_SERVICE'])
    expect(apiMocks.assignUserStores).toHaveBeenCalledWith(unboundUser.id, [{ store_id: 8, is_default: true }])
  })

  it('edits display information in a dedicated modal without changing the login identity', async () => {
    const wrapper = mount(UserManagementView)
    await flushPromises()
    await wrapper.get(`[data-testid="edit-user-${user.id}"]`).trigger('click')
    const form = wrapper.get('form[data-testid="user-profile-form"]')

    expect(wrapper.get('[data-testid="user-profile-modal"]').text()).toContain(user.username)
    expect(form.find('input[value="support.one"]').exists()).toBe(false)
    const displayName = form.get('input[type="text"]')
    await displayName.setValue('客服组长')
    await form.trigger('submit')
    await flushPromises()

    expect(apiMocks.updateUser).toHaveBeenCalledWith(user.id, { display_name: '客服组长' })
  })

  it('uses the existing secure reset route and does not send an unchanged display name', async () => {
    const wrapper = mount(UserManagementView)
    await flushPromises()
    await wrapper.get(`[data-testid="edit-user-${user.id}"]`).trigger('click')
    const form = wrapper.get('form[data-testid="user-profile-form"]')
    await form.get('input[type="password"]').setValue('Temporary-reset-42!')
    expect(form.text()).toContain('撤销该用户所有登录状态')
    await form.trigger('submit')
    await flushPromises()

    expect(apiMocks.updateUser).toHaveBeenCalledWith(user.id, { password: 'Temporary-reset-42!' })
  })

  it('preserves one default while selecting multiple Stores and reassigns it when unchecked', async () => {
    const wrapper = mount(UserManagementView)
    await flushPromises()
    await wrapper.get(`[data-testid="assign-user-${user.id}"]`).trigger('click')
    const assignment = wrapper.get('form[data-testid="user-assignment-form"]')

    await assignment.get('[data-testid="edit-store-9"]').setValue(true)
    await flushPromises()
    expect((assignment.get('input[name="edit-default-store"][value="8"]').element as HTMLInputElement).checked).toBe(true)
    await assignment.get('[data-testid="edit-store-8"]').setValue(false)
    await flushPromises()
    expect((assignment.get('input[name="edit-default-store"][value="9"]').element as HTMLInputElement).checked).toBe(true)

    await assignment.trigger('submit')
    await flushPromises()
    expect(apiMocks.assignUserStores).toHaveBeenCalledWith(user.id, [{ store_id: 9, is_default: true }])
  })

  it('assigns operator all-store role and clears obsolete customer Store bindings', async () => {
    const wrapper = mount(UserManagementView)
    await flushPromises()
    await wrapper.get(`[data-testid="assign-user-${user.id}"]`).trigger('click')
    const assignment = wrapper.get('form[data-testid="user-assignment-form"]')
    const roleInputs = assignment.findAll('.choice input[type="checkbox"]')
    await roleInputs[1].setValue(true)
    await roleInputs[2].setValue(false)
    await assignment.trigger('submit')
    await flushPromises()
    expect(apiMocks.assignUserRoles).toHaveBeenCalledWith(user.id, ['OPERATOR'])
    expect(apiMocks.assignUserStores).toHaveBeenCalledWith(user.id, [])
    expect(apiMocks.assignUserRoles.mock.invocationCallOrder[0])
      .toBeLessThan(apiMocks.assignUserStores.mock.invocationCallOrder[0])
  })
})
