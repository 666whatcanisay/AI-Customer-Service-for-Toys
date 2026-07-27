<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  apiErrorMessage,
  getAdminOperationsToday,
  getHealth,
  listPilotStores,
  listAiModules,
  type AdminOperationsToday,
} from '../api/client'

type Availability = 'loading' | 'ready' | 'unavailable'

const operations = ref<AdminOperationsToday | null>(null)
const platformState = ref<Availability>('loading')
const aiState = ref<Availability>('loading')
const isLoading = ref(true)
const error = ref('')
const pilotStoreState = ref<'loading' | 'ready' | 'unavailable'>('loading')
const pilotStores = ref<{ total: number; needsProduct: number; needsKnowledge: number; observable: number }>({ total: 0, needsProduct: 0, needsKnowledge: 0, observable: 0 })

function zeroAware(value: number | null, suffix = ''): string {
  if (value === null) return '待启用'
  return value === 0 ? '样本不足' : `${value}${suffix}`
}

function shortTime(value: string | null): string {
  if (!value) return '暂无导入记录'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short', hour12: false }).format(new Date(value))
}

const serviceText = computed(() => {
  const platform = ({ loading: '检测中', ready: '平台可用', unavailable: '平台待连接' })[platformState.value]
  const ai = ({ loading: '检测中', ready: 'AI 可用', unavailable: 'AI 待连接' })[aiState.value]
  return `${platform} · ${ai}`
})
const aiUsageDetail = computed(() => {
  const today = operations.value?.today
  if (!today || today.ai_request_count === 0) return '当前统计窗口没有 AI 使用样本'
  return `采用率 ${(today.adoption_rate * 100).toFixed(1)}%，直接采用 ${today.direct_adoption_count}，编辑采用 ${today.edited_adoption_count}`
})
const knowledgeReady = computed(() => {
  const knowledge = operations.value?.knowledge
  if (!knowledge) return false
  return knowledge.store_count + knowledge.product_count + knowledge.sku_count + knowledge.faq_count + knowledge.safety_rule_count > 0
})
const dashboardCards = computed(() => {
  const today = operations.value?.today
  const knowledge = operations.value?.knowledge
  return [
    { label: '今日 AI 使用', value: zeroAware(today?.ai_request_count ?? null, ' 次'), detail: aiUsageDetail.value, to: '/customer-efficiency' },
    { label: '今日案例', value: zeroAware(today?.experience_case_submission_count ?? null, ' 件'), detail: '按客服经验案例创建时间统计', to: '/experience-cases' },
    { label: '今日问题', value: zeroAware(today?.ai_feedback_submission_count ?? null, ' 个'), detail: `已完成分析 ${zeroAware(today?.completed_ai_analysis_count ?? null, ' 个')}`, to: '/ai-feedback-optimization-pool' },
    { label: '知识状态', value: knowledgeReady.value ? '已连接' : '待启用', detail: knowledge ? `${knowledge.store_count} 店铺 · ${knowledge.product_count} 商品 · ${knowledge.faq_count} FAQ` : '知识资产统计尚未连接', to: '/imports/new' },
    { label: '服务状态', value: serviceText.value, detail: '平台健康检查与 AI 能力目录实时读取', to: '/system-status' },
  ]
})

const windowLabel = computed(() => {
  const today = operations.value?.today
  return today ? `统计窗口（UTC）：${shortTime(today.window_start)} 至 ${shortTime(today.window_end)}` : '统计窗口：待启用'
})

