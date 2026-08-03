import { describe, expect, it } from 'vitest'
import {
  adaptProductsResponse,
  adaptSkusResponse,
  adaptStoresResponse,
  PlatformAdapterError
} from './platformAdapter'

const warning = {
  code: 'CUSTOMER_SERVICE_SOURCE_INVALID',
  entity_type: 'PRODUCT',
  count: 1,
  message: '1 product source row was isolated.'
}

const envelope = (
  items: unknown[],
  resultStatus: 'COMPLETE' | 'PARTIAL' = 'COMPLETE',
  warnings: unknown[] = []
) => ({
  schema_version: 'pilot-business-catalog.v1.1',
  result_status: resultStatus,
  items,
  total: items.length,
  warnings
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
    expect(adaptStoresResponse(envelope([store])).items[0]).toMatchObject({
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
    }])).items[0]).toMatchObject({
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
    }])).items[0]).toMatchObject({ skuId: 'SKU-RED', componentSkuRefs: [] })
  })

  it('accepts the formalized INITIAL_IMPORT source without changing availability rules', () => {
    expect(adaptStoresResponse(envelope([{ ...store, data_source: 'INITIAL_IMPORT' }])).items[0])
      .toMatchObject({
        dataSource: 'INITIAL_IMPORT',
        customerServiceStatus: 'ENABLED'
      })
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

    expect(result.items).toHaveLength(1)
    expect(result.items[0]?.storeCode).toBe('PDD-SM')
    expect(result.resultStatus).toBe('PARTIAL')
    expect(result.total).toBe(2)
  })

  it('rejects a malformed item when C declares the envelope COMPLETE', () => {
    expect(() => adaptStoresResponse(envelope([
      store,
      { ...store, store_code: '', store_name: '坏数据' }
    ]))).toThrow('store_code')
  })

  it('preserves COMPLETE zero as an authoritative empty envelope', () => {
    expect(adaptProductsResponse(envelope([]))).toEqual({
      schemaVersion: 'pilot-business-catalog.v1.1',
      resultStatus: 'COMPLETE',
      items: [],
      total: 0,
      warnings: []
    })
  })

  it('preserves PARTIAL zero and warning evidence instead of collapsing it to an empty list', () => {
    const result = adaptProductsResponse(envelope([], 'PARTIAL', [warning]))

    expect(result).toEqual({
      schemaVersion: 'pilot-business-catalog.v1.1',
      resultStatus: 'PARTIAL',
      items: [],
      total: 0,
      warnings: [{
        code: 'CUSTOMER_SERVICE_SOURCE_INVALID',
        entityType: 'PRODUCT',
        count: 1,
        message: '1 product source row was isolated.'
      }]
    })
  })

  it('keeps valid PARTIAL items and warning evidence together', () => {
    const result = adaptStoresResponse(envelope([store], 'PARTIAL', [{
      ...warning,
      entity_type: 'STORE'
    }]))

    expect(result.resultStatus).toBe('PARTIAL')
    expect(result.items).toHaveLength(1)
    expect(result.warnings[0]).toMatchObject({ entityType: 'STORE', count: 1 })
  })

  it('rejects an invalid warning instead of discarding its audit evidence', () => {
    expect(() => adaptProductsResponse(envelope([], 'PARTIAL', [{
      ...warning,
      count: 0
    }]))).toThrow('warning 字段 count')
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
