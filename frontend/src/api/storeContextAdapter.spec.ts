import { describe, expect, it } from 'vitest'

import { adaptContextResolution, adaptWorkspaceContext } from './storeContextAdapter'


const store = {
  store_id: 8, tenant_id: 'TENANT-1', platform: 'pdd', store_code: 'STORE-1',
  store_name: '合成测试店', is_default: true
}

describe('store context contract adapter', () => {
  it('maps C-owned workspace identity and default Store without client inference', () => {
    expect(adaptWorkspaceContext({
      schema_version: 'ai-cs.store-context.v1', user_id: 'user-1',
      roles: ['CUSTOMER_SERVICE'], all_store_access: false, state: 'READY',
      stores: [store], effective_store: store
    })).toEqual(expect.objectContaining({
      userId: 'user-1', state: 'READY',
      effectiveStore: expect.objectContaining({ storeId: 8, isDefault: true })
    }))
  })

  it('maps only server supplied Product/SKU candidates and status', () => {
    const result = adaptContextResolution({
      schema_version: 'ai-cs.store-context.v1',
      resolution_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
      status: 'SKU_CONFIRMATION_REQUIRED', store,
      product: { product_id: 'PRODUCT-1', display_name: '合成玩具' }, sku: null,
      product_candidates: [{ product_id: 'PRODUCT-1', display_name: '合成玩具' }],
      sku_candidates: [{ sku_id: 'SKU-1', display_name: '红色款' }],
      reason_code: 'MULTIPLE_SKU_OPTIONS', created_at: '2026-08-06T00:00:00Z'
    })
    expect(result.status).toBe('SKU_CONFIRMATION_REQUIRED')
    expect(result.skuCandidates).toEqual([{ skuId: 'SKU-1', displayName: '红色款' }])
  })

  it('fails closed on an incompatible schema version', () => {
    expect(() => adaptWorkspaceContext({ schema_version: 'unknown' }))
      .toThrow('版本不兼容')
  })

  it('fails closed on an unknown resolver state', () => {
    expect(() => adaptContextResolution({
      schema_version: 'ai-cs.store-context.v1',
      resolution_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', status: 'GUESSED'
    })).toThrow('状态无效')
  })
})
