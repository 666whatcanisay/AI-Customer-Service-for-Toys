import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const authMocks = vi.hoisted(() => ({
  user: { value: {
    display_name: '客服小木',
    stores: [{ id: 1, store_id: 1, store_code: 'STORE-A', store_name: '玩具乐园积木店', platform: 'pdd', is_default: false, platform_bindings: [{ platform: 'pinduoduo', platform_store_id: '328616090', status: 'ACTIVE', verified_at: '2026-08-10T00:00:00Z', verified_by: 'admin' }] }]
  } },
  defaultStore: { value: null },
  setDefaultStore: vi.fn()
}))
const localApi = vi.hoisted(() => ({
  bootstrap: vi.fn(), enroll: vi.fn(), sync: vi.fn(), selectStore: vi.fn(), discover: vi.fn(), pair: vi.fn()
}))
const serverApi = vi.hoisted(() => ({
  status: vi.fn(), grant: vi.fn(), activate: vi.fn(), selectStore: vi.fn()
}))
const clipboardWrite = vi.fn()

vi.mock('@/auth/authSession', () => ({
  useAuthSession: () => authMocks
}))
vi.mock('@/api/channelAgentDesktopClient', () => ({
  fetchChannelAgentBootstrap: localApi.bootstrap,
  enrollChannelAgentDevice: localApi.enroll,
  syncChannelAgentIdentity: localApi.sync,
  selectChannelAgentActiveStore: localApi.selectStore,
  discoverChannelAgentHosts: localApi.discover,
  pairChannelAgentHost: localApi.pair
}))
vi.mock('@/api/desktopAgentClient', () => ({
  desktopAgentClient: {
    getStatus: serverApi.status,
    requestBindingGrant: serverApi.grant,
    activateBinding: serverApi.activate,
    selectActiveStore: serverApi.selectStore
  }
}))

import DeviceSetupView from './DeviceSetupView.vue'

const bootstrap = (overrides: Record<string, unknown> = {}) => ({
  schema_version: 'channel-agent-desktop-bootstrap.v1',
  agent: { process_status: 'RUNNING', runtime_status: 'ONLINE', version: '1.6.0', node_id: 'agent-001' },
  browser: { status: 'STOPPED', pdd_login_state: null },
  binding: {
    agent_id: 'agent-001', device_id: 'device-001', identity_status: 'UNBOUND',
    production_eligible: false, authorized_store_ids: [], active_store_id: null,
    observed_store_id: null, store_reference: null,
    ...overrides
  },
  safety: { manual_approval: true, auto_reply: false, real_send_enabled: false }
})

async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/device-setup', component: DeviceSetupView },
      { path: '/workspace', component: { template: '<div>workspace</div>' } }
    ]
  })
  await router.push('/device-setup')
  await router.isReady()
  const wrapper = mount(DeviceSetupView, { global: { plugins: [router] } })
  await flushPromises()
  return { router, wrapper }
}

