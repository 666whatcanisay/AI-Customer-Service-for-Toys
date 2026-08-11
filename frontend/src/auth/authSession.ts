import axios from 'axios'
import { computed, readonly, ref } from 'vue'
import {
  channelAgentLocalSecurityHeaders,
  fetchChannelAgentBootstrap
} from '@/api/channelAgentDesktopClient'

export type RoleName = 'ADMIN' | 'OPERATOR' | 'CUSTOMER_SERVICE'

export interface AuthStorePlatformBinding {
  platform: string
  platform_store_id: string
  status: 'ACTIVE' | 'REVOKED'
  verified_at: string
  verified_by: string
}

export interface AuthStoreBinding {
  id: number
  store_id: number
  store_code: string
  store_name: string
  platform: string
  is_default: boolean
  platform_bindings?: AuthStorePlatformBinding[]
}

export interface AuthUser {
  id: string
  username: string
  display_name: string
  status: 'ACTIVE' | 'DISABLED'
  roles: RoleName[]
  permissions: string[]
  stores: AuthStoreBinding[]
  must_change_password?: boolean
  all_store_access?: boolean
  created_at: string
  updated_at: string
}

interface LoginResponse {
  schema_version: 'ai-cs.iam.v1'
  token_type: 'Bearer'
  access_token: string
  expires_at: string
  user: AuthUser
}

const STORAGE_KEY = 'ai-cs-customer-session-v1'
const API_BASE_URL = (import.meta.env.VITE_PLATFORM_API_BASE_URL || '/platform-api').replace(/\/$/, '')
const CHANNEL_AGENT_DESKTOP = import.meta.env.VITE_CHANNEL_AGENT_DESKTOP === 'true'
const authHttp = axios.create({ baseURL: API_BASE_URL, timeout: 15_000 })
const token = ref('')
const user = ref<AuthUser | null>(null)
const initialized = ref(false)

function readStoredToken(): string {
  try {
    return globalThis.sessionStorage?.getItem(STORAGE_KEY)?.trim() ?? ''
  } catch {
    return ''
  }
}

function storeToken(value: string): void {
  try {
    if (value) globalThis.sessionStorage?.setItem(STORAGE_KEY, value)
    else globalThis.sessionStorage?.removeItem(STORAGE_KEY)
  } catch {
    // The in-memory session remains usable in restricted browser modes.
  }
}

export function clearAuthSession(): void {
  token.value = ''
  user.value = null
  initialized.value = true
  storeToken('')
}

export function authorizationHeader(): Record<string, string> {
  return token.value ? { Authorization: `Bearer ${token.value}` } : {}
}

async function restore(): Promise<boolean> {
  if (initialized.value) return user.value !== null
  const stored = readStoredToken()
  if (!stored) {
    initialized.value = true
    return false
  }
  token.value = stored
  try {
    const response = await authHttp.get<{ user: AuthUser }>('/api/v1/auth/me', {
      headers: authorizationHeader()
    })
    user.value = response.data.user
    initialized.value = true
    return true
  } catch {
    clearAuthSession()
    return false
  }
}

async function login(username: string, password: string): Promise<AuthUser> {
  // Public login routes do not pass through the authenticated router guard.
  // Refresh the process-local CSRF immediately before submitting credentials so
  // an EXE restart can never leave the page using a token from the old runtime.
  if (CHANNEL_AGENT_DESKTOP) await fetchChannelAgentBootstrap()
  const response = await authHttp.post<LoginResponse>('/api/v1/auth/login', { username, password }, {
    headers: channelAgentLocalSecurityHeaders()
  })
  token.value = response.data.access_token
  user.value = response.data.user
  initialized.value = true
  storeToken(token.value)
  return response.data.user
}

async function logout(): Promise<void> {
  try {
    if (token.value) {
      await authHttp.post('/api/v1/auth/logout', undefined, {
        headers: { ...authorizationHeader(), ...channelAgentLocalSecurityHeaders() }
      })
    }
  } finally {
    clearAuthSession()
  }
}

async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await authHttp.post('/api/v1/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword
  }, { headers: { ...authorizationHeader(), ...channelAgentLocalSecurityHeaders() } })
  clearAuthSession()
}

export interface AuthStoreOption {
  store_id: number
  store_code: string
  store_name: string
  platform: string
  platform_bindings?: AuthStorePlatformBinding[]
}

async function listStoreOptions(): Promise<AuthStoreOption[]> {
  const response = await authHttp.get<{ items: AuthStoreOption[] }>('/api/v1/auth/store-options', {
    headers: authorizationHeader()
  })
  return response.data.items
}

async function replaceStoreBindings(storeIds: number[], defaultStoreId?: number): Promise<AuthUser> {
  const response = await authHttp.put<AuthUser>('/api/v1/auth/store-bindings', {
    store_ids: storeIds,
    default_store_id: defaultStoreId ?? storeIds[0]
  }, { headers: { ...authorizationHeader(), ...channelAgentLocalSecurityHeaders() } })
  user.value = response.data
  return response.data
}

async function setDefaultStore(storeId: number): Promise<AuthUser> {
  const response = await authHttp.put<AuthUser>('/api/v1/auth/default-store', {
    store_id: storeId
  }, { headers: { ...authorizationHeader(), ...channelAgentLocalSecurityHeaders() } })
  user.value = response.data
  return response.data
}

export function useAuthSession() {
  const defaultStore = computed(() => user.value?.stores.find((item) => item.is_default) ?? null)
  const requiresStoreSelection = computed(() =>
    user.value?.roles.includes('CUSTOMER_SERVICE') === true
      && !user.value.stores.some((item) => item.is_default)
  )
  return {
    token: readonly(token),
    user: readonly(user),
    initialized: readonly(initialized),
    defaultStore,
    requiresStoreSelection,
    login,
    logout,
    changePassword,
    listStoreOptions,
    replaceStoreBindings,
    setDefaultStore,
    restore,
    hasPermission: (permission: string) => user.value?.permissions.includes(permission) === true
  }
}

export const authSessionTestControl = {
  setUser(value: AuthUser | null, accessToken = 'test-token') {
    user.value = value
    token.value = value ? accessToken : ''
    initialized.value = true
  },
  reset() {
    token.value = ''
    user.value = null
    initialized.value = false
    storeToken('')
  }
}
