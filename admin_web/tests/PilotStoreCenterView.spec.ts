import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import PilotStoreCenterView from '../src/views/PilotStoreCenterView.vue'
import { createPilotStore, listPilotStores } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  listPilotStores: vi.fn(),
  createPilotStore: vi.fn(),
  apiErrorMessage: vi.fn(() => 'Store request failed'),
}))

const mockedList = vi.mocked(listPilotStores)
const mockedCreate = vi.mocked(createPilotStore)
const routerLink = { props: ['to'], template: '<a :href="to"><slot /></a>' }
const store = {
  store_code: 'STORE-ONE', store_name: 'Store One', platform: 'pdd', created_at: '2026-07-27T08:00:00Z',
  setup_status: 'NEEDS_KNOWLEDGE' as const, catalog_product_count: 0, catalog_sku_count: 0,
  staged_product_count: 2, staged_sku_count: 3, faq_count: 0, safety_rule_count: 0,
  experience_case_count: 1, ai_feedback_count: 2, latest_product_imported_at: '2026-07-27T09:00:00Z',
  test_data_mode: true, production_usable: false,
}

describe('PilotStoreCenterView', () => {
  beforeEach(() => { mockedList.mockReset(); mockedCreate.mockReset() })

  it('renders API-backed store readiness and keeps per-store AI usage unavailable', async () => {
    mockedList.mockResolvedValue({ items: [store], total: 1 })
    const wrapper = mount(PilotStoreCenterView, { global: { stubs: { RouterLink: routerLink } } })
    await flushPromises()

    expect(wrapper.text()).toContain('STORE-ONE')
    expect(wrapper.text()).toContain('待维护知识')
    expect(wrapper.text()).toContain('单店 AI 使用：待启用')
    expect(wrapper.get('a[href="/imports/new?store_code=STORE-ONE"]').text()).toContain('导入商品')
    expect(wrapper.get('a[href="/test-data-packages?store_code=STORE-ONE"]').text()).toContain('维护知识')
  })

  it('creates a trial store and reloads real status', async () => {
    mockedList.mockResolvedValueOnce({ items: [], total: 0 }).mockResolvedValueOnce({ items: [store], total: 1 })
    mockedCreate.mockResolvedValue(store)
    const wrapper = mount(PilotStoreCenterView, { global: { stubs: { RouterLink: routerLink } } })
    await flushPromises()
    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('STORE-ONE')
    await inputs[1].setValue('Store One')
    await inputs[2].setValue('pdd')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mockedCreate).toHaveBeenCalledWith({ store_code: 'STORE-ONE', store_name: 'Store One', platform: 'pdd' })
    expect(mockedList).toHaveBeenCalledTimes(2)
  })
})
