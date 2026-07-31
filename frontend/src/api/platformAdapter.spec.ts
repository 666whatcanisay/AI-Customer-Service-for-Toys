import { describe, expect, it } from 'vitest'
import {
  adaptProductsResponse,
  adaptSkusResponse,
  adaptStoresResponse,
  PlatformAdapterError
} from './platformAdapter'

const envelope = (items: unknown[], resultStatus: 'COMPLETE' | 'PARTIAL' = 'COMPLETE') => ({
  schema_version: 'pilot-business-catalog.v1.1',
  result_status: resultStatus,
  items,
  total: items.length,
  warnings: []
})

const store = {
  entity_type: 'STORE',
  tenant_id: 'TENANT-PDD-SM-TEST',
  platform: 'pdd',
  store_code: 'PDD-SM',
  store_name: '汕明',
  data_source: 'TEST',
  customer_service_status: 'ENABLED',
  allow_auto_send: false
}

describe('platformAdapter Customer Available Catalog contract', () => {
  it('adapts the C-owned final Store, Product, and SKU projections', () => {
    expect(adaptStoresResponse(envelope([store]))[0]).toMatchObject({
      tenantId: 'TENANT-PDD-SM-TEST',
      storeCode: 'PDD-SM',
      dataSource: 'TEST',
      customerServiceStatus: 'ENABLED'
    })

    expect(adaptProductsResponse(envelope([{
      entity_type: 'PRODUCT',
      product_id: 'PROD-001',
      platform: 'pdd',
      store_code: 'PDD-SM',
      product_name_official: '测试积木',
      product_name_display: '测试积木套装',
      sales_status: 'ON_SALE',
      age_min: 6,
      age_max: 12,
      safety_summary: '仅使用测试资料。',
      knowledge_status: 'DRAFT',
      data_source: 'TEST',
      customer_service_status: 'ENABLED'
    }]))[0]).toMatchObject({
      displayName: '测试积木套装',
      knowledgeStatus: 'DRAFT',
      customerServiceStatus: 'ENABLED'
    })

    expect(adaptSkusResponse(envelope([{
      entity_type: 'SKU',
      sku_id: 'SKU-RED',
      product_id: 'PROD-001',
      sku_code: 'RED',
      sku_name_official: '红色款',
      sku_name_display: '红色款（测试）',
      relation_type: 'CANONICAL',
      canonical_sku_id: null,
      reference_sku_id: null,
      component_sku_refs: [],
      data_source: 'TEST',
      customer_service_status: 'ENABLED'
    }]))[0]).toMatchObject({ skuId: 'SKU-RED', componentSkuRefs: [] })
  })

  it('rejects legacy envelopes and never infers missing status as enabled', () => {
    expect(() => adaptStoresResponse({ items: [store], total: 1 }))
      .toThrow(PlatformAdapterError)
    expect(() => adaptStoresResponse(envelope([{
      ...store,
      customer_service_status: undefined,
      test_data_mode: true,
      production_usable: false
    }]))).toThrow('customer_service_status')
  })

  it('isolates one malformed projected item without clearing valid items', () => {
    const result = adaptStoresResponse(envelope([
      store,
      { ...store, store_code: '', store_name: '坏数据' }
    ], 'PARTIAL'))

    expect(result).toHaveLength(1)
    expect(result[0]?.storeCode).toBe('PDD-SM')
  })

  it('surfaces a contract failure when every returned item is malformed', () => {
    expect(() => adaptSkusResponse(envelope([{
      entity_type: 'SKU',
      sku_id: 'SKU-RED',
      product_id: 'PROD-001',
      sku_code: 'RED',
      sku_name_official: '红色款',
      sku_name_display: '红色款',
      relation_type: 'CANONICAL',
      canonical_sku_id: null,
      reference_sku_id: null,
      component_sku_refs: null,
      data_source: 'TEST',
      customer_service_status: 'ENABLED'
    }]))).toThrow('string[]')
  })
})
