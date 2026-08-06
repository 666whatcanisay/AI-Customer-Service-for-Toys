import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

const listStoreOptions = vi.fn()
const replaceStoreBindings = vi.fn()
vi.mock('@/auth/authSession', () => ({
  useAuthSession: () => ({
    user: ref({ stores: [] }), defaultStore: ref(null), listStoreOptions, replaceStoreBindings,
  })
}))
import StoreSelectionView from './StoreSelectionView.vue'

describe('customer StoreSelectionView', () => {
  it('binds multiple enabled Stores before entering the workspace', async () => {
    listStoreOptions.mockResolvedValue([
      { store_id: 1, store_code: 'STORE-A', store_name: '一店', platform: 'pdd' },
      { store_id: 2, store_code: 'STORE-B', store_name: '二店', platform: 'pdd' },
    ])
    replaceStoreBindings.mockResolvedValue({ stores: [] })
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/store-selection', component: StoreSelectionView },
      { path: '/workspace', component: { template: '<div>workspace</div>' } },
    ] })
    await router.push('/store-selection'); await router.isReady()
    const wrapper = mount(StoreSelectionView, { global: { plugins: [router] } })
    await flushPromises()
    const choices = wrapper.findAll('input[type="checkbox"]')
    await choices[0].setValue(true); await choices[1].setValue(true)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(replaceStoreBindings).toHaveBeenCalledWith([1, 2], 1)
    expect(router.currentRoute.value.path).toBe('/workspace')
  })
})
