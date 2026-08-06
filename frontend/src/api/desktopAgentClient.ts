import axios from 'axios'

import { createAuthenticatedHttp } from './authenticatedHttp'
import { DesktopAgentAdapterError, adaptDesktopAgentStatus, adaptDesktopBindingGrant } from './desktopAgentAdapter'
import { DesktopAgentClientError, type DesktopAgentStatus, type DesktopBindingGrant } from './desktopAgentTypes'

const configuredBaseUrl = (import.meta.env.VITE_PLATFORM_API_BASE_URL || '/platform-api')
  .trim().replace(/\/$/, '')
const http = createAuthenticatedHttp({ baseURL: configuredBaseUrl, timeout: 12_000 })

const responseCode = (value: unknown): string | null => {
  if (!value || typeof value !== 'object') return null
  const error = (value as Record<string, unknown>).error
  if (!error || typeof error !== 'object') return null
  const code = (error as Record<string, unknown>).code
  return typeof code === 'string' ? code : null
}

const mapError = (error: unknown): DesktopAgentClientError => {
  if (error instanceof DesktopAgentClientError) return error
  if (error instanceof DesktopAgentAdapterError) {
    return new DesktopAgentClientError('contract', error.message)
  }
  if (axios.isCancel(error)) return new DesktopAgentClientError('canceled', '客服设备状态检查已取消。')
  if (axios.isAxiosError(error)) {
    const status = error.response?.status ?? null
    const code = responseCode(error.response?.data)
    if (error.code === 'ECONNABORTED') {
      return new DesktopAgentClientError('timeout', '客服设备状态检查超时。', status)
    }
    const mapped: Record<string, [DesktopAgentClientError['kind'], string]> = {
      CHANNEL_AGENT_INTEGRATION_NOT_CONFIGURED: ['not_configured', '客服设备接入尚未配置，请联系管理员。'],
      CHANNEL_AGENT_SERVER_UNREACHABLE: ['server_unreachable', 'Agent 服务器不可达，请检查网络或服务状态。'],
      CHANNEL_AGENT_OPERATOR_PERMISSION_INVALID: ['permission_invalid', 'Agent 接入权限已失效，请联系管理员更新授权。'],
      AUTHORIZATION_DENIED: ['authorization_denied', '当前账号无权访问该店铺的客服设备。'],
      CHANNEL_AGENT_RESPONSE_INVALID: ['contract', 'Agent 状态响应版本不兼容，请联系管理员。'],
      CHANNEL_AGENT_REQUEST_REJECTED: ['rejected', 'Agent 服务器拒绝了本次设备操作。'],
      CHANNEL_AGENT_NOT_REGISTERED: ['rejected', '未找到对应的 Agent 与设备，请先启动并注册客户端。'],
      CHANNEL_AGENT_BINDING_INVALID: ['rejected', '该 Agent 已绑定或不可用于本次绑定。']
    }
    if (code && mapped[code]) return new DesktopAgentClientError(mapped[code][0], mapped[code][1], status)
    if (error.code === 'ERR_NETWORK' || status === 500 || status === 502 || status === 503) {
      return new DesktopAgentClientError('server_unreachable', 'Agent 状态服务暂时不可用。', status)
    }
    return new DesktopAgentClientError('unknown', '客服设备操作失败。', status)
  }
  return new DesktopAgentClientError('unknown', error instanceof Error ? error.message : '客服设备操作失败。')
}

export const desktopAgentClient = {
  async getStatus(storeId: number, signal?: AbortSignal): Promise<DesktopAgentStatus> {
    try {
      const response = await http.get('/api/v1/workspace/desktop-agent', {
        params: { store_id: storeId }, signal
      })
      return adaptDesktopAgentStatus(response.data)
    } catch (error) {
      throw mapError(error)
    }
  },

  async requestBindingGrant(
    request: { agentId: string; deviceId: string; storeId: number },
    signal?: AbortSignal
  ): Promise<DesktopBindingGrant> {
    try {
      const response = await http.post('/api/v1/workspace/desktop-agent/binding-grants', {
        agent_id: request.agentId,
        device_id: request.deviceId,
        store_id: request.storeId
      }, { signal })
      return adaptDesktopBindingGrant(response.data)
    } catch (error) {
      throw mapError(error)
    }
  }
}
