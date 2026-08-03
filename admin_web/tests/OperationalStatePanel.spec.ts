import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import OperationalStatePanel from '../src/components/OperationalStatePanel.vue'

describe('OperationalStatePanel', () => {
  it.each([
    ['loading', '正在处理'],
    ['empty', '暂无数据'],
    ['error', '读取失败'],
    ['success', '操作完成'],
  ] as const)('renders %s with what happened, why and what to do next', (state, label) => {
    const wrapper = mount(OperationalStatePanel, {
      props: { state, title: '当前状态', reason: '真实原因', nextStep: '执行下一步' },
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })

    expect(wrapper.attributes('data-state')).toBe(state)
    expect(wrapper.text()).toContain(label)
    expect(wrapper.text()).toContain('当前状态')
    expect(wrapper.text()).toContain('原因：真实原因')
    expect(wrapper.text()).toContain('下一步：执行下一步')
    expect(wrapper.attributes('role')).toBe(state === 'error' ? 'alert' : 'status')
  })

  it('supports existing-route navigation and an explicit retry action', async () => {
    const retry = vi.fn()
    const wrapper = mount(OperationalStatePanel, {
      props: {
        state: 'error', title: '读取失败', reason: '服务异常', nextStep: '重试或返回',
        actionLabel: '返回工作台', actionTo: '/overview', retryLabel: '重新读取', onRetry: retry,
      },
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })

    expect(wrapper.text()).toContain('返回工作台')
    await wrapper.get('button').trigger('click')
    expect(retry).toHaveBeenCalledOnce()
  })
})
