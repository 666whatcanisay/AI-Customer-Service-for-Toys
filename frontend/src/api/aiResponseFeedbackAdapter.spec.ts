import { describe, expect, it } from 'vitest'
import { PlatformAdapterError } from './platformAdapter'
import {
  adaptAiResponseFeedbackReceipt,
  toAiResponseFeedbackPayload
} from './aiResponseFeedbackAdapter'

const draft = {
  storeCode: ' PDD-SM ',
  productId: ' PROD-1 ',
  skuId: '',
  question: ' 测试问题 ',
  aiAnswer: ' AI 测试回复 ',
  feedbackType: 'MISSING_INFO' as const,
  feedbackNote: null,
  finalAnswer: '',
  createdBy: ' TESTER-ONE '
}

describe('aiResponseFeedbackAdapter', () => {
  it('serializes only the frozen feedback payload and its controlled context', () => {
    expect(toAiResponseFeedbackPayload(draft)).toEqual({
      store_code: 'PDD-SM',
      product_id: 'PROD-1',
      sku_id: null,
      question: '测试问题',
      ai_answer: 'AI 测试回复',
      feedback_type: 'MISSING_INFO',
      feedback_note: null,
      final_answer: null,
      created_by: 'TESTER-ONE',
      context: { store_code: 'PDD-SM', product_id: 'PROD-1', sku_id: null }
    })
  })

  it('requires a de-identified note only when OTHER is selected', () => {
    expect(() => toAiResponseFeedbackPayload({ ...draft, feedbackType: 'OTHER', feedbackNote: null }))
      .toThrow(PlatformAdapterError)
    expect(toAiResponseFeedbackPayload({ ...draft, feedbackType: 'OTHER', feedbackNote: '无法归类的测试问题' }))
      .toMatchObject({ feedback_type: 'OTHER', feedback_note: '无法归类的测试问题' })
  })

  it('adds the saved interaction link only when the new client provides it', () => {
    expect(toAiResponseFeedbackPayload({ ...draft, interactionId: ' req-001 ' }))
      .toMatchObject({ interaction_id: 'req-001' })
    expect(toAiResponseFeedbackPayload(draft)).not.toHaveProperty('interaction_id')
  })

  it('accepts only the frozen creation receipt', () => {
    expect(adaptAiResponseFeedbackReceipt({
      feedback_id: 'ARF-001', status: 'NEW'
    })).toEqual({
      feedbackId: 'ARF-001', status: 'NEW'
    })
    expect(() => adaptAiResponseFeedbackReceipt({
      feedback_id: 'ARF-001', status: 'ANALYZING'
    })).toThrow(PlatformAdapterError)
    expect(() => adaptAiResponseFeedbackReceipt({
      data: { feedback_id: 'ARF-001', status: 'NEW' }
    })).toThrow(PlatformAdapterError)
  })
})
