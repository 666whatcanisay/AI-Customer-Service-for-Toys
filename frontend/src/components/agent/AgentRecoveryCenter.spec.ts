import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  doctor: vi.fn(), config: vi.fn(), repair: vi.fn(), repairStatus: vi.fn(),
  validate: vi.fn(), save: vi.fn(), discover: vi.fn(), pair: vi.fn()
}))

vi.mock('@/api/channelAgentDesktopClient', () => ({
  fetchChannelAgentDoctor: api.doctor,
  fetchChannelAgentConfig: api.config,
  startChannelAgentRepair: api.repair,
  fetchChannelAgentRepair: api.repairStatus,
  validateChannelAgentConfig: api.validate,
  saveChannelAgentConfig: api.save,
  discoverChannelAgentHosts: api.discover,
  pairChannelAgentHost: api.pair
}))

import AgentRecoveryCenter from './AgentRecoveryCenter.vue'

const safeConfig = {
  schema_version: 'channel-agent-config-center.v1', status: 'PASS',
  basic: { server_url: 'http://127.0.0.1:18020', ai_cs_platform_url: 'http://127.0.0.1:8422', connect_timeout_seconds: 5, heartbeat_interval_seconds: 30 },
  advanced: { runtime_mode: 'MOCK', browser_enabled: false, pdd_login_observation_enabled: false, customer_assistant_enabled: false, pdd_login_url: null, pdd_customer_service_url: null, conversation_buffer_window_seconds: 4 },
  read_only: { agent_id: 'agent-001', device_id: 'device-001' },
  safety: { manual_approval_required: true, auto_reply_enabled: false, real_send_enabled: false, real_platform_activation_allowed: false }
}

describe('AgentRecoveryCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.config.mockResolvedValue(safeConfig)
    api.doctor.mockResolvedValue({
      schema_version: 'channel-agent-doctor.v1', overall: 'BLOCKED', checked_at: '2026-08-08T10:00:00+08:00', mode: 'QUICK', auto_expand: true, safe_to_continue: false, login_allowed: false, sanitized: true,
      components: [
        { component: '本地配置文件', status: 'PASS', status_label: '正常', error_code: 'CONFIG_VALID', reason: '配置正确。', checked_at: '2026-08-08T10:00:00+08:00', repairable: false, next_action: '无需操作。', scope: 'LOGIN', technical: {} },
        { component: 'AI-CS身份服务', status: 'BLOCKED', status_label: '已阻断', error_code: 'AI_CS_ADDRESS_MISSING', reason: '未配置 AI-CS 身份服务地址。', checked_at: '2026-08-08T10:00:00+08:00', repairable: true, next_action: '填写地址。', scope: 'LOGIN', technical: {} }
      ]
    })
  })

  it('auto-expands precise diagnostics when the quick check is blocked', async () => {
    const wrapper = mount(AgentRecoveryCenter)
    await flushPromises()
    expect(wrapper.classes()).toContain('expanded')
    const items = wrapper.findAll('.diagnostic-item')
    expect(items[0].attributes('data-status')).toBe('BLOCKED')
    expect(items[0].attributes('open')).toBeUndefined()
    expect(items[1].attributes('data-status')).toBe('PASS')
    expect(items[0].text()).toContain('AI_CS_ADDRESS_MISSING')
    expect(wrapper.emitted('blocked')?.at(-1)).toEqual([true])
  })

  it('keeps safety switches read-only inside manual configuration', async () => {
    const wrapper = mount(AgentRecoveryCenter)
    await flushPromises()
    await wrapper.get('[data-testid="config-toggle"]').trigger('click')
    expect(wrapper.text()).toContain('必须人工审批')
    expect(wrapper.text()).toContain('禁止自动回复')
    expect(wrapper.text()).toContain('禁止真实发送')
    expect(wrapper.find('input[name="real_send_enabled"]').exists()).toBe(false)
  })

  it('allows account login and sequences dependent onboarding tasks', async () => {
    api.doctor.mockResolvedValue({
      schema_version: 'channel-agent-doctor.v1', overall: 'BLOCKED', checked_at: '2026-08-08T10:00:00+08:00', mode: 'QUICK', auto_expand: true, safe_to_continue: false, login_allowed: true, sanitized: true,
      components: [
        { component: '设备注册与身份绑定', status: 'BLOCKED', status_label: '已阻断', error_code: 'CHANNEL_ENGINE_IDENTITY_UNBOUND', reason: '这是这台电脑第一次使用，尚未和客服账号绑定；不是密码错误。', checked_at: '2026-08-08T10:00:00+08:00', repairable: false, next_action: '请先登录客服账号。', scope: 'ONBOARDING', technical: { identityStatus: 'UNBOUND' } },
        { component: '当前店铺绑定', status: 'WARNING', status_label: '需关注', error_code: 'ACTIVE_STORE_NOT_SELECTED', reason: '等待完成设备绑定后读取授权店铺。', checked_at: '2026-08-08T10:00:00+08:00', repairable: false, next_action: '先完成设备绑定。', scope: 'ONBOARDING', technical: { dependsOn: 'CHANNEL_ENGINE_IDENTITY_UNBOUND' } }
      ]
    })
    const wrapper = mount(AgentRecoveryCenter)
    await flushPromises()

    expect(wrapper.emitted('blocked')?.at(-1)).toEqual([false])
    expect(wrapper.text()).toContain('现在需要完成 1 步')
    expect(wrapper.text()).toContain('随后完成 1 步')
    expect(wrapper.text()).toContain('等待上一步')
    expect(wrapper.text()).toContain('先在左侧登录客服账号')
  })

  it('runs bounded repair and displays the result', async () => {
    api.repair.mockResolvedValue({ repair_id: 'a'.repeat(32), status: 'RUNNING' })
    api.repairStatus.mockResolvedValue({ status: 'RELOAD_REQUESTED', message: '修复检查通过。', requires_human: false })
    const wrapper = mount(AgentRecoveryCenter)
    await flushPromises()
    await wrapper.get('[data-testid="doctor-repair"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 380))
    await flushPromises()
    expect(api.repair).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('修复检查通过')
  })

  it('shows one explicit local Agent failure instead of a false healthy zero-issue state', async () => {
    api.doctor.mockRejectedValue(new Error('synthetic local API unavailable'))
    api.config.mockRejectedValue(new Error('synthetic local API unavailable'))

    const wrapper = mount(AgentRecoveryCenter)
    await flushPromises()

    expect(wrapper.text()).toContain('需要先解决运行故障')
    expect(wrapper.text()).toContain('现在需要完成 1 步')
    expect(wrapper.text()).toContain('客服助手窗口没有连接到本机 ChannelAgent 后台')
    expect(wrapper.text()).toContain('检查并恢复连接')
    expect(wrapper.text()).not.toContain('需要先处理 0 项运行问题')
    expect(wrapper.emitted('blocked')?.at(-1)).toEqual([true])
    expect(wrapper.emitted('status')?.at(-1)).toEqual([{ overall: 'BLOCKED', issues: 1 }])
  })
})
