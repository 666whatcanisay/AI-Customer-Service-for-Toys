import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CustomerOperationsView from './CustomerOperationsView.vue'

describe('CustomerOperationsView', () => {
  it('reuses the existing quality, badcase, knowledge-gap and feedback routes', () => {
    const wrapper = mount(CustomerOperationsView, {
      global: {
        stubs: { RouterLink: { props: ['to'], template: '<a :href="String(to)"><slot /></a>' } }
      }
    })

    expect(wrapper.text()).toContain('AI 回复质量')
    expect(wrapper.text()).toContain('Badcase')
    expect(wrapper.text()).toContain('知识缺口')
    expect(wrapper.text()).toContain('Feedback 分析')
    expect(wrapper.find('a[href="/experience-cases"]').exists()).toBe(true)
    expect(wrapper.find('a[href="/ai-feedback-optimization-pool"]').exists()).toBe(true)
    expect(wrapper.find('a[href="/knowledge-gaps"]').exists()).toBe(true)
    expect(wrapper.find('a[href="/ai-issues"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('不自动修改 Prompt')
  })
})
