<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  apiErrorMessage,
  getAdminCustomerEfficiencySummary,
  getAdminOverview,
  getHealth,
  listAdminExperienceCases,
  listAiFeedbackAnalysisResults,
  listAiModules,
  type AdminOverview,
  type CustomerEfficiencySummary,
} from '../api/client'

type Availability = 'loading' | 'ready' | 'unavailable'

const overview = ref<AdminOverview | null>(null)
const efficiency = ref<CustomerEfficiencySummary | null>(null)
const experienceTotal = ref<number | null>(null)
const issueTotal = ref<number | null>(null)
const platformState = ref<Availability>('loading')
const aiState = ref<Availability>('loading')
const isLoading = ref(true)
const error = ref('')

function noSamples(value: number | null): string {
  if (value === null) return '待启用'
  return value === 0 ? '样本不足' : String(value)
}

const aiServiceText = computed(() => ({ loading: '检测中', ready: '可用', unavailable: '待启用' })[aiState.value])
const systemText = computed(() => ({ loading: '检测中', ready: '运行中', unavailable: '待启用' })[platformState.value])
const efficiencyText = computed(() => {
  if (!efficiency.value) return '待启用'
  return efficiency.value.ai_request_count === 0 ? '样本不足' : `${(efficiency.value.adoption_rate * 100).toFixed(1)}%`
})
const efficiencyDetail = computed(() => {
  if (!efficiency.value) return '效率摘要接口尚未连接'
  if (efficiency.value.ai_request_count === 0) return '当前统计窗口没有 AI 请求样本'
  return `采用率：直接采用与编辑采用占 AI 请求的比例；共 ${efficiency.value.ai_request_count} 次请求`
})
const dashboardCards = computed(() => [
  { label: '系统状态', value: systemText.value, detail: platformState.value === 'ready' ? '平台健康检查已通过' : '未读取到平台健康状态', to: '/system-status' },
  { label: 'AI 服务状态', value: aiServiceText.value, detail: aiState.value === 'ready' ? '已连接 AI 能力目录' : 'AI 能力目录尚未连接', to: '/ai-capabilities' },
  { label: '客服效率', value: efficiencyText.value, detail: efficiencyDetail.value, to: '/customer-efficiency' },
  { label: '案例数量', value: noSamples(experienceTotal.value), detail: experienceTotal.value === 0 ? '尚无客服经验案例样本' : '客服经验库中的真实记录数', to: '/experience-cases' },
  { label: 'AI 问题数量', value: noSamples(issueTotal.value), detail: issueTotal.value === 0 ? '尚无已完成分析的问题样本' : '已完成 AI 分析的问题记录数', to: '/ai-feedback-optimization-pool' },
])

