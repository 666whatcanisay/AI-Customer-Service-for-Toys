import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpGet = vi.hoisted(() => vi.fn())
const httpPut = vi.hoisted(() => vi.fn())
const httpPost = vi.hoisted(() => vi.fn())
const requestUse = vi.hoisted(() => vi.fn())
const responseUse = vi.hoisted(() => vi.fn())

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      get: httpGet,
      put: httpPut,
      post: httpPost,
      interceptors: {
        request: { use: requestUse },
        response: { use: responseUse }
      }
    })),
    isAxiosError: () => false,
    isCancel: () => false
  }
}))

import { offlineReplyControlClient } from './offlineReplyControlClient'

describe('offlineReplyControlClient', () => {
  beforeEach(() => {
    httpGet.mockReset()
    httpPut.mockReset()
    httpPost.mockReset()
  })

  it('loads and human-confirms the reply policy with revision control', async () => {
    httpGet.mockResolvedValue({ data: {
      store_id: 'STORE-1', mode: 'MANUAL_CONFIRM', revision: 3,
      updated_by: 'operator-1', updated_at: '2026-08-11T10:00:00Z'
    } })
    httpPut.mockResolvedValue({ data: {
      store_id: 'STORE-1', mode: 'AUTO_LOW_RISK', revision: 4,
      updated_by: 'operator-1', updated_at: '2026-08-11T10:01:00Z'
    } })

    await expect(offlineReplyControlClient.getPolicy(8)).resolves.toMatchObject({
      storeId: 'STORE-1', mode: 'MANUAL_CONFIRM', revision: 3
    })
    await expect(offlineReplyControlClient.setPolicy({
      storeId: 8, mode: 'AUTO_LOW_RISK', expectedRevision: 3
    })).resolves.toMatchObject({ mode: 'AUTO_LOW_RISK', revision: 4 })
    expect(httpPut).toHaveBeenCalledWith('/api/v1/workspace/reply-policy', {
      store_id: 8, mode: 'AUTO_LOW_RISK', expected_revision: 3, human_confirmed: true
    })
  })

  it('prepares execution without accepting any real-send side effect', async () => {
    httpPost.mockResolvedValue({ data: {
      preparation_version: '1.0', preparation_id: `execution-preparation:${'a'.repeat(64)}`,
      decision_id: 'decision-1', trace_id: `trace:${'b'.repeat(64)}`, store_id: 'STORE-1',
      conversation_id: 'conversation-1', customer_reference: `sha256:${'c'.repeat(64)}`,
      conversation_revision: 2, policy_mode: 'MANUAL_CONFIRM', policy_revision: 1,
      authorization_kind: 'HUMAN', authorized_by: 'operator-1', state: 'READY',
      prepared_at: '2026-08-11T10:00:00Z', expires_at: '2026-08-11T10:05:00Z',
      real_send_enabled: false, external_side_effect: false
    } })
    const customerReference = `sha256:${'c'.repeat(64)}`

    await expect(offlineReplyControlClient.prepareExecution({
      decisionId: 'decision/1', storeId: 8, conversationId: 'conversation-1', customerReference
    })).resolves.toMatchObject({
      state: 'READY', realSendEnabled: false, externalSideEffect: false
    })
    expect(httpPost).toHaveBeenCalledWith(
      '/api/v1/workspace/decisions/decision%2F1/execution-preparations',
      { store_id: 8, conversation_id: 'conversation-1', customer_reference: customerReference, human_confirmed: true }
    )
  })

  it('fails closed if a preparation response claims a real side effect', async () => {
    httpPost.mockResolvedValue({ data: {
      real_send_enabled: true, external_side_effect: true
    } })
    await expect(offlineReplyControlClient.prepareExecution({
      decisionId: 'decision-1', storeId: 8, conversationId: 'conversation-1',
      customerReference: `sha256:${'c'.repeat(64)}`
    })).rejects.toBeInstanceOf(Error)
  })
})
