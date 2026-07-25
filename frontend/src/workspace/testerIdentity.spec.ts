import { beforeEach, describe, expect, it } from 'vitest'
import {
  TESTER_IDENTITY_STORAGE_KEY,
  createTesterIdentityStore,
  type TesterIdentity
} from './testerIdentity'

function readPersistedIdentity(): TesterIdentity {
  return JSON.parse(window.localStorage.getItem(TESTER_IDENTITY_STORAGE_KEY) ?? 'null')
}

describe('testerIdentity', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('creates and persists a non-sensitive tester identity on first use', () => {
    const store = createTesterIdentityStore()

    expect(store.identity.value).toEqual({
      reporterId: expect.stringMatching(/^TESTER-[A-Z0-9-]+$/),
      reporterName: '',
      defaultStoreCode: ''
    })
    expect(readPersistedIdentity()).toEqual(store.identity.value)
  })

  it('saves and restores only the tester identity fields', () => {
    const store = createTesterIdentityStore()
    const reporterId = store.identity.value.reporterId

    store.save('木木测试员', 'PDD-SM')

    expect(readPersistedIdentity()).toEqual({
      reporterId,
      reporterName: '木木测试员',
      defaultStoreCode: 'PDD-SM'
    })
    expect(createTesterIdentityStore().identity.value).toEqual({
      reporterId,
      reporterName: '木木测试员',
      defaultStoreCode: 'PDD-SM'
    })
  })

  it.each([
    '{broken json',
    JSON.stringify({ reporterId: 'customer-phone-13800000000', reporterName: '测试员' }),
    JSON.stringify({ reporterId: 'TESTER-VALID', reporterName: 123, defaultStoreCode: [] })
  ])('safely replaces damaged or invalid stored data', (storedValue) => {
    window.localStorage.setItem(TESTER_IDENTITY_STORAGE_KEY, storedValue)

    const store = createTesterIdentityStore()

    expect(store.identity.value.reporterId).toMatch(/^TESTER-[A-Z0-9-]+$/)
    expect(store.identity.value.reporterName).toBe('')
    expect(store.identity.value.defaultStoreCode).toBe('')
    expect(readPersistedIdentity()).toEqual(store.identity.value)
  })

  it('trims editable values before keeping them in memory or storage', () => {
    const store = createTesterIdentityStore()

    store.save('  小白测试员  ', '  PDD-SM  ')

    expect(store.identity.value.reporterName).toBe('小白测试员')
    expect(store.identity.value.defaultStoreCode).toBe('PDD-SM')
    expect(readPersistedIdentity()).toEqual(store.identity.value)
  })

  it('reloads the current valid storage value', () => {
    const store = createTesterIdentityStore()
    const reporterId = store.identity.value.reporterId
    window.localStorage.setItem(
      TESTER_IDENTITY_STORAGE_KEY,
      JSON.stringify({
        reporterId,
        reporterName: '重新载入',
        defaultStoreCode: 'PDD-OTHER',
        customerQuestion: '不得持久化的建议正文'
      })
    )

    store.reload()

    expect(store.identity.value).toEqual({
      reporterId,
      reporterName: '重新载入',
      defaultStoreCode: 'PDD-OTHER'
    })
    expect(readPersistedIdentity()).toEqual(store.identity.value)
    expect(window.localStorage.getItem(TESTER_IDENTITY_STORAGE_KEY)).not.toContain('customerQuestion')
  })
})
