import { beforeEach, describe, expect, it, vi } from 'vitest'

const aiGet = vi.hoisted(() => vi.fn())

vi.mock('axios', () => {
  class AxiosError extends Error {}

  return {
    default: {
      create: vi.fn((config: { baseURL?: string }) => ({
        get: config.baseURL === '/ai-api' ? aiGet : vi.fn(),
      })),
    },
    AxiosError,
  }
})

import { getAiControlCenterOverview, getServerRuntime, listAiModules } from '../src/api/client'

describe('listAiModules', () => {
  beforeEach(() => aiGet.mockReset())

  it('unwraps the frozen A success envelope from data.modules', async () => {
    aiGet.mockResolvedValue({
      data: {
        success: true,
        message: 'ok',
        data: {
          modules: [{
            module_id: 'ai_customer_service',
            name: 'AI Customer Service',
            description: 'Provides controlled customer-service answers.',
            status: 'RUNNING',
          }],
        },
      },
    })

    await expect(listAiModules()).resolves.toEqual([{
      id: 'ai_customer_service',
      name: 'AI Customer Service',
      status: 'RUNNING',
      description: 'Provides controlled customer-service answers.',
      promptMetadata: null,
      recentEvaluations: [],
    }])
    expect(aiGet).toHaveBeenCalledWith('/api/admin/ai/modules')
  })

  it('does not reinterpret malformed, legacy, or non-success shapes as modules', async () => {
    aiGet.mockResolvedValue({ data: { success: true, data: { items: [{ module_id: 'wrong-shape' }] } } })
    await expect(listAiModules()).resolves.toEqual([])

    aiGet.mockResolvedValue({ data: [{ module_id: 'legacy-array' }] })
    await expect(listAiModules()).resolves.toEqual([])

    aiGet.mockResolvedValue({ data: { success: false, data: { modules: [{ module_id: 'not-successful' }] } } })
    await expect(listAiModules()).resolves.toEqual([])
  })

  it('reads the v1.1 control-centre overview only from a successful data envelope', async () => {
    aiGet.mockResolvedValue({
      data: {
        success: true,
        data: {
          module_id: 'ai_customer_service',
          service: { status: 'RUNNING', ready: true, model_configured: true, initialization_error: null },
          model: { provider: 'ollama', name: 'qwen3.5:9b', configured: true },
          knowledge: { status: 'AVAILABLE', queryable_chunk_count: 47, scope: 'LIVE_QUERYABLE_COLLECTIONS' },
          runtime: { metrics_scope: 'since_start', call_count: 12, success_count: 11, error_count: 1, average_latency_ms: 836.4, last_called_at: null, last_error_summary: null },
          latest_evaluation: { status: 'NOT_AVAILABLE', evaluation: null },
          technical: { prompt_version: 'rag-customer-reply-v1', prompt_hash: 'sha256:test' },
        },
      },
    })

    await expect(getAiControlCenterOverview()).resolves.toMatchObject({
      moduleId: 'ai_customer_service',
      model: { name: 'qwen3.5:9b', configured: true },
      knowledge: { queryableChunkCount: 47 },
      runtime: { metricsScope: 'since_start', callCount: 12 },
      technical: { promptVersion: 'rag-customer-reply-v1' },
    })
    expect(aiGet).toHaveBeenCalledWith('/api/admin/ai/control-center/overview')
  })

  it('treats a failed overview envelope as an error, never as empty operational data', async () => {
    aiGet.mockResolvedValue({ data: { success: false, data: {} } })
    await expect(getAiControlCenterOverview()).rejects.toThrow('AI状态未返回成功结果')
  })

  it('reads the additive server runtime projection from the local AI proxy', async () => {
    const runtime = {
      schema_version: 'ai-cs.server-runtime-console.v1',
      server: { status: 'READY', version: 'ai-cs-server-runtime.rc1', runtime_mode: 'standard' },
      gateway: { enabled: true, status: 'HEALTHY', version: 'ai-cs-gateway.v1', contract_version: '1.0', configuration_state: 'CONFIGURED' },
    }
    aiGet.mockResolvedValue({ data: runtime })

    await expect(getServerRuntime()).resolves.toEqual(runtime)
    expect(aiGet).toHaveBeenCalledWith('/api/admin/server-runtime')
  })
})
