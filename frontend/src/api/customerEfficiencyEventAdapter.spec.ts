import { describe, expect, it } from 'vitest'
import { PlatformAdapterError } from './platformAdapter'
import {
  adaptCustomerEfficiencyEventReceipt,
  toCustomerEfficiencyEventPayload
} from './customerEfficiencyEventAdapter'

const draft = {
  eventType: 'AI_REQUEST' as const,
  operatorId: ' op-test-001 ',
  storeCode: ' PDD-SM ',
  productId: ' PROD-001 ',
  skuId: ' SKU-RED ',
  conversationId: ' conv-test-001 ',
  interactionId: ' int-test-001 ',
  feedbackId: null
}

describe('customerEfficiencyEventAdapter', () => {
  it('serializes exactly the frozen privacy-safe event payload', () => {
    expect(toCustomerEfficiencyEventPayload(draft)).toEqual({
      schema_version: 'customer-efficiency.v1',
      event_type: 'AI_REQUEST',
      operator_id: 'op-test-001',
      store_code: 'PDD-SM',
      product_id: 'PROD-001',
      sku_id: 'SKU-RED',
      conversation_id: 'conv-test-001',
      interaction_id: 'int-test-001',
      feedback_id: null
    })
  })

  it('requires the frozen event references instead of sending partial events', () => {
    expect(() => toCustomerEfficiencyEventPayload({ ...draft, interactionId: null }))
      .toThrow(PlatformAdapterError)
    expect(() => toCustomerEfficiencyEventPayload({ ...draft, feedbackId: 'ARF-001' }))
      .toThrow(PlatformAdapterError)
    expect(() => toCustomerEfficiencyEventPayload({
      ...draft,
      eventType: 'AI_FEEDBACK_SUBMIT',
      feedbackId: null
    })).toThrow(PlatformAdapterError)
    expect(toCustomerEfficiencyEventPayload({
      ...draft,
      eventType: 'AI_FEEDBACK_SUBMIT',
      feedbackId: 'ARF-001'
    })).toMatchObject({ event_type: 'AI_FEEDBACK_SUBMIT', feedback_id: 'ARF-001' })
  })

  it('accepts only the frozen receipt for the submitted event type', () => {
    expect(adaptCustomerEfficiencyEventReceipt({
      event_id: 'CEE-001',
      event_type: 'AI_REQUEST',
      created_at: '2026-07-27T09:00:00Z',
      accepted: true
    }, 'AI_REQUEST')).toEqual({
      eventId: 'CEE-001',
      eventType: 'AI_REQUEST',
      createdAt: '2026-07-27T09:00:00Z',
      accepted: true
    })
    expect(() => adaptCustomerEfficiencyEventReceipt({
      event_id: 'CEE-001',
      event_type: 'AI_REJECT',
      created_at: '2026-07-27T09:00:00Z',
      accepted: true
    }, 'AI_REQUEST')).toThrow(PlatformAdapterError)
  })
})
