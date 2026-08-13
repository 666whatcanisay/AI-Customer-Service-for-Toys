export type ChannelAgentBootstrap = {
  schema_version: string
  csrf_token: string
  assistant_event_cursor?: number
  agent: {
    process_status: string
    runtime_status: string
    version: string
    node_id: string | null
  }
  browser: {
    status: string
    pdd_login_state: string | null
    pdd_workspace_launch_available?: boolean
    pdd_workspace_refresh_available?: boolean
    observer_status?: string
    observer_restart_available?: boolean
    message_source?: 'REAL_PDD' | 'OFFLINE_REPLAY' | 'DISABLED'
    real_pdd_message_observation_enabled?: boolean
  }
  binding: {
    agent_id: string | null
    device_id: string | null
    identity_status: 'UNBOUND' | 'REGISTERED' | 'BOUND' | 'ACTIVE' | 'DISABLED'
    production_eligible: boolean
    authorized_store_ids: string[]
    active_store_id: string | null
    observed_store_id: string | null
    store_reference: string | null
    secure_control_ready: boolean
  }
  safety: {
    manual_approval: true
    auto_reply: false
    real_send_enabled: boolean
  }
}

let localCsrfToken = ''

export function channelAgentLocalSecurityHeaders(): Record<string, string> {
  return localCsrfToken ? { 'X-Channel-Agent-CSRF': localCsrfToken } : {}
}

export async function selectChannelAgentActiveStore(storeReference: string): Promise<void> {
  const response = await fetch('/local-api/v1/active-store', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-Channel-Agent-Intent': 'HUMAN_CONFIRMED_STORE_SELECTION',
      ...channelAgentLocalSecurityHeaders()
    },
    body: JSON.stringify({
      store_reference: storeReference,
      reason: '客服在桌面助手中人工切换当前工作店铺'
    })
  })
  if (!response.ok) throw new Error(`CHANNEL_AGENT_ACTIVE_STORE_${response.status}`)
}

export async function fetchChannelAgentBootstrap(): Promise<ChannelAgentBootstrap> {
  const response = await fetch('/local-api/v1/bootstrap', {
    credentials: 'same-origin',
    headers: { Accept: 'application/json' }
  })
  if (!response.ok) {
    // Never keep a process-old CSRF token after the local Agent has restarted.
    localCsrfToken = ''
    throw new Error(`CHANNEL_AGENT_BOOTSTRAP_${response.status}`)
  }
  const payload = await response.json() as ChannelAgentBootstrap
  localCsrfToken = payload.csrf_token
  return payload
}

export async function requestChannelAgentSafeStop(): Promise<void> {
  const response = await fetch('/local-api/v1/runtime/safe-stop', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      ...channelAgentLocalSecurityHeaders()
    }
  })
  if (!response.ok) throw new Error(`CHANNEL_AGENT_STOP_${response.status}`)
}

export type ChannelAgentPddWindowLaunch = {
  schema_version: 'channel-agent-pdd-window-launch.v1'
  status: 'OPENING' | 'READY'
  browser_status: string
  pdd_login_state: string | null
  human_login_required: true
  observer_started: false
  real_send_enabled: false
}

export function requestChannelAgentPddWindowOpen(): Promise<ChannelAgentPddWindowLaunch> {
  return localJson('/local-api/v1/browser/pdd/open', {
    method: 'POST',
    headers: { 'X-Channel-Agent-Intent': 'HUMAN_REQUESTED_PDD_WINDOW' },
    body: '{}'
  })
}

export type ChannelAgentPddWorkspaceRefresh = {
  schema_version: 'channel-agent-pdd-workspace-refresh.v1'
  status: 'OPENING' | 'READY' | 'REFRESHING'
  browser_status: string
  pdd_login_state: string | null
  observer_started: false
  real_send_enabled: false
}

export function requestChannelAgentPddWorkspaceRefresh(): Promise<ChannelAgentPddWorkspaceRefresh> {
  return localJson('/local-api/v1/browser/pdd/refresh', {
    method: 'POST',
    headers: { 'X-Channel-Agent-Intent': 'HUMAN_CONFIRMED_PDD_WORKSPACE_READY' },
    body: '{}'
  })
}

export function requestChannelAgentPddObserverRestart(): Promise<{
  status: 'RESTART_REQUESTED' | 'ALREADY_REQUESTED'
  real_send_enabled: false
}> {
  return localJson('/local-api/v1/observer/pdd/restart', {
    method: 'POST',
    headers: { 'X-Channel-Agent-Intent': 'HUMAN_CONFIRMED_PDD_OBSERVER_RESTART' },
    body: '{}'
  })
}

export type DoctorStatus = 'PASS' | 'WARNING' | 'BLOCKED'

