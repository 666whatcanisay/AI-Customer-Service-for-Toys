import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AiCapabilityCenterView from '../src/views/AiCapabilityCenterView.vue'
import {
  getAiKnowledgeStatistics,
  getAiModuleDetail,
  getAiModuleLatestEvaluation,
  getAiModulePrompt,
  getAiRuntimeStatus,
  listAiModules,
} from '../src/api/client'

vi.mock('../src/api/client', () => ({
  listAiModules: vi.fn(), getAiRuntimeStatus: vi.fn(), getAiKnowledgeStatistics: vi.fn(),
  getAiModuleDetail: vi.fn(), getAiModulePrompt: vi.fn(), getAiModuleLatestEvaluation: vi.fn(),
  apiErrorMessage: vi.fn(() => 'AI request failed'),
}))

const mockedModules = vi.mocked(listAiModules)
const mockedRuntime = vi.mocked(getAiRuntimeStatus)
const mockedKnowledge = vi.mocked(getAiKnowledgeStatistics)
const mockedDetail = vi.mocked(getAiModuleDetail)
const mockedPrompt = vi.mocked(getAiModulePrompt)
const mockedEvaluation = vi.mocked(getAiModuleLatestEvaluation)

describe('AiCapabilityCenterView', () => {
  beforeEach(() => {
    mockedModules.mockReset(); mockedRuntime.mockReset(); mockedKnowledge.mockReset()
    mockedDetail.mockReset(); mockedPrompt.mockReset(); mockedEvaluation.mockReset()
  })

  it('renders returned A-line runtime facts and labels incomplete historical evaluation honestly', async () => {
    mockedModules.mockResolvedValue([{ id: 'answer', name: 'Answer module', status: 'RUNNING', description: null, implemented: true, promptMetadata: null, recentEvaluations: [] }])
    mockedRuntime.mockResolvedValue({ ready: true, modelConfigured: true, initializationError: null })
    mockedKnowledge.mockResolvedValue({ documentCount: 0, chunkCount: 47, collectionName: 'documents', embeddingModel: 'bge', vectorDatabase: 'ChromaDB', modelConfigured: true })
    mockedDetail.mockResolvedValue({ id: 'answer', name: 'Answer module', status: 'RUNNING', description: null, implemented: true, promptMetadata: null, recentEvaluations: [], modelProvider: 'ollama', modelName: 'qwen3.5:9b', ready: true, modelConfigured: true, initializationError: null, knowledgeCount: 47, promptVersion: 'prompt-v1', promptHash: 'hash', safePreview: 'Safe preview', metricsScope: 'process', callCount: null, successCount: null, errorCount: null, averageLatencyMs: null, lastCalledAt: null, lastErrorSummary: null, supportedActions: ['search_knowledge'], raw: {} })
    mockedPrompt.mockResolvedValue({ moduleId: 'answer', status: null, promptVersion: 'prompt-v1', promptHash: 'hash', updatedAt: 'code-managed', sourceType: 'code', safePreview: 'Safe preview', raw: {} })
    mockedEvaluation.mockResolvedValue({ moduleId: 'answer', status: 'AVAILABLE', evaluation: { evaluationId: 'eval-1', executedAt: '2026-07-27', datasetVersion: 'v1', totalCases: 28, passedCases: 19, passRate: 68, checks: {}, failedCaseIds: ['case-1'], reportAvailable: true }, raw: {} })
    const wrapper = mount(AiCapabilityCenterView, {
      global: { stubs: { RouterLink: { props: ['to'], template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Answer module')
    expect(wrapper.text()).toContain('47 个知识块')
    expect(wrapper.text()).toContain('历史评测记录：19/28，尚未达到全量通过。')
    expect(wrapper.text()).not.toContain('运行在线测试')
  })
})
