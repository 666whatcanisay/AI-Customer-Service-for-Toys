import type {
  DesktopAgentIdentityStatus,
  DesktopAgentOnlineStatus,
  DesktopAgentStatus,
  DesktopAssociationState,
  DesktopBindingGrant
} from './desktopAgentTypes'

type JsonRecord = Record<string, unknown>

export class DesktopAgentAdapterError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'DesktopAgentAdapterError'
  }
}

const record = (value: unknown): JsonRecord => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new DesktopAgentAdapterError('客服设备状态响应格式无效。')
  }
  return value as JsonRecord
}

const text = (value: unknown, label = '文本'): string => {
  if (typeof value !== 'string' || !value) {
    throw new DesktopAgentAdapterError(`客服设备状态缺少${label}。`)
  }
  return value
}

const nullableText = (value: unknown): string | null => {
  if (value === null) return null
  return text(value)
}

const integer = (value: unknown, minimum = 0): number => {
  if (!Number.isInteger(value) || (value as number) < minimum) {
    throw new DesktopAgentAdapterError('客服设备状态缺少有效数字。')
  }
  return value as number
}

const boolean = (value: unknown): boolean => {
  if (typeof value !== 'boolean') throw new DesktopAgentAdapterError('客服设备状态缺少布尔字段。')
  return value
}

const oneOf = <T extends string>(value: unknown, allowed: readonly T[], label: string): T => {
  const result = text(value, label)
  if (!allowed.includes(result as T)) throw new DesktopAgentAdapterError(`客服设备${label}无效。`)
  return result as T
}

const associationStates: readonly DesktopAssociationState[] = [
  'READY', 'BINDING_REQUIRED', 'ACTIVATION_REQUIRED', 'STORE_MISMATCH',
  'MULTIPLE_MATCHES', 'DISABLED'
]
const onlineStates: readonly DesktopAgentOnlineStatus[] = ['ONLINE', 'DEGRADED', 'OFFLINE']
const identityStates: readonly DesktopAgentIdentityStatus[] = ['UNBOUND', 'BOUND', 'ACTIVE', 'DISABLED']

export function adaptDesktopAgentStatus(value: unknown): DesktopAgentStatus {
  const item = record(value)
  if (item.schema_version !== 'ai-cs.customer-desktop-workflow.v1') {
    throw new DesktopAgentAdapterError('客服设备状态版本不兼容。')
  }
  const rawAgent = item.agent
  let agent: DesktopAgentStatus['agent'] = null
  if (rawAgent !== null) {
    const data = record(rawAgent)
    agent = {
      agentId: text(data.agent_id, 'Agent 标识'),
      deviceId: text(data.device_id, '设备标识'),
      deviceName: nullableText(data.device_name),
      agentVersion: nullableText(data.agent_version),
      identityStatus: oneOf(data.identity_status, identityStates, '绑定状态'),
      onlineStatus: oneOf(data.online_status, onlineStates, '在线状态'),
      runtimeStatus: text(data.runtime_status, '运行状态'),
      productionEligible: boolean(data.production_eligible),
      bindingRevision: integer(data.binding_revision),
      lastHeartbeat: nullableText(data.last_heartbeat)
    }
  }
  return {
    userId: text(item.user_id, '用户标识'),
    storeId: integer(item.store_id, 1),
    storeCode: text(item.store_code, '店铺编码'),
    associationState: oneOf(item.association_state, associationStates, '关联状态'),
    agent,
    checkedAt: text(item.checked_at, '检查时间')
  }
}

export function adaptDesktopBindingGrant(value: unknown): DesktopBindingGrant {
  const item = record(value)
  if (item.schema_version !== 'ai-cs.customer-desktop-workflow.v1') {
    throw new DesktopAgentAdapterError('客服设备绑定响应版本不兼容。')
  }
  const bindingCode = text(item.binding_code, '一次性绑定码')
  if (!/^[A-F0-9]{32}$/.test(bindingCode)) {
    throw new DesktopAgentAdapterError('一次性绑定码格式无效。')
  }
  return {
    grantId: text(item.grant_id, '授权标识'),
    agentId: text(item.agent_id, 'Agent 标识'),
    deviceId: text(item.device_id, '设备标识'),
    bindingCode,
    expiresAt: text(item.expires_at, '过期时间')
  }
}
