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

  it('keeps source filenames and checksums in controlled table cells', async () => {
    mockedList.mockResolvedValue({
      items: [{
        source_type: 'PRODUCT_DETAIL_SCREENSHOT',
        file_name: '汕明_812580876528_商品参数_G1005.png',
        file_sha256: '66850eb1a594e3f408566711382f7139daa474abb696112b483b80d8796387',
        product_id: 'PDD-SM-P0001',
        sku_id: null,
      }],
      page: 1,
      size: 20,
      total: 1,
    })
    const wrapper = mount(ReadonlyListView, {
      props: {
        resource: 'sources',
        title: '知识来源',
        description: '只读来源元数据。',
        columns: [
          { key: 'source_type', label: '类型' },
          { key: 'file_name', label: '文件' },
          { key: 'file_sha256', label: '校验值' },
          { key: 'product_id', label: '商品' },
          { key: 'sku_id', label: 'SKU' },
        ],
      },
      global: { stubs: { RouterLink: routerLink } },
    })
    await flushPromises()

    expect(wrapper.find('table').classes()).toContain('source-table')
    expect(wrapper.find('.source-type-cell').text()).toBe('商品详情截图')
    expect(wrapper.find('.source-file-cell').text()).toContain('汕明_812580876528_商品参数_G1005.png')
    expect(wrapper.find('.source-hash-cell').text()).toContain('66850eb1a594e3f408566711382f7139daa474abb696112b483b80d8796387')
  })
})
