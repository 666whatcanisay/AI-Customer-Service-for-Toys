import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { authSessionTestControl } from '@/auth/authSession'
import ChannelAgentDesktopLayout from './ChannelAgentDesktopLayout.vue'

const desktopMocks = vi.hoisted(() => ({
  bootstrap: vi.fn(),
  safeStop: vi.fn(),
  selectStore: vi.fn(),
  openPdd: vi.fn()
}))

vi.mock('@/api/channelAgentDesktopClient', () => ({
  fetchChannelAgentBootstrap: desktopMocks.bootstrap,
  requestChannelAgentSafeStop: desktopMocks.safeStop,
  selectChannelAgentActiveStore: desktopMocks.selectStore,
  requestChannelAgentPddWindowOpen: desktopMocks.openPdd
}))

describe('ChannelAgentDesktopLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authSessionTestControl.setUser({
      id: '11111111-1111-4111-8111-111111111111',
      username: 'support.one',
      display_name: '客服小木',
      status: 'ACTIVE',
      roles: ['CUSTOMER_SERVICE'],
      permissions: ['workspace.access', 'ai.reply'],
      stores: [
        {
          id: 1,
          store_id: 1,
          store_code: 'store-ref:1',
          store_name: '玩具乐园积木店',
          platform: 'pdd',
          is_default: true,
          platform_bindings: [{
            platform: 'pinduoduo',
            platform_store_id: '328616090',
            status: 'ACTIVE',
            verified_at: '2026-08-10T00:00:00Z',
            verified_by: 'admin'
          }]
        },
        {
          id: 2,
          store_id: 2,
          store_code: 'store-ref:2',
          store_name: '旧测试店铺',
          platform: 'pdd',
          is_default: false,
          platform_bindings: []
        }
      ],
      must_change_password: false,
      all_store_access: false,
      created_at: '2026-08-07T00:00:00Z',
      updated_at: '2026-08-07T00:00:00Z'
    })
    desktopMocks.bootstrap.mockResolvedValue({
      schema_version: '1.0',
      agent: { process_status: 'RUNNING', runtime_status: 'ONLINE', version: '1.4.0', node_id: 'agent-1' },
      browser: {
        status: 'OPENED',
        pdd_login_state: 'CUSTOMER_SERVICE_READY',
        pdd_workspace_refresh_available: true,
        message_source: 'OFFLINE_REPLAY',
        real_pdd_message_observation_enabled: false
      },
      binding: {
        authorized_store_ids: ['store-ref:1', 'store-ref:2'],
        active_store_id: 'store-ref:1',
        observed_store_id: 'store-ref:1',
        store_reference: 'store-ref:1'
      },
      safety: { manual_approval: true, auto_reply: false, real_send_enabled: false }
    })
  })

  it('opens the dedicated PDD Edge only after the user clicks while stopped', async () => {
    desktopMocks.bootstrap.mockResolvedValue({
      schema_version: '1.0',
      agent: { process_status: 'RUNNING', runtime_status: 'ONLINE', version: '1.4.0', node_id: 'agent-1' },
      browser: {
        status: 'STOPPED',
        pdd_login_state: null,
        pdd_workspace_launch_available: true,
        message_source: 'OFFLINE_REPLAY',
        real_pdd_message_observation_enabled: false
      },
      binding: {
        authorized_store_ids: ['store-ref:1'],
        active_store_id: 'store-ref:1',
        observed_store_id: 'store-ref:1',
        store_reference: 'store-ref:1'
      },
      safety: { manual_approval: true, auto_reply: false, real_send_enabled: false }
    })
    desktopMocks.openPdd.mockResolvedValue({
      schema_version: 'channel-agent-pdd-window-launch.v1',
      status: 'OPENING',
      browser_status: 'WAITING_LOGIN',
      pdd_login_state: 'PDD_LOGIN_PAGE',
      human_login_required: true,
      observer_started: false,
      real_send_enabled: false
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }]
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(ChannelAgentDesktopLayout, {
      global: { plugins: [router, ElementPlus] }
    })
    await flushPromises()

    expect(wrapper.text()).toContain('PDD 已停止')
    await wrapper.get('[data-testid="open-pdd-window"]').trigger('click')
    await flushPromises()

    expect(desktopMocks.openPdd).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('PDD 等待扫码')
    expect(wrapper.find('[data-testid="open-pdd-window"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows only the customer desktop shell with Agent, PDD and safety status', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div>客服会话内容</div>' } }]
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(ChannelAgentDesktopLayout, {
      global: { plugins: [router, ElementPlus] }
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="agent-desktop-shell"]').text()).toContain('AI 客服助手')
    expect(wrapper.text()).toContain('Agent 在线')
    expect(wrapper.text()).toContain('PDD 客服工作台已就绪')
    expect(wrapper.get('[data-testid="message-source-status"]').text()).toContain('消息源 离线回放')
    expect(wrapper.get('[data-testid="message-source-status"]').classes()).toContain('attention')
    expect(wrapper.get('[data-testid="pdd-workspace-guide"]').text()).toContain(
      'https://mms.pinduoduo.com/chat-merchant/index.html#'
    )
    expect(wrapper.text()).toContain('当前店铺 玩具乐园积木店 · PDD 328616090')
    expect(wrapper.get('[data-testid="active-store-status"]').classes()).toContain('healthy')
    expect(wrapper.get('select[aria-label="当前工作店铺"]').element).toBeInstanceOf(HTMLSelectElement)
    expect(wrapper.get('select[aria-label="当前工作店铺"]').text()).toContain('玩具乐园积木店 · PDD 328616090')
    expect(wrapper.get('select[aria-label="当前工作店铺"]').text()).toContain('旧测试店铺（未绑定PDD）')
    expect(wrapper.text()).toContain('人工确认模式')
    expect(wrapper.text()).not.toContain('知识管理')
    expect(wrapper.text()).not.toContain('系统管理')
    wrapper.unmount()
  })

  it('does not present the offline replay restart as real PDD observation', async () => {
    desktopMocks.bootstrap.mockResolvedValue({
      schema_version: '1.0',
      agent: { process_status: 'RUNNING', runtime_status: 'ONLINE', version: '1.4.0', node_id: 'agent-1' },
      browser: {
        status: 'READY',
        pdd_login_state: 'CUSTOMER_SERVICE_READY',
        observer_status: 'SESSION_LIMIT_REACHED',
        observer_restart_available: true,
        pdd_workspace_refresh_available: true,
        message_source: 'OFFLINE_REPLAY',
        real_pdd_message_observation_enabled: false
      },
      binding: {
        authorized_store_ids: ['store-ref:1'],
        active_store_id: 'store-ref:1',
        observed_store_id: 'store-ref:1',
        store_reference: 'store-ref:1'
      },
      safety: { manual_approval: true, auto_reply: false, real_send_enabled: false }
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }]
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(ChannelAgentDesktopLayout, {
      global: { plugins: [router, ElementPlus] }
    })
    await flushPromises()

    const restart = wrapper.get('[data-testid="restart-pdd-observer"]')
    expect(restart.text()).toContain('当前为离线回放')
    expect((restart.element as HTMLButtonElement).disabled).toBe(true)
    wrapper.unmount()
  })

  it('only reports real message reading as enabled from explicit runtime facts', async () => {
    desktopMocks.bootstrap.mockResolvedValue({
      schema_version: '1.0',
      agent: { process_status: 'RUNNING', runtime_status: 'ONLINE', version: '1.4.0', node_id: 'agent-1' },
      browser: {
        status: 'READY',
        pdd_login_state: 'CUSTOMER_SERVICE_READY',
        message_source: 'REAL_PDD',
        real_pdd_message_observation_enabled: true
      },
      binding: {
        authorized_store_ids: ['store-ref:1'],
        active_store_id: 'store-ref:1',
        observed_store_id: 'store-ref:1',
        store_reference: 'store-ref:1'
      },
      safety: { manual_approval: true, auto_reply: false, real_send_enabled: false }
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }]
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(ChannelAgentDesktopLayout, {
      global: { plugins: [router, ElementPlus] }
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="message-source-status"]').text()).toContain('真实消息读取 已启用')
    expect(wrapper.get('[data-testid="message-source-status"]').classes()).toContain('healthy')
    wrapper.unmount()
  })
})
