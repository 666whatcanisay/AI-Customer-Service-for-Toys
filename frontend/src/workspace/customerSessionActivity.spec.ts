import { describe, expect, it } from 'vitest'
import {
  clearCustomerSessionActivity,
  recordAiAssist,
  recordAiFeedbackSubmission,
  useCustomerSessionActivity
} from './customerSessionActivity'

describe('customerSessionActivity', () => {
  it('exposes only the current browser session activity', () => {
    clearCustomerSessionActivity()
    const activity = useCustomerSessionActivity()

    recordAiAssist()
    recordAiAssist()
    recordAiFeedbackSubmission()

    expect(activity.aiAssists.value).toBe(2)
    expect(activity.feedbackSubmissions.value).toBe(1)
    clearCustomerSessionActivity()
  })
})
