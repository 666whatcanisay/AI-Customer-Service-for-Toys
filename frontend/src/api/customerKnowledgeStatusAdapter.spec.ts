import { describe, expect, it } from 'vitest'
import {
  adaptCustomerKnowledgeStatus,
  CustomerKnowledgeStatusAdapterError
} from './customerKnowledgeStatusAdapter'

describe('customerKnowledgeStatusAdapter knowledge-quality-loop.v1', () => {
  it('adapts only the frozen customer-safe status fields', () => {
    expect(adaptCustomerKnowledgeStatus({
      status: 'NEEDS_REVIEW',
      summary: '该商品资料仍有待补全项，回复前请人工核对。',
      last_checked_at: '2026-07-28T10:00:00Z',
      analysis_text: 'must never be rendered by the customer client',
      content_hash: 'sha256:not-used'
    })).toEqual({
      status: 'NEEDS_REVIEW',
      summary: '该商品资料仍有待补全项，回复前请人工核对。',
      lastCheckedAt: '2026-07-28T10:00:00Z'
    })
  })

  it('rejects unknown statuses and malformed frozen fields', () => {
    expect(() => adaptCustomerKnowledgeStatus({
      status: 'PUBLISHED_TO_RAG',
      summary: '未知状态',
      last_checked_at: '2026-07-28T10:00:00Z'
    })).toThrow(CustomerKnowledgeStatusAdapterError)

    expect(() => adaptCustomerKnowledgeStatus({
      status: 'READY',
      summary: '',
      last_checked_at: 'not-a-time'
    })).toThrow(CustomerKnowledgeStatusAdapterError)
  })
})
