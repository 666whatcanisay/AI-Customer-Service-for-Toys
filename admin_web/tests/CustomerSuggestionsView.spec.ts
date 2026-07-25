import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CustomerSuggestionsView from '../src/views/CustomerSuggestionsView.vue'
import { listAdminSuggestions, updateAdminSuggestion } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  listAdminSuggestions: vi.fn(),
  updateAdminSuggestion: vi.fn(),
  apiErrorMessage: vi.fn(() => 'Suggestion request failed'),
}))

const mockedList = vi.mocked(listAdminSuggestions)
const mockedUpdate = vi.mocked(updateAdminSuggestion)

function suggestion(status: 'SUBMITTED' | 'REVIEWING' = 'SUBMITTED') {
  return {
    id: 'suggestion-1', reporter_id: 'private-agent', reporter_name: 'Private name', store_code: 'STORE-1',
    module_key: 'customer-chat', category: 'workflow', title: 'Safety reminder', description: 'Make it easier to find.',
    frequency: 'weekly', urgency: 'HIGH', status, internal_note: null,
    created_at: '2026-07-25T08:00:00Z', updated_at: '2026-07-25T08:00:00Z',
  }
}

describe('CustomerSuggestionsView', () => {
  beforeEach(() => { mockedList.mockReset(); mockedUpdate.mockReset() })

  it('masks reporter details in the portal and submits only lifecycle fields', async () => {
    mockedList.mockResolvedValue({ items: [suggestion()], page: 1, size: 20, total: 1 })
    mockedUpdate.mockResolvedValue({ ...suggestion('REVIEWING'), internal_note: 'Reviewed.' })
    const wrapper = mount(CustomerSuggestionsView)
    await flushPromises()

    expect(wrapper.text()).toContain('Safety reminder')
    expect(wrapper.text()).not.toContain('Private name')
    await wrapper.get('.link-button').trigger('click')
    await wrapper.get('textarea').setValue('Reviewed.')
    await wrapper.get('.detail .button').trigger('click')
    await flushPromises()
    expect(mockedUpdate).toHaveBeenCalledWith('suggestion-1', { status: 'SUBMITTED', internal_note: 'Reviewed.' })
  })
})
