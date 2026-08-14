import axios from 'axios'
import { computed, readonly, ref } from 'vue'

import { resetReplyReadinessDebugState } from '../stores/replyReadinessDebug'

export type RoleName = 'ADMIN' | 'OPERATOR' | 'CUSTOMER_SERVICE'
export interface AuthStoreBinding { id: number; store_id: number; store_code: string; store_name: string; platform: string; is_default: boolean }
export interface AuthUser {
  id: string; username: string; display_name: string; status: 'ACTIVE' | 'DISABLED'
  roles: RoleName[]; permissions: string[]; stores: AuthStoreBinding[]
  must_change_password?: boolean; all_store_access?: boolean
  created_at: string; updated_at: string
}

const STORAGE_KEY = 'ai-cs-admin-session-v1'
const API_BASE_URL = import.meta.env.VITE_PLATFORM_API_BASE_URL || '/platform-api'
const http = axios.create({ baseURL: API_BASE_URL, timeout: 15_000 })
const token = ref('')
const user = ref<AuthUser | null>(null)
const initialized = ref(false)

function storedToken(): string {
  try { return sessionStorage.getItem(STORAGE_KEY)?.trim() ?? '' } catch { return '' }
}
function persist(value: string): void {
  try { value ? sessionStorage.setItem(STORAGE_KEY, value) : sessionStorage.removeItem(STORAGE_KEY) } catch { /* in-memory fallback */ }
}
export function authorizationHeader(): Record<string, string> {
  return token.value ? { Authorization: `Bearer ${token.value}` } : {}
}
export function clearAdminSession(): void {
  token.value = ''; user.value = null; initialized.value = true; persist(''); resetReplyReadinessDebugState()
}

async function restore(): Promise<boolean> {
  if (initialized.value) return user.value !== null
  const stored = storedToken()
  if (!stored) { initialized.value = true; return false }
  token.value = stored
  try {
    const response = await http.get<{ user: AuthUser }>('/api/v1/auth/me', { headers: authorizationHeader() })
    user.value = response.data.user; initialized.value = true; return true
  } catch { clearAdminSession(); return false }
}
async function login(username: string, password: string): Promise<AuthUser> {
  const response = await http.post<{ access_token: string; user: AuthUser }>('/api/v1/auth/login', { username, password })
  token.value = response.data.access_token; user.value = response.data.user; initialized.value = true; persist(token.value)
  return response.data.user
}
async function logout(): Promise<void> {
  try { if (token.value) await http.post('/api/v1/auth/logout', undefined, { headers: authorizationHeader() }) }
  finally { clearAdminSession() }
}
async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await http.post('/api/v1/auth/change-password', {
    current_password: currentPassword, new_password: newPassword,
  }, { headers: authorizationHeader() })
  clearAdminSession()
}

export function useAdminSession() {
  return {
    token: readonly(token), user: readonly(user), initialized: readonly(initialized),
    displayName: computed(() => user.value?.display_name ?? ''), login, logout, restore, changePassword,
    hasPermission: (permission: string) => user.value?.permissions.includes(permission) === true,
    hasAnyPermission: (permissions: string[]) => permissions.some((item) => user.value?.permissions.includes(item))
  }
}

export const adminSessionTestControl = {
  setUser(value: AuthUser | null, accessToken = 'test-token') { user.value = value; token.value = value ? accessToken : ''; initialized.value = true },
  reset() { token.value = ''; user.value = null; initialized.value = false; persist(''); resetReplyReadinessDebugState() }
}
