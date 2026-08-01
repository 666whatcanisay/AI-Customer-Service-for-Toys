<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  apiErrorMessage,
  getAdminOverview,
  getAiControlCenterOverview,
  getHealth,
  getProductKnowledgeOverview,
  listAiProblems,
  listProductKnowledgeProducts,
  type AdminOverview,
  type AiControlCenterOverview,
  type ProductKnowledgeListItem,
  type ProductKnowledgeOverview,
} from '../api/client'

const overview = ref<AdminOverview | null>(null)
const knowledgeOverview = ref<ProductKnowledgeOverview | null>(null)
const products = ref<ProductKnowledgeListItem[] | null>(null)
const aiOverview = ref<AiControlCenterOverview | null>(null)
const newProblemTotal = ref<number | null>(null)
const loading = ref(false)
const overviewError = ref('')
const knowledgeError = ref('')
const problemError = ref('')
const aiError = ref('')
const platformAvailable = ref<'loading' | 'available' | 'unavailable'>('loading')
const platformError = ref('')

const openSuggestionCount = computed(() => {
  const suggestions = overview.value?.counts.suggestions
  return suggestions
    ? suggestions.submitted + suggestions.reviewing + suggestions.planned
    : null
})

const lifecycleTotal = computed(() => products.value?.length ?? null)
const approvedProductCount = computed(() => products.value
  ? products.value.filter((product) => product.data_status === 'APPROVED').length
  : null)
const customerEnabledCount = computed(() => products.value
  ? products.value.filter((product) => product.customer_service_status === 'ENABLED').length
  : null)
const aiPublishedCount = computed(() => products.value
  ? products.value.filter((product) => product.ai_knowledge.status === 'PUBLISHED').length
  : null)

const aiServiceSummary = computed(() => {
  const value = aiOverview.value
  if (!value) return '暂无法判断'
  if (value.service.ready === true && value.service.modelConfigured === true && value.service.status === 'RUNNING') return '正常'
  if (value.service.status === 'ERROR' || value.service.ready === false) return '需要关注'
  return '尚未就绪'
})

const aiKnowledgeSummary = computed(() => {
  const knowledge = aiOverview.value?.knowledge
  if (!knowledge) return '暂无法判断'
  if (knowledge.status !== 'AVAILABLE') return '当前不可检索'
  if (knowledge.queryableChunkCount === null) return '可检索，数量暂无法读取'
  return `${knowledge.queryableChunkCount} 条知识可检索`
})

const answerCapabilitySummary = computed(() => {
  const value = aiOverview.value
  if (!value) return '暂无法判断'
  if (
    value.service.ready === true
    && value.service.modelConfigured === true
    && value.service.status === 'RUNNING'
    && value.knowledge.status === 'AVAILABLE'
  ) return '正常'
  if (value.service.ready === false || value.service.status === 'ERROR' || value.knowledge.status !== 'AVAILABLE') return '需要关注'
  return '暂无法判断'
})

const aiAttentionSummary = computed(() => {
  const value = aiOverview.value
  if (!value) return '暂无法判断'
  const issues: string[] = []
  if (value.service.status !== 'RUNNING' || value.service.ready !== true) {
    issues.push(value.service.initializationError || 'AI服务尚未就绪')
  }
  if (value.service.modelConfigured === false) issues.push('回答模型尚未配置')
  if (value.knowledge.status !== 'AVAILABLE') issues.push('知识当前不可检索')
  if (value.runtime.lastErrorSummary) issues.push(value.runtime.lastErrorSummary)
  return issues.length ? issues.join('；') : '无'
})

function displayCount(value: number | null | undefined): string {
  return typeof value === 'number' ? String(value) : '暂无法读取'
}

function lifecycleValue(value: number | null): string {
  if (value === null || lifecycleTotal.value === null) return '暂无法读取'
  return `${value} / ${lifecycleTotal.value}`
}

async function load(): Promise<void> {
  if (loading.value) return
  loading.value = true
  overview.value = null
  knowledgeOverview.value = null
  products.value = null
  aiOverview.value = null
  newProblemTotal.value = null
  overviewError.value = ''
  knowledgeError.value = ''
  problemError.value = ''
  aiError.value = ''
  platformError.value = ''
  platformAvailable.value = 'loading'

  const knowledgeWorkspace = async () => {
    const [summary, productList] = await Promise.all([
      getProductKnowledgeOverview(),
      listProductKnowledgeProducts(),
    ])
    return { summary, products: productList.items }
  }

  const [overviewResult, healthResult, knowledgeResult, problemsResult, aiResult] = await Promise.allSettled([
    getAdminOverview(),
    getHealth(),
    knowledgeWorkspace(),
    listAiProblems({ status: 'NEW' }),
    getAiControlCenterOverview(),
  ])

  if (overviewResult.status === 'fulfilled') overview.value = overviewResult.value
  else overviewError.value = apiErrorMessage(overviewResult.reason)

  if (healthResult.status === 'fulfilled') platformAvailable.value = 'available'
  else {
    platformAvailable.value = 'unavailable'
    platformError.value = apiErrorMessage(healthResult.reason)
  }

  if (knowledgeResult.status === 'fulfilled') {
    knowledgeOverview.value = knowledgeResult.value.summary
    products.value = knowledgeResult.value.products
  } else knowledgeError.value = apiErrorMessage(knowledgeResult.reason)

  if (problemsResult.status === 'fulfilled') newProblemTotal.value = problemsResult.value.total
  else problemError.value = apiErrorMessage(problemsResult.reason)

  if (aiResult.status === 'fulfilled') aiOverview.value = aiResult.value
  else aiError.value = apiErrorMessage(aiResult.reason)

  loading.value = false
}

