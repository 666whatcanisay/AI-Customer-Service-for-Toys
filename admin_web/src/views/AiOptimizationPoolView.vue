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
  } finally {
    loading.value = false
  }
}

function choose(item: AiOptimizationCase): void { selected.value = item }
function formatted(value: unknown): string { return JSON.stringify(value, null, 2) }

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header"><div><h1>AI 评测</h1><p>查看已通过客服案例的不可变快照与已回写评测结果。页面只读，不提供修改提示词、发布知识或自动执行业务的操作。</p></div><button class="button secondary" type="button" @click="load">刷新数据</button></div>
    <form class="filters card" @submit.prevent="filters.page = 1; load()">
      <label>店铺<input v-model.trim="filters.store_code" /></label>
      <label>商品<input v-model.trim="filters.product_id" /></label>
      <label>SKU<input v-model.trim="filters.sku_id" /></label>
      <label>评测状态<select v-model="filters.evaluation_status"><option value="">全部</option><option v-for="status in statuses" :key="status" :value="status">{{ displayStatus(status) }}</option></select></label>
      <button class="button" type="submit">筛选记录</button>
    </form>
    <p v-if="loading" class="notice">正在读取已通过案例快照…</p>
    <p v-else-if="error" class="notice error" role="alert">暂时无法读取评测记录。{{ error }}</p>
    <p v-else-if="cases.length === 0" class="notice">样本不足：没有符合当前筛选条件的已通过案例。先在客服案例中完成审核。</p>
    <section v-else class="pool-grid">
      <div class="card table-wrap"><table class="data-table"><thead><tr><th>案例</th><th>适用范围</th><th>评测状态</th><th>最近评测</th></tr></thead><tbody>
        <tr v-for="item in cases" :key="`${item.case_id}-${item.revision}`"><td><button class="link-button" type="button" @click="choose(item)">{{ item.case_id }}</button><small>版本 {{ item.revision }}</small></td><td>{{ item.store_code }}<small>{{ item.product_id || '未关联商品' }} / {{ item.sku_id || '未关联 SKU' }}</small></td><td><span class="badge">{{ displayStatus(item.evaluation_status) }}</span></td><td>{{ item.latest_evaluation_run_id || '尚无回写结果' }}</td></tr>
      </tbody></table></div>
      <aside v-if="selected" class="card detail"><h2>评测详情</h2><p><strong>客户问题</strong><br>{{ selected.question }}</p><p><strong>AI 回答</strong><br>{{ selected.ai_answer }}</p><p><strong>人工最终回复</strong><br>{{ selected.final_answer }}</p><template v-if="selected.latest_evaluation"><p><strong>评测结论</strong></p><pre>{{ formatted(selected.latest_evaluation.result) }}</pre><p><strong>改进建议</strong></p><pre>{{ formatted(selected.latest_evaluation.suggestions) }}</pre><details class="technical-details"><summary>技术信息</summary><dl><div><dt>模型 / 提示词版本</dt><dd>{{ selected.latest_evaluation.model_version }} / {{ selected.latest_evaluation.prompt_version }}</dd></div><div><dt>评测任务</dt><dd>{{ selected.latest_evaluation_run_id }}</dd></div><div><dt>案例版本</dt><dd>{{ selected.revision }}</dd></div></dl></details></template><p v-else class="notice">样本不足：该案例尚无已回写的评测结果。请等待分析结果回写。</p></aside>
      <aside v-else class="card detail"><h2>评测详情</h2><p>选择一条已通过案例，查看受控的评测证据。</p></aside>
    </section>
  </main>
</template>

<style scoped>
.filters { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; margin-bottom: 20px; padding: 16px; }label { display: grid; gap: 5px; color: #526279; font-size: 13px; }input, select { min-height: 38px; padding: 8px; border: 1px solid #cbd7e6; border-radius: 7px; font: inherit; }.pool-grid { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(310px, 1fr); gap: 20px; }.detail { display: grid; align-content: start; gap: 12px; }.detail h2, .detail p { margin: 0; }.detail h2 { color: #172554; }.detail p { line-height: 1.5; white-space: pre-wrap; }.link-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; text-align: left; cursor: pointer; }small { display: block; margin-top: 4px; color: #64748b; }pre { max-width: 100%; margin: 0; padding: 10px; overflow: auto; border-radius: 8px; background: #f4f7fb; font-size: 12px; white-space: pre-wrap; }.technical-details { margin-top: 3px; border-top: 1px solid #e6edf5; color: #526279; font-size: 13px; }.technical-details summary { padding-top: 12px; cursor: pointer; }.technical-details dl { display: grid; gap: 8px; margin: 11px 0 0; }.technical-details dt { color: #64748b; }.technical-details dd { margin: 2px 0 0; overflow-wrap: anywhere; }@media (max-width: 900px) { .pool-grid { grid-template-columns: 1fr; } }
</style>
