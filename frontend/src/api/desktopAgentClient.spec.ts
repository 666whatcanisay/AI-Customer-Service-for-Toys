import { describe, expect, it } from 'vitest'

import { mapDesktopAgentError } from './desktopAgentClient'


describe('desktopAgentClient error mapping', () => {
  it('preserves the server error code and request id for sanitized diagnostics', () => {
    const mapped = mapDesktopAgentError({
      isAxiosError: true,
      response: {
        status: 502,
        data: {
          error: {
            code: 'CHANNEL_AGENT_RESPONSE_INVALID',
            message: 'internal message must not be shown directly'
          },
          request_id: 'request-safe-001'
        }
      }
    })

    expect(mapped.kind).toBe('contract')
    expect(mapped.status).toBe(502)
    expect(mapped.code).toBe('CHANNEL_AGENT_RESPONSE_INVALID')
    expect(mapped.requestId).toBe('request-safe-001')
    expect(mapped.message).toContain('版本不兼容')
    expect(mapped.message).not.toContain('internal message')
  })

  it('does not misreport service failures as password failures', () => {
    const mapped = mapDesktopAgentError({
      isAxiosError: true,
      response: {
        status: 503,
        data: {
          error: { code: 'CHANNEL_AGENT_OPERATOR_PERMISSION_INVALID' },
          request_id: 'request-safe-002'
        }
      }
    })

    expect(mapped.kind).toBe('permission_invalid')
    expect(mapped.message).toContain('接入权限')
    expect(mapped.message).not.toContain('密码')
  })
})
