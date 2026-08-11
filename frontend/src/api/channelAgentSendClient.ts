import { channelAgentLocalSecurityHeaders } from './channelAgentDesktopClient'

export type ChannelAgentSendOutcome = 'SUCCESS' | 'FAILED' | 'UNKNOWN'

export interface ChannelAgentApprovedReplyRequest {
  contractVersion: '1.0'
  decisionId: string
  conversationId: string
  customerMessageId: string
  replyText: string
  operatorReference: string
  confirmationPhrase: string
  idempotencyKey: string
  confirmedAt: string
}

export interface ChannelAgentApprovedReplyResponse {
  contract_version: '1.0'
  decision_id: string
  approval_id: string
  execution_id: string
  receipt_id: string
  outcome: ChannelAgentSendOutcome
  customer_message_sent: boolean
  automatic_retry_allowed: false
  manual_intervention_required: boolean
  error_code: string | null
}

const errorLabels: Record<string, string> = {
  PDD_CONTROLLED_SEND_DISABLED: '当前客服电脑尚未启用受控发送。',
  PDD_SEND_CONFIRMATION_EXPIRED: '本次人工确认已过期，请重新核对后再发送。',
  PDD_SEND_REPLY_PACKAGE_MISMATCH: '当前 AI 回复已变化，请重新核对。',
  PDD_SEND_CURRENT_TARGET_MISMATCH: 'PDD 当前店铺、会话或客户已变化，已拒绝发送。',
  PDD_SEND_PRODUCT_CHANGED: 'PDD 当前商品已变化，已拒绝发送。',
  PDD_SEND_INPUT_NOT_EMPTY: 'PDD 回复框已有客服输入内容，已拒绝覆盖。',
  PDD_SEND_SELECTOR_MISMATCH: 'PDD 页面结构发生变化，已停止发送。',
  PDD_SEND_RECEIPT_MISSING: '执行未生成回执，已停止，请人工检查。'
}

export class ChannelAgentSendError extends Error {
  constructor(public readonly code: string) {
    super(errorLabels[code] ?? 'Channel Agent 受控发送失败，请核对 PDD 当前窗口。')
  }
}

export const channelAgentSendClient = {
  async approveAndSend(
    request: ChannelAgentApprovedReplyRequest
  ): Promise<ChannelAgentApprovedReplyResponse> {
    const response = await fetch('/channel-agent-api/v1/approved-replies', {
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-Channel-Agent-Intent': 'HUMAN_CONFIRMED_SEND',
        ...channelAgentLocalSecurityHeaders()
      },
      body: JSON.stringify({
        contract_version: request.contractVersion,
        decision_id: request.decisionId,
        conversation_id: request.conversationId,
        customer_message_id: request.customerMessageId,
        reply_text: request.replyText,
        operator_reference: request.operatorReference,
        confirmation_phrase: request.confirmationPhrase,
        idempotency_key: request.idempotencyKey,
        confirmed_at: request.confirmedAt
      })
    })
    const payload: unknown = await response.json().catch(() => ({}))
    if (!response.ok) {
      const code = payload && typeof payload === 'object' && 'error_code' in payload
        ? String(payload.error_code)
        : 'CHANNEL_AGENT_SEND_FAILED'
      throw new ChannelAgentSendError(code)
    }
    return payload as ChannelAgentApprovedReplyResponse
  }
}
