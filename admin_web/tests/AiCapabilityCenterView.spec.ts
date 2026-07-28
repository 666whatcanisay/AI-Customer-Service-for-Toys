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

  it('uses Chinese product names and business descriptions for known A-module identifiers', async () => {
    mockedModules.mockResolvedValue([
      { id: 'ai_customer_service', name: 'AI Customer Service', status: 'RUNNING', description: 'RAG-backed toy customer-service answer capability.', implemented: true, promptMetadata: null, recentEvaluations: [] },
      { id: 'aftersales_intent', name: 'After-sales Intent Recognition', status: 'PLANNED', description: 'Planned after-sales intent classification capability.', implemented: false, promptMetadata: null, recentEvaluations: [] },
      { id: 'shipping_note_extractor', name: 'Shipping Note Extractor', status: 'PLANNED', description: 'Planned shipping-note extraction capability.', implemented: false, promptMetadata: null, recentEvaluations: [] },
      { id: 'appeal_writer', name: 'Order Appeal Writer', status: 'PLANNED', description: 'Planned order-appeal drafting capability.', implemented: false, promptMetadata: null, recentEvaluations: [] },
      { id: 'risk_checker', name: 'Reply Risk Checker', status: 'PLANNED', description: 'Planned reply-risk review capability.', implemented: false, promptMetadata: null, recentEvaluations: [] },
    ])
    mockedRuntime.mockResolvedValue({ ready: true, modelConfigured: true, initializationError: null })
    mockedKnowledge.mockResolvedValue({ documentCount: 0, chunkCount: 47, collectionName: 'documents', embeddingModel: 'bge', vectorDatabase: 'ChromaDB', modelConfigured: true })
    mockedDetail.mockResolvedValue({ id: 'ai_customer_service', name: 'AI Customer Service', status: 'RUNNING', description: 'RAG-backed toy customer-service answer capability.', implemented: true, promptMetadata: null, recentEvaluations: [], modelProvider: 'ollama', modelName: 'qwen3.5:9b', ready: true, modelConfigured: true, initializationError: null, knowledgeCount: 47, promptVersion: 'prompt-v1', promptHash: 'hash', safePreview: 'Safe preview', metricsScope: 'process', callCount: null, successCount: null, errorCount: null, averageLatencyMs: null, lastCalledAt: null, lastErrorSummary: null, supportedActions: ['search_knowledge'], raw: {} })
    mockedPrompt.mockResolvedValue({ moduleId: 'ai_customer_service', status: null, promptVersion: 'prompt-v1', promptHash: 'hash', updatedAt: 'code-managed', sourceType: 'code', safePreview: 'Safe preview', raw: {} })
    mockedEvaluation.mockResolvedValue({ moduleId: 'ai_customer_service', status: 'AVAILABLE', evaluation: { evaluationId: 'eval-1', executedAt: '2026-07-27', datasetVersion: 'v1', totalCases: 28, passedCases: 19, passRate: 68, checks: {}, failedCaseIds: ['case-1'], reportAvailable: true }, raw: {} })
    const wrapper = mount(AiCapabilityCenterView, {
      global: { stubs: { RouterLink: { props: ['to'], template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('AI客服')
    expect(wrapper.text()).toContain('基于已导入商品知识生成客服回复建议')
    expect(wrapper.text()).toContain('售后意图识别')
    expect(wrapper.text()).toContain('物流信息提取')
    expect(wrapper.text()).toContain('申诉文案助手')
    expect(wrapper.text()).toContain('回复风险检查')
    expect(wrapper.text()).not.toContain('AI Customer Service')
    expect(wrapper.text()).not.toContain('RAG-backed toy customer-service answer capability.')
    expect(wrapper.text()).toContain('47 个知识块')
    expect(wrapper.text()).toContain('历史评测记录：19/28，尚未达到全量通过。')
    expect(wrapper.text()).not.toContain('运行在线测试')

    const descriptions = [
      '识别售后咨询的处理意图，当前仍处于规划中，尚未提供自动执行能力。',
      '从物流相关文本中提取关键信息，当前仍处于规划中。',
      '协助整理订单申诉文案，当前仍处于规划中，所有内容需人工复核。',
      '辅助识别客服回复中的风险提示，当前仍处于规划中，不会自动拦截或发送回复。',
    ]
    const moduleTabs = wrapper.findAll('button.module-tab')
    for (const [index, description] of descriptions.entries()) {
      await moduleTabs[index + 1].trigger('click')
      await flushPromises()
      expect(wrapper.text()).toContain(description)
    }
  })
})