onMounted(() => { void load() })
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">AI客服平台 · 日常运营入口</p>
        <h1>运营工作台</h1>
        <p>先处理当前待办，再检查商品上线状态和 AI 可用情况。页面只展示现有接口能够证明的数据，不使用“今日”或虚构趋势。</p>
      </div>
      <button class="button secondary" type="button" :disabled="loading" @click="load">{{ loading ? '刷新中…' : '刷新工作台' }}</button>
    </div>

    <p v-if="loading" class="notice" role="status">正在读取当前运营状态…</p>
    <p class="notice warning">AI 只生成建议。客服发送前必须人工确认；系统不会自动发送消息、自动退款或修改订单。</p>

    <section class="workspace-section" aria-labelledby="current-work-title">
      <div class="section-heading">
        <div><p class="eyebrow">区域 1</p><h2 id="current-work-title">当前工作</h2></div>
        <span>只显示当前待处理和需要关注的事项</span>
      </div>
      <div class="current-grid">
        <RouterLink class="current-card primary" to="/knowledge-center">
          <span>待审核资料</span>
          <strong>{{ displayCount(knowledgeOverview?.stats.pending_review_count) }}</strong>
          <small v-if="knowledgeError" class="error-text">读取失败：{{ knowledgeError }}</small>
          <small v-else>商品资料尚待运营确认。</small>
        </RouterLink>
        <RouterLink class="current-card" to="/knowledge-gaps">
          <span>知识缺口</span>
          <strong>{{ displayCount(knowledgeOverview?.stats.gap_count) }}</strong>
          <small v-if="knowledgeError" class="error-text">读取失败：{{ knowledgeError }}</small>
          <small v-else>需要补充或核实的商品知识项。</small>
        </RouterLink>
        <RouterLink class="current-card" to="/ai-issues">
          <span>待处理 AI 问题</span>
          <strong>{{ displayCount(newProblemTotal) }}</strong>
          <small v-if="problemError" class="error-text">读取失败：{{ problemError }}</small>
          <small v-else>当前状态为“新问题”的客服反馈。</small>
        </RouterLink>
        <RouterLink class="current-card" to="/customer-operations">
          <span>未关闭运营建议</span>
          <strong>{{ displayCount(openSuggestionCount) }}</strong>
          <small v-if="overviewError" class="error-text">读取失败：{{ overviewError }}</small>
          <small v-else>已提交、处理中或已规划但尚未完成。</small>
        </RouterLink>
      </div>
    </section>

    <section class="workspace-section lifecycle-section" aria-labelledby="lifecycle-title">
      <div class="section-heading">
        <div><p class="eyebrow">区域 2</p><h2 id="lifecycle-title">商品生命周期</h2></div>
        <span v-if="overview">当前范围：{{ overview.counts.stores }} 个店铺 · {{ overview.counts.products }} 个商品</span>
        <span v-else>当前范围暂无法读取</span>
      </div>
      <p v-if="knowledgeError" class="notice error" role="alert">商品状态读取失败：{{ knowledgeError }}。以下数量不会以 0 代替失败。</p>
      <div v-else class="lifecycle-grid">
        <article><span>资料已审核</span><strong>{{ lifecycleValue(approvedProductCount) }}</strong><small>已完成人工审核 / 当前读取商品</small></article>
        <article><span>客服可用</span><strong>{{ lifecycleValue(customerEnabledCount) }}</strong><small>已进入客服商品目录 / 当前读取商品</small></article>
        <article><span>AI知识已发布</span><strong>{{ lifecycleValue(aiPublishedCount) }}</strong><small>已有可检索发布状态 / 当前读取商品</small></article>
      </div>
    </section>

    <section class="workspace-section" aria-labelledby="quick-actions-title">
      <div class="section-heading"><div><p class="eyebrow">区域 3</p><h2 id="quick-actions-title">快捷操作</h2></div><span>全部跳转到已有页面</span></div>
      <div class="quick-grid">
        <RouterLink class="quick-link primary" to="/knowledge-materials"><strong>上传商品资料</strong><span>进入三步上传与人工审核流程。</span></RouterLink>
        <RouterLink class="quick-link" to="/store-management"><strong>查看商品</strong><span>维护店铺、商品和客服使用状态。</span></RouterLink>
        <RouterLink class="quick-link" to="/knowledge-gaps"><strong>处理知识问题</strong><span>查看缺失内容和建议补充方向。</span></RouterLink>
        <RouterLink class="quick-link" to="/ai-capabilities"><strong>查看AI状态</strong><span>确认 AI 服务、知识和回答能力。</span></RouterLink>
      </div>
    </section>

    <section class="workspace-section ai-section" aria-labelledby="ai-status-title">
      <div class="section-heading"><div><p class="eyebrow">区域 4</p><h2 id="ai-status-title">AI状态</h2></div><RouterLink class="text-link" to="/ai-capabilities">查看完整状态</RouterLink></div>
      <p v-if="aiError" class="notice error" role="alert">AI状态读取失败：{{ aiError }}</p>
      <div v-else-if="aiOverview" class="ai-grid">
        <article><span>AI服务</span><strong>{{ aiServiceSummary }}</strong></article>
        <article><span>知识</span><strong>{{ aiKnowledgeSummary }}</strong></article>
        <article><span>回答能力</span><strong>{{ answerCapabilitySummary }}</strong></article>
        <article :class="{ attention: aiAttentionSummary !== '无' }"><span>需要关注</span><strong>{{ aiAttentionSummary }}</strong></article>
      </div>
      <p v-else class="notice">AI状态正在读取，尚未返回时不显示正常或零值。</p>
      <div class="platform-strip">
        <span>运营平台</span>
        <strong>{{ platformAvailable === 'available' ? '正常' : platformAvailable === 'loading' ? '检测中' : '需要关注' }}</strong>
        <small v-if="platformError">{{ platformError }}</small>
        <small v-else>平台状态来自 C 服务健康检查。</small>
      </div>
    </section>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.warning { margin-bottom: 22px; color: #75570a; background: #fff8df; }
.workspace-section { margin-top: 24px; }
.section-heading { display: flex; justify-content: space-between; gap: 18px; align-items: end; margin-bottom: 13px; }
.section-heading h2 { margin: 0; color: #172554; }
.section-heading > span { color: #718096; font-size: 13px; }
.current-grid, .quick-grid, .ai-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.current-card, .quick-link { display: grid; gap: 8px; min-height: 136px; padding: 18px; border: 1px solid #dbe4ef; border-radius: 13px; color: #25466f; background: #fff; text-decoration: none; }
.current-card.primary, .quick-link.primary { border-color: #92b5e8; background: linear-gradient(145deg, #f5f9ff, #fff); }
.current-card > span { color: #617087; font-size: 13px; }
.current-card strong { color: #172554; font-size: 28px; overflow-wrap: anywhere; }
.current-card small, .quick-link span { color: #617087; font-size: 13px; line-height: 1.55; }
.current-card .error-text { color: #a23d3d; }
.lifecycle-section { padding: 20px; border: 1px solid #dbe4ef; border-radius: 14px; background: #fff; }
.lifecycle-section .section-heading { margin-bottom: 16px; }
.lifecycle-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.lifecycle-grid article, .ai-grid article { display: grid; gap: 7px; padding: 16px; border-radius: 11px; background: #f6f9fd; }
.lifecycle-grid span, .lifecycle-grid small, .ai-grid span { color: #617087; font-size: 13px; }
.lifecycle-grid strong, .ai-grid strong { color: #172554; font-size: 20px; overflow-wrap: anywhere; }
.quick-link { min-height: 104px; }
.quick-link strong { color: #172554; }
.ai-section { padding: 20px; border: 1px solid #cbdcee; border-radius: 14px; background: #f8fbff; }
.ai-grid article { border: 1px solid #e0e8f2; background: #fff; }
.ai-grid article.attention { border-color: #efc98b; background: #fff9ed; }
.ai-grid article.attention strong { color: #8a580e; font-size: 15px; line-height: 1.5; }
.text-link { color: #285493; font-size: 13px; font-weight: 700; text-decoration: none; }
.platform-strip { display: grid; grid-template-columns: auto auto 1fr; gap: 10px; align-items: center; margin-top: 14px; padding-top: 14px; border-top: 1px solid #dbe4ef; }
.platform-strip span, .platform-strip small { color: #617087; font-size: 13px; }
.platform-strip strong { color: #217447; }
@media (max-width: 1050px) { .current-grid, .quick-grid, .ai-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 720px) { .lifecycle-grid { grid-template-columns: 1fr; }.section-heading { display: block; }.section-heading > span, .section-heading > .text-link { display: inline-block; margin-top: 6px; }.platform-strip { grid-template-columns: 1fr; gap: 4px; } }
@media (max-width: 520px) { .current-grid, .quick-grid, .ai-grid { grid-template-columns: 1fr; } }
</style>
