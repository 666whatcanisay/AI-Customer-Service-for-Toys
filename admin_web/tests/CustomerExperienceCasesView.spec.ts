import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CustomerExperienceCasesView from '../src/views/CustomerExperienceCasesView.vue'
import { listAdminExperienceCases, updateAdminExperienceCaseReview } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  listAdminExperienceCases: vi.fn(),
  updateAdminExperienceCaseReview: vi.fn(),
  apiErrorMessage: vi.fn(() => 'Experience-case request failed'),
}))

const mockedList = vi.mocked(listAdminExperienceCases)
const mockedUpdate = vi.mocked(updateAdminExperienceCaseReview)

function experienceCase(status: 'NEW' | 'REVIEWING' = 'NEW') {
  return {
    case_id: 'CEC-TEST-1', revision: 1, source_type: 'CUSTOMER_SERVICE_SUBMITTED',
    store_code: 'STORE-1', product_id: 'PRODUCT-1', sku_id: 'SKU-1',
    question: 'What age is appropriate?', ai_answer: 'AI answer', final_answer: 'Final service answer',
    feedback_type: 'EDITED_ADOPTED' as const, created_by: 'support-tester', review_status: status,
    review_note: null, reviewed_by: null, reviewed_at: null, export_revision: null, content_hash: null,
    redaction_version: 'v1-reminder-only', evaluation_status: 'NOT_EXPORTED' as const,
    latest_evaluation_run_id: null, created_at: '2026-07-25T08:00:00Z', updated_at: '2026-07-25T08:00:00Z',
  }
}

describe('CustomerExperienceCasesView', () => {
  beforeEach(() => { mockedList.mockReset(); mockedUpdate.mockReset() })

  it('filters, reveals the review detail, and sends only review lifecycle data', async () => {
    mockedList.mockResolvedValue({ items: [experienceCase()], page: 1, size: 20, total: 1 })
    mockedUpdate.mockResolvedValue({ ...experienceCase('REVIEWING'), reviewed_by: 'ops-1', review_note: 'Started.' })
    const wrapper = mount(CustomerExperienceCasesView)
    await flushPromises()

    expect(wrapper.text()).toContain('CEC-TEST-1')
    await wrapper.get('.link-button').trigger('click')
    expect(wrapper.text()).toContain('What age is appropriate?')
    await wrapper.get('input[aria-label="试运行操作人 ID"]').setValue('ops-1')
    await wrapper.get('textarea').setValue('Started.')
    await wrapper.get('.actions .button').trigger('click')
    await flushPromises()

    expect(mockedUpdate).toHaveBeenCalledWith('CEC-TEST-1', {
      review_status: 'REVIEWING', review_note: 'Started.', reviewed_by: 'ops-1',
    })

    const inputs = wrapper.findAll('.filters input')
    await inputs[0].setValue('STORE-1')
    await wrapper.get('form').trigger('submit')
    expect(mockedList.mock.calls.at(-1)?.[0]).toMatchObject({ store_code: 'STORE-1' })
  })
})
