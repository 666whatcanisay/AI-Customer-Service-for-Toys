export type DesktopAssociationState =
  | 'READY'
  | 'BINDING_REQUIRED'
  | 'ACTIVATION_REQUIRED'
  | 'STORE_MISMATCH'
  | 'MULTIPLE_MATCHES'
  | 'DISABLED'

export type DesktopAgentOnlineStatus = 'ONLINE' | 'DEGRADED' | 'OFFLINE'
export type DesktopAgentIdentityStatus = 'UNBOUND' | 'BOUND' | 'ACTIVE' | 'DISABLED'

export interface DesktopAgentProjection {
  agentId: string
  deviceId: string
  deviceName: string | null
  agentVersion: string | null
  identityStatus: DesktopAgentIdentityStatus
  onlineStatus: DesktopAgentOnlineStatus
  runtimeStatus: string
  productionEligible: boolean
  bindingRevision: number
  lastHeartbeat: string | null
}

export interface DesktopAgentStatus {
  userId: string
  storeId: number
  storeCode: string
  associationState: DesktopAssociationState
  agent: DesktopAgentProjection | null
  checkedAt: string
}

export interface DesktopBindingGrant {
  grantId: string
  agentId: string
  deviceId: string
  bindingCode: string
  expiresAt: string
}

export type DesktopAgentErrorKind =
  | 'canceled'
  | 'timeout'
  | 'not_configured'
  | 'server_unreachable'
  | 'permission_invalid'
  | 'authorization_denied'
  | 'contract'
  | 'rejected'
  | 'unknown'

export class DesktopAgentClientError extends Error {
  constructor(
    public readonly kind: DesktopAgentErrorKind,
    message: string,
    public readonly status: number | null = null
  ) {
    super(message)
    this.name = 'DesktopAgentClientError'
  }
}
