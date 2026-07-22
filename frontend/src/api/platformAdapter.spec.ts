import { describe, expect, it } from 'vitest'
import {
  adaptProductsResponse,
  adaptSkusResponse,
  adaptStoresResponse,
  PlatformAdapterError
} from './platformAdapter'

describe('platformAdapter B-T03 contract', () => {
  it('adapts the frozen C store, product, and SKU envelopes', () => {
    expect(adaptStoresResponse({
      items: [{
        tenant_id: 'TENANT-PDD-SM-TEST',
        platform: 'pdd',
        store_code: 'PDD-SM',
        store_name: '汕明',
        trial_enabled: true,
        knowledge_scope: 'STORE_PRODUCT_SKU',
        response_mode: 'SUGGESTION_ONLY',
        allow_auto_send: false,
        test_data_mode: true,
        production_usable: false
      }],
      total: 1
    })[0]).toMatchObject({
      tenantId: 'TENANT-PDD-SM-TEST',
      storeCode: 'PDD-SM',
      testDataMode: true,
      productionUsable: false
    })

    expect(adaptProductsResponse({
      items: [{
        product_id: 'PROD-001',
        platform: 'pdd',
        store_code: 'PDD-SM',
        product_name_official: '测试积木',
        product_name_display: '测试积木套装',
        sales_status: 'ON_SALE',
        age_min: 6,
        age_max: 12,
        safety_summary: '仅使用测试资料。',
        review_status: 'APPROVED',
        publishable: true
      }],
      total: 1
    })[0]?.displayName).toBe('测试积木套装')

    expect(adaptSkusResponse({
      items: [{
        sku_id: 'SKU-RED',
        product_id: 'PROD-001',
        sku_code: 'RED',
        sku_name_official: '红色款',
        sku_name_display: '红色款（测试）',
        relation_type: 'CANONICAL',
        canonical_sku_id: null,
        reference_sku_id: null,
        component_sku_refs: [],
        publishable: true
      }],
      total: 1
    })[0]).toMatchObject({ skuId: 'SKU-RED', componentSkuRefs: [] })
  })

  it('rejects data.items aliases and malformed component_sku_refs', () => {
    expect(() => adaptStoresResponse({ data: { items: [] }, total: 0 }))
      .toThrow(PlatformAdapterError)
    expect(() => adaptSkusResponse({
      items: [{
        sku_id: 'SKU-RED',
        product_id: 'PROD-001',
        sku_code: 'RED',
        sku_name_official: '红色款',
        sku_name_display: '红色款',
        relation_type: 'CANONICAL',
        canonical_sku_id: null,
        reference_sku_id: null,
        component_sku_refs: null,
        publishable: true
      }],
      total: 1
    })).toThrow('string[]')
  })
})
