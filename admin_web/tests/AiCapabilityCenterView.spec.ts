import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AiCapabilityCenterView from '../src/views/AiCapabilityCenterView.vue'
import { getAiControlCenterOverview } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  getAiControlCenterOverview: vi.fn(),
  apiErrorMessage: vi.fn(() => 'AI 服务尚未就绪，请先检查服务状态。'),
}))

const mockedOverview = vi.mocked(getAiControlCenterOverview)

const overview = {
  moduleId: 'ai_customer_service',
  service: { status: 'RUNNING', ready: true, modelConfigured: true, initializationError: null },
  model: { provider: 'ollama', name: 'qwen3.5:9b', configured: true },
  knowledge: { status: 'AVAILABLE', queryableChunkCount: 47, scope: 'LIVE_QUERYABLE_COLLECTIONS' },
  runtime: { metricsScope: 'since_start', callCount: 12, successCount: 11, errorCount: 1, averageLatencyMs: 836.4, lastCalledAt: null, lastErrorSummary: null },
  latestEvaluation: { status: 'NOT_AVAILABLE', evaluation: null },
  technical: { promptVersion: 'rag-customer-reply-v1', promptHash: 'sha256:test' },
}

describe('AiCapabilityCenterView', () => {
  beforeEach(() => mockedOverview.mockReset())

  it('renders only the frozen A overview as business summaries and keeps technical data folded', async () => {
    mockedOverview.mockResolvedValue(overview)
    const wrapper = mount(AiCapabilityCenterView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    expect(wrapper.text()).toContain('AI状态')
    expect(wrapper.text()).toContain('qwen3.5:9b')
    expect(wrapper.text()).toContain('可查询 47 条知识片段')
    expect(wrapper.text()).toContain('调用次数')
    expect(wrapper.text()).toContain('暂无已保存评测')
    expect(wrapper.find('details').exists()).toBe(true)
    expect(wrapper.find('details').attributes('open')).toBeUndefined()
    expect(wrapper.text()).not.toContain('自动修改 Prompt')
  })
})
