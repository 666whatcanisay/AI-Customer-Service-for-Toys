import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ReadonlyListView from '../src/views/ReadonlyListView.vue'
import { listAdminResource } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  listAdminResource: vi.fn(),
  apiErrorMessage: vi.fn(() => 'List request failed'),
}))

const mockedList = vi.mocked(listAdminResource)
const routerLink = { props: ['to'], template: '<a><slot /></a>' }
const props = {
  resource: 'products' as const,
  title: 'Products and SKUs',
  description: 'Read-only data.',
  columns: [{ key: 'product_id', label: 'Product ID' }, { key: 'product_name_display', label: 'Product' }],
}

describe('ReadonlyListView', () => {
  beforeEach(() => mockedList.mockReset())

  it('renders returned rows and does not create a fake empty state', async () => {
    mockedList.mockResolvedValue({ items: [{ product_id: 'P-1', product_name_display: 'Synthetic product' }], page: 1, size: 20, total: 1 })
    const wrapper = mount(ReadonlyListView, { props, global: { stubs: { RouterLink: routerLink } } })
    await flushPromises()

    expect(wrapper.text()).toContain('P-1')
    expect(wrapper.text()).toContain('Synthetic product')
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
  })

  it('shows the explicit empty state returned by the API', async () => {
    mockedList.mockResolvedValue({ items: [], page: 1, size: 20, total: 0 })
    const wrapper = mount(ReadonlyListView, { props, global: { stubs: { RouterLink: routerLink } } })
    await flushPromises()

    expect(wrapper.find('p.notice').exists()).toBe(true)
  })
})
