import { describe, expect, it } from 'vitest'
import { adaptChatResponse, adaptHealthResponse, RagAdapterError } from './ragAdapter'

describe('ragAdapter', () => {
  it('adapts the current A-line chat response without inventing risk', () => {
    const result = adaptChatResponse({
      answer: '建议由客服核对商品年龄标识后回复。',
      action: 'ANSWER',
      sources: [
        {
          source_name: 'toy-guide.pdf',
          page: 3,
          chunk_id: 'chunk-7',
          distance: 0.18,
          excerpt: '适用年龄以包装标识为准。'
        }
      ],
      model: 'qwen-turbo',
      latency_ms: 82,
      request_id: 'req-001'
    })

    expect(result).toMatchObject({
      requestId: 'req-001',
      model: 'qwen-turbo',
      answer: '建议由客服核对商品年龄标识后回复。',
      action: 'DIRECT_ANSWER',
      riskLevel: null,
      latencyMs: 82
    })
    expect(result.citations[0]).toEqual({
      file: 'toy-guide.pdf',
      page: 3,
      chunkId: 'chunk-7',
      summary: '适用年龄以包装标识为准。',
      distance: 0.18,
      knowledgeVersion: null
    })
  })

  it('adapts the shared-contract envelope and citation fields', () => {
    const result = adaptChatResponse({
      success: true,
      data: {
        request_id: 'req-002',
        answer: '需要转人工确认。',
        action: 'TRANSFER_HUMAN',
        risk_level: 'HIGH',
        warnings: ['信息存在冲突'],
        required_fields: ['sku'],
        latency_ms: 120,
        citations: [
          {
            source_name: 'policy.pdf',
            page_number: 8,
            summary: '高风险场景需人工复核。',
            knowledge_version: 'v2'
          }
        ]
      }
    })

    expect(result.action).toBe('TRANSFER_HUMAN')
    expect(result.riskLevel).toBe('HIGH')
    expect(result.warnings).toEqual(['信息存在冲突'])
    expect(result.requiredFields).toEqual(['sku'])
    expect(result.citations[0]?.knowledgeVersion).toBe('v2')
  })

  it('rejects a response without an answer', () => {
    expect(() => adaptChatResponse({ sources: [] })).toThrow(RagAdapterError)
  })

  it('adapts health envelopes', () => {
    expect(adaptHealthResponse({ data: { status: 'ok', ready: true } })).toEqual({
      status: 'ok',
      ready: true
    })
  })
})
