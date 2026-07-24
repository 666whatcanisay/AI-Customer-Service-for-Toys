import { inject, ref, type InjectionKey, type Ref } from 'vue'

export const TESTER_IDENTITY_STORAGE_KEY = 'mumu-customer-workspace:tester-identity'

export interface TesterIdentity {
  reporterId: string
  reporterName: string
  defaultStoreCode: string
}

export interface TesterIdentityStore {
  identity: Ref<TesterIdentity>
  save: (reporterName: string, defaultStoreCode: string) => void
  reload: () => void
}

export const TesterIdentityKey: InjectionKey<TesterIdentityStore> = Symbol('testerIdentity')
export const testerIdentityKey = TesterIdentityKey

const TESTER_ID_PATTERN = /^TESTER-[A-Z0-9-]+$/

function createReporterId(): string {
  const randomPart =
    typeof globalThis.crypto?.randomUUID === 'function'
      ? globalThis.crypto.randomUUID().replace(/-/g, '').slice(0, 16).toUpperCase()
      : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`.toUpperCase()

  return `TESTER-${randomPart}`
}

function createEmptyIdentity(): TesterIdentity {
  return {
    reporterId: createReporterId(),
    reporterName: '',
    defaultStoreCode: ''
  }
}

function parseIdentity(rawValue: string | null): TesterIdentity | null {
  if (!rawValue) return null

  try {
    const value: unknown = JSON.parse(rawValue)
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null

    const candidate = value as Record<string, unknown>
    if (
      typeof candidate.reporterId !== 'string' ||
      typeof candidate.reporterName !== 'string' ||
      typeof candidate.defaultStoreCode !== 'string'
    ) {
      return null
    }

    const reporterId = candidate.reporterId.trim()
    if (!TESTER_ID_PATTERN.test(reporterId)) return null

    return {
      reporterId,
      reporterName: candidate.reporterName.trim(),
      defaultStoreCode: candidate.defaultStoreCode.trim()
    }
  } catch {
    return null
  }
}

function readStoredIdentity(): TesterIdentity | null {
  try {
    return parseIdentity(globalThis.localStorage?.getItem(TESTER_IDENTITY_STORAGE_KEY) ?? null)
  } catch {
    return null
  }
}

function persistIdentity(identity: TesterIdentity): void {
  try {
    globalThis.localStorage?.setItem(
      TESTER_IDENTITY_STORAGE_KEY,
      JSON.stringify({
        reporterId: identity.reporterId,
        reporterName: identity.reporterName,
        defaultStoreCode: identity.defaultStoreCode
      })
    )
  } catch {
    // Storage can be unavailable in restricted browser modes; the in-memory ref remains usable.
  }
}

export function createTesterIdentityStore(): TesterIdentityStore {
  const initialIdentity = readStoredIdentity() ?? createEmptyIdentity()
  const identity = ref<TesterIdentity>(initialIdentity)
  persistIdentity(initialIdentity)

  function save(reporterName: string, defaultStoreCode: string): void {
    const nextIdentity: TesterIdentity = {
      reporterId: identity.value.reporterId,
      reporterName: reporterName.trim(),
      defaultStoreCode: defaultStoreCode.trim()
    }

    identity.value = nextIdentity
    persistIdentity(nextIdentity)
  }

  function reload(): void {
    const nextIdentity = readStoredIdentity() ?? createEmptyIdentity()
    identity.value = nextIdentity
    persistIdentity(nextIdentity)
  }

  return { identity, save, reload }
}

export function useTesterIdentity(): TesterIdentityStore {
  const store = inject(TesterIdentityKey)
  if (!store) {
    throw new Error('Tester identity store has not been provided.')
  }
  return store
}
