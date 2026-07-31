import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiGet = vi.hoisted(() => vi.fn())
const apiPut = vi.hoisted(() => vi.fn())
const apiPost = vi.hoisted(() => vi.fn())
const apiPatch = vi.hoisted(() => vi.fn())
const create = vi.hoisted(() => vi.fn(() => ({
  get: apiGet,
  put: apiPut,
  post: apiPost,
  patch: apiPatch,
})))

vi.mock('axios', () => ({
  default: {
    create,
    isAxiosError: () => false,
  },
}))

import {
  listCatalogActivationReceipts,
  setProductCustomerServiceStatus,
  setStoreCustomerServiceStatus,
} from './client'

describe('C Admin customer catalog activation client', () => {
  beforeEach(() => {
    apiGet.mockReset()
    apiPut.mockReset()
    apiGet.mockResolvedValue({ data: { items: [], total: 0, page: 1, size: 20 } })
    apiPut.mockResolvedValue({
      data: {
        schema_version: 'pilot-business-catalog-activation-response.v1',
        changed: false,
        entity: {},
        activation_receipt: null,
        server_time: '2026-07-31T00:00:00Z',
      },
    })
  })

  it('uses the frozen Store and Product activation paths with idempotency keys', async () => {
    await setStoreCustomerServiceStatus(17, 'ENABLED', '运营甲', 'store-key')
    await setProductCustomerServiceStatus('P/1', 'DISABLED', '运营乙', 'product-key')

    expect(apiPut.mock.calls).toEqual([
      [
        '/api/v1/admin/operations/stores/17/customer-service-status',
        {
          customer_service_status: 'ENABLED',
          confirmed_by: '运营甲',
          confirmation_note: '运营已确认该店铺可供客服人工选择使用',
        },
        { headers: { 'Idempotency-Key': 'store-key' } },
      ],
      [
        '/api/v1/admin/operations/products/P%2F1/customer-service-status',
        {
          customer_service_status: 'DISABLED',
          confirmed_by: '运营乙',
          confirmation_note: '运营已关闭该商品的客服人工选择入口',
        },
        { headers: { 'Idempotency-Key': 'product-key' } },
      ],
    ])
  })

  it('reads immutable receipts by entity without inventing local history', async () => {
    await listCatalogActivationReceipts('PRODUCT', 'P/1')

    expect(apiGet).toHaveBeenCalledWith(
      '/api/v1/admin/operations/activation-receipts',
      { params: { entity_type: 'PRODUCT', entity_ref: 'P/1', page: 1, size: 20 } },
    )
  })
})
