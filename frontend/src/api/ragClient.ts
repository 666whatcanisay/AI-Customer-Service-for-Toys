import axios from 'axios'
import { adaptChatResponse, adaptHealthResponse } from './ragAdapter'
import { toRagClientError } from './errorMapper'
import type { RagApiClient, RagChatRequest } from './ragTypes'

const configuredBaseUrl = (import.meta.env.VITE_RAG_API_BASE_URL || 'http://127.0.0.1:8000')
  .trim()
  .replace(/\/$/, '')

const http = axios.create({
  baseURL: configuredBaseUrl,
  timeout: 15_000,
  headers: {
    'Content-Type': 'application/json'
  }
})

export const ragClient: RagApiClient = {
  async getHealth(signal) {
    try {
      const response = await http.get('/api/health', { signal })
      return adaptHealthResponse(response.data)
    } catch (error) {
      throw toRagClientError(error)
    }
  },

  async chat(request: RagChatRequest, signal) {
    try {
      const response = await http.post('/api/chat', request, { signal })
      return adaptChatResponse(response.data)
    } catch (error) {
      throw toRagClientError(error)
    }
  }
}
