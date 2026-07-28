<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { businessText, formatEvidenceTime, summarizeAnalysis, technicalJson } from '../aiPresentation'
import {
  getAdminOperationsToday,
  getHealth,
  listAiFeedbackAnalysisResults,
  listAiModules,
  listAiOptimizationCases,
  type AdminOperationsToday,
  type AiFeedbackAnalysisResult,
  type AiModule,
  type AiOptimizationCase,
} from '../api/client'

type Availability = 'loading' | 'available' | 'unavailable'

const platformState = ref<Availability>('loading')
const aiState = ref<Availability>('loading')
const operations = ref<AdminOperationsToday | null>(null)
const modules = ref<AiModule[]>([])
const feedbackResults = ref<AiFeedbackAnalysisResult[]>([])
const evaluations = ref<AiOptimizationCase[]>([])
const error = ref('')
const checkedAt = ref('')

function metadataText(module: AiModule | undefined, keys: string[]): string | null {
  const metadata = module?.promptMetadata || {}
  for (const key of keys) {
    const value = metadata[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return null
}

function latestBy<T>(items: T[], value: (item: T) => string | null | undefined): T | null {
  return [...items].sort((left, right) => {
    const leftTime = new Date(value(left) || 0).getTime()
    const rightTime = new Date(value(right) || 0).getTime()
    return rightTime - leftTime
  })[0] || null
}

const aiLabel = computed(() => ({
  loading: '正在检查',
  available: modules.value.length ? 'AI 服务可用' : '接口可用，暂无可展示数据',
  unavailable: 'AI 服务待连接',
})[aiState.value])
const platformLabel = computed(() => ({ loading: '正在检查', available: '平台服务可用', unavailable: '平台服务待连接' })[platformState.value])
const currentModel = computed(() => metadataText(modules.value[0], ['model_version', 'model', 'model_name']) || '暂无可展示数据')
const knowledgeLabel = computed(() => {
  const knowledge = operations.value?.knowledge
  if (!knowledge) return '待启用'
  const total = knowledge.store_count + knowledge.product_count + knowledge.sku_count + knowledge.faq_count + knowledge.safety_rule_count
  return total === 0 ? '样本不足' : `${knowledge.product_count} 个商品 · ${knowledge.sku_count} 个 SKU · ${knowledge.faq_count} 条 FAQ`
})
const latestEvaluation = computed(() => latestBy(evaluations.value, (item) => item.latest_evaluation?.recorded_at))
const latestFeedback = computed(() => latestBy(feedbackResults.value, (item) => item.created_at))
const latestEvaluationSummary = computed(() => latestEvaluation.value?.latest_evaluation
  ? summarizeAnalysis(latestEvaluation.value.latest_evaluation.result, latestEvaluation.value.latest_evaluation.suggestions)
  : null)
const latestFeedbackSummary = computed(() => latestFeedback.value
  ? summarizeAnalysis(latestFeedback.value.analysis, latestFeedback.value.suggestions)
  : null)
const moduleName = (module: AiModule): string => businessText(module.name, 'AI 模块')

async function load(): Promise<void> {
  error.value = ''
  const [healthResult, operationsResult, moduleResult, feedbackResult, evaluationResult] = await Promise.allSettled([
    getHealth(), getAdminOperationsToday(), listAiModules(), listAiFeedbackAnalysisResults(), listAiOptimizationCases(),
  ])
  platformState.value = healthResult.status === 'fulfilled' ? 'available' : 'unavailable'
  aiState.value = moduleResult.status === 'fulfilled' ? 'available' : 'unavailable'
  operations.value = operationsResult.status === 'fulfilled' ? operationsResult.value : null
  modules.value = moduleResult.status === 'fulfilled' ? moduleResult.value : []
  feedbackResults.value = feedbackResult.status === 'fulfilled' ? feedbackResult.value.items : []
  evaluations.value = evaluationResult.status === 'fulfilled' ? evaluationResult.value.items : []
  const failures = [healthResult, operationsResult, moduleResult, feedbackResult, evaluationResult]
    .filter((result) => result.status === 'rejected').length
  if (failures) error.value = `${failures} 项数据暂时无法读取；其余已连接数据仍会照常展示。`
  checkedAt.value = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short', hour12: false }).format(new Date())
}

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div><h1>AI 控制中心</h1><p>在一个页面确认 AI 服务、知识准备、评测与问题分析的真实状态。此页面只读，不提供自动发布、自动训练或自动修改提示词。</p></div>
      <button class="button secondary" type="button" @click="load">重新检查</button>
    </div>
    <p class="notice trial-note">当前数据用于测试 / 试运行观察，不构成正式运营报表或生产可用性承诺。</p>
    <p v-if="error" class="notice error" role="alert"><strong>部分数据加载失败</strong><br />原因：{{ error }}<br />建议下一步：检查服务状态后重新检查。</p>

    <section class="summary-grid" aria-label="管理摘要">
      <article class="status-card"><span>AI 是否可用</span><strong>{{ aiLabel }}</strong><small>以 A 的能力目录接口是否可访问为准；无模块时不补造能力。</small></article>
      <article class="status-card"><span>当前模型</span><strong>{{ currentModel }}</strong><small>只显示接口已返回的模型元数据。</small></article>
      <article class="status-card"><span>当前知识状态</span><strong>{{ knowledgeLabel }}</strong><small>来自 C 平台已保存的知识资产统计。</small></article>
      <article class="status-card"><span>最近评测结果</span><strong>{{ latestEvaluationSummary?.overview || '暂无可展示数据' }}</strong><small>{{ latestEvaluation ? `评测时间：${formatEvidenceTime(latestEvaluation.latest_evaluation?.recorded_at)}` : '尚无已回写评测证据。' }}</small></article>
      <article class="status-card"><span>最近 AI 问题分析</span><strong>{{ latestFeedbackSummary?.overview || '暂无可展示数据' }}</strong><small>{{ latestFeedback ? `分析时间：${formatEvidenceTime(latestFeedback.created_at)}` : '尚无已完成分析的 AI 问题。' }}</small></article>
    </section>

    <section class="card business-layer">
      <h2>运营怎么看</h2>
      <div class="business-grid">
        <div><strong>老板</strong><p>先看 AI 是否可用、知识是否准备，再看最近评测和问题分析是否有明确结论。</p></div>
        <div><strong>运营</strong><p>知识待启用时先补商品和 FAQ；出现已分析问题时进入“AI 问题”核对人工处理；有建议时由人工判断后再推进。</p></div>
        <div><strong>技术负责人</strong><p>需要排查接口或版本时再展开技术详情。页面不会以接口可达推断 AI 回答质量。</p></div>
      </div>
      <div class="module-row"><span>当前可用模块</span><template v-if="modules.length"><span v-for="module in modules" :key="module.id" class="badge">{{ moduleName(module) }}</span></template><span v-else class="subtle">{{ aiState === 'available' ? '接口可用，暂无可展示数据' : '待启用' }}</span></div>
    </section>

    <details class="card technical-details">
      <summary>技术详情（供技术负责人查看）</summary>
      <dl><div><dt>平台服务</dt><dd>{{ platformLabel }}</dd></div><div><dt>检查时间</dt><dd>{{ checkedAt || '未提供' }}</dd></div><div><dt>能力目录数量</dt><dd>{{ modules.length }}</dd></div><div><dt>已分析问题数量</dt><dd>{{ feedbackResults.length }}</dd></div><div><dt>已批准案例数量</dt><dd>{{ evaluations.length }}</dd></div></dl>
      <pre>{{ technicalJson({ modules, platform_available: platformState === 'available', ai_interface_available: aiState === 'available' }) }}</pre>
    </details>
  </main>
</template>

<style scoped>
.trial-note { margin-bottom: 20px; color: #75570a; background: #fff8df; }.summary-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 14px; }.status-card { display: grid; min-height: 160px; align-content: start; gap: 9px; padding: 18px; border: 1px solid #dfe7f2; border-radius: 13px; color: #475569; background: #fff; box-shadow: 0 9px 24px rgb(15 23 42 / 4%); }.status-card strong { color: #172554; font-size: 19px; line-height: 1.35; overflow-wrap: anywhere; }.status-card small, .subtle { color: #64748b; line-height: 1.45; }.business-layer { margin-top: 18px; }.business-layer h2 { margin: 0; color: #172554; font-size: 19px; }.business-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 16px; }.business-grid div { padding: 14px; border-radius: 10px; background: #f6f8fc; }.business-grid strong { color: #172554; }.business-grid p { margin: 7px 0 0; color: #526279; font-size: 13px; line-height: 1.6; }.module-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 18px; color: #475569; font-size: 13px; }.technical-details { margin-top: 18px; color: #526279; }.technical-details summary { color: #284568; cursor: pointer; font-weight: 700; }.technical-details dl { display: grid; gap: 9px; margin: 16px 0; }.technical-details dt { color: #64748b; font-size: 12px; }.technical-details dd { margin: 3px 0 0; overflow-wrap: anywhere; }.technical-details pre { max-width: 100%; margin: 0; padding: 10px; overflow: auto; border-radius: 8px; background: #f4f7fb; font-size: 12px; white-space: pre-wrap; }@media (max-width: 1180px) { .summary-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }@media (max-width: 760px) { .summary-grid, .business-grid { grid-template-columns: 1fr; } }
</style>
