import { describe, expect, it } from 'vitest'

import { CustomerEfficiencyAdapterError, toCustomerEfficiencyPayload } from './customerEfficiencyAdapter'

const baseDraft = {
  eventType: 'AI_DIRECT_ADOPT' as const,
  operatorId: 'CSU-001',
  storeCode: 'PDD-SM',
  productId: 'PROD-001',
  skuId: 'SKU-001',
  conversationId: null,
  interactionId: 'interaction-001',
  feedbackId: null
}

describe('customerEfficiencyAdapter', () => {
  it('creates a privacy-bounded v1 payload without question or answer content', () => {
    const payload = toCustomerEfficiencyPayload(baseDraft)
    expect(payload).toMatchObject({ schema_version: 'customer-efficiency.v1', operator_id: 'CSU-001' })
    expect(payload).not.toHaveProperty('question')
    expect(payload).not.toHaveProperty('ai_answer')
  })

  it('requires a real interaction for AI request and adoption events', () => {
    expect(() => toCustomerEfficiencyPayload({ ...baseDraft, interactionId: null })).toThrow(CustomerEfficiencyAdapterError)
  })

  it('requires the C receipt id for feedback submission events', () => {
    expect(() => toCustomerEfficiencyPayload({ ...baseDraft, eventType: 'AI_FEEDBACK_SUBMIT', feedbackId: null })).toThrow(CustomerEfficiencyAdapterError)
  })
})
