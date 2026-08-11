import { describe, expect, it } from 'vitest'

import { DesktopAgentAdapterError, adaptDesktopAgentStatus, adaptDesktopBindingGrant } from './desktopAgentAdapter'


describe('desktopAgentAdapter', () => {
  it('accepts the authoritative Host Control V2.1 REGISTERED and OFFLINE projection', () => {
    const status = adaptDesktopAgentStatus({
      schema_version: 'ai-cs.customer-desktop-workflow.v1',
      user_id: 'user-001',
      store_id: 1,
      store_code: 'STORE-A',
      association_state: 'BINDING_REQUIRED',
      agent: {
        agent_id: 'agent-001',
        device_id: 'device-001',
        device_name: '客服电脑',
        agent_version: '2.0.0rc1',
        identity_status: 'REGISTERED',
        online_status: 'OFFLINE',
        runtime_status: 'OFFLINE',
        production_eligible: false,
        binding_revision: 0,
        last_heartbeat: null
      },
      checked_at: '2026-08-08T17:50:00+08:00'
    })

    expect(status.agent?.identityStatus).toBe('REGISTERED')
    expect(status.agent?.onlineStatus).toBe('OFFLINE')
  })

  it('normalizes the legacy UNBOUND input to REGISTERED', () => {
    const status = adaptDesktopAgentStatus({
      schema_version: 'ai-cs.customer-desktop-workflow.v1',
      user_id: 'user-001',
      store_id: 1,
      store_code: 'STORE-A',
      association_state: 'BINDING_REQUIRED',
      agent: {
        agent_id: 'agent-001',
        device_id: 'device-001',
        device_name: null,
        agent_version: null,
        identity_status: 'UNBOUND',
        online_status: 'OFFLINE',
        runtime_status: 'OFFLINE',
        production_eligible: false,
        binding_revision: 0,
        last_heartbeat: null
      },
      checked_at: '2026-08-08T17:50:00+08:00'
    })

    expect(status.agent?.identityStatus).toBe('REGISTERED')
  })

  it('adapts a strict current-user and Store Agent projection', () => {
    expect(adaptDesktopAgentStatus({
      schema_version: 'ai-cs.customer-desktop-workflow.v1',
      user_id: '11111111-1111-4111-8111-111111111111',
      store_id: 8,
      store_code: 'STORE-1',
      association_state: 'READY',
      agent: {
        agent_id: 'agent-1', device_id: 'device-1', device_name: 'CS-PC-01',
        agent_version: '1.1.0', identity_status: 'ACTIVE', online_status: 'ONLINE',
        runtime_status: 'ONLINE', production_eligible: true, binding_revision: 3,
        last_heartbeat: '2026-08-06T08:00:00Z'
      },
      checked_at: '2026-08-06T08:00:01Z'
    })).toEqual({
      userId: '11111111-1111-4111-8111-111111111111', storeId: 8,
      storeCode: 'STORE-1', associationState: 'READY',
      agent: {
        agentId: 'agent-1', deviceId: 'device-1', deviceName: 'CS-PC-01',
        agentVersion: '1.1.0', identityStatus: 'ACTIVE', onlineStatus: 'ONLINE',
        runtimeStatus: 'ONLINE', productionEligible: true, bindingRevision: 3,
        lastHeartbeat: '2026-08-06T08:00:00Z'
      },
      checkedAt: '2026-08-06T08:00:01Z'
    })
  })

  it('rejects unknown states instead of guessing an Agent status', () => {
    expect(() => adaptDesktopAgentStatus({
      schema_version: 'ai-cs.customer-desktop-workflow.v1',
      user_id: '11111111-1111-4111-8111-111111111111', store_id: 8,
      store_code: 'STORE-1', association_state: 'CONNECTED', agent: null,
      checked_at: '2026-08-06T08:00:01Z'
    })).toThrow(DesktopAgentAdapterError)
  })

  it('validates the one-time grant code without persisting it', () => {
    expect(adaptDesktopBindingGrant({
      schema_version: 'ai-cs.customer-desktop-workflow.v1',
      grant_id: 'grant-1', agent_id: 'agent-1', device_id: 'device-1',
      binding_code: 'ABCDEF0123456789ABCDEF0123456789',
      expires_at: '2026-08-06T08:10:00Z'
    }).bindingCode).toBe('ABCDEF0123456789ABCDEF0123456789')
    expect(() => adaptDesktopBindingGrant({
      schema_version: 'ai-cs.customer-desktop-workflow.v1',
      grant_id: 'grant-1', agent_id: 'agent-1', device_id: 'device-1',
      binding_code: 'plain-secret', expires_at: '2026-08-06T08:10:00Z'
    })).toThrow('一次性绑定码格式无效')
  })
})