describe('DeviceSetupView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authMocks.user.value.stores = [{ id: 1, store_id: 1, store_code: 'STORE-A', store_name: '玩具乐园积木店', platform: 'pdd', is_default: false, platform_bindings: [{ platform: 'pinduoduo', platform_store_id: '328616090', status: 'ACTIVE', verified_at: '2026-08-10T00:00:00Z', verified_by: 'admin' }] }]
    authMocks.setDefaultStore.mockResolvedValue(undefined)
    serverApi.grant.mockResolvedValue({ bindingCode: 'A'.repeat(32) })
    serverApi.status.mockResolvedValue({ associationState: 'ACTIVATION_REQUIRED' })
    serverApi.activate.mockResolvedValue({ associationState: 'READY' })
    serverApi.selectStore.mockResolvedValue({ associationState: 'READY' })
    localApi.enroll.mockResolvedValue({ identity_status: 'BOUND' })
    localApi.sync.mockResolvedValue({ identity_status: 'ACTIVE' })
    localApi.selectStore.mockResolvedValue(undefined)
    localApi.discover.mockResolvedValue({ hosts: [{ hostId: 'host-001', hostName: '客服主机', serverAddress: 'https://127.0.0.1:18443', environment: 'STAGING' }] })
    localApi.pair.mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: clipboardWrite }
    })
  })

  it('completes grant, local enrollment, activation and identity sync without exposing the code', async () => {
    localApi.bootstrap
      .mockResolvedValueOnce(bootstrap())
      .mockResolvedValueOnce(bootstrap({ identity_status: 'ACTIVE', authorized_store_ids: ['STORE-A'] }))
    const { wrapper } = await mountView()

    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.get('button.primary').trigger('click')
    await flushPromises()

    expect(serverApi.grant).toHaveBeenCalledWith({ agentId: 'agent-001', deviceId: 'device-001', storeId: 1 })
    expect(localApi.enroll).toHaveBeenCalledWith('A'.repeat(32))
    expect(serverApi.activate).toHaveBeenCalledOnce()
    expect(localApi.sync).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('登录PDD并确认工作店铺')
    expect(wrapper.html()).not.toContain('AAAAAAAA')
  })

  it('accepts an administrator one-time code without requesting another grant or persisting it', async () => {
    localApi.bootstrap
      .mockResolvedValueOnce(bootstrap())
      .mockResolvedValueOnce(bootstrap({ identity_status: 'ACTIVE', authorized_store_ids: ['STORE-A'] }))
    const { wrapper } = await mountView()

    await wrapper.get('input[type="checkbox"]').setValue(true)
    const codeInput = wrapper.get('input[placeholder="输入或粘贴32位绑定码"]')
    await codeInput.setValue('abcd-ef01-2345-6789-abcd-ef01-2345-6789')
    await wrapper.get('.admin-code-entry button').trigger('click')
    await flushPromises()

    expect(localApi.enroll).toHaveBeenCalledWith('ABCDEF0123456789ABCDEF0123456789')
    expect(serverApi.grant).not.toHaveBeenCalled()
    expect(serverApi.activate).toHaveBeenCalledOnce()
    expect(localApi.sync).toHaveBeenCalledOnce()
    expect((codeInput.element as HTMLInputElement).value).toBe('')
    expect(wrapper.html()).not.toContain('ABCDEF0123456789ABCDEF0123456789')
  })

  it('does not silently truncate a 32-character account binding code in the 12-character host pairing step', async () => {
    localApi.bootstrap.mockResolvedValue(bootstrap({ secure_control_ready: false }))
    const { wrapper } = await mountView()

    await wrapper.get('button.secondary').trigger('click')
    await flushPromises()
    const codeInput = wrapper.get('[data-testid="host-pairing-code"]')
    await codeInput.setValue('838912FC25A374145F483B19BB596726')

    expect((codeInput.element as HTMLInputElement).value).toHaveLength(32)
    expect(wrapper.get('[data-testid="host-pairing-code-hint"]').text()).toContain('32位账号绑定码')
    expect(wrapper.get('[data-testid="host-pairing-code-hint"]').text()).toContain('12位主机连接码')
    expect(localApi.pair).not.toHaveBeenCalled()
  })

  it('blocks a selected Store that does not match the read-only PDD observation', async () => {
    localApi.bootstrap.mockResolvedValue(bootstrap({
      identity_status: 'ACTIVE', authorized_store_ids: ['STORE-A'], observed_store_id: 'STORE-B'
    }))
    const { wrapper } = await mountView()

    await wrapper.get('button.primary').trigger('click')
    await flushPromises()

    expect(localApi.selectStore).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('店铺不一致，已安全停止')
    expect(wrapper.text()).toContain('STORE-B')
  })

  it('maps the observed PDD platform ID to the internal Store code and keeps manual confirmation', async () => {
    localApi.bootstrap.mockResolvedValue(bootstrap({
      identity_status: 'ACTIVE', authorized_store_ids: ['STORE-A'], observed_store_id: '328616090'
    }))
    const { wrapper } = await mountView()

    expect(wrapper.text()).toContain('玩具乐园积木店 · PDD 328616090')
    expect(localApi.selectStore).not.toHaveBeenCalled()
    await wrapper.get('.task-box button.primary').trigger('click')
    await flushPromises()

    expect(serverApi.selectStore).toHaveBeenCalledWith({
      agentId: 'agent-001',
      deviceId: 'device-001',
      storeId: 1,
      platform: 'pinduoduo',
      observedPlatformStoreId: '328616090'
    })
    expect(localApi.sync).toHaveBeenCalledOnce()
    expect(authMocks.setDefaultStore).toHaveBeenCalledWith(1)
  })

  it('explains the exact admin path when the account has no Store permission', async () => {
    authMocks.user.value.stores = []
    localApi.bootstrap.mockResolvedValue(bootstrap())
    const { wrapper } = await mountView()

    expect(wrapper.text()).toContain('账号还没有店铺权限')
    expect(wrapper.text()).toContain('运营中心 → 用户管理 → 修改分配')
  })

  it('explains a real Agent response version mismatch without repeating enrollment', async () => {
    localApi.bootstrap
      .mockResolvedValueOnce(bootstrap())
      .mockResolvedValueOnce(bootstrap({ identity_status: 'BOUND', authorized_store_ids: ['STORE-A'] }))
      .mockResolvedValueOnce(bootstrap({ identity_status: 'ACTIVE', authorized_store_ids: ['STORE-A'] }))
    serverApi.activate.mockRejectedValueOnce({
      kind: 'contract', code: 'CHANNEL_AGENT_RESPONSE_INVALID', requestId: 'req-safe-001', status: 502
    })
    const { wrapper } = await mountView()

    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.get('button.primary').trigger('click')
    await flushPromises()

    const guide = wrapper.get('[data-testid="binding-error-guide"]')
    expect(guide.text()).toContain('程序组件版本不一致')
    expect(guide.text()).toContain('不是账号、密码或PDD登录问题')
    expect(guide.text()).toContain('您现在不用做：重新扫码、修改密码、重复绑定电脑')
    expect(guide.text()).toContain('管理员处理方法')
    expect(guide.text()).toContain('stop_ai_customer_service.ps1')
    expect(serverApi.grant).toHaveBeenCalledTimes(1)

    await guide.get('button.primary').trigger('click')
    await flushPromises()
    expect(serverApi.grant).toHaveBeenCalledTimes(1)
    expect(serverApi.status).toHaveBeenCalledWith(1)
    expect(wrapper.text()).toContain('继续完成启用')

    await wrapper.get('.task-box button.primary').trigger('click')
    await flushPromises()
    expect(serverApi.grant).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('登录PDD并确认工作店铺')
  })

  it('copies only the sanitized binding diagnostic', async () => {
    localApi.bootstrap.mockResolvedValue(bootstrap())
    serverApi.grant.mockRejectedValueOnce({
      kind: 'permission_invalid', code: 'CHANNEL_AGENT_OPERATOR_PERMISSION_INVALID',
      requestId: 'req-safe-002', status: 503
    })
    const { wrapper } = await mountView()

    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.get('button.primary').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="binding-error-guide"] button.secondary').trigger('click')
    await flushPromises()

    const copied = String(clipboardWrite.mock.calls[0]?.[0])
    expect(copied).toContain('CHANNEL_AGENT_OPERATOR_PERMISSION_INVALID')
    expect(copied).toContain('req-safe-002')
    expect(copied).toContain('1.6.0')
    expect(copied).not.toContain('binding_code')
    expect(copied).not.toContain('password')
    expect(copied).not.toContain('Cookie')
  })

  it.each([
    [{ kind: 'not_configured', code: 'CHANNEL_AGENT_INTEGRATION_NOT_CONFIGURED' }, '客服设备服务还没有配置好'],
    [{ kind: 'server_unreachable', code: 'CHANNEL_AGENT_SERVER_UNREACHABLE' }, '设备服务暂时没有连接'],
    [{ kind: 'permission_invalid', code: 'CHANNEL_AGENT_OPERATOR_PERMISSION_INVALID' }, '主机接入授权已失效'],
    [{ kind: 'authorization_denied', code: 'AUTHORIZATION_DENIED' }, '当前账号不能绑定这台电脑'],
    [{ body: { error: { code: 'BINDING_CODE_EXPIRED' } } }, '一次性绑定许可已失效'],
    [{ body: { error: { code: 'AGENT_DEVICE_MISMATCH' } } }, '设备信息不匹配'],
    [{ code: 'CHANNEL_AGENT_NOT_REGISTERED' }, '本机Agent还没有注册']
  ])('shows novice guidance for %o', async (caught, expected) => {
    localApi.bootstrap.mockResolvedValue(bootstrap())
    serverApi.grant.mockRejectedValueOnce(caught)
    const { wrapper } = await mountView()

    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.get('button.primary').trigger('click')
    await flushPromises()

    const guide = wrapper.get('[data-testid="binding-error-guide"]')
    expect(guide.text()).toContain(expected)
    expect(guide.text()).toContain('请按下面步骤处理')
    expect(guide.text()).toContain('复制诊断信息')
  })
})
