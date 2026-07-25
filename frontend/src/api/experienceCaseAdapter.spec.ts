import { describe, expect, it } from 'vitest'
import { PlatformAdapterError } from './platformAdapter'
import { adaptExperienceCaseReceipt, toExperienceCasePayload } from './experienceCaseAdapter'

describe('experienceCaseAdapter', () => {
  it('serializes the task-local experience-case payload without optional SKU', () => {
    expect(toExperienceCasePayload({
      storeCode: ' PDD-SM ', productId: ' PROD-1 ', skuId: '', question: ' 问题 ', aiAnswer: ' AI 回复 ',
      finalAnswer: ' 最终回复 ', feedbackType: 'EDITED_ACCEPT', createdBy: ' TESTER-1 '
    })).toEqual({
      store_code: 'PDD-SM', product_id: 'PROD-1', sku_id: null, question: '问题', ai_answer: 'AI 回复',
      final_answer: '最终回复', feedback_type: 'EDITED_ACCEPT', created_by: 'TESTER-1'
    })
  })

  it('accepts only a published experience-case status from a real response shape', () => {
    expect(adaptExperienceCaseReceipt({ data: { status: 'NEW' } })).toEqual({ status: 'NEW' })
    expect(() => adaptExperienceCaseReceipt({ status: 'SAVED' })).toThrow(PlatformAdapterError)
  })
})
