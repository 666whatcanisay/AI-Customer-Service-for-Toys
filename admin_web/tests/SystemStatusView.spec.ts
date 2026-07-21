import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SystemStatusView from '../src/views/SystemStatusView.vue'
import { getHealth, isOfflineError } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  getHealth: vi.fn(),
  isOfflineError: vi.fn(() => false),
}))

const mockedGetHealth = vi.mocked(getHealth)
const mockedIsOfflineError = vi.mocked(isOfflineError)

describe('SystemStatusView', () => {
  beforeEach(() => {
    mockedGetHealth.mockReset()
    mockedIsOfflineError.mockReset()
    mockedIsOfflineError.mockReturnValue(false)
  })

  it('shows loading and then the actual health response', async () => {
    mockedGetHealth.mockResolvedValue({
      status: 'ok',
      service: 'platform-backend',
      version: '0.1.0',
      request_id: 'view-test-id',
    })

    const wrapper = mount(SystemStatusView)
    expect(wrapper.text()).toContain('正在加载')

    await flushPromises()
    expect(wrapper.text()).toContain('正常')
    expect(wrapper.text()).toContain('platform-backend · v0.1.0')
    expect(wrapper.text()).toContain('view-test-id')
  })

  it('shows the offline state when no server response is available', async () => {
    mockedGetHealth.mockRejectedValue(new Error('network unavailable'))
    mockedIsOfflineError.mockReturnValue(true)

    const wrapper = mount(SystemStatusView)
    await flushPromises()

    expect(wrapper.text()).toContain('断网')
    expect(wrapper.text()).toContain('无法连接平台服务')
  })

  it('shows the error state when the server rejects the request', async () => {
    mockedGetHealth.mockRejectedValue(new Error('server error'))

    const wrapper = mount(SystemStatusView)
    await flushPromises()

    expect(wrapper.text()).toContain('错误')
    expect(wrapper.text()).toContain('平台服务返回错误')
  })
})
