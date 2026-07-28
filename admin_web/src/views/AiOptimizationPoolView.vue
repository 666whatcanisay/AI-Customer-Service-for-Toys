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

const outcomeLabels: Record<string, string> = {
  NEEDS_REVIEW: '需要人工复核',
  PASSED: '评测通过',
  FAILED: '需要改进',
}

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
function textValue(value: unknown): string | null { return typeof value === 'string' && value.trim() ? value.trim() : null }

function evaluationSummary(item: AiOptimizationCase): string {
  const result = item.latest_evaluation?.result
  if (!result) return '尚无已回写的评测结果。'
  return textValue(result.summary)
    ?? textValue(result.conclusion)
    ?? (typeof result.outcome === 'string' ? outcomeLabels[result.outcome] ?? '评测已完成，摘要暂无法读取。' : '评测已完成，摘要暂无法读取。')
}

function evaluationReasons(item: AiOptimizationCase): Array<{ label: string; value: string }> {
  const result = item.latest_evaluation?.result ?? {}
  return [
    { label: '评测原因', value: textValue(result.reason) },
    { label: '主要原因', value: textValue(result.root_cause) },
  ].filter((entry): entry is { label: string; value: string } => entry.value !== null)
}

function suggestionSummary(value: Record<string, unknown>): string {
  return textValue(value.recommended_action)
    ?? textValue(value.action)
    ?? textValue(value.suggestion)
    ?? textValue(value.description)
    ?? textValue(value.title)
    ?? (typeof value.category === 'string' && value.category === 'PROMPT_HYPOTHESIS'
      ? '提示词改进假设（仅供人工评估）'
      : '已提供建议，详情暂无法以业务摘要展示。')
}

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div><p class="eyebrow">AI 运营 · 评测</p><h1>AI 评测中心</h1><p>查看已通过客服案例的不可变快照与已回写评测结果。页面只读，不提供提示词修改、知识发布或自动执行业务的操作。</p></div>
      <button class="button secondary" type="button" @click="load">刷新数据</button>
    </div>
    <form class="filters card" @submit.prevent="filters.page = 1; load()">
      <label>店铺<input v-model.trim="filters.store_code" /></label><label>商品<input v-model.trim="filters.product_id" /></label><label>SKU<input v-model.trim="filters.sku_id" /></label>
      <label>评测状态<select v-model="filters.evaluation_status"><option value="">全部</option><option v-for="status in statuses" :key="status" :value="status">{{ displayStatus(status) }}</option></select></label><button class="button" type="submit">筛选记录</button>
    </form>
    <p v-if="loading" class="notice" role="status">正在读取已通过案例快照…</p>
    <p v-else-if="error" class="notice error" role="alert">暂时无法读取评测记录。{{ error }}</p>
    <p v-else-if="cases.length === 0" class="notice">没有符合当前筛选条件的已通过案例。请先在客服案例中完成人工审核。</p>
    <section v-else class="pool-grid">
      <div class="card table-wrap"><table class="data-table"><thead><tr><th>案例</th><th>适用范围</th><th>评测状态</th><th>评测摘要</th></tr></thead><tbody>
        <tr v-for="item in cases" :key="`${item.case_id}-${item.revision}`"><td><button class="link-button" type="button" @click="choose(item)">{{ item.case_id }}</button><small>版本 {{ item.revision }}</small></td><td>{{ item.store_code }}<small>{{ item.product_id || '未关联商品' }} / {{ item.sku_id || '未关联 SKU' }}</small></td><td><span class="badge">{{ displayStatus(item.evaluation_status) }}</span></td><td>{{ evaluationSummary(item) }}</td></tr>
      </tbody></table></div>
      <aside v-if="selected" class="card detail"><h2>评测详情</h2><p><strong>客户问题</strong><br>{{ selected.question }}</p><p><strong>AI 回答</strong><br>{{ selected.ai_answer }}</p><p><strong>人工最终回复</strong><br>{{ selected.final_answer }}</p><template v-if="selected.latest_evaluation"><section class="summary-panel"><h3>评测结论</h3><p>{{ evaluationSummary(selected) }}</p><dl v-if="evaluationReasons(selected).length"><div v-for="reason in evaluationReasons(selected)" :key="reason.label"><dt>{{ reason.label }}</dt><dd>{{ reason.value }}</dd></div></dl></section><section class="suggestion-panel"><h3>建议下一步</h3><ul v-if="selected.latest_evaluation.suggestions.length"><li v-for="(suggestion, index) in selected.latest_evaluation.suggestions" :key="index">{{ suggestionSummary(suggestion) }}</li></ul><p v-else>本次评测没有返回结构化建议。请保持人工审核，不要自动修改 Prompt 或知识。</p></section><details class="technical-details"><summary>技术信息</summary><dl><div><dt>模型 / 提示词版本</dt><dd>{{ selected.latest_evaluation.model_version }} / {{ selected.latest_evaluation.prompt_version }}</dd></div><div><dt>评测任务</dt><dd>{{ selected.latest_evaluation_run_id }}</dd></div><div><dt>案例版本</dt><dd>{{ selected.revision }}</dd></div></dl></details></template><p v-else class="notice">该案例尚无已回写的评测结果。请等待受控分析流程完成。</p></aside>
      <aside v-else class="card detail"><h2>评测详情</h2><p>选择一条已通过案例，查看面向运营的评测结论和建议。</p></aside>
    </section>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }.filters { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; margin-bottom: 20px; padding: 16px; }label { display: grid; gap: 5px; color: #526279; font-size: 13px; }input, select { min-height: 38px; padding: 8px; border: 1px solid #cbd7e6; border-radius: 7px; font: inherit; }.pool-grid { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(310px, 1fr); gap: 20px; }.detail { display: grid; align-content: start; gap: 12px; }.detail h2, .detail h3, .detail p { margin: 0; }.detail h2, .detail h3 { color: #172554; }.detail p { line-height: 1.55; white-space: pre-wrap; overflow-wrap: anywhere; }.link-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; text-align: left; cursor: pointer; }small { display: block; margin-top: 4px; color: #64748b; }.summary-panel, .suggestion-panel { padding: 13px; border: 1px solid #dce5f1; border-radius: 10px; background: #f9fbfe; }.summary-panel dl { display: grid; gap: 8px; margin: 12px 0 0; }.summary-panel dt, .technical-details dt { color: #64748b; font-size: 13px; }.summary-panel dd, .technical-details dd { margin: 3px 0 0; overflow-wrap: anywhere; }.suggestion-panel ul { display: grid; gap: 9px; margin: 10px 0 0; padding-left: 20px; line-height: 1.55; }.technical-details { margin-top: 3px; border-top: 1px solid #e6edf5; color: #526279; font-size: 13px; }.technical-details summary { padding-top: 12px; cursor: pointer; }.technical-details dl { display: grid; gap: 8px; margin: 11px 0 0; }@media (max-width: 900px) { .pool-grid { grid-template-columns: 1fr; } }
</style>
