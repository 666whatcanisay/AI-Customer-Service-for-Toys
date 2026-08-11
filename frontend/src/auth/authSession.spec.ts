import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpPost = vi.hoisted(() => vi.fn())
const httpGet = vi.hoisted(() => vi.fn())
const httpPut = vi.hoisted(() => vi.fn())
const httpCreate = vi.hoisted(() => vi.fn(() => ({
  post: httpPost,
  get: httpGet,
  put: httpPut
})))
const localSecurityHeaders = vi.hoisted(() => vi.fn(() => ({
  'X-Channel-Agent-CSRF': 'local-csrf-test'
})))
const fetchBootstrap = vi.hoisted(() => vi.fn())

vi.mock('axios', () => ({
  default: { create: httpCreate }
}))

vi.mock('@/api/channelAgentDesktopClient', () => ({
  channelAgentLocalSecurityHeaders: localSecurityHeaders,
  fetchChannelAgentBootstrap: fetchBootstrap
}))

import { authSessionTestControl, useAuthSession } from './authSession'

const activeUser = {
  id: 'user-1',
  username: 'support.one',
  display_name: '客服一号',
  status: 'ACTIVE' as const,
  roles: ['CUSTOMER_SERVICE' as const],
  permissions: ['workspace.access'],
  stores: [],
  created_at: '2026-08-08T00:00:00Z',
  updated_at: '2026-08-08T00:00:00Z'
}

describe('customer auth local proxy security', () => {
  beforeEach(() => {
    httpPost.mockReset()
    httpGet.mockReset()
    httpPut.mockReset()
    localSecurityHeaders.mockClear()
    fetchBootstrap.mockReset()
    fetchBootstrap.mockResolvedValue({ csrf_token: 'local-csrf-test' })
    authSessionTestControl.reset()
  })

  it('sends the ChannelAgent CSRF header with login credentials', async () => {
    httpPost.mockResolvedValue({
      data: {
        schema_version: 'ai-cs.iam.v1',
        token_type: 'Bearer',
        access_token: 'access-token',
        expires_at: '2026-08-08T01:00:00Z',
        user: activeUser
      }
    })

    await useAuthSession().login('support.one', 'not-a-real-secret')

    if (import.meta.env.VITE_CHANNEL_AGENT_DESKTOP === 'true') {
      expect(fetchBootstrap).toHaveBeenCalledOnce()
    } else {
      expect(fetchBootstrap).not.toHaveBeenCalled()
    }
    expect(httpPost).toHaveBeenCalledWith(
      '/api/v1/auth/login',
      { username: 'support.one', password: 'not-a-real-secret' },
      { headers: { 'X-Channel-Agent-CSRF': 'local-csrf-test' } }
    )
  })

  it('sends both authorization and local CSRF headers for account mutations', async () => {
    authSessionTestControl.setUser(activeUser, 'access-token')
    httpPost.mockResolvedValue({ data: {} })

    await useAuthSession().changePassword('old-value', 'new-value')

    expect(httpPost).toHaveBeenCalledWith(
      '/api/v1/auth/change-password',
      { current_password: 'old-value', new_password: 'new-value' },
      { headers: {
        Authorization: 'Bearer access-token',
        'X-Channel-Agent-CSRF': 'local-csrf-test'
      } }
    )
  })
})