export type DoctorComponent = {
  component: string
  status: DoctorStatus
  status_label: string
  error_code: string
  reason: string
  checked_at: string
  repairable: boolean
  next_action: string
  scope: 'LOGIN' | 'ONBOARDING' | 'RUNTIME'
  technical: Record<string, unknown>
}

export type ChannelAgentDoctor = {
  schema_version: string
  overall: DoctorStatus
  checked_at: string
  mode: 'QUICK' | 'DEEP'
  auto_expand: boolean
  safe_to_continue: boolean
  login_allowed: boolean
  sanitized: true
  components: DoctorComponent[]
}

export type ChannelAgentConfigCenter = {
  schema_version: string
  status: DoctorStatus
  basic: Record<string, unknown>
  advanced: Record<string, unknown>
  read_only: Record<string, unknown>
  safety: {
    manual_approval_required: true
    auto_reply_enabled: false
    real_send_enabled: false
    real_platform_activation_allowed: false
  }
  advanced_confirmation_phrase?: string
  error?: { code: string; message: string }
}

type ConfigPayload = {
  changes: Record<string, unknown>
  advanced_confirmation?: string
}

async function localJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = String(init.method ?? 'GET').toUpperCase()
  const csrfHeaders = method === 'GET' || method === 'HEAD'
    ? {}
    : channelAgentLocalSecurityHeaders()
  const response = await fetch(path, {
    credentials: 'same-origin',
    ...init,
    headers: { Accept: 'application/json', ...csrfHeaders, ...(init.headers ?? {}) }
  })
  const body = await response.json().catch(() => ({})) as Record<string, unknown>
  if (!response.ok) {
    const error = new Error(`CHANNEL_AGENT_LOCAL_${response.status}`) as Error & {
      status?: number
      body?: Record<string, unknown>
    }
    error.status = response.status
    error.body = body
    throw error
  }
  return body as T
}

export function fetchChannelAgentDoctor(deep = false): Promise<ChannelAgentDoctor> {
  return localJson(`/local-api/v1/doctor${deep ? '?deep=1' : ''}`)
}

export function fetchChannelAgentConfig(): Promise<ChannelAgentConfigCenter> {
  return localJson('/local-api/v1/config')
}

export function validateChannelAgentConfig(payload: ConfigPayload): Promise<Record<string, unknown>> {
  return localJson('/local-api/v1/config/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}

export function saveChannelAgentConfig(payload: ConfigPayload): Promise<Record<string, unknown>> {
  return localJson('/local-api/v1/config', {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'X-Channel-Agent-Intent': 'HUMAN_CONFIRMED_CONFIGURATION'
    },
    body: JSON.stringify(payload)
  })
}

export function startChannelAgentRepair(): Promise<{ repair_id: string; status: string }> {
  return localJson('/local-api/v1/repair', {
    method: 'POST',
    headers: { 'X-Channel-Agent-Intent': 'HUMAN_CONFIRMED_REPAIR' },
    body: '{}'
  })
}

export function fetchChannelAgentRepair(repairId: string): Promise<Record<string, unknown>> {
  return localJson(`/local-api/v1/repair/${encodeURIComponent(repairId)}`)
}

export type ChannelAgentEnrollmentResult = {
  schema_version: 'channel-agent-local-enrollment.v1'
  agent_id: string
  device_id: string
  identity_status: 'BOUND' | 'ACTIVE'
  authorized_store_ids: string[]
  active_store_id: string | null
  binding_revision: number
  production_eligible: boolean
}

export function enrollChannelAgentDevice(bindingCode: string): Promise<ChannelAgentEnrollmentResult> {
  return localJson('/local-api/v1/enrollment', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Channel-Agent-Intent': 'HUMAN_CONFIRMED_DEVICE_BINDING'
    },
    body: JSON.stringify({ binding_code: bindingCode })
  })
}

export function syncChannelAgentIdentity(): Promise<ChannelAgentEnrollmentResult> {
  return localJson('/local-api/v1/identity/sync', {
    method: 'POST',
    headers: { 'X-Channel-Agent-Intent': 'HUMAN_CONFIRMED_DEVICE_BINDING' },
    body: '{}'
  })
}

export function discoverChannelAgentHosts(): Promise<{ hosts: Array<Record<string, unknown>> }> {
  return localJson('/local-api/v1/onboarding/discover', { method: 'POST', body: '{}' })
}

export function pairChannelAgentHost(payload: {
  host_id: string
  pairing_code: string
  human_confirmed: true
}): Promise<Record<string, unknown>> {
  return localJson('/local-api/v1/onboarding/pair', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Channel-Agent-Intent': 'HUMAN_CONFIRMED_CONFIGURATION'
    },
    body: JSON.stringify(payload)
  })
}
