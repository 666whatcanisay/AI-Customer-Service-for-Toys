<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import {
  apiErrorMessage,
  listAiOptimizationCases,
  type AiOptimizationCase,
  type ExperienceCaseEvaluationStatus,
} from '../api/client'

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
    <div class="page-header"><div><h1>AI optimization pool</h1><p>Approved case snapshots and recorded evaluation evidence only. No prompt, model, or knowledge publication controls are available.</p></div></div>
    <form class="filters card" @submit.prevent="filters.page = 1; load()">
      <label>Store<input v-model.trim="filters.store_code" /></label>
      <label>Product<input v-model.trim="filters.product_id" /></label>
      <label>SKU<input v-model.trim="filters.sku_id" /></label>
      <label>Evaluation<select v-model="filters.evaluation_status"><option value="">All</option><option v-for="status in statuses" :key="status" :value="status">{{ status }}</option></select></label>
      <button class="button" type="submit">Filter pool</button>
    </form>
    <p v-if="loading" class="notice">Loading approved snapshots…</p>
    <p v-else-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-else-if="cases.length === 0" class="notice">No approved cases match the current filters.</p>
    <section v-else class="pool-grid">
      <div class="card table-wrap"><table class="data-table"><thead><tr><th>Case</th><th>Context</th><th>Evaluation</th><th>Latest run</th></tr></thead><tbody>
        <tr v-for="item in cases" :key="`${item.case_id}-${item.revision}`"><td><button class="link-button" type="button" @click="choose(item)">{{ item.case_id }}</button><small>Revision {{ item.revision }}</small></td><td>{{ item.store_code }}<small>{{ item.product_id || '—' }} / {{ item.sku_id || '—' }}</small></td><td><span class="badge">{{ item.evaluation_status }}</span></td><td>{{ item.latest_evaluation_run_id || 'No recorded evaluation' }}</td></tr>
      </tbody></table></div>
      <aside v-if="selected" class="card detail"><h2>Evaluation detail</h2><p><strong>Question</strong><br>{{ selected.question }}</p><p><strong>AI answer</strong><br>{{ selected.ai_answer }}</p><p><strong>Final answer</strong><br>{{ selected.final_answer }}</p><template v-if="selected.latest_evaluation"><p><strong>Model / prompt</strong><br>{{ selected.latest_evaluation.model_version }} · {{ selected.latest_evaluation.prompt_version }}</p><p><strong>Result</strong></p><pre>{{ formatted(selected.latest_evaluation.result) }}</pre><p><strong>Suggestions</strong></p><pre>{{ formatted(selected.latest_evaluation.suggestions) }}</pre></template><p v-else class="notice">No evaluation result has been written back for this snapshot.</p></aside>
      <aside v-else class="card detail"><h2>Evaluation detail</h2><p>Select an approved case to inspect its controlled evaluation evidence.</p></aside>
    </section>
  </main>
</template>

<style scoped>
.filters { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; margin-bottom: 20px; padding: 16px; }
label { display: grid; gap: 5px; color: #526279; font-size: 13px; }
input, select { min-height: 38px; padding: 8px; border: 1px solid #cbd7e6; border-radius: 7px; font: inherit; }
.pool-grid { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(310px, 1fr); gap: 20px; }
.detail { display: grid; align-content: start; gap: 12px; }
.detail h2, .detail p { margin: 0; }
.detail p { line-height: 1.5; white-space: pre-wrap; }
.link-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; text-align: left; cursor: pointer; }
small { display: block; margin-top: 4px; color: #617087; }
pre { max-width: 100%; margin: 0; padding: 10px; overflow: auto; border-radius: 8px; background: #f4f7fb; font-size: 12px; white-space: pre-wrap; }
@media (max-width: 900px) { .pool-grid { grid-template-columns: 1fr; } }
</style>
