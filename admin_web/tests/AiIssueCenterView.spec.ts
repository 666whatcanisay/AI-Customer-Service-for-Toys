import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AiIssueCenterView from '../src/views/AiIssueCenterView.vue'
import {
  createKnowledgeOptimizationTask,
  listAiProblems,
  updateAiProblemStatus,
  updateKnowledgeOptimizationTaskStatus,
  verifyKnowledgeOptimizationTask,
  type AiProblem,
} from '../src/api/client'

vi.mock('../src/api/client', () => ({
  listAiProblems: vi.fn(),
  updateAiProblemStatus: vi.fn(),
  createKnowledgeOptimizationTask: vi.fn(),
  updateKnowledgeOptimizationTaskStatus: vi.fn(),
  verifyKnowledgeOptimizationTask: vi.fn(),
  apiErrorMessage: vi.fn((reason: unknown) => reason instanceof Error ? reason.message : '请求失败'),
}))

const mockedList = vi.mocked(listAiProblems)
const mockedUpdateProblem = vi.mocked(updateAiProblemStatus)
const mockedCreateTask = vi.mocked(createKnowledgeOptimizationTask)
const mockedUpdateTask = vi.mocked(updateKnowledgeOptimizationTaskStatus)
const mockedVerify = vi.mocked(verifyKnowledgeOptimizationTask)

const problem = (overrides: Partial<AiProblem> = {}): AiProblem => ({
  problem_id: 'AIP-001',
  store_code: 'STORE-ONE',
  store_name: '测试店铺',
  product_id: 'PRODUCT-ONE',
  product_name: '测试积木',
  sku_id: 'SKU-ONE',
  sku_name: '红色款',
  question_summary: '这个商品适合几岁？',
  ai_answer_summary: '适用年龄是六到十二岁。',
  issue_type: 'UNCLASSIFIED',
  occurrence_count: 3,
  status: 'NEW',
  first_seen_at: '2026-07-29T08:00:00Z',
  last_seen_at: '2026-07-29T09:00:00Z',
  knowledge_task: null,
  ...overrides,
})

const task = {
  task_id: 'KOT-001',
  source_problem_id: 'AIP-001',
  store_code: 'STORE-ONE',
  product_id: 'PRODUCT-ONE',
  sku_id: 'SKU-ONE',
  missing_topic: '适用年龄与低龄限制',
  status: 'COMPLETED' as const,
  status_note: '已补充',
  verification_result: null,
  verification_note: null,
  verified_by: null,
  verified_at: null,
  created_by: '运营测试员',
  updated_by: '运营测试员',
  created_at: '2026-07-29T09:10:00Z',
  updated_at: '2026-07-29T09:20:00Z',
}

describe('AiIssueCenterView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows product, SKU, summaries, type, count and status for NEW feedback', async () => {
    mockedList.mockResolvedValue({ items: [problem()], total: 1 })
    const wrapper = mount(AiIssueCenterView)
    await flushPromises()

    expect(wrapper.text()).toContain('测试积木')
    expect(wrapper.text()).toContain('红色款')
    expect(wrapper.text()).toContain('这个商品适合几岁？')
    expect(wrapper.text()).toContain('适用年龄是六到十二岁。')
    expect(wrapper.text()).toContain('待分析')
    expect(wrapper.text()).toContain('3')
    expect(wrapper.text()).toContain('新建')
  })

  it('lets operations confirm the issue and create a knowledge task', async () => {
    const newProblem = problem()
    const confirmed = problem({
      issue_type: 'KNOWLEDGE_MISSING',
      status: 'CONFIRMED',
    })
    const processing = problem({
      issue_type: 'KNOWLEDGE_MISSING',
      status: 'PROCESSING',
      knowledge_task: { ...task, status: 'PENDING' },
    })
    mockedList
      .mockResolvedValueOnce({ items: [newProblem], total: 1 })
      .mockResolvedValueOnce({ items: [confirmed], total: 1 })
      .mockResolvedValueOnce({ items: [processing], total: 1 })
    mockedUpdateProblem.mockResolvedValue(confirmed)
    mockedCreateTask.mockResolvedValue(processing.knowledge_task!)

    const wrapper = mount(AiIssueCenterView)
    await flushPromises()
    await wrapper.get('.link-button').trigger('click')
    await wrapper.get('[data-testid="ai-issue-type"]').setValue('KNOWLEDGE_MISSING')
    await wrapper.get('[data-testid="confirm-ai-issue"]').trigger('click')
    await flushPromises()

    expect(mockedUpdateProblem).toHaveBeenCalledWith('AIP-001', expect.objectContaining({
      status: 'CONFIRMED',
      issue_type: 'KNOWLEDGE_MISSING',
      operator: '运营测试员',
    }))
    await wrapper.get('[data-testid="missing-topic"]').setValue('适用年龄与低龄限制')
    await wrapper.get('[data-testid="create-knowledge-task"]').trigger('click')
    await flushPromises()
    expect(mockedCreateTask).toHaveBeenCalledWith('AIP-001', expect.objectContaining({
      missing_topic: '适用年龄与低龄限制',
      operator: '运营测试员',
    }))
    expect(wrapper.text()).toContain('待补充')
    expect(wrapper.text()).toContain('不自动生成知识')
  })

  it('records re-verification and displays the completed loop without an automatic action', async () => {
    const solved = problem({
      issue_type: 'KNOWLEDGE_MISSING',
      status: 'SOLVED',
      knowledge_task: task,
    })
    const verifiedTask = {
      ...task,
      status: 'VERIFIED' as const,
      verification_result: 'IMPROVED' as const,
      verification_note: '重新提问后已包含低龄限制。',
      verified_by: '运营测试员',
      verified_at: '2026-07-29T10:00:00Z',
    }
    const verified = problem({
      issue_type: 'KNOWLEDGE_MISSING',
      status: 'VERIFIED',
      knowledge_task: verifiedTask,
    })
    mockedList
      .mockResolvedValueOnce({ items: [solved], total: 1 })
      .mockResolvedValueOnce({ items: [verified], total: 1 })
    mockedVerify.mockResolvedValue(verifiedTask)

    const wrapper = mount(AiIssueCenterView)
    await flushPromises()
    await wrapper.get('.link-button').trigger('click')
    await wrapper.get('[data-testid="verification-note"]').setValue('重新提问后已包含低龄限制。')
    await wrapper.get('[data-testid="verify-improved"]').trigger('click')
    await flushPromises()

    expect(mockedVerify).toHaveBeenCalledWith('KOT-001', {
      result: 'IMPROVED',
      operator: '运营测试员',
      note: '重新提问后已包含低龄限制。',
    })
    expect(wrapper.text()).toContain('客服问题 → AI 问题 → 知识补充 → AI 改善')
    expect(wrapper.findAll('button').some((button) => button.text() === '发布知识')).toBe(false)
    expect(mockedUpdateTask).not.toHaveBeenCalled()
  })
})
