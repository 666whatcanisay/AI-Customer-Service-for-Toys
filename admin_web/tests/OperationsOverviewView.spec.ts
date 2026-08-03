import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import OperationsOverviewView from '../src/views/OperationsOverviewView.vue'
import {
  getAdminOverview,
  getAiControlCenterOverview,
  getHealth,
  getProductKnowledgeOverview,
  listAiProblems,
  listProductKnowledgeProducts,
} from '../src/api/client'

vi.mock('../src/api/client', () => ({
  getAdminOverview: vi.fn(),
  getAiControlCenterOverview: vi.fn(),
  getHealth: vi.fn(),
  getProductKnowledgeOverview: vi.fn(),
  listAiProblems: vi.fn(),
  listProductKnowledgeProducts: vi.fn(),
  apiErrorMessage: vi.fn((reason: unknown) => reason instanceof Error ? reason.message : '请求失败'),
}))

const technicalDetails = {
  store_code: 'demo-store', platform: 'pinduoduo', product_id: 'PRODUCT-1', product_code: 'P-1',
  sku_id: null, sku_code: null, source_id: null, material_id: null, revision: null, content_hash: null,
}

const publishedProduct = {
  store_name: '演示店铺', product_name: '星际探索积木', product_summary: '探索主题积木', core_selling_points: ['探索玩法'],
  applicable_age: '6 岁+', material_safety: 'ABS', package_contents: '积木、说明书', faq_count: 2, sku_names: ['标准版'],
  coverage_percent: 90, ai_usable: true, knowledge_state: 'WELL_COVERED' as const, data_status: 'APPROVED' as const,
  ai_status: 'EFFECTIVE' as const,
  ai_knowledge: { status: 'PUBLISHED' as const, embedding_status: 'COMPLETE' as const, current_fingerprint: 'current', indexed_fingerprint: 'current', active_collection: 'active', chunk_count: 3, embedding_count: 3, updated_at: null, published_at: null, last_error_code: null },
  answerable_topics: ['年龄'], missing_topics: [], gap_count: 0, data_source: 'PILOT' as const, customer_service_status: 'ENABLED' as const,
  customer_service_status_updated_at: null, customer_service_status_updated_by: null, technical_details: technicalDetails,
}

const pendingProduct = {
  ...publishedProduct,
  product_name: '森林伙伴积木',
  data_status: 'PENDING_REVIEW' as const,
  customer_service_status: 'DISABLED' as const,
  ai_knowledge: { ...publishedProduct.ai_knowledge, status: 'NOT_GENERATED' as const, embedding_status: 'NOT_GENERATED' as const, indexed_fingerprint: null, active_collection: null, chunk_count: 0, embedding_count: 0 },
  technical_details: { ...technicalDetails, product_id: 'PRODUCT-2', product_code: 'P-2' },
}

const adminOverview = {
  counts: {
    stores: 1, products: 2, skus: 3, faqs: 2, safety_rules: 1, sources: 2,
    conflicts: 0, import_batches: 1,
    suggestions: { submitted: 2, reviewing: 1, planned: 1, done: 4, rejected: 0 },
  },
  recent_imported_at: '2026-07-25T08:00:00Z',
  test_data_mode: false,
  production_usable: true,
}

const knowledgeOverview = {
  generated_at: '2026-08-01T00:00:00Z', has_data: true,
  stats: { store_count: 1, product_count: 2, ai_usable_product_count: 1, gap_count: 2, pending_review_count: 1 },
  stores: [], boundary_note: '人工确认。',
}

const aiOverview = {
  moduleId: 'ai_customer_service',
  service: { status: 'RUNNING', ready: true, modelConfigured: true, initializationError: null },
  model: { provider: 'ollama', name: 'qwen3.5:9b', configured: true },
  knowledge: { status: 'AVAILABLE', queryableChunkCount: 56, scope: 'LIVE_QUERYABLE_COLLECTIONS' },
  runtime: { metricsScope: 'since_start', callCount: 12, successCount: 12, errorCount: 0, averageLatencyMs: 800, lastCalledAt: null, lastErrorSummary: null },
  latestEvaluation: { status: 'NOT_AVAILABLE', evaluation: null },
  technical: { promptVersion: 'v1', promptHash: 'hash' },
}

