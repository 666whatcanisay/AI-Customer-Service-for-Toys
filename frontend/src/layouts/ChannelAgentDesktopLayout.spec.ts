import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { authSessionTestControl } from '@/auth/authSession'
import ChannelAgentDesktopLayout from './ChannelAgentDesktopLayout.vue'

const desktopMocks = vi.hoisted(() => ({
  bootstrap: vi.fn(),
  safeStop: vi.fn(),
  toggleAuto: vi.fn(),
  repairAuto: vi.fn(),
  selectStore: vi.fn(),
  openPdd: vi.fn(),
  refreshPdd: vi.fn(),
  restartObserver: vi.fn(),
  getDesktopStatus: vi.fn(),
  getPolicy: vi.fn(),
  setPolicy: vi.fn()
}))

vi.mock('@/api/channelAgentDesktopClient', () => ({
  fetchChannelAgentBootstrap: desktopMocks.bootstrap,
  requestChannelAgentControlledAutoToggle: desktopMocks.toggleAuto,
  requestChannelAgentControlledAutoRepair: desktopMocks.repairAuto,
  requestChannelAgentSafeStop: desktopMocks.safeStop,
  selectChannelAgentActiveStore: desktopMocks.selectStore,
  requestChannelAgentPddWindowOpen: desktopMocks.openPdd,
  requestChannelAgentPddWorkspaceRefresh: desktopMocks.refreshPdd,
  requestChannelAgentPddObserverRestart: desktopMocks.restartObserver
}))

vi.mock('@/api/desktopAgentClient', () => ({
  desktopAgentClient: { getStatus: desktopMocks.getDesktopStatus }
}))

