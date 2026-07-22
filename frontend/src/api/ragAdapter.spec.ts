import { describe, expect, it } from 'vitest'
import { adaptChatResponse, adaptHealthResponse, RagAdapterError } from './ragAdapter'
import { RAG_ACTIONS, type RagAction } from './ragTypes'

const responseFor = (action: RagAction = 'DIRECT_ANSWER') => ({
  answer: '建议由客服核对商品年龄标识后回复。',
  action,
  risk_level: action === 'TRANSFER_HUMAN' ? 'HIGH' : 'LOW',
  sources: [
    {
      source_name: 'toy-guide.pdf',
      page: 3,
      chunk_id: 'chunk-7',
      distance: 0.18,
      excerpt: '适用年龄以包装标识为准。',
      knowledge_version: 'v3',
      source_ids: ['SRC-001'],
      product_id: 'PROD-001',
      sku_id: 'SKU-RED'
    }
  ],
  warnings: [],
  required_fields: action === 'ASK_CLARIFY' ? ['sku_id'] : [],
  model: 'qwen-turbo',
  latency_ms: 82,
  request_id: 'req-001',
  context: {
    tenant_id: 'TENANT-PDD-SM-TEST',
    platform: 'pdd',
    store_code: 'PDD-SM',
    product_id: 'PROD-001',
    sku_id: 'SKU-RED'
  }
})

describe('ragAdapter B-T03 contract', () => {
  it('consumes only the authoritative data payload and exact source fields', () => {
    const result = adaptChatResponse({
      answer: 'top-level mirror must be ignored',
      data: responseFor()
    })

    expect(result).toMatchObject({
      requestId: 'req-001',
      model: 'qwen-turbo',
      answer: '建议由客服核对商品年龄标识后回复。',
      action: 'DIRECT_ANSWER',
      riskLevel: 'LOW',
      latencyMs: 82,
      context: responseFor().context
    })
    expect(result.citations[0]).toEqual({
      file: 'toy-guide.pdf',
      page: 3,
      chunkId: 'chunk-7',
      summary: '适用年龄以包装标识为准。',
      distance: 0.18,
      knowledgeVersion: 'v3',
      sourceIds: ['SRC-001'],
      productId: 'PROD-001',
      skuId: 'SKU-RED'
    })
  })

  it.each(RAG_ACTIONS)('accepts frozen action %s', (action) => {
    expect(adaptChatResponse({ data: responseFor(action) }).action).toBe(action)
  })

  it('rejects a legacy top-level-only chat response', () => {
    expect(() => adaptChatResponse(responseFor())).toThrow(RagAdapterError)
  })

  it('rejects an unknown action and invalid source_ids', () => {
    expect(() => adaptChatResponse({ data: { ...responseFor(), action: 'ANSWER' } }))
      .toThrow('六种动作')
    expect(() => adaptChatResponse({
      data: {
        ...responseFor(),
        sources: [{ ...responseFor().sources[0], source_ids: null }]
      }
    })).toThrow('string[]')
  })

  it('adapts current health envelopes separately from chat', () => {
    expect(adaptHealthResponse({ data: { status: 'ok', ready: true } })).toEqual({
      status: 'ok',
      ready: true
    })
  })
})
