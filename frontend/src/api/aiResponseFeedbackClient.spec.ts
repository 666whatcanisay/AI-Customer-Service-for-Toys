import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpPost = vi.hoisted(() => vi.fn())
const httpCreate = vi.hoisted(() => vi.fn(() => ({ post: httpPost })))

vi.mock('axios', () => ({
  default: { create: httpCreate, isCancel: () => false, isAxiosError: () => false }
}))

import {
  aiResponseFeedbackClient,
  createAiResponseFeedbackIdempotencyKey
} from './aiResponseFeedbackClient'

const draft = {
  storeCode: 'PDD-SM',
  productId: 'PROD-1',
  skuId: 'SKU-1',
  question: '测试问题',
  aiAnswer: 'AI 测试回复',
  feedbackType: 'RISK_ISSUE' as const,
  feedbackNote: null,
  finalAnswer: null,
  createdBy: 'TESTER-ONE'
}

describe('aiResponseFeedbackClient', () => {
  beforeEach(() => httpPost.mockReset())

  it('posts to the frozen feedback endpoint with a generated Idempotency-Key and no experience-case fallback', async () => {
    httpPost.mockResolvedValue({
      data: { feedback_id: 'ARF-001', status: 'NEW' }
    })

    const idempotencyKey = createAiResponseFeedbackIdempotencyKey()
    await expect(aiResponseFeedbackClient.submit(draft, idempotencyKey)).resolves.toEqual({
      feedbackId: 'ARF-001', status: 'NEW'
    })
    expect(httpPost).toHaveBeenCalledWith('/api/v1/ai-response-feedback', {
      store_code: 'PDD-SM',
      product_id: 'PROD-1',
      sku_id: 'SKU-1',
      question: '测试问题',
      ai_answer: 'AI 测试回复',
      feedback_type: 'RISK_ISSUE',
      feedback_note: null,
      final_answer: null,
      created_by: 'TESTER-ONE',
      context: { store_code: 'PDD-SM', product_id: 'PROD-1', sku_id: 'SKU-1' }
    }, { signal: undefined, headers: { 'Idempotency-Key': idempotencyKey } })
  })

  it('reuses an explicit Idempotency-Key so C can return the existing result without creating a duplicate', async () => {
    httpPost.mockResolvedValue({ data: { feedback_id: 'ARF-001', status: 'NEW' } })

    const idempotencyKey = 'ai-feedback-replay-001'
    await expect(aiResponseFeedbackClient.submit(draft, idempotencyKey)).resolves.toEqual({
      feedbackId: 'ARF-001', status: 'NEW'
    })
    await expect(aiResponseFeedbackClient.submit(draft, idempotencyKey)).resolves.toEqual({
      feedbackId: 'ARF-001', status: 'NEW'
    })

    expect(httpPost).toHaveBeenCalledTimes(2)
    expect(httpPost.mock.calls[0]?.[2]).toEqual({
      signal: undefined, headers: { 'Idempotency-Key': idempotencyKey }
    })
    expect(httpPost.mock.calls[1]?.[2]).toEqual({
      signal: undefined, headers: { 'Idempotency-Key': idempotencyKey }
    })
  })

  it('rejects an unrecognized response or a missing Idempotency-Key instead of reporting feedback as recorded', async () => {
    httpPost.mockResolvedValue({ data: { feedback_id: 'ARF-001', status: 'ANALYZING' } })
    await expect(aiResponseFeedbackClient.submit(draft, 'ai-feedback-invalid-receipt')).rejects.toBeInstanceOf(Error)
    await expect(aiResponseFeedbackClient.submit(draft, '   ')).rejects.toBeInstanceOf(Error)
    expect(httpPost).toHaveBeenCalledTimes(1)
  })
})
