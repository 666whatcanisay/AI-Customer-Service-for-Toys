import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ImportCenterView from '../src/views/ImportCenterView.vue'

describe('ImportCenterView', () => {
  it('offers the four actual preparation templates and labels non-batch material preparation honestly', () => {
    const wrapper = mount(ImportCenterView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })

    const downloads = wrapper.findAll('a[download]')
    expect(downloads).toHaveLength(4)
    expect(downloads.map((link) => link.attributes('href'))).toEqual([
      '/templates/product-material-template.csv',
      '/templates/sku-material-template.csv',
      '/templates/faq-material-template.csv',
      '/templates/safety-rule-template.csv',
    ])
    expect(wrapper.text()).toContain('不是商品批量导入文件')
    expect(wrapper.text()).toContain('不会自动发布到 AI')
  })
})
