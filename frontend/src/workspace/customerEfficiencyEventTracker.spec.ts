import { describe, expect, it, vi } from 'vitest'
import { CustomerEfficiencyEventTracker } from './customerEfficiencyEventTracker'
import type { CustomerEfficiencyEventDraft } from '@/api/customerEfficiencyEventTypes'

const request: CustomerEfficiencyEventDraft = {
  eventType: 'AI_REQUEST',
  operatorId: 'op-test-001',
  storeCode: 'PDD-SM',
  productId: 'PROD-001',
  skuId: 'SKU-RED',
  conversationId: 'conv-test-001',
  interactionId: 'int-test-001',
  feedbackId: null
}

describe('CustomerEfficiencyEventTracker', () => {
  it('sends events in order so the terminal outcome follows AI_REQUEST', async () => {
    let releaseFirst: (() => void) | undefined
    const firstSubmission = new Promise<void>((resolve) => { releaseFirst = resolve })
    const submit = vi.fn()
      .mockReturnValueOnce(firstSubmission)
      .mockResolvedValueOnce({})
    const tracker = new CustomerEfficiencyEventTracker({ submit })

    tracker.record(request)
    tracker.record({ ...request, eventType: 'AI_DIRECT_ADOPT' })
    await Promise.resolve()
    expect(submit).toHaveBeenCalledTimes(1)

    releaseFirst?.()
    await tracker.whenIdle()
    expect(submit).toHaveBeenCalledTimes(2)
    expect(submit.mock.calls.map(([event]) => event.eventType)).toEqual([
      'AI_REQUEST',
      'AI_DIRECT_ADOPT'
    ])
  })

  it('swallows event failures and continues with later events', async () => {
    const submit = vi.fn()
      .mockRejectedValueOnce(new Error('service unavailable'))
      .mockResolvedValueOnce({})
    const tracker = new CustomerEfficiencyEventTracker({ submit })

    tracker.record(request)
    tracker.record({ ...request, eventType: 'AI_REJECT' })

    await expect(tracker.whenIdle()).resolves.toBeUndefined()
    expect(submit).toHaveBeenCalledTimes(2)
    expect(submit.mock.calls.map(([event]) => event.eventType)).toEqual([
      'AI_REQUEST',
      'AI_REJECT'
    ])
  })
})
