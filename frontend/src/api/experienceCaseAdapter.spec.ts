import { describe, expect, it } from 'vitest'
import { PlatformAdapterError } from './platformAdapter'
import { adaptExperienceCaseReceipt, toExperienceCasePayload } from './experienceCaseAdapter'

describe('experienceCaseAdapter', () => {
  it('serializes only the frozen experience-case feedback type without optional SKU', () => {
    expect(toExperienceCasePayload({
      storeCode: ' PDD-SM ', productId: ' PROD-1 ', skuId: '', question: ' 问题 ', aiAnswer: ' AI 回复 ',
      finalAnswer: ' 最终回复 ', feedbackType: 'EDITED_ADOPTED', createdBy: ' TESTER-1 '
    })).toEqual({
      store_code: 'PDD-SM', product_id: 'PROD-1', sku_id: null, question: '问题', ai_answer: 'AI 回复',
      final_answer: '最终回复', feedback_type: 'EDITED_ADOPTED', created_by: 'TESTER-1'
    })
  })

  it('rejects former page-adoption values and empty final answers instead of sending them', () => {
    const validDraft = {
      storeCode: 'PDD-SM', productId: 'PROD-1', skuId: null, question: '问题', aiAnswer: 'AI 回复',
      finalAnswer: '最终回复', feedbackType: 'ADOPTED' as const, createdBy: 'TESTER-1'
    }
    expect(() => toExperienceCasePayload({ ...validDraft, feedbackType: 'EDITED_ACCEPT' as never })).toThrow(PlatformAdapterError)
    expect(() => toExperienceCasePayload({ ...validDraft, feedbackType: 'REJECTED' as never })).toThrow(PlatformAdapterError)
    expect(() => toExperienceCasePayload({ ...validDraft, finalAnswer: ' ' })).toThrow(PlatformAdapterError)
  })

  it('accepts only top-level case_id and review_status from a real response shape', () => {
    expect(adaptExperienceCaseReceipt({ case_id: 'CEC-001', review_status: 'NEW' })).toEqual({
      caseId: 'CEC-001', reviewStatus: 'NEW'
    })
    expect(() => adaptExperienceCaseReceipt({ case_id: 'CEC-001', status: 'NEW' })).toThrow(PlatformAdapterError)
    expect(() => adaptExperienceCaseReceipt({ data: { case_id: 'CEC-001', review_status: 'NEW' } })).toThrow(PlatformAdapterError)
  })
})
