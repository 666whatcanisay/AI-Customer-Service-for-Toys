import {
  createCustomerEfficiencyOpaqueId,
  customerEfficiencyEventClient
} from '@/api/customerEfficiencyEventClient'
import type {
  CustomerEfficiencyEventApiClient,
  CustomerEfficiencyEventDraft
} from '@/api/customerEfficiencyEventTypes'

export class CustomerEfficiencyEventTracker {
  private queue: Promise<void> = Promise.resolve()

  constructor(private readonly client: CustomerEfficiencyEventApiClient = customerEfficiencyEventClient) {}

  record(draft: CustomerEfficiencyEventDraft): void {
    const idempotencyKey = createCustomerEfficiencyOpaqueId('cee')
    this.queue = this.queue
      .then(() => this.client.submit(draft, idempotencyKey))
      .then(
        () => undefined,
        () => undefined
      )
  }

  whenIdle(): Promise<void> {
    return this.queue
  }
}

export const customerEfficiencyEventTracker = new CustomerEfficiencyEventTracker()
