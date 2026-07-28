import { describe, expect, it } from 'vitest'

import { CustomerIdentityAdapterError, adaptCustomerIdentity, adaptCustomerIdentityList } from './customerIdentityAdapter'

const activeIdentity = {
  user_id: 'CSU-001',
  display_name: '小木',
  role: 'CUSTOMER_SERVICE',
  status: 'ACTIVE',
  default_store_code: 'PDD-SM',
  store_bindings: [{ store_code: 'PDD-SM', is_default: true }]
}

describe('customerIdentityAdapter', () => {
  it('accepts a C-owned active identity and preserves only contract fields', () => {
    expect(adaptCustomerIdentity(activeIdentity)).toEqual({
      userId: 'CSU-001',
      displayName: '小木',
      role: 'CUSTOMER_SERVICE',
      status: 'ACTIVE',
      defaultStoreCode: 'PDD-SM',
      storeBindings: [{ storeCode: 'PDD-SM', isDefault: true }]
    })
  })

  it('rejects a list whose default store is not a default binding', () => {
    expect(() => adaptCustomerIdentityList({
      items: [{ ...activeIdentity, default_store_code: 'PDD-OTHER' }], total: 1
    })).toThrow(CustomerIdentityAdapterError)
  })

  it('rejects disabled identities from the customer selection endpoint', () => {
    expect(() => adaptCustomerIdentityList({
      items: [{ ...activeIdentity, status: 'DISABLED' }], total: 1
    })).toThrow(CustomerIdentityAdapterError)
  })
})
