import axios, { type AxiosRequestConfig } from 'axios'
import { authorizationHeader, clearAuthSession } from '@/auth/authSession'
import { channelAgentLocalSecurityHeaders } from './channelAgentDesktopClient'


export function createAuthenticatedHttp(config: AxiosRequestConfig) {
  const client = axios.create(config)
  client.interceptors?.request.use((request) => {
    const authorization = authorizationHeader().Authorization
    if (authorization) request.headers.Authorization = authorization
    const method = String(request.method ?? 'get').toUpperCase()
    if (method !== 'GET' && method !== 'HEAD') {
      Object.assign(request.headers, channelAgentLocalSecurityHeaders())
    }
    return request
  })
  client.interceptors?.response.use(
    (response) => response,
    (error) => {
      if (error?.response?.status === 401) clearAuthSession()
      return Promise.reject(error)
    }
  )
  return client
}
