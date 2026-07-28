<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { apiErrorMessage, listAiOptimizationCases, type AiOptimizationCase, type ExperienceCaseEvaluationStatus } from '../api/client'
import { displayStatus } from '../presentation'

const cases = ref<AiOptimizationCase[]>([])
const selected = ref<AiOptimizationCase | null>(null)
const loading = ref(false)
const error = ref('')
const filters = reactive({ store_code: '', product_id: '', sku_id: '', evaluation_status: '', page: 1, size: 20 })
const statuses: ExperienceCaseEvaluationStatus[] = ['NOT_EXPORTED', 'EXPORTED', 'EVALUATED', 'WRITEBACK_REJECTED']

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const result = await listAiOptimizationCases(filters)
    cases.value = result.items
    if (selected.value) selected.value = result.items.find((item) => item.case_id === selected.value?.case_id) || selected.value
  } catch (reason: unknown) {
    cases.value = []
    error.value = apiErrorMessage(reason)
  } finally { loading.value = false }
}

function choose(item: AiOptimizationCase): void { selected.value = item }
function formatJson(value: unknown): string { return JSON.stringify(value, null, 2) }

function readableSummary(value: unknown, empty = '已记录结构化评测结果，请展开原始记录查看。'): string {
  if (typeof value === 'string' && value.trim()) return value
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return empty
  const record = value as Record<string, unknown>
  for (const key of ['summary', 'conclusion', 'outcome', 'reason', 'recommendation']) {
    if (typeof record[key] === 'string' && record[key].trim()) return record[key] as string
  }
  return empty
}

