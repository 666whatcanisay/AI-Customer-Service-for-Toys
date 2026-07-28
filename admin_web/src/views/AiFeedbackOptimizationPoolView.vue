<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { apiErrorMessage, listAiFeedbackAnalysisResults, type AiFeedbackAnalysisResult } from '../api/client'
import { displayStatus } from '../presentation'

const results = ref<AiFeedbackAnalysisResult[]>([])
const total = ref<number | null>(null)
const selected = ref<AiFeedbackAnalysisResult | null>(null)
const loading = ref(false)
const error = ref('')

const analysisFieldLabels: Record<string, string> = {
  reason: '问题原因',
  root_cause: '主要原因',
  category: '问题归类',
  evidence: '分析依据',
}

const suggestionCategoryLabels: Record<string, string> = {
  PROMPT_HYPOTHESIS: '提示词改进假设（仅供人工评估）',
  KNOWLEDGE_GAP: '知识缺口待补充',
  CUSTOMER_FLOW: '客服流程需人工核对',
  SAFETY_REVIEW: '需要安全复核',
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const response = await listAiFeedbackAnalysisResults()
    results.value = response.items
    total.value = response.total
    if (selected.value) selected.value = response.items.find((item) => item.feedback_id === selected.value?.feedback_id) || null
  } catch (reason: unknown) {
    results.value = []
    total.value = null
    selected.value = null
    error.value = apiErrorMessage(reason)
  } finally { loading.value = false }
}

function choose(item: AiFeedbackAnalysisResult): void { selected.value = item }

function textValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function analysisSummary(item: AiFeedbackAnalysisResult): string {
  const analysis = item.analysis
  return textValue(analysis.summary)
    ?? textValue(analysis.conclusion)
    ?? textValue(analysis.result)
    ?? '分析已完成，但未提供可展示的业务摘要。'
}

function analysisReasons(item: AiFeedbackAnalysisResult): Array<{ label: string; value: string }> {
  return Object.entries(analysisFieldLabels)
    .map(([key, label]) => ({ label, value: textValue(item.analysis[key]) }))
    .filter((entry): entry is { label: string; value: string } => entry.value !== null)
}

function suggestionSummary(value: Record<string, unknown>): string {
  return textValue(value.recommended_action)
    ?? textValue(value.action)
    ?? textValue(value.suggestion)
    ?? textValue(value.description)
    ?? textValue(value.title)
    ?? (typeof value.category === 'string' ? suggestionCategoryLabels[value.category] ?? '已提供建议，详情暂无法以业务摘要展示。' : '已提供建议，详情暂无法以业务摘要展示。')
}

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header"><div><p class="eyebrow">客服运营 · AI 质量</p><h1>AI 问题中心</h1><p>查看客服人工确认后、已完成分析的问题。这里的建议只供运营判断，不会自动修改 Prompt、知识或客户回复。</p></div><button class="button secondary" type="button" @click="load">刷新数据</button></div>
    <p class="notice trial-note">当前仅展示测试/试运行中已经完成的分析证据；未分析的问题不会被当作结果显示。</p>
    <p v-if="loading" class="notice" role="status">正在读取已分析问题…</p>
    <p v-else-if="error" class="notice error" role="alert">暂时无法读取 AI 问题。{{ error }}</p>
    <p v-else-if="results.length === 0" class="notice">{{ total === 0 ? '尚无已完成分析的 AI 问题。客服提交反馈并完成分析后，会在这里显示。' : '当前没有可展示的 AI 问题。请刷新后重试。' }}</p>
    <section v-else class="pool-grid">
      <div class="card table-wrap"><table class="data-table"><thead><tr><th>客户问题</th><th>问题类型</th><th>分析摘要</th><th>状态</th></tr></thead><tbody>
        <tr v-for="item in results" :key="`${item.feedback_id}-${item.revision}`"><td><button class="link-button" type="button" @click="choose(item)">{{ item.question }}</button></td><td><span class="badge">{{ displayStatus(item.feedback_type) }}</span></td><td class="analysis-cell">{{ analysisSummary(item) }}</td><td><span class="badge">{{ displayStatus(item.analysis_status) }}</span></td></tr>
      </tbody></table></div>
      <aside v-if="selected" class="card detail"><h2>问题与改进建议</h2><p><strong>客户问题</strong><br>{{ selected.question }}</p><p><strong>AI 原回复</strong><br>{{ selected.ai_answer }}</p><p><strong>人工处理</strong><br>{{ selected.final_answer || '未提供人工回复' }}</p><section class="summary-panel"><h3>分析摘要</h3><p>{{ analysisSummary(selected) }}</p><dl v-if="analysisReasons(selected).length"><div v-for="reason in analysisReasons(selected)" :key="reason.label"><dt>{{ reason.label }}</dt><dd>{{ reason.value }}</dd></div></dl></section><section class="suggestion-panel"><h3>建议下一步</h3><ul v-if="selected.suggestions.length"><li v-for="(suggestion, index) in selected.suggestions" :key="index">{{ suggestionSummary(suggestion) }}</li></ul><p v-else>本次分析没有返回结构化建议。请根据问题类型和人工核对流程处理。</p></section><details class="technical-details"><summary>技术详情</summary><dl><div><dt>证据版本</dt><dd>修订版本 {{ selected.revision }}</dd></div><div><dt>内容校验</dt><dd>{{ selected.content_hash }}</dd></div><div><dt>分析任务</dt><dd>{{ selected.analysis_run_id }}</dd></div><div><dt>模型 / 提示词版本</dt><dd>{{ selected.model_version }} / {{ selected.prompt_version }}</dd></div><div><dt>写入时间</dt><dd>{{ selected.created_at }}</dd></div></dl></details></aside>
      <aside v-else class="card detail"><h2>问题与改进建议</h2><p>选择一条已分析问题，查看业务摘要、原因和建议操作。</p></aside>
    </section>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }.trial-note { margin-bottom: 20px; color: #75570a; background: #fff8df; }.pool-grid { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(310px, 1fr); gap: 20px; }.detail { display: grid; align-content: start; gap: 14px; }.detail h2, .detail h3, .detail p { margin: 0; }.detail h2, .detail h3 { color: #172554; }.detail p { line-height: 1.6; overflow-wrap: anywhere; white-space: pre-wrap; }.link-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; text-align: left; cursor: pointer; }.analysis-cell { min-width: 220px; line-height: 1.55; }.summary-panel, .suggestion-panel { padding: 13px; border: 1px solid #dce5f1; border-radius: 10px; background: #f9fbfe; }.summary-panel dl { display: grid; gap: 8px; margin: 12px 0 0; }.summary-panel dt, .technical-details dt { color: #64748b; font-size: 13px; }.summary-panel dd, .technical-details dd { margin: 3px 0 0; overflow-wrap: anywhere; }.suggestion-panel ul { display: grid; gap: 9px; margin: 10px 0 0; padding-left: 20px; line-height: 1.55; }.technical-details { margin-top: 3px; border-top: 1px solid #e6edf5; color: #526279; font-size: 13px; }.technical-details summary { padding-top: 12px; cursor: pointer; }.technical-details dl { display: grid; gap: 8px; margin: 11px 0 0; }@media (max-width: 900px) { .pool-grid { grid-template-columns: 1fr; } }
</style>