async function load(): Promise<void> {
  isLoading.value = true
  error.value = ''
  const [operationsResult, healthResult, aiResult, pilotStoresResult] = await Promise.allSettled([
    getAdminOperationsToday(),
    getHealth(),
    listAiModules(),
    listPilotStores(),
  ])
  operations.value = operationsResult.status === 'fulfilled' ? operationsResult.value : null
  platformState.value = healthResult.status === 'fulfilled' ? 'ready' : 'unavailable'
  aiState.value = aiResult.status === 'fulfilled' ? 'ready' : 'unavailable'
  if (pilotStoresResult.status === 'fulfilled') {
    pilotStoreState.value = 'ready'
    const items = pilotStoresResult.value.items
    pilotStores.value = {
      total: pilotStoresResult.value.total,
      needsProduct: items.filter((item) => item.setup_status === 'NEEDS_PRODUCT_IMPORT').length,
      needsKnowledge: items.filter((item) => item.setup_status === 'NEEDS_KNOWLEDGE').length,
      observable: items.filter((item) => item.setup_status === 'OBSERVABLE').length,
    }
  } else {
    pilotStoreState.value = 'unavailable'
  }
  if (operationsResult.status === 'rejected') error.value = apiErrorMessage(operationsResult.reason)
  isLoading.value = false
}

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <h1>AI 运营中心</h1>
        <p>打开后快速了解今日 AI 使用、客服反馈、案例、知识与服务状态。所有数字均来自当前 C 平台接口。</p>
      </div>
      <button class="button secondary" type="button" @click="load">刷新数据</button>
    </div>

    <p class="notice trial-note">当前数据用于测试/试运行观察，不是正式运营报表。{{ windowLabel }}</p>
    <p v-if="error" class="notice error" role="alert">运营概览待启用：{{ error }}。服务状态仍会独立展示。</p>

    <section class="dashboard-grid" aria-label="今日运营状态">
      <RouterLink v-for="card in dashboardCards" :key="card.label" class="status-card" :to="card.to">
        <span>{{ card.label }}</span>
        <strong>{{ isLoading ? '读取中' : card.value }}</strong>
        <small>{{ card.detail }}</small>
      </RouterLink>
    </section>

    <section class="operations-grid">
      <article class="card work-card">
        <div class="section-heading"><div><h2>今日待办</h2><p>优先处理会阻塞客服经验沉淀和 AI 分析的事项。</p></div></div>
        <div class="work-list">
          <RouterLink to="/experience-cases"><span>待审核经验案例</span><strong>{{ zeroAware(operations?.work_queue.pending_experience_review_count ?? null, ' 件') }}</strong><small>进入经验库审核</small></RouterLink>
          <RouterLink to="/ai-feedback-optimization-pool"><span>待分析 AI 问题</span><strong>{{ zeroAware(operations?.work_queue.pending_ai_analysis_count ?? null, ' 个') }}</strong><small>查看已完成分析证据</small></RouterLink>
          <RouterLink to="/conflicts"><span>开放知识冲突</span><strong>{{ zeroAware(operations?.work_queue.open_knowledge_conflict_count ?? null, ' 项') }}</strong><small>核对商品知识来源</small></RouterLink>
        </div>
      </article>

      <article class="card knowledge-card">
        <div class="section-heading"><div><h2>商品知识状态</h2><p>当前平台保存的知识资产；维护通过受控导入流程进行。</p></div><RouterLink to="/imports/new">维护知识</RouterLink></div>
        <div v-if="operations" class="knowledge-metrics">
          <div><span>店铺</span><strong>{{ operations.knowledge.store_count }}</strong></div>
          <div><span>商品</span><strong>{{ operations.knowledge.product_count }}</strong></div>
          <div><span>SKU</span><strong>{{ operations.knowledge.sku_count }}</strong></div>
          <div><span>FAQ</span><strong>{{ operations.knowledge.faq_count }}</strong></div>
          <div><span>安全规则</span><strong>{{ operations.knowledge.safety_rule_count }}</strong></div>
        </div>
        <p v-else class="notice compact">待启用：未读取到知识资产统计。</p>
        <p v-if="operations" class="subtle">最近导入：{{ shortTime(operations.knowledge.recent_imported_at) }}</p>
      </article>
    </section>

    <section class="card multi-store-card">
      <div class="section-heading"><div><h2>多店铺准备状态</h2><p>试运行店铺遵循创建、目标绑定导入、知识维护、观察的受控流程。</p></div><RouterLink to="/store-center">进入店铺中心</RouterLink></div>
      <p v-if="pilotStoreState === 'unavailable'" class="notice compact">待启用：未读取到试运行店铺状态。</p>
      <div v-else class="store-summary"><div><span>试运行店铺</span><strong>{{ pilotStoreState === 'loading' ? '读取中' : pilotStores.total }}</strong></div><div><span>待导入商品</span><strong>{{ pilotStoreState === 'loading' ? '读取中' : pilotStores.needsProduct }}</strong></div><div><span>待维护知识</span><strong>{{ pilotStoreState === 'loading' ? '读取中' : pilotStores.needsKnowledge }}</strong></div><div><span>可观察</span><strong>{{ pilotStoreState === 'loading' ? '读取中' : pilotStores.observable }}</strong></div></div>
      <p class="subtle">单店 AI 使用待启用：现有效率事件是无店铺字段的全局汇总，不能据此推断单店指标。</p>
    </section>

    <section class="card operating-note">
      <h2>运营口径</h2>
      <p>“今日 AI 使用”仅统计无客服内容的效率事件；“今日案例”和“今日问题”按创建时间统计；“已完成分析”按分析证据写入时间统计。页面不展示员工排名、绩效评价、提示词修改、知识发布或业务自动执行。</p>
    </section>
  </main>