describe('OperationsOverviewView', () => {
  beforeEach(() => {
    vi.mocked(getAdminOverview).mockResolvedValue(adminOverview)
    vi.mocked(getHealth).mockResolvedValue({ status: 'ok', service: 'platform-backend', version: '1.0.0', request_id: 'health-1' })
    vi.mocked(getProductKnowledgeOverview).mockResolvedValue(knowledgeOverview)
    vi.mocked(listProductKnowledgeProducts).mockResolvedValue({ items: [publishedProduct, pendingProduct], total: 2 })
    vi.mocked(listAiProblems).mockResolvedValue({ items: [], total: 3 })
    vi.mocked(getAiControlCenterOverview).mockResolvedValue(aiOverview)
  })

  it('answers current work, product lifecycle and AI availability with existing API facts', async () => {
    const wrapper = mount(OperationsOverviewView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    expect(wrapper.text()).toContain('运营工作台')
    expect(wrapper.text()).toContain('当前工作')
    expect(wrapper.text()).toContain('待审核资料1')
    expect(wrapper.text()).toContain('知识缺口2')
    expect(wrapper.text()).toContain('待处理 AI 问题3')
    expect(wrapper.text()).toContain('未关闭运营建议4')
    expect(wrapper.findAll('.lifecycle-grid article').map((item) => item.text())).toEqual([
      '资料已审核1 / 2已完成人工审核 / 当前读取商品',
      '客服可用1 / 2已进入客服商品目录 / 当前读取商品',
      'AI知识已发布1 / 2已有可检索发布状态 / 当前读取商品',
    ])
    expect(wrapper.text()).toContain('AI服务正常')
    expect(wrapper.text()).toContain('56 条知识可检索')
    expect(wrapper.text()).toContain('回答能力正常')
    expect(wrapper.text()).toContain('需要关注无')
    expect(wrapper.text()).toContain('上传商品资料')
    expect(wrapper.text()).not.toContain('今天从哪里开始')
    expect(wrapper.text()).not.toContain('customer_service_status')
  })

  it('explains the loading state before current data has returned', () => {
    vi.mocked(getAdminOverview).mockReturnValueOnce(new Promise(() => {}))

    const wrapper = mount(OperationsOverviewView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })

    expect(wrapper.get('[data-testid="overview-loading-state"]').text()).toContain('正在汇总运营工作台')
    expect(wrapper.get('[data-testid="overview-loading-state"]').text()).toContain('原因：')
    expect(wrapper.get('[data-testid="overview-loading-state"]').text()).toContain('下一步：')
    expect(wrapper.find('.current-grid').exists()).toBe(false)
  })

  it('distinguishes a successful no-work snapshot from a data failure', async () => {
    vi.mocked(getAdminOverview).mockResolvedValueOnce({
      ...adminOverview,
      counts: { ...adminOverview.counts, suggestions: { submitted: 0, reviewing: 0, planned: 0, done: 4, rejected: 0 } },
    })
    vi.mocked(getProductKnowledgeOverview).mockResolvedValueOnce({
      ...knowledgeOverview,
      stats: { store_count: 1, product_count: 0, ai_usable_product_count: 0, gap_count: 0, pending_review_count: 0 },
    })
    vi.mocked(listProductKnowledgeProducts).mockResolvedValueOnce({ items: [], total: 0 })
    vi.mocked(listAiProblems).mockResolvedValueOnce({ items: [], total: 0 })

    const wrapper = mount(OperationsOverviewView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    expect(wrapper.text()).toContain('当前没有待处理事项')
    expect(wrapper.text()).toContain('均为 0')
    expect(wrapper.text()).toContain('当前还没有商品生命周期数据')
    expect(wrapper.text()).toContain('前往商品管理')
  })

  it('shows a real failure instead of zero when product lifecycle data cannot be read', async () => {
    vi.mocked(listProductKnowledgeProducts).mockRejectedValueOnce(new Error('商品状态接口暂时不可用'))
    vi.mocked(getAiControlCenterOverview).mockRejectedValueOnce(new Error('AI状态接口暂时不可用'))

    const wrapper = mount(OperationsOverviewView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    expect(wrapper.text()).toContain('商品生命周期暂时无法读取')
    expect(wrapper.text()).toContain('原因：商品状态接口暂时不可用')
    expect(wrapper.text()).toContain('下一步：刷新工作台重试')
    expect(wrapper.text()).toContain('AI 状态暂时无法读取')
    expect(wrapper.text()).toContain('原因：AI状态接口暂时不可用')
    expect(wrapper.find('.lifecycle-grid').exists()).toBe(false)
  })
})
