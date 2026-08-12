import { createAuthenticatedHttp } from './authenticatedHttp'
import { toPlatformClientError } from './errorMapper'

const configuredBaseUrl = (import.meta.env.VITE_PLATFORM_API_BASE_URL || '/platform-api')
  .trim().replace(/\/$/, '')
const http = createAuthenticatedHttp({ baseURL: configuredBaseUrl, timeout: 15_000 })

export type ReplyPolicyMode = 'MANUAL_CONFIRM' | 'AUTO_LOW_RISK'

export interface ReplyPolicy {
  storeId: string
  mode: ReplyPolicyMode
  revision: number
  updatedBy: string
  updatedAt: string
}

export interface ExecutionPreparation {
  preparationVersion: '1.0'
  preparationId: string
  decisionId: string
  traceId: string
  storeId: string
  conversationId: string
  customerReference: string
  conversationRevision: number
  policyMode: ReplyPolicyMode
  policyRevision: number
  authorizationKind: 'HUMAN' | 'AUTO_POLICY'
  authorizedBy: string
  state: 'READY' | 'INVALIDATED' | 'EXPIRED' | 'CONSUMED'
  preparedAt: string
  expiresAt: string
  realSendEnabled: false
  externalSideEffect: false
}

const adaptPolicy = (value: Record<string, unknown>): ReplyPolicy => {
  if (value.mode !== 'MANUAL_CONFIRM' && value.mode !== 'AUTO_LOW_RISK') {
    throw new Error('OFFLINE_REPLY_POLICY_INVALID')
  }
  return {
    storeId: String(value.store_id),
    mode: value.mode,
    revision: Number(value.revision),
    updatedBy: String(value.updated_by),
    updatedAt: String(value.updated_at)
  }
}

const adaptPreparation = (value: Record<string, unknown>): ExecutionPreparation => {
  if (value.real_send_enabled !== false || value.external_side_effect !== false) {
    throw new Error('OFFLINE_EXECUTION_SAFETY_FACTS_INVALID')
  }
  return {
    preparationVersion: value.preparation_version as '1.0',
    preparationId: String(value.preparation_id),
    decisionId: String(value.decision_id),
    traceId: String(value.trace_id),
    storeId: String(value.store_id),
    conversationId: String(value.conversation_id),
    customerReference: String(value.customer_reference),
    conversationRevision: Number(value.conversation_revision),
    policyMode: value.policy_mode as ReplyPolicyMode,
    policyRevision: Number(value.policy_revision),
    authorizationKind: value.authorization_kind as 'HUMAN' | 'AUTO_POLICY',
    authorizedBy: String(value.authorized_by),
    state: value.state as ExecutionPreparation['state'],
    preparedAt: String(value.prepared_at),
    expiresAt: String(value.expires_at),
    realSendEnabled: false,
    externalSideEffect: false
  }
}

export const offlineReplyControlClient = {
  async getPolicy(storeId: number): Promise<ReplyPolicy> {
    try {
      const response = await http.get('/api/v1/workspace/reply-policy', {
        params: { store_id: storeId }
      })
      return adaptPolicy(response.data as Record<string, unknown>)
    } catch (error) { throw toPlatformClientError(error) }
  },

  async setPolicy(request: {
    storeId: number
    mode: ReplyPolicyMode
    expectedRevision: number | null
  }): Promise<ReplyPolicy> {
    try {
      const response = await http.put('/api/v1/workspace/reply-policy', {
        store_id: request.storeId,
        mode: request.mode,
        expected_revision: request.expectedRevision,
        human_confirmed: true
      })
      return adaptPolicy(response.data as Record<string, unknown>)
    } catch (error) { throw toPlatformClientError(error) }
  },

  async prepareExecution(request: {
    decisionId: string
    storeId: number
    conversationId: string
    customerReference: string
  }): Promise<ExecutionPreparation> {
    try {
      const response = await http.post(
        `/api/v1/workspace/decisions/${encodeURIComponent(request.decisionId)}/execution-preparations`,
        {
          store_id: request.storeId,
          conversation_id: request.conversationId,
          customer_reference: request.customerReference,
          human_confirmed: true
        }
      )
      return adaptPreparation(response.data as Record<string, unknown>)
    } catch (error) { throw toPlatformClientError(error) }
  }
}
