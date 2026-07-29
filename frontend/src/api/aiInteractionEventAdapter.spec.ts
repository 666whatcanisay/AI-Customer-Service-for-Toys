import { describe, expect, it } from 'vitest'

import {
  adaptAiInteractionEventReceipt,
  minimizeInteractionSummary,
  toAiInteractionEventPayload
} from './aiInteractionEventAdapter'
import { PlatformAdapterError } from './platformAdapter'

const draft = {
  interactionId: ' request-001 ',
  storeCode: ' STORE-ONE ',
  storeName: ' 测试店铺 ',
  productId: ' PRODUCT-ONE ',
  productName: ' 测试商品 ',
  skuId: ' SKU-ONE ',
  skuName: ' 红色款 ',
  actionType: 'EDITED_ACCEPT' as const,
  questionSummary: '客户 13800138000 问订单 123456789012',
  aiAnswerSummary: '请联系 test@example.com',
  finalAnswerSummary: '人工核对后的回复',
  createdBy: ' TESTER-ONE '
}

describe('aiInteractionEventAdapter', () => {
  it('serializes the approved v1 event contract and minimizes direct identifiers', () => {
    expect(toAiInteractionEventPayload(draft)).toEqual({
      interaction_id: 'request-001',
      store_code: 'STORE-ONE',
      store_name: '测试店铺',
      product_id: 'PRODUCT-ONE',
      product_name: '测试商品',
      sku_id: 'SKU-ONE',
      sku_name: '红色款',
      action_type: 'EDITED_ACCEPT',
      question_summary: '客户 [手机号已移除] 问订单 [长编号已移除]',
      ai_answer_summary: '请联系 [邮箱已移除]',
      final_answer_summary: '人工核对后的回复',
      created_by: 'TESTER-ONE'
    })
    expect(minimizeInteractionSummary('a'.repeat(300))).toHaveLength(240)
  })

  it('requires the edited final answer and exact recorded receipt', () => {
    expect(() => toAiInteractionEventPayload({ ...draft, finalAnswerSummary: null }))
      .toThrow(PlatformAdapterError)
    expect(adaptAiInteractionEventReceipt({
      event_id: 'AIE-001',
      interaction_id: 'request-001',
      status: 'RECORDED',
      occurred_at: '2026-07-29T08:00:00Z'
    })).toEqual({
      eventId: 'AIE-001',
      interactionId: 'request-001',
      status: 'RECORDED',
      occurredAt: '2026-07-29T08:00:00Z'
    })
    expect(() => adaptAiInteractionEventReceipt({
      event_id: 'AIE-001',
      interaction_id: 'request-001',
      status: 'NEW',
      occurred_at: '2026-07-29T08:00:00Z'
    })).toThrow(PlatformAdapterError)
  })
})
