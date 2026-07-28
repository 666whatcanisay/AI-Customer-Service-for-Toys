import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CustomerIdentityKey } from '@/workspace/customerIdentity'
import MySuggestions from './MySuggestions.vue'

const apiMocks = vi.hoisted(() => ({ listMine: vi.fn() }))
vi.mock('@/api/suggestionClient', () => ({ suggestionClient: { listMine: apiMocks.listMine } }))

const mountPage = async () => {
  return mount(MySuggestions, {
    global: {
      plugins: [ElementPlus],
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
      provide: {
        [CustomerIdentityKey as symbol]: {
          identity: ref({ userId: 'CSU-ONE', displayName: '小木', role: 'CUSTOMER_SERVICE', status: 'ACTIVE', defaultStoreCode: 'PDD-SM', storeBindings: [{ storeCode: 'PDD-SM', isDefault: true }] })
        }
      }
    }
  })
}

describe('MySuggestions', () => {
  beforeEach(() => apiMocks.listMine.mockReset())

  it('queries only the current reporter and presents Chinese summaries', async () => {
    apiMocks.listMine.mockResolvedValue({ items: [{ suggestionId: 'SUG-1', reporterId: 'CSU-ONE', storeCode: null, moduleKey: 'ai-chat', category: 'BUG', title: '复制按钮问题', frequency: 'FREQUENT', urgency: 'HIGH', status: 'REVIEWING' }], total: 1 })
    const wrapper = await mountPage()
    await flushPromises()
    expect(apiMocks.listMine).toHaveBeenCalledWith('CSU-ONE')
    expect(wrapper.get('[data-testid="suggestion-list"]').text()).toContain('处理中')
    expect(wrapper.text()).toContain('问题反馈')
    expect(wrapper.text()).not.toContain('CSU-ONE')
  })

})
