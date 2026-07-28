import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import { CustomerIdentityKey } from '@/workspace/customerIdentity'
import CustomerIdentitySelection from './CustomerIdentitySelection.vue'

const identity = {
  userId: 'CSU-001', displayName: '小木', role: 'CUSTOMER_SERVICE' as const,
  status: 'ACTIVE' as const, defaultStoreCode: 'PDD-SM',
  storeBindings: [{ storeCode: 'PDD-SM', isDefault: true }]
}

describe('CustomerIdentitySelection', () => {
  it('requires selection of a C-provided active identity before the workbench can open', async () => {
    const select = vi.fn()
    const wrapper = mount(CustomerIdentitySelection, {
      global: {
        provide: {
          [CustomerIdentityKey as symbol]: {
            identity: ref(null), loading: ref(false), error: ref(''),
            loadSelectable: vi.fn().mockResolvedValue([identity]), select, clear: vi.fn(), restore: vi.fn()
          }
        }
      }
    })
    await flushPromises()

    expect(wrapper.text()).toContain('先选择你的客服身份')
    expect(wrapper.text()).toContain('小木')
    await wrapper.get('.identity-option').trigger('click')
    await wrapper.get('.primary').trigger('click')
    expect(select).toHaveBeenCalledWith(identity)
  })
})
