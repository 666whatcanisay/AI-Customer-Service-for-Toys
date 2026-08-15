<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import {
  apiErrorMessage,
  compareReplyReadinessRuns,
  createReplyReadinessRun,
  debugPublishedReply,
  getProductKnowledgeOverview,
  getProductKnowledgeProduct,
  getReplyReadinessQuestionSet,
  getReplyReadinessRun,
  isOfflineError,
  listKnowledgeMaterials,
  listProductKnowledgeProducts,
  listReplyReadinessRuns,
  type KnowledgeMaterial,
  type KnowledgeTemplateType,
  type ProductKnowledgeDetail,
  type ProductKnowledgeListItem,
  type ReplyReadinessAction,
  type ReplyReadinessItemResult,
  type ReplyReadinessPublishedDebugResult,
  type ReplyReadinessQuestionSet,
  type ReplyReadinessRisk,
  type ReplyReadinessRun,
  type ReplyReadinessRunComparison,
  type StoreKnowledgeSummary,
} from '../api/client'
import { displayStatus } from '../presentation'
import {
  rememberReplyReadinessDebugScope,
  replyReadinessDebugState,
  type ReplyReadinessWorkspaceTab,
} from '../stores/replyReadinessDebug'

type ComparisonGroup = 'WORSE' | 'IMPROVED' | 'ANSWER_CHANGED' | 'OTHER'

const route = useRoute()
const router = useRouter()
const initialLoading = ref(true)
const scopeLoading = ref(false)
const running = ref(false)
const debugRunning = ref(false)
const debugError = ref('')
const scopeError = ref('')
const runError = ref('')
const comparisonError = ref('')
const routeNotice = ref('')
const runMessage = ref('')
const stores = ref<StoreKnowledgeSummary[]>([])
const products = ref<ProductKnowledgeListItem[]>([])
const productDetail = ref<ProductKnowledgeDetail | null>(null)
const materialRevisions = ref<KnowledgeMaterial[]>([])
const questionSet = ref<ReplyReadinessQuestionSet | null>(null)
const runs = ref<ReplyReadinessRun[]>([])
const selectedRunId = ref('')
const baselineRunId = ref('')
const comparison = ref<ReplyReadinessRunComparison | null>(null)
const riskFilter = ref<ReplyReadinessRisk | ''>('')
const categoryFilter = ref('')
const actionFilter = ref<ReplyReadinessAction | ''>('')
const questionSearch = ref('')
const expandedItems = ref<string[]>([])
const scope = reactive({ store_code: '', product_id: '', sku_id: '', material_key: '' })
const activeTab = computed({
  get: () => replyReadinessDebugState.tab,
  set: (value: ReplyReadinessWorkspaceTab) => { replyReadinessDebugState.tab = value },
})
const debugResult = computed(() => (
  replyReadinessDebugState.latestMessage === replyReadinessDebugState.customerMessage.trim()
    ? replyReadinessDebugState.latestResult
    : null
))
const debugItem = computed(() => debugResult.value?.item || null)
const previousDebugItem = computed(() => replyReadinessDebugState.previousResult?.item || null)

let scopeLoadEpoch = 0
let pollingEpoch = 0
let debugRequestEpoch = 0

const RISK_ORDER: Record<ReplyReadinessRisk, number> = { LOW: 1, MEDIUM: 2, HIGH: 3 }
const COMPARISON_ORDER: ComparisonGroup[] = ['WORSE', 'IMPROVED', 'ANSWER_CHANGED', 'OTHER']
const ACTION_LABELS: Record<ReplyReadinessAction, string> = {
  DIRECT_ANSWER: '直接回答',
  CONTROLLED_ANSWER: '按审核话术回答',
  ASK_CLARIFY: '向客户补充询问',
  REQUIRE_LOOKUP: '查询实时信息',
  TRANSFER_HUMAN: '转人工处理',
  REFUSE: '拒绝处理',
}
const actionOptions = Object.entries(ACTION_LABELS) as Array<[ReplyReadinessAction, string]>
const ORIGIN_LABELS: Record<string, string> = {
  FIXED_RULE: '固定回复规则',
  RAG: '知识检索回答',
  COMPOSITE: '组合回答',
  MANUAL: '人工处理',
}
const CATEGORY_LABELS: Record<string, string> = {
  GREETING: '问候', AFFIRMATION: '确认', THANKS: '感谢', PRODUCT_MEDIA: '图片与视频',
  PRODUCT_FACT: '商品参数', PRODUCT_USAGE: '安装与使用', SKU_FACT: '款式区别',
  REALTIME_ORDER: '实时订单', PROMOTION: '优惠活动', SHOPPING_GUIDE: '选购推荐',
  FULFILLMENT: '发货与配送', AFTERSALES: '售后处理', AUTHENTICITY: '真假授权',
}
const BLOCKER_LABELS: Record<string, string> = {
  REALTIME_ORDER_REQUIRES_MANUAL: '需要查询实时订单信息',
  REALTIME_LOOKUP_REQUIRED: '需要查询实时业务信息',
  MISSING_REQUIRED_FACTS: '缺少回答所需资料',
  FACT_CONFLICT: '资料中存在互相冲突的事实',
  ESTIMATED_FACT: '资料包含估测值，不能作为确定回答',
  AUTHENTICITY_EVIDENCE_REQUIRED: '缺少品牌授权或真伪证据',
  PROHIBITED_CLAIM: '回答命中禁止承诺',
  QUALITY_GATE_FAILED: '回答质量检查未通过',
  SOURCE_SCOPE_MISMATCH: '引用资料不属于当前商品范围',
  RAG_FAILURE: '知识检索暂时不可用',
  KNOWLEDGE_NOT_PUBLISHED: '当前商品知识尚未发布，知识检索回答已转人工',
  KNOWLEDGE_FINGERPRINT_DRIFT: '商品知识版本与已发布索引不一致',
  RAG_COLLECTION_IDENTITY_DRIFT: '当前知识集合与发布记录不一致',
  PRODUCTION_RUNTIME_VERSION_DRIFT: '本次实际使用的生产依赖在评测期间发生变化',
  SYNTHETIC_MANUAL: '当前题目需要人工核对',
}

