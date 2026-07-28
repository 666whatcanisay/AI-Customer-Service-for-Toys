import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpGet = vi.hoisted(() => vi.fn())
const httpCreate = vi.hoisted(() => vi.fn(() => ({ get: httpGet })))

vi.mock('axios', () => ({
  default: {
    create: httpCreate,
    isCancel: () => false,
    isAxiosError: () => false
  }
}))

import { customerKnowledgeStatusClient } from './customerKnowledgeStatusClient'

describe('customerKnowledgeStatusClient knowledge-quality-loop.v1', () => {
  beforeEach(() => {
    httpGet.mockReset()
    httpGet.mockResolvedValue({
      data: {
        status: 'READY',
        summary: '资料已完成审核，可作为人工核对参考。',
        last_checked_at: '2026-07-28T10:00:00Z'
      }
    })
  })

  it('uses the same-origin platform proxy unless direct debug mode is configured', () => {
    expect(httpCreate).toHaveBeenCalledWith(expect.objectContaining({
      baseURL: '/platform-api'
    }))
  })

  it('calls only the frozen customer-safe status path and scope fields', async () => {
    await customerKnowledgeStatusClient.getStatus({
      storeCode: 'PDD-SM',
      productId: 'PROD-001',
      skuId: 'SKU-RED'
    })
    await customerKnowledgeStatusClient.getStatus({
      storeCode: 'PDD-SM',
      productId: 'PROD-001',
      skuId: null
    })

    expect(httpGet.mock.calls).toEqual([
      [
        '/api/v1/customer-knowledge-status',
        {
          signal: undefined,
          params: {
            store_code: 'PDD-SM',
            product_id: 'PROD-001',
            sku_id: 'SKU-RED'
          }
        }
      ],
      [
        '/api/v1/customer-knowledge-status',
        {
          signal: undefined,
          params: {
            store_code: 'PDD-SM',
            product_id: 'PROD-001'
          }
        }
      ]
    ])
  })

  it('maps a malformed status response to the nontechnical customer-safe failure', async () => {
    httpGet.mockResolvedValueOnce({
      data: {
        status: 'NOT_FROZEN',
        summary: 'raw upstream detail must not reach the page',
        last_checked_at: '2026-07-28T10:00:00Z'
      }
    })

    await expect(customerKnowledgeStatusClient.getStatus({
      storeCode: 'PDD-SM',
      productId: 'PROD-001',
      skuId: null
    })).rejects.toThrow('无法获取资料状态，可继续咨询。')
  })
})