vi.mock('@/api/offlineReplyControlClient', () => ({
  offlineReplyControlClient: {
    getPolicy: desktopMocks.getPolicy,
    setPolicy: desktopMocks.setPolicy
  }
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
        message_source: 'REAL_PDD',
        real_pdd_message_observation_enabled: true
      },
      binding: {
        authorized_store_ids: ['store-ref:1', 'store-ref:2'],
        active_store_id: 'store-ref:1',
        observed_store_id: '328616090',
        store_reference: 'store-ref:1'
      },
      safety: { manual_approval: true, auto_reply: false, real_send_enabled: false }
    })
    desktopMocks.getDesktopStatus.mockResolvedValue({
      userId: '11111111-1111-4111-8111-111111111111', storeId: 1,
      storeCode: 'store-ref:1', associationState: 'READY',
      agent: {
        agentId: 'agent-1', deviceId: 'device-1', deviceName: 'CS-PC-01',
        agentVersion: '1.4.0', identityStatus: 'ACTIVE', onlineStatus: 'ONLINE',
        runtimeStatus: 'RUNNING', productionEligible: true, bindingRevision: 1,
        lastHeartbeat: '2026-08-15T01:00:00Z'
      }, checkedAt: '2026-08-15T01:00:01Z'
    })
    desktopMocks.getPolicy.mockResolvedValue({
      storeId: '1', mode: 'MANUAL_CONFIRM', revision: 1,
      updatedBy: 'admin', updatedAt: '2026-08-15T01:00:00Z'
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
        observed_store_id: '328616090',
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
      global: { plugins: [createPinia(), router, ElementPlus] }
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="runtime-action-alert"]').text()).toContain('PDD 专属窗口未启动')
    await wrapper.get('[data-testid="open-pdd-window"]').trigger('click')
    await flushPromises()

    expect(desktopMocks.openPdd).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[data-testid="runtime-action-alert"]').text()).toContain('等待扫码登录')
    expect(wrapper.find('[data-testid="open-pdd-window"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps the healthy header minimal and moves diagnostics into runtime details', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div>客服会话内容</div>' } }]
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(ChannelAgentDesktopLayout, {
      global: { plugins: [createPinia(), router, ElementPlus] }
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="agent-desktop-shell"]').text()).toContain('AI 客服助手')
    expect(wrapper.get('[data-testid="overall-runtime-status"]').text()).toContain('就绪')
    expect(wrapper.find('[data-testid="runtime-action-alert"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="message-source-status"]').exists()).toBe(false)
    expect(wrapper.get('select[aria-label="当前工作店铺"]').element).toBeInstanceOf(HTMLSelectElement)
    expect(wrapper.get('select[aria-label="当前工作店铺"]').text()).toContain('玩具乐园积木店 · PDD 328616090')
    expect(wrapper.get('select[aria-label="当前工作店铺"]').text()).toContain('旧测试店铺（未绑定PDD）')
    await wrapper.get('[data-testid="open-runtime-details"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="message-source-status"]').text()).toContain('真实消息读取 已启用')
    expect(wrapper.get('[data-testid="runtime-details-drawer"]').text()).toContain(
      'https://mms.pinduoduo.com/chat-merchant/index.html#'
    )
    expect(wrapper.get('[data-testid="runtime-details-drawer"]').text()).toContain('CS-PC-01')
    expect(wrapper.get('[data-testid="runtime-details-drawer"]').text()).toContain('REAL_SEND = OFF')
    expect(wrapper.get('[data-testid="controlled-auto-scope"]').text()).toContain('仅当前人工打开的 PDD 会话')
    expect(wrapper.get('[data-testid="controlled-auto-scope"]').text()).toContain('不会自动点击、滚动或切换买家列表')
    expect(wrapper.text()).not.toContain('知识管理')
    expect(wrapper.text()).not.toContain('系统管理')
    wrapper.unmount()
  })

  it('shows desired AUTO as waiting instead of claiming it is already running', async () => {
    desktopMocks.bootstrap.mockResolvedValue({
      schema_version: '1.0',
      agent: { process_status: 'RUNNING', runtime_status: 'ONLINE', version: '1.4.0', node_id: 'agent-1' },
      browser: {
        status: 'OPENED', pdd_login_state: 'PDD_LOGIN_PAGE',
        message_source: 'REAL_PDD', real_pdd_message_observation_enabled: true
      },
      binding: {
        authorized_store_ids: ['store-ref:1'], active_store_id: 'store-ref:1',
        observed_store_id: null, store_reference: 'store-ref:1'
      },
      safety: {
        manual_approval: true, auto_reply: false, real_send_enabled: false,
        controlled_auto: {
          runtime_mode: 'PRODUCTION_AUTO', production_real_send_enabled: true,
          controlled_store_auto_enabled: true, policy_mode: 'AUTO_ALL_MESSAGES_V1',
          kill_switch_enabled: false, ai_cs_store_id: 'store-ref:1',
          platform_store_id: '328616090', state_revision: 4, state_reason: 'ACTIVE',
          runner_active: false, control_available: false, auto_reply_running: false,
          desired_auto_reply_enabled: true, supervisor_active: true,
          supervisor_state: 'WAITING_FOR_CURRENT_PDD_CONVERSATION',
          observation_scope: 'CURRENT_ACTIVE_CONVERSATION_ONLY',
          automatic_navigation_enabled: false,
          control_error_code: null, updated_at: '2026-08-16T08:00:00Z'
        }
      }
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }]
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(ChannelAgentDesktopLayout, {
      global: { plugins: [createPinia(), router, ElementPlus] }
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="controlled-auto-toggle"]').text()).toContain('等待当前会话')
    expect(wrapper.get('[data-testid="controlled-auto-toggle"]').attributes('title')).toContain('不会自动切换其他买家会话')
    expect(wrapper.get('[data-testid="controlled-auto-repair"]').text()).toContain('一键修复')
    wrapper.unmount()
  })

  it('shows and switches the authoritative production AUTO state', async () => {
    vi.useFakeTimers()
    const running = {
      schema_version: '1.0',
      agent: { process_status: 'RUNNING', runtime_status: 'ONLINE', version: '1.4.0', node_id: 'agent-1' },
      browser: {
        status: 'OPENED', pdd_login_state: 'CUSTOMER_SERVICE_READY',
        message_source: 'REAL_PDD', real_pdd_message_observation_enabled: true
      },
      binding: {
        authorized_store_ids: ['store-ref:1'], active_store_id: 'store-ref:1',
        observed_store_id: '328616090', store_reference: 'store-ref:1'
      },
      safety: {
        manual_approval: true, auto_reply: true, real_send_enabled: true,
        controlled_auto: {
          runtime_mode: 'PRODUCTION_AUTO', production_real_send_enabled: true,
          controlled_store_auto_enabled: true, policy_mode: 'AUTO_ALL_MESSAGES_V1',
          kill_switch_enabled: false, ai_cs_store_id: 'store-ref:1',
          platform_store_id: '328616090', state_revision: 4, state_reason: 'ACTIVE',
          runner_active: true, control_available: true, auto_reply_running: true,
          control_error_code: null, updated_at: '2026-08-15T08:00:00Z'
        }
      }
    }
    const paused = {
      ...running,
      safety: {
        ...running.safety,
        auto_reply: false,
        real_send_enabled: false,
        controlled_auto: {
          ...running.safety.controlled_auto,
          runtime_mode: 'PILOT',
          production_real_send_enabled: false,
          controlled_store_auto_enabled: false,
          kill_switch_enabled: true,
          state_revision: 5,
          state_reason: 'USER_PAUSED',
          auto_reply_running: false
        }
      }
    }
    desktopMocks.bootstrap.mockResolvedValueOnce(running).mockResolvedValue(paused)
    desktopMocks.toggleAuto.mockResolvedValue({
      schema_version: 'controlled-auto-toggle-response.v1',
      status: 'TOGGLE_REQUESTED',
      target_enabled: false
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }]
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(ChannelAgentDesktopLayout, {
      global: { plugins: [createPinia(), router, ElementPlus] }
    })
    await flushPromises()
    expect(wrapper.get('[data-testid="controlled-auto-toggle"]').text()).toContain('当前会话自动回复中')
    await wrapper.get('[data-testid="open-runtime-details"]').trigger('click')
    expect(wrapper.get('[data-testid="runtime-details-drawer"]').text()).toContain('REAL_SEND = ON')

    await wrapper.get('[data-testid="controlled-auto-toggle"]').trigger('click')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    expect(desktopMocks.toggleAuto).toHaveBeenCalledWith(false)
    expect(wrapper.get('[data-testid="controlled-auto-toggle"]').text()).toContain('当前会话自动回复已暂停')
    wrapper.unmount()
    vi.useRealTimers()
  })

  it('offers one-click repair and restores AUTO to a paused usable state', async () => {
    vi.useFakeTimers()
    const broken = {
      schema_version: '1.0',
      agent: { process_status: 'RUNNING', runtime_status: 'ONLINE', version: '1.4.0', node_id: 'agent-1' },
      browser: {
        status: 'OPENED', pdd_login_state: 'CUSTOMER_SERVICE_READY',
        message_source: 'REAL_PDD', real_pdd_message_observation_enabled: true
      },
      binding: {
        authorized_store_ids: ['store-ref:1'], active_store_id: 'store-ref:1',
        observed_store_id: '328616090', store_reference: 'store-ref:1'
      },
      safety: {
        manual_approval: true, auto_reply: false, real_send_enabled: false,
        controlled_auto: {
          runtime_mode: 'PILOT', production_real_send_enabled: false,
          controlled_store_auto_enabled: false, policy_mode: 'MANUAL_CONFIRM',
          kill_switch_enabled: true, ai_cs_store_id: null, platform_store_id: null,
          state_revision: 8, state_reason: 'UNKNOWN_SEND_RESULT', runner_active: true,
          control_available: true, auto_reply_running: false,
          control_error_code: 'PDD_SEND_CONFIRMATION_TIMEOUT_UNKNOWN',
          updated_at: '2026-08-15T09:00:00Z'
        }
      }
    }
    const repaired = {
      ...broken,
      safety: {
        ...broken.safety,
        controlled_auto: {
          ...broken.safety.controlled_auto,
          policy_mode: 'AUTO_ALL_MESSAGES_V1', ai_cs_store_id: 'store-ref:1',
          platform_store_id: '328616090', state_revision: 9,
          state_reason: 'USER_REPAIRED_PRODUCTION_AUTO_FROM_DESKTOP',
          control_error_code: null
        }
      }
    }
    desktopMocks.bootstrap.mockResolvedValueOnce(broken).mockResolvedValue(repaired)
    desktopMocks.repairAuto.mockResolvedValue({
      schema_version: 'controlled-auto-repair-response.v1',
      status: 'REPAIR_REQUESTED'
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }]
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(ChannelAgentDesktopLayout, {
      global: { plugins: [createPinia(), router, ElementPlus] }
    })
    await flushPromises()
    expect(wrapper.get('[data-testid="controlled-auto-repair"]').text()).toContain('一键修复')

    await wrapper.get('[data-testid="controlled-auto-repair"]').trigger('click')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    expect(desktopMocks.repairAuto).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-testid="controlled-auto-repair"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="controlled-auto-toggle"]').text()).toContain('当前会话自动回复已暂停')
    wrapper.unmount()
    vi.useRealTimers()
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
        observed_store_id: '328616090',
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
      global: { plugins: [createPinia(), router, ElementPlus] }
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="runtime-action-alert"]').text()).toContain('当前为离线回放')
    expect(wrapper.find('[data-testid="restart-pdd-observer"]').exists()).toBe(false)
    await wrapper.get('[data-testid="open-runtime-details"]').trigger('click')
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
        observed_store_id: '328616090',
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
      global: { plugins: [createPinia(), router, ElementPlus] }
    })
    await flushPromises()

    await wrapper.get('[data-testid="open-runtime-details"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="message-source-status"]').text()).toContain('真实消息读取 已启用')
    expect(wrapper.get('[data-testid="overall-runtime-status"]').text()).toContain('就绪')
    wrapper.unmount()
  })

  it('compares PDD store ids and lets the operator confirm a unique authorized mapping', async () => {
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
        authorized_store_ids: ['store-ref:1', 'store-ref:2'],
        active_store_id: 'store-ref:2',
        observed_store_id: '328616090',
        store_reference: 'store-ref:1'
      },
      safety: { manual_approval: true, auto_reply: false, real_send_enabled: false }
    })
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({ action: 'confirm' } as never)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }]
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(ChannelAgentDesktopLayout, {
      global: { plugins: [createPinia(), router, ElementPlus] }
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="runtime-action-alert"]').text()).toContain('页面店铺与当前店铺不一致')
    await wrapper.get('[data-testid="confirm-observed-store"]').trigger('click')
    await flushPromises()

    expect(desktopMocks.selectStore).toHaveBeenCalledOnce()
    expect(desktopMocks.selectStore).toHaveBeenCalledWith('store-ref:1')
    wrapper.unmount()
  })
})