const scopedProducts = computed(() => products.value.filter(
  (item) => item.technical_details.store_code === scope.store_code,
))
const selectedProduct = computed(() => scopedProducts.value.find(
  (item) => item.technical_details.product_id === scope.product_id,
))
const selectedSku = computed(() => productDetail.value?.skus.find(
  (item) => item.technical_details.sku_id === scope.sku_id,
))
const selectedRun = computed(() => runs.value.find((item) => item.run_id === selectedRunId.value) || null)
const questionById = computed(() => new Map(
  (questionSet.value?.questions || []).map((item) => [item.question_id, item]),
))
const categoryOptions = computed(() => Array.from(new Set(
  (questionSet.value?.questions || []).map((item) => item.category),
)).sort())
const scopeReady = computed(() => Boolean(
  scope.store_code && scope.product_id && productDetail.value && questionSet.value && !scopeLoading.value,
))
const completedRuns = computed(() => runs.value.filter(
  (item) => item.status === 'COMPLETED' && item.result && item.run_id !== selectedRun.value?.run_id,
))
const riskCounts = computed(() => {
  const counts: Record<ReplyReadinessRisk, number> = { LOW: 0, MEDIUM: 0, HIGH: 0 }
  for (const item of selectedRun.value?.result?.items || []) counts[item.effective_risk] += 1
  return counts
})
const visibleItems = computed(() => {
  const keyword = questionSearch.value.trim().toLowerCase()
  return [...(selectedRun.value?.result?.items || [])]
    .filter((item) => {
      const question = questionById.value.get(item.question_id)
      const searchable = [question?.canonical_question, ...(question?.aliases || [])].join(' ').toLowerCase()
      return (!riskFilter.value || item.effective_risk === riskFilter.value)
        && (!categoryFilter.value || question?.category === categoryFilter.value)
        && (!actionFilter.value || item.action === actionFilter.value)
        && (!keyword || searchable.includes(keyword))
    })
    .sort((left, right) => RISK_ORDER[right.effective_risk] - RISK_ORDER[left.effective_risk]
      || itemQuestion(left).localeCompare(itemQuestion(right), 'zh-CN'))
})
const hasActiveFilters = computed(() => Boolean(
  questionSearch.value || categoryFilter.value || actionFilter.value || riskFilter.value,
))
const comparisonGroups = computed(() => {
  const groups: Record<ComparisonGroup, ReplyReadinessRunComparison['changed_items']> = {
    WORSE: [], IMPROVED: [], ANSWER_CHANGED: [], OTHER: [],
  }
  for (const item of comparison.value?.changed_items || []) {
    if (item.before_risk && RISK_ORDER[item.after_risk] > RISK_ORDER[item.before_risk]) groups.WORSE.push(item)
    else if (item.before_risk && RISK_ORDER[item.after_risk] < RISK_ORDER[item.before_risk]) groups.IMPROVED.push(item)
    else if (item.answer_changed) groups.ANSWER_CHANGED.push(item)
    else groups.OTHER.push(item)
  }
  return groups
})
const selectedMaterial = computed(() => materialRevisions.value.find(
  (item) => `${item.material_id}:${item.revision}` === scope.material_key,
))

function riskLabel(value: ReplyReadinessRisk): string {
  return value === 'LOW' ? '低风险' : value === 'MEDIUM' ? '中风险' : '高风险'
}

function actionLabel(value: ReplyReadinessAction): string {
  return ACTION_LABELS[value] || '人工核对'
}

function originLabel(value: string): string {
  return ORIGIN_LABELS[value] || '其他来源'
}

function clearResultFilters(): void {
  questionSearch.value = ''
  categoryFilter.value = ''
  actionFilter.value = ''
  riskFilter.value = ''
}

function categoryLabel(value: string): string {
  return CATEGORY_LABELS[value] || value
}

function blockerLabel(value: string): string {
  return BLOCKER_LABELS[value] || '需要人工核对具体原因'
}

function dependencyLabel(value: string): string {
  return {
    router: '回答路由', reply_rule: '固定回复规则', rag_collection: '知识集合',
    knowledge: '已发布知识', model: '模型与提示词',
  }[value] || value
}

function dataSourceLabel(value: ProductKnowledgeListItem['data_source']): string {
  if (value === 'INITIAL_IMPORT') return '正式导入资料'
  if (value === 'PILOT') return 'Pilot资料'
  if (value === 'TEST') return '测试资料'
  return '来源待确认'
}

function invalidateDebugRequest(): void {
  debugRequestEpoch += 1
  debugRunning.value = false
}

function rememberDebugScope(): void {
  rememberReplyReadinessDebugScope({
    store_code: scope.store_code,
    product_id: scope.product_id,
    sku_id: scope.sku_id,
  })
}

function selectTab(value: ReplyReadinessWorkspaceTab): void {
  if (activeTab.value !== value) invalidateDebugRequest()
  activeTab.value = value
  debugError.value = ''
  if (value === 'DEBUG') rememberDebugScope()
  else syncRoute()
}

function runStatusLabel(value: ReplyReadinessRun['status']): string {
  if (value === 'PENDING') return '等待评测'
  if (value === 'RUNNING') return '评测中'
  if (value === 'COMPLETED') return '已完成'
  return '评测失败'
}

function itemQuestion(item: ReplyReadinessItemResult): string {
  return questionById.value.get(item.question_id)?.canonical_question || item.question_id
}

function questionLabel(questionId: string): string {
  return questionById.value.get(questionId)?.canonical_question || questionId
}

function formatDate(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(parsed)
}

function materialReference(): { material_id?: string; material_revision?: number } {
  const item = selectedMaterial.value
  return item ? { material_id: item.material_id, material_revision: item.revision } : {}
}

function supplementTemplate(item: ReplyReadinessItemResult): KnowledgeTemplateType {
  if (item.missing_fact_keys.length) return 'PRODUCT_KNOWLEDGE'
  if (item.prohibited_claim_hits.length || item.blocker_codes.some((code) => (
    code.includes('PROHIBITED') || code.includes('SAFETY')
  ))) return 'SAFETY_RULE'
  return 'FAQ'
}

function supplementQuery(item: ReplyReadinessItemResult): Record<string, string> {
  const template = supplementTemplate(item)
  const selected = selectedMaterial.value
  const canReviseSelected = selected?.recognition_summary?.template_type === template
  return {
    store: scope.store_code,
    product: scope.product_id,
    ...(scope.sku_id ? { sku: scope.sku_id } : {}),
    question_id: item.question_id,
    ...(item.missing_fact_keys[0] ? { fact_key: item.missing_fact_keys[0] } : {}),
    template,
    ...(canReviseSelected && selected ? {
      material_id: selected.material_id,
      material_revision: String(selected.revision),
    } : {}),
  }
}

function debugSupplementQuery(item: ReplyReadinessItemResult): Record<string, string> {
  const template = supplementTemplate(item)
  return {
    store: scope.store_code,
    product: scope.product_id,
    ...(scope.sku_id ? { sku: scope.sku_id } : {}),
    question_id: item.question_id,
    ...(item.missing_fact_keys[0] ? { fact_key: item.missing_fact_keys[0] } : {}),
    template,
  }
}

function primaryGap(item: ReplyReadinessItemResult): string {
  if (item.missing_fact_keys.length) return `缺少资料：${item.missing_fact_keys.join('、')}`
  if (item.blocker_codes.length) return blockerLabel(item.blocker_codes[0])
  return '资料和安全检查均通过'
}

