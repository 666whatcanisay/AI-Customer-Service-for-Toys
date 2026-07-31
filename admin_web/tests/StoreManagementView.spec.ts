import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import StoreManagementView from '../src/views/StoreManagementView.vue'

const apiMocks = vi.hoisted(() => ({
  apiErrorMessage: vi.fn(() => '暂时不可用'),
  createOperationProduct: vi.fn(),
  createOperationStore: vi.fn(),
  getOperationStore: vi.fn(),
  listCatalogActivationReceipts: vi.fn(),
  listOperationStores: vi.fn(),
  setStoreCustomerServiceStatus: vi.fn(),
  updateOperationStore: vi.fn(),
}))

vi.mock('../src/api/client', () => apiMocks)

const store = {
  store_ref: 8,
  store_name: '木木小栈拼多多旗舰店',
  platform_name: '拼多多',
  status: 'ACTIVE' as const,
  status_name: '正常',
  product_count: 3,
  created_at: '2026-07-29T08:00:00Z',
  remarks: '玩具商品知识运营',
  data_source: 'PILOT' as const,
  customer_service_status: 'DISABLED' as const,
  customer_service_status_updated_at: null,
  customer_service_status_updated_by: null,
}

const product = {
  product_ref: 'C-PRODUCT-ONE',
  store_ref: 8,
  store_name: store.store_name,
  product_name: '城市消防局机械积木玩具套装',
  product_summary: '可拼装消防局场景的机械积木套装。',
  data_status: 'PENDING_REVIEW' as const,
  data_status_name: '待审核',
  sku_count: 0,
  created_at: '2026-07-29T09:00:00Z',
  data_source: 'PILOT' as const,
  customer_service_status: 'DISABLED' as const,
}

