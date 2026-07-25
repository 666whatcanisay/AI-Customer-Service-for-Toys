import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpPost = vi.hoisted(() => vi.fn())
const httpCreate = vi.hoisted(() => vi.fn(() => ({ post: httpPost })))

vi.mock('axios', () => ({
  default: { create: httpCreate, isCancel: () => false, isAxiosError: () => false }
}))

import { aiResponseFeedbackClient } from './aiResponseFeedbackClient'

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

  it('posts only to the frozen feedback endpoint with no experience-case fallback', async () => {
    httpPost.mockResolvedValue({
      data: { feedback_id: 'ARF-001', status: 'NEW', analysis_status: 'NEW', created_at: '2026-07-25T16:00:00+08:00' }
    })

    await expect(aiResponseFeedbackClient.submit(draft)).resolves.toMatchObject({ feedbackId: 'ARF-001' })
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
    }, { signal: undefined })
  })

  it('rejects an unrecognized response instead of reporting feedback as recorded', async () => {
    httpPost.mockResolvedValue({ data: { feedback_id: 'ARF-001', status: 'NEW' } })
    await expect(aiResponseFeedbackClient.submit(draft)).rejects.toBeInstanceOf(Error)
  })
})
