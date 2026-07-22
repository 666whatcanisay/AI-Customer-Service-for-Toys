import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RagClientError } from '@/api/errorMapper'
import AiChat from './AiChat.vue'

const apiMocks = vi.hoisted(() => ({
  getHealth: vi.fn(),
  chat: vi.fn()
}))

vi.mock('@/api/ragClient', () => ({
  ragClient: apiMocks
}))

const mountPage = () => mount(AiChat, {
  global: {
    plugins: [ElementPlus]
  }
})

describe('AiChat', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.getHealth.mockResolvedValue({ status: 'ok', ready: true })
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) }
    })
  })

  it('submits a real-client request and renders answer, source, copy, and adoption state', async () => {
    apiMocks.chat.mockResolvedValue({
      requestId: 'req-ui-1',
      model: 'qwen-turbo',
      answer: '建议回复：适用年龄请以商品包装标识为准。',
      action: 'DIRECT_ANSWER',
      riskLevel: null,
      citations: [{
        file: 'toy-guide.pdf',
        page: 4,
        chunkId: 'chunk-4',
        summary: '包装标明适用年龄。',
        distance: 0.2,
        knowledgeVersion: null
      }],
      warnings: [],
      requiredFields: [],
      latencyMs: 95
    })

    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[data-testid="question-input"]').setValue('这个玩具适合几岁？')
    await wrapper.find('[data-testid="submit-button"]').trigger('click')
    await flushPromises()

    expect(apiMocks.chat).toHaveBeenCalledWith(
      { message: '这个玩具适合几岁？' },
      expect.any(AbortSignal)
    )
    expect(
      (wrapper.get('[data-testid="reply-draft"]').element as HTMLTextAreaElement).value
    ).toContain('适用年龄请以商品包装标识为准')
    expect(wrapper.get('[data-testid="answer-card"]').text()).toContain('直接回答')
    expect(wrapper.get('[data-testid="answer-card"]').text()).toContain('风险未分类')
    expect(wrapper.get('[data-testid="citation-item"]').text()).toContain('toy-guide.pdf')
    expect(wrapper.get('[data-testid="citation-item"]').text()).toContain('第 4 页')

    await wrapper.get('[data-testid="copy-button"]').trigger('click')
    await flushPromises()
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      '建议回复：适用年龄请以商品包装标识为准。'
    )

    await wrapper.get('[data-testid="direct-accept"]').trigger('click')
    expect(wrapper.get('[data-testid="adoption-result"]').text()).toContain('直接采用')
    expect(wrapper.get('[data-testid="adoption-result"]').text()).toContain('反馈 API 待发布')
  })

  it('shows loading, blocks another submission, and allows cancellation', async () => {
    apiMocks.chat.mockImplementation((_request, signal: AbortSignal) =>
      new Promise((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(new Error('aborted')))
      })
    )

    const wrapper = mountPage()
    await flushPromises()
    await wrapper.get('[data-testid="question-input"]').setValue('请查询库存说明')
    await wrapper.find('[data-testid="submit-button"]').trigger('click')

    expect(wrapper.find('[data-testid="loading-state"]').exists()).toBe(true)
    await wrapper.find('[data-testid="submit-button"]').trigger('click')
    expect(apiMocks.chat).toHaveBeenCalledTimes(1)

    await wrapper.get('[data-testid="cancel-button"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="request-error"]').text()).toContain('请求已取消')
  })

  it('shows an unavailable API state without falling back to Mock', async () => {
    apiMocks.getHealth.mockRejectedValue(
      new RagClientError('unavailable', 'RAG API 当前不可用，请稍后重试', 503)
    )

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.get('[data-testid="health-status"]').text()).toContain('RAG API 不可用')
    expect(wrapper.text()).toContain('RAG API 当前不可用，请稍后重试')
    expect(wrapper.text()).toContain('生产运行没有 Mock 回退')
  })
})
