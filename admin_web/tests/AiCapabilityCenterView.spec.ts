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
    expect(wrapper.findAll('.summary-card').map((item) => item.text())).toEqual([
      'AI 服务正常服务和回答模型均就绪时才显示正常。',
      '知识47 条知识可检索仅代表 A 当前可查询知识，不代表资料已自动发布。',
      '回答能力正常综合 AI 服务、模型配置和知识可检索状态。',
      '需要关注无真实异常不会显示为正常或 0。',
    ])
    expect(wrapper.text()).toContain('业务可用说明')
    expect(wrapper.text()).toContain('暂无已保存评测')
    expect(wrapper.find('details').exists()).toBe(true)
    expect(wrapper.find('details').attributes('open')).toBeUndefined()
    expect(wrapper.find('details').text()).toContain('高级技术信息')
    expect(wrapper.find('details').text()).toContain('模型名称qwen3.5:9b')
    expect(wrapper.find('details').text()).toContain('知识集合当前接口未提供集合名称')
    expect(wrapper.find('details').text()).toContain('服务版本当前接口未提供')
    expect(wrapper.find('details').text()).toContain('调用次数12')
    expect(wrapper.text()).not.toContain('自动修改 Prompt')
  })
})
