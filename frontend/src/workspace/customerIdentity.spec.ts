import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CUSTOMER_IDENTITY_STORAGE_KEY, createCustomerIdentityStore } from './customerIdentity'

const identityMocks = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn() }))

vi.mock('@/api/customerIdentityClient', () => ({
  customerIdentityClient: identityMocks,
  CustomerIdentityClientError: class CustomerIdentityClientError extends Error {
    constructor(public readonly kind: string, message: string) { super(message) }
  }
}))

const activeIdentity = {
  userId: 'CSU-001', displayName: '小木', role: 'CUSTOMER_SERVICE' as const,
  status: 'ACTIVE' as const, defaultStoreCode: 'PDD-SM',
  storeBindings: [{ storeCode: 'PDD-SM', isDefault: true }]
}

describe('customerIdentity', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('persists only the selected C user id, not a browser-created identity', () => {
    const store = createCustomerIdentityStore()
    store.select(activeIdentity)

    expect(store.identity.value).toEqual(activeIdentity)
    expect(JSON.parse(localStorage.getItem(CUSTOMER_IDENTITY_STORAGE_KEY) ?? '{}')).toEqual({ userId: 'CSU-001' })
  })

  it('clears a stale saved selection instead of allowing anonymous fallback', async () => {
    localStorage.setItem(CUSTOMER_IDENTITY_STORAGE_KEY, JSON.stringify({ userId: 'CSU-DISABLED' }))
    identityMocks.get.mockRejectedValue(new Error('所选客服身份已失效'))
    const store = createCustomerIdentityStore()

    await expect(store.restore()).resolves.toBeNull()
    expect(store.identity.value).toBeNull()
    expect(localStorage.getItem(CUSTOMER_IDENTITY_STORAGE_KEY)).toBeNull()
  })

  it('restores an active identity from C before opening the workbench', async () => {
    localStorage.setItem(CUSTOMER_IDENTITY_STORAGE_KEY, JSON.stringify({ userId: 'CSU-001' }))
    identityMocks.get.mockResolvedValue(activeIdentity)
    const store = createCustomerIdentityStore()

    await expect(store.restore()).resolves.toEqual(activeIdentity)
    expect(identityMocks.get).toHaveBeenCalledWith('CSU-001')
  })
})
