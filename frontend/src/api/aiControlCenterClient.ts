import axios from 'axios'
import {
  adaptAiControlCenterResponse,
  adaptAiOperationsOverviewResponse,
  adaptAiQualityBaselineResponse,
  adaptAiLatestEvaluationResponse,
  adaptAiModuleDetailResponse,
  adaptAiModulesResponse,
  adaptAiPromptResponse
} from './aiControlCenterAdapter'
import { toRagClientError } from './errorMapper'
import type { AiControlCenterApiClient } from './aiControlCenterTypes'

const configuredBaseUrl = (import.meta.env.VITE_RAG_API_BASE_URL || '/rag-api')
  .trim()
  .replace(/\/$/, '')

const http = axios.create({
  baseURL: configuredBaseUrl,
  timeout: 15_000,
  headers: { Accept: 'application/json' }
})

const moduleEndpoint = (moduleId: string) => `/api/admin/ai/modules/${encodeURIComponent(moduleId)}`

// This is a read-only consumer of A-T04 capability endpoints. It intentionally
// has no fallback records: unavailable or malformed upstream data is shown as
// an unavailable state by the view instead of being substituted with fixtures.
export const aiControlCenterClient: AiControlCenterApiClient = {
  async getControlCenter(signal) {
    try {
      const response = await http.get('/api/admin/ai/control-center', { signal })
      return adaptAiControlCenterResponse(response.data)
    } catch (error) {
      throw toRagClientError(error)
    }
  },

  async getOperationsOverview(signal) {
    try {
      const response = await http.get('/api/admin/ai/operations/overview', { signal })
      return adaptAiOperationsOverviewResponse(response.data)
    } catch (error) {
      throw toRagClientError(error)
    }
  },

  async getQualityBaseline(signal) {
    try {
      const response = await http.get('/api/admin/ai/quality-baseline/latest', { signal })
      return adaptAiQualityBaselineResponse(response.data)
    } catch (error) {
      throw toRagClientError(error)
    }
  },

  async listModules(signal) {
    try {
      const response = await http.get('/api/admin/ai/modules', { signal })
      return adaptAiModulesResponse(response.data)
    } catch (error) {
      throw toRagClientError(error)
    }
  },

  async getModule(moduleId, signal) {
    try {
      const response = await http.get(moduleEndpoint(moduleId), { signal })
      return adaptAiModuleDetailResponse(response.data)
    } catch (error) {
      throw toRagClientError(error)
    }
  },

  async getPrompt(moduleId, signal) {
    try {
      const response = await http.get(`${moduleEndpoint(moduleId)}/prompt`, { signal })
      return adaptAiPromptResponse(response.data)
    } catch (error) {
      throw toRagClientError(error)
    }
  },

  async getLatestEvaluation(moduleId, signal) {
    try {
      const response = await http.get(`${moduleEndpoint(moduleId)}/evaluations/latest`, { signal })
      return adaptAiLatestEvaluationResponse(response.data)
    } catch (error) {
      throw toRagClientError(error)
    }
  }
}
