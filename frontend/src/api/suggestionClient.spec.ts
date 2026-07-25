import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpGet = vi.hoisted(() => vi.fn())
const httpPost = vi.hoisted(() => vi.fn())
const httpCreate = vi.hoisted(() => vi.fn(() => ({ get: httpGet, post: httpPost })))

vi.mock('axios', () => ({
  default: {
    create: httpCreate,
    isCancel: () => false,
    isAxiosError: () => false
  }
}))

import { PlatformClientError } from './errorMapper'
import { suggestionClient } from './suggestionClient'
import type { SuggestionDraft } from './suggestionTypes'

const draft: SuggestionDraft = {
  reporterId: 'agent-001',
  reporterName: '木木',
  storeCode: null,
  moduleKey: 'AI_CHAT',
  category: 'NEW_FEATURE',
  title: '增加快捷入口',
  description: '希望从首页直接进入。',
  frequency: 'OCCASIONAL',
  urgency: 'LOW'
}

describe('suggestionClient', () => {
  beforeEach(() => {
    httpGet.mockReset()
    httpPost.mockReset()
  })

  it('uses the platform base URL without any Mock fallback', () => {
    expect(httpCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        baseURL: '/platform-api',
        timeout: 15_000
      })
    )
  })

  it('posts the frozen payload to the single suggestion endpoint', async () => {
    httpPost.mockResolvedValue({
      data: { data: { suggestion_id: 'SUG-001', status: 'SUBMITTED' } }
    })

    await expect(suggestionClient.submit(draft)).resolves.toEqual({
      suggestionId: 'SUG-001',
      status: 'SUBMITTED'
    })
    expect(httpPost).toHaveBeenCalledWith(
      '/api/v1/customer-suggestions',
      {
        reporter_id: 'agent-001',
        reporter_name: '木木',
        store_code: null,
        module_key: 'AI_CHAT',
        category: 'NEW_FEATURE',
        title: '增加快捷入口',
        description: '希望从首页直接进入。',
        frequency: 'OCCASIONAL',
        urgency: 'LOW'
      },
      { signal: undefined }
    )
  })

  it('lists only the current reporter through reporter_id', async () => {
    httpGet.mockResolvedValue({ data: { items: [], total: 0 } })

    await expect(suggestionClient.listMine('agent-001')).resolves.toEqual({
      items: [],
      total: 0
    })
    expect(httpGet).toHaveBeenCalledWith('/api/v1/customer-suggestions', {
      signal: undefined,
      params: { reporter_id: 'agent-001' }
    })
  })

  it('maps adapter failures through the shared platform error mapper', async () => {
    httpGet.mockResolvedValue({
      data: {
        items: [
          {
            suggestion_id: 'SUG-002',
            reporter_id: 'agent-002',
            store_code: null,
            module_key: 'AI_CHAT',
            category: 'BUG',
            title: '串号记录',
            frequency: 'ONCE',
            urgency: 'LOW',
            status: 'SUBMITTED'
          }
        ],
        total: 1
      }
    })

    await expect(suggestionClient.listMine('agent-001')).rejects.toMatchObject({
      kind: 'contract'
    } satisfies Partial<PlatformClientError>)
  })

  it('surfaces a C-service failure without falling back to Mock data', async () => {
    httpPost.mockRejectedValue(new Error('C suggestion endpoint unavailable'))

    await expect(suggestionClient.submit(draft)).rejects.toMatchObject({
      kind: 'unknown',
      message: 'C suggestion endpoint unavailable'
    } satisfies Partial<PlatformClientError>)
  })
})
