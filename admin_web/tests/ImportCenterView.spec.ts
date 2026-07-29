import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ImportCenterView from '../src/views/ImportCenterView.vue'

const apiMocks = vi.hoisted(() => ({
  listOperationStores: vi.fn(),
  apiErrorMessage: vi.fn(() => '暂时不可用'),
}))

vi.mock('../src/api/client', () => apiMocks)

describe('ImportCenterView', () => {
  beforeEach(() => {
    sessionStorage.clear()
    apiMocks.listOperationStores.mockResolvedValue({ items: [], total: 0 })
  })

  it('offers six Chinese operations workbooks and a create-store entry when no store exists', async () => {
    const wrapper = mount(ImportCenterView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    const downloads = wrapper.findAll('a[download]')
    expect(downloads).toHaveLength(6)
    expect(downloads.map((item) => item.attributes('href'))).toEqual([
      '/templates/商品知识采集模板V1.xlsx',
      '/templates/SKU差异知识采集模板V1.xlsx',
      '/templates/客服FAQ知识采集模板V1.xlsx',
      '/templates/商品安全规则采集模板V1.xlsx',
      '/templates/客服AI问题反馈模板V1.xlsx',
      '/templates/AI知识缺口管理模板V1.xlsx',
    ])
    expect(wrapper.text()).toContain('数据填写')
    expect(wrapper.text()).toContain('不收集价格、库存、财务、采购和平台技术标识')
    expect(wrapper.text()).toContain('旧版试点数据入口（兼容保留）')
    expect(wrapper.text()).toContain('不会在下载或上传后自动发布知识')
    expect(wrapper.text()).toContain('当前还没有可用店铺')
    expect(wrapper.text()).toContain('创建店铺')
  })

  it('allows a newly created active store to be selected by Chinese business name', async () => {
    apiMocks.listOperationStores.mockResolvedValue({
      items: [{
        store_ref: 7,
        store_name: '木木小栈拼多多旗舰店',
        platform_name: '拼多多',
        status: 'ACTIVE',
        status_name: '正常',
        product_count: 0,
        created_at: '2026-07-29T08:00:00Z',
        remarks: '',
      }],
      total: 1,
    })
    const wrapper = mount(ImportCenterView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    await wrapper.get('select').setValue('7')

    expect(wrapper.text()).toContain('木木小栈拼多多旗舰店 · 拼多多')
    expect(wrapper.text()).toContain('已选择：木木小栈拼多多旗舰店')
    expect(sessionStorage.getItem('c-operation-import-store-ref')).toBe('7')
  })
})
