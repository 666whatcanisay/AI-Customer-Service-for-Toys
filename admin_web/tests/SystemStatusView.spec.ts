import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SystemStatusView from '../src/views/SystemStatusView.vue'
import { getHealth, getServerRuntime, isOfflineError } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  getHealth: vi.fn(),
  getServerRuntime: vi.fn(),
  isOfflineError: vi.fn(() => false),
}))

const mockedGetHealth = vi.mocked(getHealth)
const mockedGetServerRuntime = vi.mocked(getServerRuntime)
const mockedIsOfflineError = vi.mocked(isOfflineError)

const serverRuntime = {
  schema_version: 'ai-cs.server-runtime-console.v1' as const,
  server: {
    status: 'READY' as const,
    version: 'ai-cs-server-runtime.rc1',
    runtime_mode: 'standard',
    network_mode: 'LAN' as const,
  },
  gateway: {
    enabled: true,
    status: 'HEALTHY' as const,
    version: 'ai-cs-gateway.v1',
    contract_version: '1.0' as const,
    configuration_state: 'CONFIGURED' as const,
  },
}

describe('SystemStatusView', () => {
  beforeEach(() => {
    mockedGetHealth.mockReset()
    mockedGetServerRuntime.mockReset()
    mockedGetServerRuntime.mockResolvedValue(serverRuntime)
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
    expect(wrapper.get('[data-testid="server-runtime-status"]').text()).toContain('READY')
    expect(wrapper.get('[data-testid="server-runtime-status"]').text()).toContain('HEALTHY')
    expect(wrapper.get('[data-testid="server-runtime-status"]').text()).toContain('1.0')
    expect(wrapper.get('[data-testid="server-runtime-status"]').text()).toContain('LAN')
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