async function load(): Promise<void> {
  isLoading.value = true
  error.value = ''
  const [overviewResult, healthResult, aiResult, efficiencyResult, casesResult, issuesResult] = await Promise.allSettled([
    getAdminOverview(),
    getHealth(),
    listAiModules(),
    getAdminCustomerEfficiencySummary(),
    listAdminExperienceCases({ page: 1, size: 1 }),
    listAiFeedbackAnalysisResults(),
  ])

  overview.value = overviewResult.status === 'fulfilled' ? overviewResult.value : null
  efficiency.value = efficiencyResult.status === 'fulfilled' ? efficiencyResult.value : null
  experienceTotal.value = casesResult.status === 'fulfilled' ? casesResult.value.total : null
  issueTotal.value = issuesResult.status === 'fulfilled' ? issuesResult.value.total : null
  platformState.value = healthResult.status === 'fulfilled' ? 'ready' : 'unavailable'
  aiState.value = aiResult.status === 'fulfilled' ? 'ready' : 'unavailable'
  if (overviewResult.status === 'rejected') error.value = apiErrorMessage(overviewResult.reason)
  isLoading.value = false
}

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <h1>AI 运营中心</h1>
        <p>汇集试运行期间可验证的系统、客服与 AI 观察数据。没有数据时保留真实状态，不补造运营指标。</p>
      </div>
      <button class="button secondary" type="button" @click="load">刷新数据</button>
    </div>

    <p class="notice trial-note">当前数据用于测试/试运行观察，不是正式运营报表。</p>
    <p v-if="error" class="notice error" role="alert">部分数据未读取：{{ error }}。其余已连接数据仍会展示。</p>

    <section class="dashboard-grid" aria-label="运营关键状态">
      <RouterLink v-for="card in dashboardCards" :key="card.label" class="status-card" :to="card.to">
        <span>{{ card.label }}</span>
        <strong>{{ isLoading ? '读取中' : card.value }}</strong>
        <small>{{ card.detail }}</small>
      </RouterLink>
    </section>

    <section class="lower-grid">
      <article class="card">
        <div class="section-heading"><div><h2>知识资产概览</h2><p>仅显示平台已保存的真实数据资产。</p></div><RouterLink to="/imports/new">维护知识</RouterLink></div>
        <div v-if="overview" class="knowledge-metrics">
          <div><span>店铺</span><strong>{{ overview.counts.stores }}</strong></div>
          <div><span>商品</span><strong>{{ overview.counts.products }}</strong></div>
          <div><span>SKU</span><strong>{{ overview.counts.skus }}</strong></div>
          <div><span>FAQ</span><strong>{{ overview.counts.faqs }}</strong></div>
          <div><span>安全规则</span><strong>{{ overview.counts.safety_rules }}</strong></div>
        </div>
        <p v-else class="notice compact">待启用：未读取到知识资产统计。</p>
        <p v-if="overview" class="subtle">最近导入：{{ overview.recent_imported_at || '暂无记录' }}</p>
      </article>

      <article class="card">
        <div class="section-heading"><div><h2>运营提醒</h2><p>来自现有平台统计，不包含客服原始对话。</p></div></div>
        <dl v-if="overview" class="reminders">
          <div><dt>待处理数据冲突</dt><dd>{{ overview.counts.conflicts }}</dd></div>
          <div><dt>待审核客户建议</dt><dd>{{ overview.counts.suggestions.submitted + overview.counts.suggestions.reviewing }}</dd></div>
          <div><dt>数据模式</dt><dd>{{ overview.test_data_mode ? '测试/试运行' : '非测试标记' }}</dd></div>
        </dl>
        <p v-else class="notice compact">待启用：运营提醒依赖平台概览数据。</p>
      </article>
    </section>
  </main>
</template>

<style scoped>
.trial-note { margin-bottom: 20px; color: #76580e; background: #fff8df; }
.dashboard-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 14px; }
.status-card { display: grid; min-height: 151px; align-content: start; gap: 9px; padding: 18px; border: 1px solid #dfe7f2; border-radius: 13px; color: #475569; background: #fff; box-shadow: 0 9px 24px rgb(15 23 42 / 4%); text-decoration: none; transition: border-color .15s ease, transform .15s ease; }.status-card:hover { border-color: #86a8d6; transform: translateY(-1px); }.status-card strong { color: #172554; font-size: 22px; }.status-card small { color: #64748b; line-height: 1.45; }
.lower-grid { display: grid; grid-template-columns: 1.15fr 1fr; gap: 18px; margin-top: 18px; }.section-heading { display: flex; justify-content: space-between; gap: 15px; }.section-heading h2 { margin: 0 0 4px; color: #172554; font-size: 18px; }.section-heading p, .subtle { margin: 0; color: #64748b; font-size: 13px; }.section-heading a { color: #285493; font-size: 13px; white-space: nowrap; }
.knowledge-metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 9px; margin-top: 18px; }.knowledge-metrics div { padding: 11px; border-radius: 9px; background: #f6f8fc; }.knowledge-metrics span { display: block; color: #64748b; font-size: 12px; }.knowledge-metrics strong { display: block; margin-top: 4px; color: #172554; font-size: 20px; }.subtle { margin-top: 13px; }.compact { margin: 18px 0 0; }
.reminders { display: grid; grid-template-columns: repeat(3, 1fr); gap: 11px; margin: 18px 0 0; }.reminders div { padding: 11px; border-radius: 9px; background: #f6f8fc; }.reminders dt { color: #64748b; font-size: 12px; }.reminders dd { margin: 5px 0 0; color: #172554; font-size: 20px; font-weight: 700; }
@media (max-width: 1100px) { .dashboard-grid { grid-template-columns: repeat(3, 1fr); }.knowledge-metrics { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 760px) { .dashboard-grid, .lower-grid { grid-template-columns: 1fr; }.knowledge-metrics, .reminders { grid-template-columns: repeat(2, 1fr); } }
</style>