function readableSuggestions(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => readableSummary(item, '')).filter(Boolean)
}

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">AI 控制中心 / 历史评测记录</p>
        <h1>优秀案例评测</h1>
        <p>查看人工审核通过的客服经验案例快照及已经回写的评测证据。页面只读，不会修改提示词、发布知识或自动执行业务。</p>
      </div>
      <button class="button secondary" type="button" :disabled="loading" @click="load">{{ loading ? '刷新中…' : '刷新数据' }}</button>
    </div>
    <form class="filters card" @submit.prevent="filters.page = 1; load()">
      <label>店铺<input v-model.trim="filters.store_code" /></label><label>商品<input v-model.trim="filters.product_id" /></label><label>SKU<input v-model.trim="filters.sku_id" /></label>
      <label>评测状态<select v-model="filters.evaluation_status"><option value="">全部</option><option v-for="status in statuses" :key="status" :value="status">{{ displayStatus(status) }}</option></select></label><button class="button" type="submit">筛选记录</button>
    </form>
    <p v-if="loading" class="notice" role="status">正在读取审核通过案例的评测状态…</p>
    <p v-else-if="error" class="notice error" role="alert">暂时无法读取优秀案例评测：{{ error }}</p>
    <p v-else-if="cases.length === 0" class="notice">样本不足：没有符合筛选条件的审核通过案例。请先在客服经验库完成人工审核；此页面不会展示未通过审核的案例。</p>
    <section v-else class="pool-grid">
      <div class="card table-wrap"><table class="data-table"><thead><tr><th>案例</th><th>适用范围</th><th>评测摘要</th><th>状态</th></tr></thead><tbody>
        <tr v-for="item in cases" :key="`${item.case_id}-${item.revision}`"><td><button class="link-button" type="button" @click="choose(item)">{{ item.case_id }}</button><small>版本 {{ item.revision }}</small></td><td>{{ item.store_code }}<small>{{ item.product_id || '未关联商品' }} / {{ item.sku_id || '未关联 SKU' }}</small></td><td class="summary-cell">{{ item.latest_evaluation ? readableSummary(item.latest_evaluation.result) : '尚无已回写评测结果。' }}</td><td><span class="badge">{{ displayStatus(item.evaluation_status) }}</span></td></tr>
      </tbody></table></div>
      <aside v-if="selected" class="card detail">
        <div class="section-title"><div><p class="eyebrow">评测证据</p><h2>案例详情</h2></div><span class="badge">{{ displayStatus(selected.evaluation_status) }}</span></div>
        <dl class="content-facts"><div><dt>客户问题</dt><dd>{{ selected.question }}</dd></div><div><dt>AI 原回答</dt><dd>{{ selected.ai_answer }}</dd></div><div><dt>人工最终回复</dt><dd>{{ selected.final_answer }}</dd></div><div><dt>客服采用方式</dt><dd>{{ displayStatus(selected.feedback_type) }}</dd></div></dl>
        <template v-if="selected.latest_evaluation"><section class="evaluation-summary"><h3>评测结论</h3><p>{{ readableSummary(selected.latest_evaluation.result) }}</p></section><section class="recommendations"><h3>优化建议</h3><ul v-if="readableSuggestions(selected.latest_evaluation.suggestions).length"><li v-for="item in readableSuggestions(selected.latest_evaluation.suggestions)" :key="item">{{ item }}</li></ul><p v-else class="muted">评测记录没有提供可直接展示的建议文本；可展开原始结构化记录核对。</p></section><details class="technical-details"><summary>技术信息与原始评测记录</summary><dl class="technical-facts"><div><dt>评测任务</dt><dd>{{ selected.latest_evaluation_run_id }}</dd></div><div><dt>模型 / Prompt</dt><dd>{{ selected.latest_evaluation.model_version }} / {{ selected.latest_evaluation.prompt_version }}</dd></div><div><dt>案例版本</dt><dd>{{ selected.revision }}</dd></div><div><dt>内容校验</dt><dd>{{ selected.content_hash }}</dd></div></dl><pre>{{ formatJson({ result: selected.latest_evaluation.result, suggestions: selected.latest_evaluation.suggestions }) }}</pre></details></template>
        <p v-else class="notice">该案例没有已回写的评测结果。它不会被当作“通过”或“失败”来展示。</p>
      </aside>
      <aside v-else class="card detail"><h2>案例详情</h2><p>选择一条审核通过案例，查看人工回复、评测摘要和可追溯证据。</p></aside>
    </section>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }.filters { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; margin-bottom: 20px; padding: 16px; }.filters label { display: grid; gap: 5px; color: #526279; font-size: 13px; }.filters input, .filters select { min-height: 38px; padding: 8px; border: 1px solid #cbd7e6; border-radius: 7px; font: inherit; }.pool-grid { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(320px, 1fr); gap: 20px; }.detail { display: grid; align-content: start; gap: 14px; }.section-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }.detail h2, .evaluation-summary h3, .recommendations h3 { margin: 0; color: #172554; }.link-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; text-align: left; cursor: pointer; }.summary-cell { min-width: 220px; line-height: 1.55; }.content-facts, .technical-facts { display: grid; gap: 11px; margin: 0; }.content-facts dt, .technical-facts dt { color: #64748b; font-size: 12px; font-weight: 700; }.content-facts dd, .technical-facts dd { margin: 3px 0 0; overflow-wrap: anywhere; line-height: 1.55; white-space: pre-wrap; }.evaluation-summary, .recommendations { padding: 14px; border-radius: 10px; background: #f5f8fc; }.evaluation-summary p { margin: 9px 0 0; line-height: 1.55; }.recommendations ul { margin: 9px 0 0; padding-left: 20px; }.recommendations li { margin-bottom: 7px; line-height: 1.55; }.muted, small { color: #64748b; font-size: 12px; line-height: 1.55; }.technical-details { border-top: 1px solid #e6edf5; color: #526279; font-size: 13px; }.technical-details summary { padding-top: 12px; cursor: pointer; }.technical-details pre { max-height: 250px; overflow: auto; padding: 10px; border-radius: 8px; background: #f4f7fb; font-size: 12px; white-space: pre-wrap; }
@media (max-width: 900px) { .pool-grid { grid-template-columns: 1fr; } }
</style>
