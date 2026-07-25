import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TesterIdentityKey } from '@/workspace/testerIdentity'
import MySuggestions from './MySuggestions.vue'

const apiMocks = vi.hoisted(() => ({ listMine: vi.fn() }))
vi.mock('@/api/suggestionClient', () => ({ suggestionClient: { listMine: apiMocks.listMine } }))

const mountPage = async () => {
  return mount(MySuggestions, {
    global: {
      plugins: [ElementPlus],
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
      provide: {
        [TesterIdentityKey as symbol]: {
          identity: ref({ reporterId: 'TESTER-ONE', reporterName: '小木', defaultStoreCode: 'PDD-SM' }),
          save: vi.fn(), reload: vi.fn()
        }
      }
    }
  })
}

describe('MySuggestions', () => {
  beforeEach(() => apiMocks.listMine.mockReset())

  it('queries only the current reporter and presents Chinese summaries', async () => {
    apiMocks.listMine.mockResolvedValue({ items: [{ suggestionId: 'SUG-1', reporterId: 'TESTER-ONE', storeCode: null, moduleKey: 'ai-chat', category: 'BUG', title: '复制按钮问题', frequency: 'FREQUENT', urgency: 'HIGH', status: 'REVIEWING' }], total: 1 })
    const wrapper = await mountPage()
    await flushPromises()
    expect(apiMocks.listMine).toHaveBeenCalledWith('TESTER-ONE')
    expect(wrapper.get('[data-testid="suggestion-list"]').text()).toContain('处理中')
    expect(wrapper.text()).toContain('问题反馈')
    expect(wrapper.text()).not.toContain('TESTER-ONE')
  })

})
