import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  apiErrorMessage: vi.fn((reason: unknown) => String(reason)),
  compareReplyReadinessRuns: vi.fn(),
  createReplyReadinessRun: vi.fn(),
  debugPublishedReply: vi.fn(),
  getProductKnowledgeOverview: vi.fn(),
  getProductKnowledgeProduct: vi.fn(),
  getReplyReadinessQuestionSet: vi.fn(),
  getReplyReadinessRun: vi.fn(),
  isOfflineError: vi.fn(() => false),
  listKnowledgeMaterials: vi.fn(),
  listProductKnowledgeProducts: vi.fn(),
  listReplyReadinessRuns: vi.fn(),
}))

vi.mock('../api/client', () => apiMocks)

import ReplyReadinessView from './ReplyReadinessView.vue'
import { resetReplyReadinessDebugState } from '../stores/replyReadinessDebug'

const questions = [
  {
    schema_version: 'pdd-reply-readiness-question.v1', question_id: 'PDD-GREETING', category: 'GREETING',
    canonical_question: '你好', aliases: ['您好'], policy_risk_floor: 'LOW', expected_action: 'DIRECT_ANSWER',
    required_fact_keys: [], requires_realtime_lookup: false, prohibited_claims: [], mandatory: true,
  },
  {
    schema_version: 'pdd-reply-readiness-question.v1', question_id: 'PDD-INVENTORY', category: 'REALTIME_ORDER',
    canonical_question: '现在有货吗', aliases: ['有库存吗'], policy_risk_floor: 'HIGH', expected_action: 'REQUIRE_LOOKUP',
    required_fact_keys: [], requires_realtime_lookup: true, prohibited_claims: [], mandatory: true,
  },
]