</template>

<style scoped>
.trial-note { margin-bottom: 20px; color: #76580e; background: #fff8df; }.dashboard-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 14px; }.status-card { display: grid; min-height: 151px; align-content: start; gap: 9px; padding: 18px; border: 1px solid #dfe7f2; border-radius: 13px; color: #475569; background: #fff; box-shadow: 0 9px 24px rgb(15 23 42 / 4%); text-decoration: none; transition: border-color .15s ease, transform .15s ease; }.status-card:hover { border-color: #86a8d6; transform: translateY(-1px); }.status-card strong { color: #172554; font-size: 21px; }.status-card small { color: #64748b; line-height: 1.45; }.operations-grid { display: grid; grid-template-columns: 1.1fr 1fr; gap: 18px; margin-top: 18px; }.section-heading { display: flex; justify-content: space-between; gap: 15px; }.section-heading h2, .operating-note h2 { margin: 0 0 4px; color: #172554; font-size: 18px; }.section-heading p, .subtle, .operating-note p { margin: 0; color: #64748b; font-size: 13px; line-height: 1.55; }.section-heading a { color: #285493; font-size: 13px; white-space: nowrap; }.work-list { display: grid; gap: 9px; margin-top: 17px; }.work-list a { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 4px 10px; padding: 11px; border-radius: 9px; color: inherit; background: #f6f8fc; text-decoration: none; }.work-list a:hover { background: #eef4ff; }.work-list span { color: #475569; font-size: 13px; }.work-list strong { grid-row: span 2; align-self: center; color: #172554; font-size: 20px; }.work-list small { color: #64748b; font-size: 12px; }.knowledge-metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 9px; margin-top: 18px; }.knowledge-metrics div, .store-summary div { padding: 11px; border-radius: 9px; background: #f6f8fc; }.knowledge-metrics span, .store-summary span { display: block; color: #64748b; font-size: 12px; }.knowledge-metrics strong, .store-summary strong { display: block; margin-top: 4px; color: #172554; font-size: 20px; }.subtle { margin-top: 13px; }.compact { margin: 18px 0 0; }.multi-store-card, .operating-note { margin-top: 18px; }.store-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 9px; margin-top: 18px; }.operating-note p { max-width: 900px; }@media (max-width: 1100px) { .dashboard-grid { grid-template-columns: repeat(3, 1fr); }.knowledge-metrics { grid-template-columns: repeat(3, 1fr); } }@media (max-width: 760px) { .dashboard-grid, .operations-grid { grid-template-columns: 1fr; }.knowledge-metrics, .store-summary { grid-template-columns: repeat(2, 1fr); } }
</style>
