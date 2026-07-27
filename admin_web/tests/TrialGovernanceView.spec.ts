import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import TrialGovernanceView from '../src/views/TrialGovernanceView.vue'
import {
  getTrialGovernance,
  listTrialAuditEvents,
  setTrialActor,
  setTrialAuditReason,
} from '../src/api/client'

vi.mock('../src/api/client', () => ({
  getTrialActor: vi.fn(() => 'trial-operator'),
  getTrialAuditReason: vi.fn(() => 'DAILY_OPERATIONS'),
  getTrialGovernance: vi.fn(),
  listTrialAuditEvents: vi.fn(),
  setTrialActor: vi.fn(),
  setTrialAuditReason: vi.fn(),
  apiErrorMessage: vi.fn(() => 'Governance request failed'),
}))

const mockedGovernance = vi.mocked(getTrialGovernance)
const mockedAudit = vi.mocked(listTrialAuditEvents)
const mockedSetActor = vi.mocked(setTrialActor)
const mockedSetReason = vi.mocked(setTrialAuditReason)

function governance(role: 'ADMIN' | 'OPERATOR' | 'SUPPORT') {
  return {
    actor_id: `trial-${role.toLowerCase()}`,
    role,
    capabilities: role === 'SUPPORT' ? ['operations.read'] : ['operations.read', 'sensitive-content.read'],
    access_boundary_mode: 'FIXED_TRIAL_CONTEXT',
    formal_authentication_enabled: false,
    formal_authorization_enabled: false,
    audit_foundation_enabled: true,
    automatic_redaction_enabled: false,
    retention_policy_configured: false,
    current_redaction_marker: 'v1-reminder-only',
    test_data_mode: true,
    production_usable: false,
  }
}

describe('TrialGovernanceView', () => {
  beforeEach(() => {
    mockedGovernance.mockReset()
    mockedAudit.mockReset()
    mockedSetActor.mockReset()
    mockedSetReason.mockReset()
  })

  it('shows explicit current and future privacy boundaries without claiming automatic redaction', async () => {
    mockedGovernance.mockResolvedValue(governance('SUPPORT'))
    const wrapper = mount(TrialGovernanceView)
    await flushPromises()

    expect(wrapper.text()).toContain('客服')
    expect(wrapper.text()).toContain('未启用')
    expect(wrapper.text()).toContain('v1-reminder-only')
    expect(wrapper.text()).toContain('正式上线前')
    expect(wrapper.text()).toContain('只读边界')
    expect(mockedAudit).not.toHaveBeenCalled()
  })

  it('loads content-free audit rows only for the trial administrator', async () => {
    mockedGovernance.mockResolvedValue(governance('ADMIN'))
    mockedAudit.mockResolvedValue({
      items: [{
        id: 'audit-1', occurred_at: '2026-07-27T08:00:00Z', actor_id: 'trial-operator', actor_role: 'OPERATOR',
        action: 'EXPERIENCE_CASE_VIEW', resource_type: 'CUSTOMER_EXPERIENCE_CASE', resource_id: 'collection',
        outcome: 'SUCCESS', reason_code: 'CASE_REVIEW', metadata: { returned_count: 1 },
      }], total: 1, page: 1, size: 20,
    })
    const wrapper = mount(TrialGovernanceView)
    await flushPromises()

    expect(wrapper.text()).toContain('EXPERIENCE_CASE_VIEW')
    expect(wrapper.text()).toContain('CASE_REVIEW')
    expect(wrapper.text()).not.toContain('Synthetic customer question')
  })

  it('persists the selected trial context before refreshing its server-resolved role', async () => {
    mockedGovernance.mockResolvedValue(governance('OPERATOR'))
    const wrapper = mount(TrialGovernanceView)
    await flushPromises()
    const selects = wrapper.findAll('select')
    await selects[0].setValue('trial-admin')
    await selects[1].setValue('GOVERNANCE_REVIEW')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mockedSetActor).toHaveBeenCalledWith('trial-admin')
    expect(mockedSetReason).toHaveBeenCalledWith('GOVERNANCE_REVIEW')
    expect(mockedGovernance).toHaveBeenCalledTimes(2)
  })
})
