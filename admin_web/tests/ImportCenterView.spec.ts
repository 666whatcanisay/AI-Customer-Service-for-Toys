import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ImportCenterView from '../src/views/ImportCenterView.vue'

describe('ImportCenterView', () => {
  it('offers six Chinese operations workbooks and the controlled upload entry', () => {
    const wrapper = mount(ImportCenterView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })

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
    expect(wrapper.text()).toContain('进入资料上传与审核')
  })
})
