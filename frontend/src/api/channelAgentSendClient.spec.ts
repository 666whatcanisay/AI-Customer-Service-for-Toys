import { afterEach, describe, expect, it, vi } from 'vitest'

import { channelAgentSendClient } from './channelAgentSendClient'

describe('channelAgentSendClient', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('marks every direct-send request as an explicit human-confirmed action', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      contract_version: '1.0',
      decision_id: 'decision-1',
      approval_id: 'approval-1',
      execution_id: 'execution-1',
      receipt_id: 'receipt-1',
      outcome: 'SUCCESS',
      customer_message_sent: true,
      automatic_retry_allowed: false,
      manual_intervention_required: false,
      error_code: null
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    }))
    vi.stubGlobal('fetch', fetchMock)

    await channelAgentSendClient.approveAndSend({
      contractVersion: '1.0',
      decisionId: 'decision-1',
      conversationId: 'conversation-1',
      customerMessageId: 'message-1',
      replyText: '人工确认后的回复',
      operatorReference: 'operator-1',
      confirmationPhrase: 'CONFIRM SEND decision-1',
      idempotencyKey: 'pdd-controlled-send:decision-1',
      confirmedAt: '2026-08-07T17:55:00+08:00'
    })

    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/channel-agent-api/v1/approved-replies')
    expect(init.method).toBe('POST')
    expect(new Headers(init.headers).get('X-Channel-Agent-Intent'))
      .toBe('HUMAN_CONFIRMED_SEND')
    expect(JSON.parse(String(init.body))).toMatchObject({
      decision_id: 'decision-1',
      confirmation_phrase: 'CONFIRM SEND decision-1',
      idempotency_key: 'pdd-controlled-send:decision-1'
    })
  })
})
