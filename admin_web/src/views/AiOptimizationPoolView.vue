<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { formatEvidenceTime, summarizeAnalysis, technicalJson } from '../aiPresentation'
import { apiErrorMessage, listAiOptimizationCases, type AiOptimizationCase } from '../api/client'
import { displayStatus } from '../presentation'

const cases = ref<AiOptimizationCase[]>([])
const selected = ref<AiOptimizationCase | null>(null)
const loading = ref(false)
const error = ref('')

const selectedSummary = computed(() => selected.value?.latest_evaluation
  ? summarizeAnalysis(selected.value.latest_evaluation.result, selected.value.latest_evaluation.suggestions)
  : null)

function summaryFor(item: AiOptimizationCase) {
  return item.latest_evaluation
    ? summarizeAnalysis(item.latest_evaluation.result, item.latest_evaluation.suggestions)
    : null
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const response = await listAiOptimizationCases()
    cases.value = response.items
    if (selected.value) selected.value = response.items.find((item) => item.case_id === selected.value?.case_id) || null
  } catch (reason: unknown) {
    cases.value = []
    selected.value = null
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div><h1>评测中心</h1><p>查看已批准案例的评测证据和可读结论。该页面仅用于观察，不会自动调整模型、提示词或知识。</p></div>
      <button class="button secondary" type="button" @click="load">刷新数据</button>
    </div>
    <p class="notice trial-note">仅显示已批准的经验案例及其已回写评测证据；没有评测的案例会明确显示为“样本不足”。</p>
    <p v-if="loading" class="notice" role="status">正在加载评测记录…</p>
    <div v-else-if="error" class="notice error" role="alert"><strong>数据加载失败</strong><br />原因：{{ error }}<br />建议下一步：检查服务状态后重试。</div>
    <p v-else-if="cases.length === 0" class="notice">样本不足：暂无已批准的案例可以展示。</p>
    <section v-else class="pool-grid">
      <div class="card table-wrap">
        <table class="data-table">
          <thead><tr><th>客户问题</th><th>问题类型</th><th>评测结论</th><th>当前状态</th><th>使用模型</th><th>提示词版本</th><th>评测时间</th></tr></thead>
          <tbody>
            <tr v-for="item in cases" :key="`${item.case_id}-${item.revision}`">
              <td><button class="link-button" type="button" @click="selected = item">{{ item.question || '未提供' }}</button></td>
              <td><span class="badge">{{ displayStatus(item.feedback_type) }}</span></td>
              <td>{{ summaryFor(item)?.overview || '样本不足' }}</td>
              <td><span class="badge">{{ displayStatus(item.evaluation_status) }}</span></td>
              <td>{{ item.latest_evaluation?.model_version || '未提供' }}</td>
              <td>{{ item.latest_evaluation?.prompt_version || '未提供' }}</td>
              <td>{{ formatEvidenceTime(item.latest_evaluation?.recorded_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <aside v-if="selected" class="card detail">
        <h2>评测详情</h2>
        <p><strong>客户问题</strong><br />{{ selected.question || '未提供' }}</p>
        <p><strong>AI 回答</strong><br />{{ selected.ai_answer || '未提供' }}</p>
        <p><strong>人工最终回复</strong><br />{{ selected.final_answer || '未提供' }}</p>
        <template v-if="selectedSummary">
          <dl class="business-summary">
            <div><dt>评测结论</dt><dd>{{ selectedSummary.overview }}</dd></div>
            <div><dt>AI 与人工差异</dt><dd>{{ selectedSummary.difference }}</dd></div>
            <div><dt>风险判断</dt><dd>{{ selectedSummary.risk }}</dd></div>
            <div><dt>建议动作</dt><dd>{{ selectedSummary.action }}</dd></div>
          </dl>
          <details class="technical-details">
            <summary>技术详情</summary>
            <dl><div><dt>模型 / 提示词版本</dt><dd>{{ selected.latest_evaluation?.model_version || '未提供' }} / {{ selected.latest_evaluation?.prompt_version || '未提供' }}</dd></div><div><dt>评测任务</dt><dd>{{ selected.latest_evaluation_run_id || '未提供' }}</dd></div><div><dt>案例版本</dt><dd>{{ selected.revision }}</dd></div><div><dt>内容校验</dt><dd>{{ selected.content_hash || '未提供' }}</dd></div></dl>
            <p class="technical-caption">原始评测证据</p>
            <pre>{{ technicalJson({ result: selected.latest_evaluation?.result, suggestions: selected.latest_evaluation?.suggestions }) }}</pre>
          </details>
        </template>
        <p v-else class="notice">样本不足：该案例尚无已回写的评测结果。请等待评测结果回写。</p>
      </aside>
    </section>
  </main>
</template>

<style scoped>
.trial-note { margin-bottom: 20px; color: #75570a; background: #fff8df; }.pool-grid { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(320px, 1fr); gap: 20px; }.detail { display: grid; align-content: start; gap: 13px; }.detail h2, .detail p { margin: 0; }.detail h2 { color: #172554; }.detail p, dd { line-height: 1.55; overflow-wrap: anywhere; white-space: pre-wrap; }.link-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; text-align: left; cursor: pointer; }.business-summary, .technical-details dl { display: grid; gap: 9px; margin: 0; }.business-summary { padding: 13px; border-radius: 9px; background: #f6f8fc; }dt { color: #64748b; font-size: 12px; font-weight: 700; } dd { margin: 3px 0 0; }.technical-details { border-top: 1px solid #e6edf5; color: #526279; font-size: 13px; }.technical-details summary { padding-top: 13px; cursor: pointer; }.technical-caption { margin: 12px 0 7px !important; color: #64748b; font-size: 12px; }pre { max-width: 100%; margin: 0; padding: 10px; overflow: auto; border-radius: 8px; background: #f4f7fb; font-size: 12px; white-space: pre-wrap; }@media (max-width: 950px) { .pool-grid { grid-template-columns: 1fr; } }
</style>
