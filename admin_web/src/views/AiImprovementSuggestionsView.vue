<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { formatEvidenceTime, summarizeAnalysis, technicalJson } from '../aiPresentation'
import { apiErrorMessage, listAiFeedbackAnalysisResults, type AiFeedbackAnalysisResult } from '../api/client'
import { displayStatus } from '../presentation'

const results = ref<AiFeedbackAnalysisResult[]>([])
const selected = ref<AiFeedbackAnalysisResult | null>(null)
const loading = ref(false)
const error = ref('')

function summaryFor(item: AiFeedbackAnalysisResult) {
  return summarizeAnalysis(item.analysis, item.suggestions)
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const response = await listAiFeedbackAnalysisResults()
    results.value = response.items
    if (selected.value) selected.value = response.items.find((item) => item.feedback_id === selected.value?.feedback_id) || null
  } catch (reason: unknown) {
    results.value = []
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
      <div><h1>改进建议</h1><p>将已完成的 AI 问题分析转换为便于运营阅读的建议清单。建议仅供人工判断，不会自动执行。</p></div>
      <button class="button secondary" type="button" @click="load">刷新数据</button>
    </div>
    <p class="notice trial-note">这里只显示已有的分析证据；没有建议时会显示“暂无建议动作”，不会补造建议。</p>
    <p v-if="loading" class="notice" role="status">正在加载改进建议…</p>
    <div v-else-if="error" class="notice error" role="alert"><strong>数据加载失败</strong><br />原因：{{ error }}<br />建议下一步：检查服务状态后重试。</div>
    <p v-else-if="results.length === 0" class="notice">样本不足：暂无可展示的改进建议。</p>
    <section v-else class="suggestion-grid">
      <div class="card table-wrap">
        <table class="data-table">
          <thead><tr><th>问题概述</th><th>问题类型</th><th>建议动作</th><th>当前状态</th><th>分析时间</th></tr></thead>
          <tbody><tr v-for="item in results" :key="`${item.feedback_id}-${item.revision}`"><td><button class="link-button" type="button" @click="selected = item">{{ summaryFor(item).overview }}</button></td><td><span class="badge">{{ displayStatus(item.feedback_type) }}</span></td><td>{{ summaryFor(item).action }}</td><td><span class="badge">{{ displayStatus(item.analysis_status) }}</span></td><td>{{ formatEvidenceTime(item.created_at) }}</td></tr></tbody>
        </table>
      </div>
      <aside v-if="selected" class="card detail">
        <h2>建议依据</h2>
        <p><strong>客户问题</strong><br />{{ selected.question || '未提供' }}</p>
        <p><strong>风险判断</strong><br />{{ summaryFor(selected).risk }}</p>
        <p><strong>建议动作</strong><br />{{ summaryFor(selected).action }}</p>
        <details class="technical-details"><summary>技术详情</summary><p>分析任务：{{ selected.analysis_run_id || '未提供' }}</p><pre>{{ technicalJson({ analysis: selected.analysis, suggestions: selected.suggestions }) }}</pre></details>
      </aside>
    </section>
  </main>
</template>

<style scoped>
.trial-note { margin-bottom: 20px; color: #75570a; background: #fff8df; }.suggestion-grid { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(300px, 1fr); gap: 20px; }.detail { display: grid; align-content: start; gap: 13px; }.detail h2, .detail p { margin: 0; }.detail h2 { color: #172554; }.detail p { line-height: 1.55; overflow-wrap: anywhere; white-space: pre-wrap; }.link-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; text-align: left; cursor: pointer; }.technical-details { border-top: 1px solid #e6edf5; color: #526279; font-size: 13px; }.technical-details summary { padding-top: 13px; cursor: pointer; }pre { max-width: 100%; margin: 10px 0 0; padding: 10px; overflow: auto; border-radius: 8px; background: #f4f7fb; font-size: 12px; white-space: pre-wrap; }@media (max-width: 950px) { .suggestion-grid { grid-template-columns: 1fr; } }
</style>