function createIdempotencyKey(): string {
  return typeof crypto?.randomUUID === 'function'
    ? `reply-readiness-ui-${crypto.randomUUID()}`
    : `reply-readiness-ui-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function resetEvaluationState(): void {
  stopPolling()
  running.value = false
  questionSet.value = null
  materialRevisions.value = []
  runs.value = []
  selectedRunId.value = ''
  baselineRunId.value = ''
  comparison.value = null
  riskFilter.value = ''
  categoryFilter.value = ''
  actionFilter.value = ''
  questionSearch.value = ''
  expandedItems.value = []
  runError.value = ''
  comparisonError.value = ''
  runMessage.value = ''
}

function stopPolling(): void {
  pollingEpoch += 1
}

function replaceRun(item: ReplyReadinessRun): void {
  runs.value = [item, ...runs.value.filter((run) => run.run_id !== item.run_id)]
  selectedRunId.value = item.run_id
}

function toggleExpanded(questionId: string): void {
  expandedItems.value = expandedItems.value.includes(questionId)
    ? expandedItems.value.filter((item) => item !== questionId)
    : [...expandedItems.value, questionId]
}

function syncRoute(): void {
  if (activeTab.value === 'DEBUG') {
    rememberDebugScope()
    return
  }
  const material = materialReference()
  void router.replace({
    path: '/reply-readiness',
    query: {
      ...(scope.store_code ? { store: scope.store_code } : {}),
      ...(scope.product_id ? { product: scope.product_id } : {}),
      ...(scope.sku_id ? { sku: scope.sku_id } : {}),
      ...(material.material_id ? {
        material_id: material.material_id,
        material_revision: String(material.material_revision),
      } : {}),
    },
  })
}

async function loadScopeData(epoch: number, requestedMaterialKey = ''): Promise<void> {
  const storeCode = scope.store_code
  const productId = scope.product_id
  const skuId = scope.sku_id
  const [materials, effectiveQuestions, runList] = await Promise.all([
    listKnowledgeMaterials({
      store_code: storeCode,
      product_id: productId,
      sku_id: skuId || undefined,
      page: 1,
      size: 100,
    }),
    getReplyReadinessQuestionSet({
      store_code: storeCode,
      product_id: productId,
      sku_id: skuId || undefined,
    }),
    listReplyReadinessRuns({
      store_code: storeCode,
      product_id: productId,
      scope_kind: skuId ? 'SKU' : 'PRODUCT',
      sku_id: skuId || undefined,
    }),
  ])
  if (epoch !== scopeLoadEpoch || storeCode !== scope.store_code
    || productId !== scope.product_id || skuId !== scope.sku_id) return

  const exactMaterials = materials.items
    .filter((item) => (item.sku_id === null || item.sku_id === (skuId || null))
      && ['RECOGNIZED', 'REVIEWING'].includes(item.material_status)
      && ['PRODUCT_KNOWLEDGE', 'SKU_DIFFERENCE', 'FAQ', 'SAFETY_RULE'].includes(
        item.recognition_summary.template_type || '',
      ))
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at) || right.revision - left.revision)
  materialRevisions.value = exactMaterials
  questionSet.value = effectiveQuestions
  runs.value = runList.items.filter((item) => item.sku_id === (skuId || null))
  selectedRunId.value = runs.value[0]?.run_id || ''
  if (requestedMaterialKey) {
    if (exactMaterials.some((item) => `${item.material_id}:${item.revision}` === requestedMaterialKey)) {
      scope.material_key = requestedMaterialKey
    } else {
      routeNotice.value = '链接中的知识修订不属于当前商品范围，已为你清除。'
    }
  }
}

async function loadProduct(options?: { requestedSku?: string; requestedMaterialKey?: string }): Promise<void> {
  invalidateDebugRequest()
  const epoch = ++scopeLoadEpoch
  resetEvaluationState()
  scope.sku_id = ''
  scope.material_key = ''
  productDetail.value = null
  scopeError.value = ''
  routeNotice.value = ''
  if (!scope.product_id) {
    scopeLoading.value = false
    syncRoute()
    return
  }
  scopeLoading.value = true
  try {
    const productId = scope.product_id
    const detail = await getProductKnowledgeProduct(productId)
    if (epoch !== scopeLoadEpoch || productId !== scope.product_id) return
    productDetail.value = detail
    const requestedSku = options?.requestedSku || ''
    if (requestedSku) {
      if (detail.skus.some((item) => item.technical_details.sku_id === requestedSku)) scope.sku_id = requestedSku
      else routeNotice.value = '链接中的SKU不属于当前商品，已改为商品级评测。'
    }
    await loadScopeData(epoch, options?.requestedMaterialKey)
    if (epoch === scopeLoadEpoch) {
      rememberDebugScope()
      syncRoute()
    }
  } catch (reason: unknown) {
    if (epoch === scopeLoadEpoch) scopeError.value = apiErrorMessage(reason)
  } finally {
    if (epoch === scopeLoadEpoch) scopeLoading.value = false
  }
}

function changeStore(): void {
  invalidateDebugRequest()
  scopeLoadEpoch += 1
  resetEvaluationState()
  scope.product_id = ''
  scope.sku_id = ''
  scope.material_key = ''
  productDetail.value = null
  scopeError.value = ''
  routeNotice.value = ''
  scopeLoading.value = false
  rememberDebugScope()
  syncRoute()
}

async function changeSku(): Promise<void> {
  invalidateDebugRequest()
  const epoch = ++scopeLoadEpoch
  resetEvaluationState()
  scope.material_key = ''
  scopeError.value = ''
  routeNotice.value = ''
  scopeLoading.value = true
  try {
    await loadScopeData(epoch)
    if (epoch === scopeLoadEpoch) {
      rememberDebugScope()
      syncRoute()
    }
  } catch (reason: unknown) {
    if (epoch === scopeLoadEpoch) scopeError.value = apiErrorMessage(reason)
  } finally {
    if (epoch === scopeLoadEpoch) scopeLoading.value = false
  }
}

async function pollRun(runId: string, epoch: number): Promise<void> {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (epoch !== pollingEpoch) return
    await new Promise((resolve) => setTimeout(resolve, 2000))
    if (epoch !== pollingEpoch) return
    try {
      const latest = await getReplyReadinessRun(runId)
      if (epoch !== pollingEpoch) return
      replaceRun(latest)
      if (latest.status === 'COMPLETED') {
        runMessage.value = '隔离评测已完成。'
        return
      }
      if (latest.status === 'FAILED') {
        runError.value = '本次隔离评测失败，没有复用旧结果。'
        return
      }
    } catch (reason: unknown) {
      if (epoch === pollingEpoch) runError.value = apiErrorMessage(reason)
      return
    }
  }
  if (epoch === pollingEpoch) {
    runMessage.value = '运行状态仍待确认。系统不会自动创建重复运行，请稍后使用“刷新状态”。'
  }
}

async function runEvaluation(): Promise<void> {
  if (!scopeReady.value || running.value) return
  const epoch = ++pollingEpoch
  running.value = true
  runError.value = ''
  runMessage.value = '正在创建隔离评测，本页不会发送任何客服消息。'
  comparison.value = null
  baselineRunId.value = ''
  selectedRunId.value = ''
  const payload = {
    store_code: scope.store_code,
    product_id: scope.product_id,
    sku_id: scope.sku_id || undefined,
    ...materialReference(),
  }
  const idempotencyKey = createIdempotencyKey()
  try {
    let result: ReplyReadinessRun
    try {
      result = await createReplyReadinessRun(payload, idempotencyKey)
    } catch (reason: unknown) {
      if (!isOfflineError(reason)) throw reason
      runMessage.value = '连接中断，正在使用同一请求凭据恢复运行，不会重复创建。'
      result = await createReplyReadinessRun(payload, idempotencyKey)
    }
    if (epoch !== pollingEpoch) return
    replaceRun(result)
    if (result.status === 'PENDING' || result.status === 'RUNNING') {
      runMessage.value = '评测正在后台完成，可以留在当前页面等待。'
      await pollRun(result.run_id, epoch)
    } else if (result.status === 'FAILED') {
      runError.value = '本次隔离评测失败，没有复用旧结果。'
    } else {
      runMessage.value = '隔离评测已完成。'
    }
  } catch (reason: unknown) {
    if (epoch === pollingEpoch) runError.value = apiErrorMessage(reason)
  } finally {
    if (epoch === pollingEpoch) running.value = false
  }
}

async function refreshSelectedRun(): Promise<void> {
  if (!selectedRunId.value) return
  runError.value = ''
  try {
    const latest = await getReplyReadinessRun(selectedRunId.value)
    if (latest.store_code !== scope.store_code || latest.product_id !== scope.product_id
      || latest.sku_id !== (scope.sku_id || null)) {
      runError.value = '运行范围与当前选择不一致，已拒绝显示。'
      return
    }
    replaceRun(latest)
  } catch (reason: unknown) {
    runError.value = apiErrorMessage(reason)
  }
}

async function compareRuns(): Promise<void> {
  if (!selectedRun.value || !baselineRunId.value) return
  comparisonError.value = ''
  try {
    comparison.value = await compareReplyReadinessRuns(selectedRun.value.run_id, baselineRunId.value)
  } catch (reason: unknown) {
    comparison.value = null
    comparisonError.value = apiErrorMessage(reason)
  }
}

async function runPublishedDebug(): Promise<void> {
  const customerMessage = replyReadinessDebugState.customerMessage.trim()
  if (!scopeReady.value || !customerMessage || debugRunning.value) return
  const epoch = ++debugRequestEpoch
  const requestScope = {
    store_code: scope.store_code,
    product_id: scope.product_id,
    sku_id: scope.sku_id,
  }
  debugRunning.value = true
  debugError.value = ''
  rememberDebugScope()
  try {
    const result = await debugPublishedReply({
      store_code: requestScope.store_code,
      product_id: requestScope.product_id,
      sku_id: requestScope.sku_id || undefined,
      customer_message: customerMessage,
    })
    if (
      epoch !== debugRequestEpoch
      || requestScope.store_code !== scope.store_code
      || requestScope.product_id !== scope.product_id
      || requestScope.sku_id !== scope.sku_id
      || customerMessage !== replyReadinessDebugState.customerMessage.trim()
    ) return
    replyReadinessDebugState.previousResult = replyReadinessDebugState.latestResult
    replyReadinessDebugState.latestResult = result
    replyReadinessDebugState.latestMessage = customerMessage
  } catch (reason: unknown) {
    if (epoch === debugRequestEpoch) debugError.value = apiErrorMessage(reason)
  } finally {
    if (epoch === debugRequestEpoch) debugRunning.value = false
  }
}

function debugVersionSummary(result: ReplyReadinessPublishedDebugResult): string {
  if (!result.dependency_usage.knowledge) return '本次未使用RAG知识'
  return result.knowledge_publication_fingerprint
    ? `本次基于已发布知识 ${result.knowledge_publication_fingerprint.slice(0, 12)}…`
    : `知识状态：${result.knowledge_publication_status}`
}

onMounted(async () => {
  try {
    const [overview, productPage] = await Promise.all([
      getProductKnowledgeOverview(),
      listProductKnowledgeProducts(),
    ])
    stores.value = overview.stores
    products.value = productPage.items
    const remembered = replyReadinessDebugState.tab === 'DEBUG'
      ? replyReadinessDebugState.scope
      : { store_code: '', product_id: '', sku_id: '' }
    const requestedStore = remembered.store_code
      || (typeof route.query.store === 'string' ? route.query.store : '')
    const requestedProduct = remembered.product_id
      || (typeof route.query.product === 'string' ? route.query.product : '')
    const requestedSku = remembered.sku_id
      || (typeof route.query.sku === 'string' ? route.query.sku : '')
    const requestedMaterial = typeof route.query.material_id === 'string' ? route.query.material_id : ''
    const requestedRevision = Number(route.query.material_revision || 0)
    if (requestedStore && stores.value.some((item) => item.technical_details.store_code === requestedStore)) {
      scope.store_code = requestedStore
    } else if (requestedStore) {
      routeNotice.value = '链接中的店铺不可用，请重新选择。'
    }
    const productMatchesStore = products.value.some((item) => (
      item.technical_details.product_id === requestedProduct
      && item.technical_details.store_code === scope.store_code
    ))
    if (requestedProduct && productMatchesStore) {
      scope.product_id = requestedProduct
      await loadProduct({
        requestedSku,
        requestedMaterialKey: requestedMaterial && requestedRevision > 0
          ? `${requestedMaterial}:${requestedRevision}`
          : '',
      })
    } else if (requestedProduct) {
      routeNotice.value = '链接中的商品不属于当前店铺，请重新选择。'
    }
  } catch (reason: unknown) {
    scopeError.value = apiErrorMessage(reason)
  } finally {
    initialLoading.value = false
  }
})

onBeforeUnmount(() => {
  invalidateDebugRequest()
  scopeLoadEpoch += 1
  stopPolling()
})
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">PDD 回答优化</p>
        <h1>商品回答风险池</h1>
        <p>既可以运行36题风险池，也可以按当前正式知识和规则调试一条真实问法。</p>
      </div>
      <RouterLink class="button secondary" to="/knowledge-review">知识审核队列</RouterLink>
    </div>

    <section class="safety-banner" aria-label="隔离评测安全边界">
      <strong>只读评测，不会发送</strong>
      <span>不发布知识、不写正式向量库、不写会话或运行账本、不授予自动发送权。</span>
      <span class="safety-flags" aria-label="不可用于生产且禁止自动发送">
        <b>不可用于生产</b><b>禁止自动发送</b>
        <code>production_usable=false · allow_auto_send=false</code>
      </span>
    </section>

    <nav class="workspace-tabs" aria-label="回答工作台模式" role="tablist">
      <button id="reply-pool-tab" type="button" role="tab" aria-controls="reply-pool-panel" :class="{ active: activeTab === 'POOL' }" :aria-selected="activeTab === 'POOL'" @click="selectTab('POOL')">36题风险池</button>
      <button id="reply-debug-tab" type="button" role="tab" aria-controls="reply-debug-panel" :class="{ active: activeTab === 'DEBUG' }" :aria-selected="activeTab === 'DEBUG'" @click="selectTab('DEBUG')">单条消息调试</button>
    </nav>

    <p v-if="routeNotice" class="notice" role="status">{{ routeNotice }}</p>
    <p v-if="scopeError" class="notice error" role="alert">{{ scopeError }}</p>
    <p v-if="initialLoading" class="notice" role="status">正在读取可用店铺和商品…</p>

    <section v-else class="card scope-card" aria-labelledby="scope-heading">
      <div class="section-title">
        <div><span class="step">1</span><div><h2 id="scope-heading">选择商品范围</h2><p>范围变化后会立即清空不兼容的结果。</p></div></div>
        <div v-if="selectedProduct" class="scope-summary">
          <span class="scope-chip">{{ selectedProduct.product_name }}<template v-if="selectedSku"> · {{ selectedSku.sku_name }}</template></span>
          <span :class="['source-badge', (selectedProduct.data_source || 'UNKNOWN').toLowerCase()]">{{ dataSourceLabel(selectedProduct.data_source || 'UNKNOWN') }}</span>
        </div>
      </div>
      <div class="controls">
        <label>店铺
          <select v-model="scope.store_code" @change="changeStore">
            <option value="">请选择店铺</option>
            <option v-for="store in stores" :key="store.technical_details.store_code || store.store_name" :value="store.technical_details.store_code || ''">{{ store.store_name }}</option>
          </select>
        </label>
        <label>商品
          <select v-model="scope.product_id" :disabled="!scope.store_code" @change="loadProduct()">
            <option value="">请选择商品</option>
            <option v-for="product in scopedProducts" :key="product.technical_details.product_id || product.product_name" :value="product.technical_details.product_id || ''">{{ product.product_name }}</option>
          </select>
        </label>
        <label>评测范围
          <select v-model="scope.sku_id" :disabled="!productDetail || scopeLoading" @change="changeSku">
            <option value="">整个商品（全部SKU通用事实）</option>
            <option v-for="sku in productDetail?.skus || []" :key="sku.technical_details.sku_id || sku.sku_name" :value="sku.technical_details.sku_id || ''">SKU：{{ sku.sku_name }}</option>
          </select>
        </label>
        <label v-if="activeTab === 'POOL'">本次草稿覆盖（可选）
          <select v-model="scope.material_key" :disabled="!scopeReady" @change="syncRoute">
            <option value="">不选择草稿覆盖</option>
            <option v-for="item in materialRevisions" :key="`${item.material_id}:${item.revision}`" :value="`${item.material_id}:${item.revision}`">
              {{ item.sku_id ? '精确SKU' : '商品级' }} · {{ displayStatus(item.recognition_summary.template_type || item.material_type) }} · {{ item.display_name }} · v{{ item.revision }} · {{ displayStatus(item.material_status) }} · {{ formatDate(item.updated_at) }}
            </option>
          </select>
        </label>
      </div>
      <p v-if="activeTab === 'POOL'" class="aggregation-note">系统会自动聚合当前商品最新已审核资料；SKU评测还会加入精确SKU资料。这里仅选择一份待审核修订覆盖同一资料的已审核版本。</p>
      <p v-else class="aggregation-note">单条调试直接调用当前正式A服务，只读使用已发布规则与知识；商品知识不可用时由真实Router按实际路由决定是否转人工。</p>
      <p v-if="selectedProduct?.data_source === 'TEST'" class="source-warning">当前为测试资料：允许调试，但不代表正式商品事实，也不会授予自动发送权。</p>
      <p v-if="scopeLoading" class="inline-status" role="status">正在切换范围并读取对应问题、资料和运行历史…</p>
      <p v-else-if="scopeReady && activeTab === 'POOL'" class="inline-status success">范围已就绪：{{ questionSet?.questions.length }} 个基线问题，{{ materialRevisions.length }} 个可用资料修订。</p>
      <p v-else-if="scopeReady" class="inline-status success">正式只读调试范围已就绪。</p>
      <button v-if="activeTab === 'POOL'" class="button run-button" type="button" :disabled="running || !scopeReady" @click="runEvaluation">
        {{ running ? '隔离评测进行中…' : '运行隔离评测' }}
      </button>
    </section>

    <template v-if="activeTab === 'POOL' && questionSet && scope.product_id">
      <section id="reply-pool-panel" class="card run-card" role="tabpanel" aria-labelledby="reply-pool-tab run-heading">
        <div class="section-title">
          <div><span class="step">2</span><div><h2 id="run-heading">选择评测结果</h2><p>只展示当前商品与SKU范围完全一致的历史。</p></div></div>
        </div>
        <div class="run-toolbar">
          <label>当前运行
            <select v-model="selectedRunId" :disabled="runs.length === 0">
              <option value="">{{ runs.length ? '请选择运行' : '当前范围暂无运行' }}</option>
              <option v-for="item in runs" :key="item.run_id" :value="item.run_id">
                {{ formatDate(item.requested_at) }} · {{ runStatusLabel(item.status) }} · {{ item.material_id ? `资料v${item.material_revision}` : '不附加草稿' }}
              </option>
            </select>
          </label>
          <button class="button secondary" type="button" :disabled="!selectedRunId" @click="refreshSelectedRun">刷新状态</button>
          <label>对比基准
            <select v-model="baselineRunId" :disabled="!selectedRun?.result">
              <option value="">请选择同范围运行</option>
              <option v-for="item in completedRuns" :key="item.run_id" :value="item.run_id">{{ formatDate(item.requested_at) }} · {{ item.material_id ? `资料v${item.material_revision}` : '无草稿' }}</option>
            </select>
          </label>
          <button class="button secondary" type="button" :disabled="!baselineRunId || !selectedRun?.result" @click="compareRuns">比较变化</button>
        </div>
        <p v-if="runMessage" class="inline-status" role="status">{{ runMessage }}</p>
        <details v-if="selectedRun" class="run-technical">
          <summary>运行技术信息</summary>
          <dl>
            <div><dt>运行编号</dt><dd>{{ selectedRun.run_id }}</dd></div>
            <div><dt>原始状态</dt><dd>{{ selectedRun.status }}</dd></div>
            <div><dt>冻结知识来源</dt><dd>{{ selectedRun.knowledge_source_count }} 份</dd></div>
            <div v-if="selectedRun.failure_code"><dt>失败码</dt><dd>{{ selectedRun.failure_code }}</dd></div>
          </dl>
        </details>
        <p v-if="runError" class="notice error" role="alert">{{ runError }}</p>
        <p v-if="comparisonError" class="notice error" role="alert">{{ comparisonError }}</p>
      </section>

      <section v-if="selectedRun?.result" class="summary-grid" aria-label="风险汇总">
        <button type="button" class="summary-card low" :class="{ active: riskFilter === 'LOW' }" :aria-pressed="riskFilter === 'LOW'" @click="riskFilter = riskFilter === 'LOW' ? '' : 'LOW'">
          <span>可直接回答</span><strong>{{ riskCounts.LOW }}</strong><small>低风险评测结论，不代表自动发送</small>
        </button>
        <button type="button" class="summary-card medium" :class="{ active: riskFilter === 'MEDIUM' }" :aria-pressed="riskFilter === 'MEDIUM'" @click="riskFilter = riskFilter === 'MEDIUM' ? '' : 'MEDIUM'">
          <span>需受控处理</span><strong>{{ riskCounts.MEDIUM }}</strong><small>使用审核话术或补充询问</small>
        </button>
        <button type="button" class="summary-card high" :class="{ active: riskFilter === 'HIGH' }" :aria-pressed="riskFilter === 'HIGH'" @click="riskFilter = riskFilter === 'HIGH' ? '' : 'HIGH'">
          <span>转人工 / 待补资料</span><strong>{{ riskCounts.HIGH }}</strong><small>优先处理这些问题</small>
        </button>
      </section>

      <section v-if="selectedRun?.result" class="card result-card" aria-labelledby="result-heading">
        <div class="section-title result-title">
          <div><span class="step">3</span><div><h2 id="result-heading">逐题结果</h2><p>默认按高风险优先排列，技术字段收在详情中。</p></div></div>
          <span class="result-count">显示 {{ visibleItems.length }} / {{ selectedRun.result.items.length }} 题</span>
        </div>
        <div class="filters" aria-label="问题筛选">
          <label class="search-field">搜索问题<input v-model.trim="questionSearch" type="search" placeholder="输入客户问法"></label>
          <label>问题分类<select v-model="categoryFilter"><option value="">全部分类</option><option v-for="category in categoryOptions" :key="category" :value="category">{{ categoryLabel(category) }}</option></select></label>
          <label>处理方式<select v-model="actionFilter"><option value="">全部方式</option><option v-for="[value, label] in actionOptions" :key="value" :value="value">{{ label }}</option></select></label>
          <label>风险<select v-model="riskFilter"><option value="">全部风险</option><option value="LOW">低风险</option><option value="MEDIUM">中风险</option><option value="HIGH">高风险</option></select></label>
          <button v-if="hasActiveFilters" class="button secondary clear-filters" type="button" @click="clearResultFilters">清除筛选</button>
        </div>

        <div v-if="visibleItems.length === 0" class="empty-state">
          <p>没有符合当前筛选的问题。</p>
          <button v-if="hasActiveFilters" class="button secondary" type="button" @click="clearResultFilters">清除全部筛选</button>
        </div>
        <div v-else class="desktop-results table-wrap">
          <table class="data-table">
            <caption>当前商品范围的逐题回答风险</caption>
            <thead><tr><th>客户问题</th><th>处理结论</th><th>回答预览</th><th>首要缺口</th><th><span class="sr-only">操作</span></th></tr></thead>
            <tbody>
              <template v-for="item in visibleItems" :key="item.question_id">
                <tr>
                  <td><strong>{{ itemQuestion(item) }}</strong><small>{{ categoryLabel(questionById.get(item.question_id)?.category || '') }}</small></td>
                  <td><span :class="['risk-pill', item.effective_risk.toLowerCase()]">{{ riskLabel(item.effective_risk) }}</span><small>{{ actionLabel(item.action) }}</small></td>
                  <td class="answer-cell">{{ item.answer_preview || '当前不生成回答，需人工处理。' }}</td>
                  <td>{{ primaryGap(item) }}</td>
                  <td class="row-actions"><RouterLink class="text-link" :to="{ path: '/knowledge-editor', query: supplementQuery(item) }">补充资料</RouterLink><button class="text-button" type="button" :aria-expanded="expandedItems.includes(item.question_id)" @click="toggleExpanded(item.question_id)">{{ expandedItems.includes(item.question_id) ? '收起' : '详情' }}</button></td>
                </tr>
                <tr v-if="expandedItems.includes(item.question_id)" class="detail-row">
                  <td colspan="5">
                    <div class="business-detail">
                      <p><strong>回答来源：</strong>{{ originLabel(item.origin) }}</p>
                      <p><strong>缺失资料：</strong>{{ item.missing_fact_keys.join('、') || '无' }}</p>
                      <p><strong>阻断原因：</strong>{{ item.blocker_codes.map(blockerLabel).join('；') || '无' }}</p>
                      <p><strong>禁止承诺命中：</strong>{{ item.prohibited_claim_hits.join('、') || '无' }}</p>
                    </div>
                    <details class="technical-details"><summary>查看技术信息</summary><dl><div><dt>问题ID</dt><dd>{{ item.question_id }}</dd></div><div><dt>动作 / 来源</dt><dd>{{ item.action }} / {{ item.origin }}</dd></div><div><dt>阻断码</dt><dd>{{ item.blocker_codes.join('、') || '无' }}</dd></div><div><dt>引用ID</dt><dd>{{ item.citation_ids.join('、') || '无' }}</dd></div><div><dt>回答哈希</dt><dd>{{ item.answer_sha256 }}</dd></div><div><dt>证据包哈希</dt><dd>{{ item.evidence_bundle_sha256 || '无' }}</dd></div></dl></details>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>

        <div v-if="visibleItems.length" class="mobile-results">
          <article v-for="item in visibleItems" :key="item.question_id" class="question-card">
            <div class="question-heading"><div><strong>{{ itemQuestion(item) }}</strong><small>{{ categoryLabel(questionById.get(item.question_id)?.category || '') }}</small></div><span :class="['risk-pill', item.effective_risk.toLowerCase()]">{{ riskLabel(item.effective_risk) }}</span></div>
            <p class="mobile-action">{{ actionLabel(item.action) }}</p>
            <p>{{ item.answer_preview || '当前不生成回答，需人工处理。' }}</p>
            <p class="gap-text">{{ primaryGap(item) }}</p>
            <RouterLink class="text-link" :to="{ path: '/knowledge-editor', query: supplementQuery(item) }">补充资料</RouterLink>
            <details><summary>查看原因与技术信息</summary><p>来源：{{ originLabel(item.origin) }}</p><p>缺失：{{ item.missing_fact_keys.join('、') || '无' }}</p><p>阻断：{{ item.blocker_codes.map(blockerLabel).join('；') || '无' }}</p><code>{{ item.question_id }} · {{ item.action }} · {{ item.origin }}</code></details>
          </article>
        </div>
      </section>

      <p v-else-if="selectedRun?.status === 'FAILED'" class="notice error">本次运行失败，没有复用旧结果。请检查当前资料或稍后重新运行。</p>
      <p v-else-if="selectedRun" class="notice">{{ runStatusLabel(selectedRun.status) }}，尚无可展示的新结果。</p>
      <p v-else class="empty-state standalone">当前范围尚无评测结果。可以选择知识修订后运行一次隔离评测。</p>

      <section v-if="comparison" class="card comparison" aria-labelledby="comparison-heading">
        <div class="section-title"><div><span class="step">4</span><div><h2 id="comparison-heading">运行变化</h2><p>只比较同一商品和SKU范围。</p></div></div></div>
        <p v-if="comparison.changed_items.length === 0" class="empty-state">两次运行的风险、回答、缺口和证据均无变化。</p>
        <template v-else>
          <section v-for="group in COMPARISON_ORDER" :key="group" v-show="comparisonGroups[group].length" :class="['comparison-group', group.toLowerCase()]">
            <h3>{{ group === 'WORSE' ? '风险恶化' : group === 'IMPROVED' ? '风险改善' : group === 'ANSWER_CHANGED' ? '回答发生变化' : '证据或缺口变化' }}（{{ comparisonGroups[group].length }}）</h3>
            <article v-for="item in comparisonGroups[group]" :key="item.question_id">
              <strong>{{ questionLabel(item.question_id) }}</strong>
              <p>风险：{{ item.before_risk ? riskLabel(item.before_risk) : '新增问题' }} → {{ riskLabel(item.after_risk) }}</p>
              <p>缺失：{{ item.missing_fact_keys_before.join('、') || '无' }} → {{ item.missing_fact_keys_after.join('、') || '无' }}</p>
              <p>阻断：{{ item.blocker_codes_before.map(blockerLabel).join('；') || '无' }} → {{ item.blocker_codes_after.map(blockerLabel).join('；') || '无' }}</p>
            </article>
          </section>
        </template>
      </section>

      <section class="actions card">
        <div><strong>下一步</strong><p>补资料后回到这里复跑；保存草稿不会自动审核或发布。</p></div>
        <RouterLink class="button secondary" :to="{ path: '/knowledge-editor', query: { store: scope.store_code, product: scope.product_id, ...(scope.sku_id ? { sku: scope.sku_id } : {}), ...materialReference() } }">创建知识新修订</RouterLink>
        <RouterLink class="button secondary" :to="{ path: '/knowledge-review', query: { store: scope.store_code, product: scope.product_id } }">进入审核队列</RouterLink>
        <RouterLink class="button secondary" to="/knowledge-center">查看知识治理</RouterLink>
      </section>
    </template>

    <section v-else-if="activeTab === 'DEBUG' && scope.product_id" id="reply-debug-panel" class="card debug-card" role="tabpanel" aria-labelledby="reply-debug-tab debug-heading">
      <div class="section-title">
        <div><span class="step">2</span><div><h2 id="debug-heading">模拟一条客户消息</h2><p>使用当前正式ReplyRouter、已发布固定规则、Published RAG、Quality Gate与Evidence。</p></div></div>
      </div>
      <label class="debug-message">客户原话
        <textarea v-model="replyReadinessDebugState.customerMessage" maxlength="2000" rows="5" placeholder="例如：这个商品拼好后多大？" @input="invalidateDebugRequest"></textarea>
        <small>{{ replyReadinessDebugState.customerMessage.length }} / 2000 字</small>
      </label>
      <div class="debug-actions">
        <button class="button" type="button" :disabled="debugRunning || !scopeReady || !replyReadinessDebugState.customerMessage.trim()" @click="runPublishedDebug">
          {{ debugRunning ? '正在调用正式只读Router…' : '运行单条调试' }}
        </button>
        <span>不会创建风险池运行、客户会话、审批、执行或发送记录。</span>
      </div>
      <p v-if="debugError" class="notice error" role="alert">{{ debugError }}</p>

      <article v-if="debugResult" class="debug-result" aria-live="polite">
        <div class="debug-result-heading">
          <div><p class="eyebrow">本次只读结果</p><h3>{{ debugResult.status === 'FAILED' ? '运行版本发生阻断性变化' : debugItem ? '已完成回答判断' : '需要人工处理' }}</h3></div>
          <span v-if="debugItem" :class="['risk-pill', debugItem.effective_risk.toLowerCase()]">{{ riskLabel(debugItem.effective_risk) }}</span>
        </div>
        <template v-if="debugItem">
          <dl class="debug-business">
            <div><dt>回答</dt><dd>{{ debugItem.answer_preview || '本次不生成可直接发送的回答。' }}</dd></div>
            <div><dt>处理方式</dt><dd>{{ actionLabel(debugItem.action) }}</dd></div>
            <div><dt>回答来源</dt><dd>{{ originLabel(debugItem.origin) }}</dd></div>
            <div><dt>质量门</dt><dd>{{ debugResult.quality_gate_status === 'PASS' ? '通过' : '转人工' }}</dd></div>
            <div><dt>缺失资料</dt><dd>{{ debugItem.missing_fact_keys.join('、') || '无' }}</dd></div>
            <div><dt>阻断原因</dt><dd>{{ debugItem.blocker_codes.map(blockerLabel).join('；') || '无' }}</dd></div>
          </dl>
          <p class="version-summary">{{ debugVersionSummary(debugResult) }} · 评测时间 {{ formatDate(debugResult.evaluated_at) }}</p>
          <p v-if="previousDebugItem" class="debug-comparison">与上次调试相比：风险 {{ riskLabel(previousDebugItem.effective_risk) }} → {{ riskLabel(debugItem.effective_risk) }}；回答{{ previousDebugItem.answer_sha256 === debugItem.answer_sha256 ? '未变化' : '已变化' }}。</p>
          <RouterLink class="button secondary" :to="{ path: '/knowledge-editor', query: debugSupplementQuery(debugItem) }">去知识编辑器补充资料</RouterLink>
        </template>
        <p v-else class="notice error">{{ blockerLabel(debugResult.failure_code || 'PRODUCTION_RUNTIME_VERSION_DRIFT') }}：{{ debugResult.drifted_dependencies.map(dependencyLabel).join('、') || '依赖集合无法可靠确认' }}。</p>
        <details class="technical-details debug-technical">
          <summary>生产版本与依赖详情</summary>
          <dl>
            <div><dt>实际依赖</dt><dd>{{ Object.entries(debugResult.dependency_usage).filter(([, used]) => used).map(([name]) => dependencyLabel(name)).join('、') || '无' }}</dd></div>
            <div><dt>Router</dt><dd>{{ debugResult.router_build_fingerprint }}</dd></div>
            <div><dt>ReplyRule</dt><dd>{{ debugResult.reply_rule_snapshot_fingerprint || '本次未使用或无已发布快照' }}</dd></div>
            <div><dt>固定规则</dt><dd>{{ debugResult.rule_references.join('、') || '无' }}</dd></div>
            <div><dt>RAG Collection</dt><dd>{{ debugResult.rag_collection_identity || '本次未使用或不可用' }}</dd></div>
            <div><dt>Knowledge</dt><dd>{{ debugResult.knowledge_publication_fingerprint || '本次未使用或不可用' }}（{{ debugResult.knowledge_publication_status }}）</dd></div>
            <div><dt>Model Config</dt><dd>{{ debugResult.model_config_identity }}</dd></div>
            <div><dt>诊断变化</dt><dd>{{ debugResult.diagnostic_changes.map((item) => `${dependencyLabel(item.dependency)}：${item.before || '无'} → ${item.after || '无'}`).join('；') || '无' }}</dd></div>
            <div><dt>调试编号</dt><dd>{{ debugResult.run_id }}</dd></div>
            <div><dt>结果哈希</dt><dd>{{ debugResult.result_sha256 }}</dd></div>
          </dl>
        </details>
      </article>
      <p v-else class="empty-state standalone">输入一条客户原话后运行，即可看到当前正式规则和知识会如何回答。结果仅在当前浏览器进程内保留。</p>
    </section>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.safety-banner { display: grid; grid-template-columns: auto minmax(260px, 1fr) auto; align-items: center; gap: 8px 14px; margin-bottom: 18px; padding: 13px 16px; border: 1px solid #edd18d; border-radius: 12px; color: #6d4d08; background: #fff9e8; }
.safety-banner strong { color: #5d4104; }.safety-flags { display: grid; grid-template-columns: repeat(2, max-content); justify-content: end; gap: 4px 6px; }.safety-flags b { padding: 4px 7px; border-radius: 999px; color: #754f00; background: #f8e7b6; font-size: 11px; }.safety-banner code { grid-column: 1 / -1; color: #7b5a12; font-size: 11px; text-align: right; }
.workspace-tabs { display: flex; gap: 8px; margin: 0 0 18px; padding: 5px; width: max-content; border: 1px solid #d8e2ef; border-radius: 12px; background: #f6f8fb; }.workspace-tabs button { min-height: 38px; padding: 8px 16px; border: 0; border-radius: 8px; color: #526279; background: transparent; font: inherit; font-weight: 800; cursor: pointer; }.workspace-tabs button.active { color: #fff; background: #315f9f; box-shadow: 0 4px 12px rgb(49 95 159 / 20%); }.workspace-tabs button:focus-visible { outline: 3px solid rgb(59 130 246 / 28%); }
.scope-card, .run-card { margin-bottom: 18px; }.section-title { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 16px; }.section-title > div { display: flex; align-items: center; gap: 11px; }.section-title h2, .section-title p { margin: 0; }.section-title h2 { color: #172554; font-size: 19px; }.section-title p { margin-top: 4px; color: #64748b; font-size: 13px; }.step { display: grid; flex: 0 0 30px; width: 30px; height: 30px; place-items: center; border-radius: 10px; color: #fff; background: #315f9f; font-size: 13px; font-weight: 800; }.scope-chip, .result-count { padding: 6px 10px; border-radius: 999px; color: #2d5a93; background: #edf4ff; font-size: 12px; font-weight: 700; }
.scope-summary { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 7px; }.source-badge { padding: 6px 9px; border-radius: 999px; color: #385675; background: #edf2f7; font-size: 12px; font-weight: 800; }.source-badge.initial_import { color: #17633a; background: #e8f7ee; }.source-badge.pilot { color: #285493; background: #edf4ff; }.source-badge.test { color: #8a4d00; background: #fff2da; }.source-warning { margin: 12px 0 0; padding: 10px 12px; border: 1px solid #edcf8d; border-radius: 8px; color: #7c4c05; background: #fff9e8; font-size: 13px; }
.controls, .run-toolbar, .filters { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; }.controls label, .run-toolbar label, .filters label { display: grid; min-width: 190px; gap: 6px; color: #526279; font-size: 13px; }.controls label { flex: 1 1 210px; }.controls select, .run-toolbar select, .filters select, .filters input { width: 100%; min-height: 42px; padding: 8px 10px; border: 1px solid #cbd7e6; border-radius: 8px; background: #fff; font: inherit; }.controls select:focus-visible, .run-toolbar select:focus-visible, .filters select:focus-visible, .filters input:focus-visible { outline: 3px solid rgb(59 130 246 / 24%); border-color: #4f7fc1; }.run-button { margin-top: 15px; }.inline-status { margin: 14px 0 0; padding: 10px 12px; border-radius: 8px; color: #385675; background: #f1f6fc; font-size: 13px; }.inline-status.success { color: #226346; background: #edf8f2; }
.clear-filters { min-height: 42px; }
.aggregation-note { margin: 12px 0 0; color: #526279; font-size: 13px; line-height: 1.55; }
.run-technical { margin-top: 10px; color: #64748b; font-size: 12px; }.run-technical summary { width: max-content; cursor: pointer; color: #3e5f86; font-weight: 700; }.run-technical dl { display: grid; gap: 5px; margin: 9px 0 0; }.run-technical dl div { display: grid; grid-template-columns: 76px minmax(0, 1fr); gap: 10px; }.run-technical dt { color: #718096; }.run-technical dd { overflow-wrap: anywhere; margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }.summary-card { display: grid; gap: 5px; padding: 16px; border: 1px solid #dce5f1; border-left-width: 4px; border-radius: 11px; text-align: left; background: #fff; cursor: pointer; }.summary-card:hover, .summary-card.active { box-shadow: 0 8px 20px rgb(30 52 86 / 12%); transform: translateY(-1px); }.summary-card:focus-visible { outline: 3px solid rgb(59 130 246 / 28%); }.summary-card span, .summary-card small { color: #64748b; font-size: 13px; }.summary-card strong { color: #172554; font-size: 28px; }.summary-card.low { border-left-color: #2f8f5b; }.summary-card.medium { border-left-color: #d5962e; }.summary-card.high { border-left-color: #c74b4b; }
.result-card { padding: 0; overflow: hidden; }.result-title { padding: 20px 20px 0; }.filters { padding: 0 20px 18px; border-bottom: 1px solid #e3e9f1; }.filters .search-field { flex: 1 1 240px; }.table-wrap { overflow: auto; }.data-table caption { position: absolute; overflow: hidden; width: 1px; height: 1px; clip: rect(0 0 0 0); }.data-table td { min-width: 130px; line-height: 1.5; }.data-table td:first-child { min-width: 190px; }.data-table .answer-cell { min-width: 260px; }.data-table small { display: block; margin-top: 5px; color: #64748b; }.risk-pill { display: inline-flex; width: max-content; padding: 4px 8px; border-radius: 999px; font-size: 12px; font-weight: 800; }.risk-pill.low { color: #17633a; background: #e8f7ee; }.risk-pill.medium { color: #8a4d00; background: #fff2da; }.risk-pill.high { color: #9b2929; background: #fff0f0; }.text-button { padding: 5px 8px; border: 0; color: #285493; background: transparent; font: inherit; font-weight: 700; cursor: pointer; }.text-button:hover { text-decoration: underline; }.detail-row td { padding: 0 16px 18px; background: #f8fafc; }.business-detail { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px 18px; padding: 14px 0; }.business-detail p { margin: 0; }.technical-details { border-top: 1px solid #dce5ef; padding-top: 11px; color: #586a82; }.technical-details summary { cursor: pointer; font-weight: 700; }.technical-details dl { display: grid; gap: 8px; }.technical-details dl div { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 10px; }.technical-details dt { color: #718096; }.technical-details dd { overflow-wrap: anywhere; margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.row-actions { white-space: nowrap; }.text-link { display: inline-block; padding: 5px 8px; color: #285493; font-weight: 700; text-decoration: none; }.text-link:hover { text-decoration: underline; }
.empty-state { margin: 20px; padding: 24px; border: 1px dashed #b9c9de; border-radius: 12px; color: #526279; text-align: center; background: #f8fbff; }.empty-state p { margin: 0 0 12px; }.empty-state p:last-child { margin-bottom: 0; }.empty-state.standalone { margin: 0 0 18px; }.mobile-results { display: none; }.question-card { padding: 16px; border-top: 1px solid #e3e9f1; }.question-heading { display: flex; align-items: start; justify-content: space-between; gap: 12px; }.question-heading strong, .question-heading small { display: block; }.question-heading small { margin-top: 4px; color: #64748b; }.question-card p { line-height: 1.55; }.mobile-action { color: #315f9f; font-weight: 700; }.gap-text { color: #7c4c05; }.question-card details { color: #586a82; }.question-card summary { cursor: pointer; font-weight: 700; }.question-card code { overflow-wrap: anywhere; font-size: 11px; }
.comparison { margin-top: 18px; }.comparison-group { margin-top: 16px; padding: 14px; border-left: 4px solid #8ca0b8; border-radius: 9px; background: #f8fafc; }.comparison-group.worse { border-color: #c74b4b; background: #fff7f7; }.comparison-group.improved { border-color: #2f8f5b; background: #f3fbf6; }.comparison-group.answer_changed { border-color: #3f72b5; background: #f5f9ff; }.comparison-group h3 { margin: 0 0 10px; font-size: 15px; }.comparison-group article { padding: 10px 0; border-top: 1px solid rgb(120 140 165 / 20%); }.comparison-group article p { margin: 4px 0 0; color: #526279; font-size: 13px; }
.actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 18px; }.actions > div { flex: 1 1 260px; }.actions p { margin: 4px 0 0; color: #64748b; font-size: 13px; }.sr-only { position: absolute; overflow: hidden; width: 1px; height: 1px; clip: rect(0 0 0 0); white-space: nowrap; }
.debug-card { margin-bottom: 18px; }.debug-message { display: grid; gap: 7px; color: #526279; font-size: 13px; font-weight: 700; }.debug-message textarea { min-height: 128px; padding: 12px; border: 1px solid #cbd7e6; border-radius: 10px; resize: vertical; font: inherit; line-height: 1.6; }.debug-message textarea:focus-visible { outline: 3px solid rgb(59 130 246 / 24%); border-color: #4f7fc1; }.debug-message small { justify-self: end; color: #718096; font-weight: 400; }.debug-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-top: 14px; }.debug-actions span { color: #64748b; font-size: 13px; }.debug-result { margin-top: 18px; padding: 18px; border: 1px solid #d9e4f1; border-radius: 12px; background: #f8fbff; }.debug-result-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }.debug-result-heading h3 { margin: 0; color: #172554; }.debug-business { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 18px; margin: 18px 0; }.debug-business div:first-child { grid-column: 1 / -1; }.debug-business dt { color: #64748b; font-size: 12px; }.debug-business dd { margin: 4px 0 0; color: #263b55; line-height: 1.6; }.version-summary, .debug-comparison { padding: 10px 12px; border-radius: 8px; color: #385675; background: #edf4ff; font-size: 13px; }.debug-comparison { background: #f1f5f9; }.debug-technical { margin-top: 16px; }.debug-technical dl div { grid-template-columns: 130px minmax(0, 1fr); }
@media (max-width: 900px) { .summary-grid { grid-template-columns: 1fr; }.business-detail { grid-template-columns: 1fr; }.section-title { align-items: flex-start; }.scope-chip { max-width: 45%; } }
@media (max-width: 680px) { .desktop-results { display: none; }.mobile-results { display: block; }.section-title { display: grid; }.section-title > div { align-items: flex-start; }.scope-chip { max-width: 100%; width: max-content; }.controls label, .run-toolbar label, .filters label { width: 100%; }.controls select, .run-toolbar select, .filters select, .filters input { width: 100%; }.run-button { width: 100%; }.safety-banner { grid-template-columns: 1fr; align-items: flex-start; }.safety-flags { justify-content: start; }.safety-banner code { text-align: left; }.workspace-tabs { display: grid; grid-template-columns: 1fr 1fr; width: 100%; }.result-count { margin-left: 41px; }.actions { align-items: stretch; flex-direction: column; }.actions .button { width: 100%; }.debug-business { grid-template-columns: 1fr; }.debug-business div:first-child { grid-column: auto; }.debug-actions { align-items: stretch; flex-direction: column; }.debug-actions .button { width: 100%; } }
</style>
