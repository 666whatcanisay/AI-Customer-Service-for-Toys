import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import FeedbackGuide from './FeedbackGuide.vue'

describe('FeedbackGuide', () => {
  it('guides the customer to the existing AI workflow without submitting anything', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/ai-chat', component: { template: '<div />' } }
      ]
    })
    const wrapper = mount(FeedbackGuide, { global: { plugins: [router] } })

    expect(wrapper.get('[data-testid="feedback-guide"]').text()).toContain('未采用')
    expect(wrapper.get('a').attributes('href')).toBe('/ai-chat')
    expect(wrapper.text()).toContain('不会自动修改 Prompt、知识或客户消息')
    expect(wrapper.get('[data-testid="feedback-path"]').text()).toContain('提交真实原因')
    expect(wrapper.get('[data-testid="feedback-reason-guide"]').text()).toContain('事实错误')
    expect(wrapper.get('[data-testid="feedback-reason-guide"]').text()).toContain('风险问题')
    expect(wrapper.findAll('[data-testid="feedback-reason-guide"] article')).toHaveLength(5)
    expect(wrapper.get('[data-testid="capture-feedback-boundary"]').text()).toContain('优秀回复')
    expect(wrapper.get('[data-testid="capture-feedback-boundary"]').text()).toContain('不会变成优秀案例')
  })
})