function run(skuId: string | null = null, status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' = 'COMPLETED') {
  const answerLow = '亲，您好，请问有什么可以帮您？'
  const answerHigh = '需要人工客服核实后处理。'
  return {
    run_id: `RRN-TEST-${skuId || 'PRODUCT'}`, status, tenant_id: 'TENANT', platform: 'pdd',
    store_code: 'STORE', product_id: 'PRODUCT', sku_id: skuId, question_set_fingerprint: 'a'.repeat(64),
    question_count: 2, material_id: 'KMT-001', material_revision: 2, material_content_hash: `sha256:${'b'.repeat(64)}`,
    knowledge_source_count: 3,
    reply_rule_snapshot_revision: 1, reply_rule_snapshot_fingerprint: 'c'.repeat(64), failure_code: null,
    requested_by: 'operator', requested_at: '2026-08-14T00:00:00Z', completed_at: status === 'COMPLETED' ? '2026-08-14T00:00:01Z' : null,
    result: status === 'COMPLETED' ? {
      schema_version: 'pdd-reply-readiness-result.v1', run_id: `RRN-TEST-${skuId || 'PRODUCT'}`, status: 'COMPLETED',
      question_set_fingerprint: 'a'.repeat(64), result_sha256: 'd'.repeat(64),
      items: [
        { schema_version: 'pdd-reply-readiness-item-result.v1', question_id: 'PDD-GREETING', effective_risk: 'LOW', action: 'DIRECT_ANSWER', origin: 'RAG', answer_preview: answerLow, answer_sha256: 'e'.repeat(64), missing_fact_keys: [], blocker_codes: [], prohibited_claim_hits: [], citation_ids: ['rr:greeting'], evidence_bundle_sha256: 'f'.repeat(64) },
        { schema_version: 'pdd-reply-readiness-item-result.v1', question_id: 'PDD-INVENTORY', effective_risk: 'HIGH', action: 'TRANSFER_HUMAN', origin: 'MANUAL', answer_preview: answerHigh, answer_sha256: '1'.repeat(64), missing_fact_keys: [], blocker_codes: ['REALTIME_ORDER_REQUIRES_MANUAL'], prohibited_claim_hits: [], citation_ids: [], evidence_bundle_sha256: null },
      ],
    } : null,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

function debugResult(answer = '您好，请问有什么可以帮您？') {
  return {
    schema_version: 'pdd-reply-readiness-published-debug-result.v1',
    simulation_mode: 'PUBLISHED_ROUTER_DEBUG', run_id: 'DBG-TEST-001', status: 'COMPLETED',
    question_set_fingerprint: 'a'.repeat(64), failure_code: null, quality_gate_status: 'PASS',
    rule_references: ['RULE-GREETING:v1'], router_build_fingerprint: 'b'.repeat(64),
    reply_rule_snapshot_fingerprint: 'c'.repeat(64), rag_collection_identity: null,
    knowledge_publication_fingerprint: null, knowledge_publication_status: 'UNAVAILABLE',
    model_config_identity: 'd'.repeat(64), evaluated_at: '2026-08-14T08:00:00Z',
    dependency_usage: { router: true, reply_rule: true, rag_collection: false, knowledge: false, model: false },
    diagnostic_changes: [{ dependency: 'model', before: 'old', after: 'new' }], drifted_dependencies: [],
    production_usable: false, allow_auto_send: false, result_sha256: 'e'.repeat(64),
    item: {
      schema_version: 'pdd-reply-readiness-item-result.v1', question_id: 'DEBUG-001',
      effective_risk: 'LOW', action: 'DIRECT_ANSWER', origin: 'FIXED_RULE', answer_preview: answer,
      answer_sha256: 'f'.repeat(64), missing_fact_keys: [], blocker_codes: [], prohibited_claim_hits: [],
      citation_ids: ['reply-rule:RULE-GREETING:v1'], evidence_bundle_sha256: '1'.repeat(64),
    },
  }
}

async function mountView(path = '/reply-readiness?store=STORE&product=PRODUCT'): Promise<VueWrapper> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/reply-readiness', component: ReplyReadinessView },
      { path: '/knowledge-editor', component: { template: '<div />' } },
      { path: '/knowledge-review', component: { template: '<div />' } },
      { path: '/knowledge-center', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(ReplyReadinessView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('ReplyReadinessView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetReplyReadinessDebugState()
    apiMocks.getProductKnowledgeOverview.mockResolvedValue({
      stores: [{ store_name: '合成店铺', technical_details: { store_code: 'STORE' } }],
    })
    apiMocks.listProductKnowledgeProducts.mockResolvedValue({
      items: [{ product_name: '合成商品', data_source: 'TEST', technical_details: { store_code: 'STORE', product_id: 'PRODUCT' } }],
    })
    apiMocks.getProductKnowledgeProduct.mockResolvedValue({
      skus: [{ sku_name: '合成SKU', technical_details: { sku_id: 'SKU' } }],
    })
    apiMocks.listKnowledgeMaterials.mockResolvedValue({
      items: [{ material_id: 'KMT-001', revision: 2, display_name: '合成资料', material_status: 'RECOGNIZED', sku_id: null, updated_at: '2026-08-14T00:00:00Z', recognition_summary: { template_type: 'PRODUCT_KNOWLEDGE' } }],
      total: 1, page: 1, size: 100,
    })
    apiMocks.getReplyReadinessQuestionSet.mockResolvedValue({
      schema_version: 'pdd-reply-readiness-question-set.v1', baseline_version: 'pdd-common-questions.v1',
      fingerprint: 'a'.repeat(64), questions,
    })
    apiMocks.listReplyReadinessRuns.mockResolvedValue({ items: [run()], total: 1 })
    apiMocks.createReplyReadinessRun.mockResolvedValue(run())
    apiMocks.getReplyReadinessRun.mockResolvedValue(run())
    apiMocks.isOfflineError.mockReturnValue(false)
    apiMocks.debugPublishedReply.mockResolvedValue(debugResult())
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('presents operational conclusions first and requests exact product scope', async () => {
    const wrapper = await mountView()

    expect(wrapper.text()).toContain('商品回答风险池')
    expect(wrapper.text()).toContain('production_usable=false')
    expect(wrapper.text()).toContain('allow_auto_send=false')
    expect(wrapper.text()).toContain('可直接回答')
    expect(wrapper.text()).toContain('转人工 / 待补资料')
    expect(wrapper.text()).toContain('系统会自动聚合当前商品最新已审核资料')
    expect(wrapper.text()).toContain('测试资料')
    expect(wrapper.text()).toContain('允许调试，但不代表正式商品事实')
    expect(wrapper.text()).toContain('冻结知识来源')
    expect(wrapper.text()).toContain('3 份')
    expect(wrapper.text()).toContain('现在有货吗')
    expect(wrapper.text()).toContain('需要查询实时订单信息')
    expect(wrapper.find('details.technical-details').exists()).toBe(false)
    expect(apiMocks.listReplyReadinessRuns).toHaveBeenCalledWith({
      store_code: 'STORE', product_id: 'PRODUCT', scope_kind: 'PRODUCT', sku_id: undefined,
    })
    expect(apiMocks.listKnowledgeMaterials).toHaveBeenCalledWith(expect.objectContaining({ size: 100 }))

    await wrapper.find('.text-button').trigger('click')
    expect(wrapper.find('details.technical-details').exists()).toBe(true)
    expect(wrapper.find('details.technical-details').attributes('open')).toBeUndefined()

    await wrapper.get('.summary-card.high').trigger('click')
    expect(wrapper.findAll('.desktop-results tbody > tr').filter((item) => !item.classes().includes('detail-row'))).toHaveLength(1)
    expect(wrapper.text()).toContain('显示 1 / 2 题')

    await wrapper.get('.clear-filters').trigger('click')
    expect(wrapper.text()).toContain('显示 2 / 2 题')
    expect(wrapper.find('.workspace-tabs').attributes('role')).toBe('tablist')
    expect(wrapper.find('#reply-pool-tab').attributes('aria-selected')).toBe('true')
  })

  it('shows the complete product name with its stable PDD identity', async () => {
    const fullName = '合成长名称积木机械模型儿童拼装益智玩具礼物测试商品'
    const productId = 'PDD-SYNTHETIC-LONG-001'
    apiMocks.listProductKnowledgeProducts.mockResolvedValue({
      items: [{ product_name: fullName, data_source: 'PILOT', technical_details: { store_code: 'STORE', product_id: productId } }],
    })
    const wrapper = await mountView(`/reply-readiness?store=STORE&product=${productId}`)

    expect(wrapper.get('.scope-chip strong').text()).toBe(fullName)
    expect(wrapper.get('.scope-chip').text()).toContain(`PDD ID：${productId}`)
    expect(wrapper.findAll('.controls select')[1].text()).toContain(fullName)
  })

  it('keeps successful scope data visible and reports the failed section precisely', async () => {
    apiMocks.listKnowledgeMaterials.mockRejectedValue(new Error('materials unavailable'))
    const wrapper = await mountView()

    expect(wrapper.text()).toContain('知识资料修订加载失败：')
    expect(wrapper.text()).toContain('materials unavailable')
    expect(wrapper.text()).toContain('现在有货吗')
    expect(wrapper.get('.run-button').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).not.toContain('36题问题集加载失败')
    expect(wrapper.text()).not.toContain('历史评测加载失败')
  })

  it('clears product results and loads only the selected SKU history', async () => {
    const wrapper = await mountView()
    apiMocks.listReplyReadinessRuns.mockResolvedValueOnce({ items: [run('SKU')], total: 1 })
    apiMocks.listKnowledgeMaterials.mockResolvedValueOnce({
      items: [{ material_id: 'KMT-SKU', revision: 1, display_name: 'SKU资料', material_status: 'RECOGNIZED', sku_id: 'SKU', updated_at: '2026-08-14T01:00:00Z', recognition_summary: { template_type: 'PRODUCT_KNOWLEDGE' } }],
      total: 1, page: 1, size: 100,
    })

    await wrapper.findAll('.controls select')[2].setValue('SKU')
    await flushPromises()

    expect(apiMocks.listReplyReadinessRuns).toHaveBeenLastCalledWith({
      store_code: 'STORE', product_id: 'PRODUCT', scope_kind: 'SKU', sku_id: 'SKU',
    })
    expect(wrapper.text()).toContain('SKU：合成SKU')
    expect(wrapper.text()).toContain('SKU资料')
  })

  it('ignores a late product response after the operator has selected another product', async () => {
    const productA = deferred<{ skus: unknown[] }>()
    apiMocks.listProductKnowledgeProducts.mockResolvedValue({
      items: [
        { product_name: '商品A', technical_details: { store_code: 'STORE', product_id: 'A' } },
        { product_name: '商品B', technical_details: { store_code: 'STORE', product_id: 'B' } },
      ],
    })
    apiMocks.getProductKnowledgeProduct.mockImplementation((productId: string) => (
      productId === 'A' ? productA.promise : Promise.resolve({ skus: [] })
    ))
    apiMocks.listReplyReadinessRuns.mockResolvedValue({ items: [], total: 0 })
    const wrapper = await mountView('/reply-readiness?store=STORE')
    const productSelect = wrapper.findAll('.controls select')[1]

    await productSelect.setValue('A')
    await productSelect.setValue('B')
    await flushPromises()
    productA.resolve({ skus: [{ sku_name: '陈旧SKU', technical_details: { sku_id: 'STALE' } }] })
    await flushPromises()

    expect(wrapper.text()).toContain('商品B')
    expect(wrapper.text()).not.toContain('陈旧SKU')
    expect(apiMocks.getReplyReadinessQuestionSet).toHaveBeenCalledTimes(1)
    expect(apiMocks.getReplyReadinessQuestionSet).toHaveBeenCalledWith({ store_code: 'STORE', product_id: 'B', sku_id: undefined })
  })

  it('recovers a timed-out run with the same idempotency key and polls its result', async () => {
    vi.useFakeTimers()
    const pending = run(null, 'RUNNING')
    apiMocks.listReplyReadinessRuns.mockResolvedValue({ items: [], total: 0 })
    apiMocks.createReplyReadinessRun
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(pending)
    apiMocks.isOfflineError.mockReturnValue(true)
    apiMocks.getReplyReadinessRun.mockResolvedValue(run())
    const wrapper = await mountView()

    await wrapper.get('.run-button').trigger('click')
    await flushPromises()
    expect(apiMocks.createReplyReadinessRun).toHaveBeenCalledTimes(2)
    expect(apiMocks.createReplyReadinessRun.mock.calls[0][1]).toBe(apiMocks.createReplyReadinessRun.mock.calls[1][1])

    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(apiMocks.getReplyReadinessRun).toHaveBeenCalledWith(pending.run_id)
    expect(wrapper.text()).toContain('隔离评测已完成')
  })

  it('deep-links each missing fact to the existing knowledge editor', async () => {
    const customized = run()
    if (customized.result) {
      Object.assign(customized.result.items[1], {
        missing_fact_keys: ['particle_count'], blocker_codes: ['MISSING_REQUIRED_FACTS'],
      })
    }
    apiMocks.listReplyReadinessRuns.mockResolvedValue({ items: [customized], total: 1 })
    const wrapper = await mountView()

    const links = wrapper.findAll('a.text-link').filter((item) => item.text() === '补充资料')
    expect(links.length).toBeGreaterThanOrEqual(2)
    const href = links.find((item) => (item.attributes('href') || '').includes('PDD-INVENTORY'))?.attributes('href') || ''
    expect(href).toContain('/knowledge-editor?')
    expect(href).toContain('question_id=PDD-INVENTORY')
    expect(href).toContain('fact_key=particle_count')
    expect(href).toContain('template=PRODUCT_KNOWLEDGE')
  })

  it('uses the production read-only debug endpoint and explains actual dependencies', async () => {
    const wrapper = await mountView()
    await wrapper.findAll('.workspace-tabs button')[1].trigger('click')
    await wrapper.get('.debug-message textarea').setValue('你好')
    await wrapper.get('.debug-actions button').trigger('click')
    await flushPromises()

    expect(apiMocks.debugPublishedReply).toHaveBeenCalledWith({
      store_code: 'STORE', product_id: 'PRODUCT', sku_id: undefined, customer_message: '你好',
    })
    expect(wrapper.text()).toContain('您好，请问有什么可以帮您？')
    expect(wrapper.text()).toContain('固定回复规则')
    expect(wrapper.text()).toContain('本次未使用RAG知识')
    expect(wrapper.text()).toContain('不会创建风险池运行、客户会话、审批、执行或发送记录')
    expect(wrapper.text()).toContain('production_usable=false')
    expect(wrapper.text()).toContain('allow_auto_send=false')
  })

  it('keeps the debug question and result only in the current SPA process', async () => {
    const first = await mountView()
    await first.findAll('.workspace-tabs button')[1].trigger('click')
    await first.get('.debug-message textarea').setValue('你好')
    await first.get('.debug-actions button').trigger('click')
    await flushPromises()
    first.unmount()

    const returned = await mountView('/reply-readiness')
    expect((returned.get('.debug-message textarea').element as HTMLTextAreaElement).value).toBe('你好')
    expect(returned.text()).toContain('您好，请问有什么可以帮您？')
    expect(returned.findAll('.workspace-tabs button')[1].classes()).toContain('active')
  })

  it('discards a late debug response after the message changes', async () => {
    const pending = deferred<ReturnType<typeof debugResult>>()
    apiMocks.debugPublishedReply.mockReturnValueOnce(pending.promise)
    const wrapper = await mountView()
    await wrapper.findAll('.workspace-tabs button')[1].trigger('click')
    const textarea = wrapper.get('.debug-message textarea')
    await textarea.setValue('你好')
    await wrapper.get('.debug-actions button').trigger('click')
    await textarea.setValue('这个有多大？')
    pending.resolve(debugResult('不应显示的旧回答'))
    await flushPromises()

    expect(wrapper.text()).not.toContain('不应显示的旧回答')
    expect(wrapper.text()).toContain('输入一条客户原话后运行')
  })

  it('discards a late debug response after the product scope changes', async () => {
    const pending = deferred<ReturnType<typeof debugResult>>()
    apiMocks.debugPublishedReply.mockReturnValueOnce(pending.promise)
    apiMocks.listProductKnowledgeProducts.mockResolvedValue({
      items: [
        { product_name: '商品A', data_source: 'INITIAL_IMPORT', technical_details: { store_code: 'STORE', product_id: 'PRODUCT' } },
        { product_name: '商品B', data_source: 'PILOT', technical_details: { store_code: 'STORE', product_id: 'PRODUCT-B' } },
      ],
    })
    apiMocks.getProductKnowledgeProduct.mockResolvedValue({ skus: [] })
    const wrapper = await mountView()
    await wrapper.findAll('.workspace-tabs button')[1].trigger('click')
    await wrapper.get('.debug-message textarea').setValue('你好')
    await wrapper.get('.debug-actions button').trigger('click')
    await wrapper.findAll('.controls select')[1].setValue('PRODUCT-B')
    await flushPromises()
    pending.resolve(debugResult('不应跨商品显示'))
    await flushPromises()

    expect(wrapper.text()).not.toContain('不应跨商品显示')
    expect(wrapper.text()).toContain('商品B')
  })
})
