import { inject, ref, type InjectionKey, type Ref } from 'vue'

import { customerIdentityClient, CustomerIdentityClientError } from '@/api/customerIdentityClient'
import type { CustomerIdentity } from '@/api/customerIdentityTypes'

export const CUSTOMER_IDENTITY_STORAGE_KEY = 'mumu-customer-workspace:customer-identity-v1'

export interface CustomerIdentityStore {
  identity: Ref<CustomerIdentity | null>
  loading: Ref<boolean>
  error: Ref<string>
  loadSelectable: () => Promise<CustomerIdentity[]>
  restore: () => Promise<CustomerIdentity | null>
  select: (identity: CustomerIdentity) => void
  clear: () => void
}

export const CustomerIdentityKey: InjectionKey<CustomerIdentityStore> = Symbol('customerIdentity')

const readStoredUserId = (): string | null => {
  try {
    const raw = globalThis.localStorage?.getItem(CUSTOMER_IDENTITY_STORAGE_KEY)
    if (!raw) return null
    const value: unknown = JSON.parse(raw)
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null
    const userId = (value as { userId?: unknown }).userId
    return typeof userId === 'string' && userId.trim() ? userId.trim() : null
  } catch {
    return null
  }
}

const persistUserId = (userId: string): void => {
  try {
    globalThis.localStorage?.setItem(CUSTOMER_IDENTITY_STORAGE_KEY, JSON.stringify({ userId }))
  } catch {
    // The current in-memory choice remains usable until the next reload.
  }
}

const clearStoredUserId = (): void => {
  try {
    globalThis.localStorage?.removeItem(CUSTOMER_IDENTITY_STORAGE_KEY)
  } catch {
    // Nothing else is required when storage is restricted.
  }
}

export function createCustomerIdentityStore(): CustomerIdentityStore {
  const identity = ref<CustomerIdentity | null>(null)
  const loading = ref(false)
  const error = ref('')

  function clear(): void {
    identity.value = null
    error.value = ''
    clearStoredUserId()
  }

  function select(nextIdentity: CustomerIdentity): void {
    if (nextIdentity.status !== 'ACTIVE') {
      clear()
      error.value = '该客服身份已停用，请选择其他身份。'
      return
    }
    identity.value = nextIdentity
    error.value = ''
    persistUserId(nextIdentity.userId)
  }

  async function loadSelectable(): Promise<CustomerIdentity[]> {
    loading.value = true
    error.value = ''
    try {
      return await customerIdentityClient.list()
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : '客服身份列表暂时不可用。'
      return []
    } finally {
      loading.value = false
    }
  }

  async function restore(): Promise<CustomerIdentity | null> {
    const userId = readStoredUserId()
    if (!userId) {
      identity.value = null
      return null
    }
    loading.value = true
    error.value = ''
    try {
      const restored = await customerIdentityClient.get(userId)
      select(restored)
      return restored
    } catch (reason) {
      identity.value = null
      clearStoredUserId()
      error.value = reason instanceof CustomerIdentityClientError && reason.kind === 'invalid-selection'
        ? '上次选择的客服身份已失效，请重新选择。'
        : reason instanceof Error ? reason.message : '无法确认上次选择的客服身份。'
      return null
    } finally {
      loading.value = false
    }
  }

  return { identity, loading, error, loadSelectable, restore, select, clear }
}

export function useCustomerIdentity(): CustomerIdentityStore {
  const store = inject(CustomerIdentityKey)
  if (!store) throw new Error('Customer identity store has not been provided.')
  return store
}