describe('StoreManagementView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.listOperationStores.mockResolvedValue({ items: [store], total: 1 })
    apiMocks.createOperationProduct.mockResolvedValue(product)
    apiMocks.createOperationStore.mockResolvedValue(store)
    apiMocks.getOperationStore.mockResolvedValue(store)
    apiMocks.updateOperationStore.mockResolvedValue(store)
    apiMocks.listCatalogActivationReceipts.mockResolvedValue({ items: [], total: 0, page: 1, size: 20 })
    apiMocks.setStoreCustomerServiceStatus.mockResolvedValue({
      changed: true,
      activation_receipt: { activation_receipt_id: 'ACT-STORE-1' },
    })
  })

  it('lists Chinese business fields without operator-facing technical identifiers', async () => {
    const wrapper = mount(StoreManagementView)
    await flushPromises()

    expect(wrapper.text()).toContain('店铺管理')
    expect(wrapper.text()).toContain('木木小栈拼多多旗舰店')
    expect(wrapper.text()).toContain('商品数量')
    expect(wrapper.text()).toContain('创建时间')
    expect(wrapper.text()).not.toContain('tenant_id')
    expect(wrapper.text()).not.toContain('store_code')
    expect(wrapper.text()).not.toContain('external_id')
    expect(wrapper.text()).toContain('客服状态')
    expect(wrapper.text()).toContain('试运行')
  })

  it('requires an operator and uses the C activation action', async () => {
    const wrapper = mount(StoreManagementView)
    await flushPromises()
    const activationButton = wrapper.findAll('button').find((button) => button.text() === '启用客服使用')
    expect(activationButton).toBeDefined()
    await activationButton!.trigger('click')
    expect(wrapper.text()).toContain('请先填写本次操作人')

    await wrapper.get('.operator-field input').setValue('运营甲')
    await activationButton!.trigger('click')
    await flushPromises()
    expect(apiMocks.setStoreCustomerServiceStatus).toHaveBeenCalledWith(
      8,
      'ENABLED',
      '运营甲',
      expect.stringMatching(/^store-8-ENABLED-/),
    )
    expect(wrapper.text()).toContain('ACT-STORE-1')
  })

  it('creates a store from name, platform and remarks only', async () => {
    const wrapper = mount(StoreManagementView)
    await flushPromises()
    await wrapper.get('.page-header button').trigger('click')
    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('木木小栈拼多多旗舰店')
    await wrapper.get('select').setValue('pinduoduo')
    await wrapper.get('textarea').setValue('玩具商品知识运营')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(apiMocks.createOperationStore).toHaveBeenCalledWith({
      store_name: '木木小栈拼多多旗舰店',
      platform: 'pinduoduo',
      remarks: '玩具商品知识运营',
    })
    expect(wrapper.text()).toContain('店铺已创建，可在导入中心选择')
  })

  it('edits the customer status with an operator and activation receipt', async () => {
    const wrapper = mount(StoreManagementView)
    await flushPromises()

    const editButton = wrapper.findAll('button').find((button) => button.text() === '编辑')
    expect(editButton).toBeDefined()
    await editButton!.trigger('click')

    const storeForm = wrapper.get('.store-form')
    expect(storeForm.text()).toContain('客服使用状态')
    expect(storeForm.text()).toContain('客服状态操作人')
    expect(storeForm.get('[data-testid="store-edit-customer-service-status"]').element).toHaveProperty('value', 'DISABLED')

    await storeForm.get('[data-testid="store-edit-customer-service-status"]').setValue('ENABLED')
    await storeForm.trigger('submit')
    expect(wrapper.text()).toContain('修改客服使用状态前，请填写客服状态操作人')
    expect(apiMocks.updateOperationStore).not.toHaveBeenCalled()
    expect(apiMocks.setStoreCustomerServiceStatus).not.toHaveBeenCalled()

    await storeForm.get('[data-testid="store-edit-activation-operator"]').setValue('运营乙')
    await storeForm.trigger('submit')
    await flushPromises()

    expect(apiMocks.updateOperationStore).toHaveBeenCalledWith(8, {
      store_name: store.store_name,
      platform: 'pinduoduo',
      remarks: store.remarks,
      status: 'ACTIVE',
    })
    expect(apiMocks.setStoreCustomerServiceStatus).toHaveBeenCalledWith(
      8,
      'ENABLED',
      '运营乙',
      expect.stringMatching(/^store-8-ENABLED-/),
    )
    expect(wrapper.text()).toContain('ACT-STORE-1')
  })

  it('does not create an activation receipt when edit keeps the customer status', async () => {
    const wrapper = mount(StoreManagementView)
    await flushPromises()

    const editButton = wrapper.findAll('button').find((button) => button.text() === '编辑')
    expect(editButton).toBeDefined()
    await editButton!.trigger('click')
    await wrapper.get('.store-form').trigger('submit')
    await flushPromises()

    expect(apiMocks.updateOperationStore).toHaveBeenCalledOnce()
    expect(apiMocks.setStoreCustomerServiceStatus).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('店铺信息已更新')
  })

  it('reports partial failure without claiming the customer status changed', async () => {
    apiMocks.setStoreCustomerServiceStatus.mockRejectedValueOnce(new Error('activation failed'))
    const wrapper = mount(StoreManagementView)
    await flushPromises()

    const editButton = wrapper.findAll('button').find((button) => button.text() === '编辑')
    expect(editButton).toBeDefined()
    await editButton!.trigger('click')
    const storeForm = wrapper.get('.store-form')
    await storeForm.get('[data-testid="store-edit-customer-service-status"]').setValue('ENABLED')
    await storeForm.get('[data-testid="store-edit-activation-operator"]').setValue('运营丙')
    await storeForm.trigger('submit')
    await flushPromises()

    expect(apiMocks.updateOperationStore).toHaveBeenCalledOnce()
    expect(apiMocks.setStoreCustomerServiceStatus).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('店铺信息已更新，但客服使用状态未修改')
    expect(wrapper.text()).toContain('暂时不可用')
    expect(wrapper.find('.store-form').exists()).toBe(true)
  })

  it('creates a pending-review product under an active store and refreshes counts', async () => {
    const wrapper = mount(StoreManagementView)
    await flushPromises()
    const addProduct = wrapper.findAll('.page-header button').find((button) => button.text() === '新增商品')
    expect(addProduct).toBeDefined()
    await addProduct!.trigger('click')

    const productForm = wrapper.get('.product-form')
    await productForm.get('select').setValue('8')
    await productForm.get('input').setValue('城市消防局机械积木玩具套装')
    await productForm.get('textarea').setValue('可拼装消防局场景的机械积木套装。')
    await productForm.trigger('submit')
    await flushPromises()

    expect(apiMocks.createOperationProduct).toHaveBeenCalledWith(8, {
      product_name: '城市消防局机械积木玩具套装',
      product_summary: '可拼装消防局场景的机械积木套装。',
    })
    expect(apiMocks.listOperationStores).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('商品已新增并进入待审核状态')
    expect(wrapper.text()).toContain('查看并维护商品知识')
  })
})
