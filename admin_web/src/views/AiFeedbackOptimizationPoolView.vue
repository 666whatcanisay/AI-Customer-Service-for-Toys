<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { apiErrorMessage, listAiFeedbackAnalysisResults, type AiFeedbackAnalysisResult } from '../api/client'
import { displayStatus } from '../presentation'

const results = ref<AiFeedbackAnalysisResult[]>([])
const total = ref<number | null>(null)
const selected = ref<AiFeedbackAnalysisResult | null>(null)
const loading = ref(false)
const error = ref('')

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
function formatJson(value: unknown): string { return JSON.stringify(value, null, 2) }

function readableSummary(value: unknown, empty = '已记录结构化结果，请展开原始记录查看。'): string {
  if (typeof value === 'string' && value.trim()) return value
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return empty
  const record = value as Record<string, unknown>
  for (const key of ['summary', 'conclusion', 'outcome', 'reason', 'category']) {
    if (typeof record[key] === 'string' && record[key].trim()) return record[key] as string
  }
  return empty
}

function readableSuggestions(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => readableSummary(item, '')).filter(Boolean)
}

function formatTime(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(parsed)
}

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">客服运营 / AI 问题与分析</p>
        <h1>AI 问题与分析</h1>
        <p>只展示已完成并回写的客服 AI 问题分析。分析用于人工优化判断，不会自动修改 Prompt、发布知识或执行客户业务。</p>
      </div>
      <button class="button secondary" type="button" :disabled="loading" @click="load">{{ loading ? '刷新中…' : '刷新数据' }}</button>
    </div>
    <p class="notice trial-note">试运行说明：未分析或未确认的问题不会被显示为分析结论；没有数据时页面会明确提示，而不是生成默认建议。</p>
    <p v-if="loading" class="notice" role="status">正在读取已分析问题…</p>
    <p v-else-if="error" class="notice error" role="alert">暂时无法读取 AI 问题与分析：{{ error }}</p>
    <p v-else-if="results.length === 0" class="notice">{{ total === 0 ? '暂无已完成分析的 AI 问题。请先等待经人工确认的问题完成分析回写。' : '未读取到可展示的分析结果。请刷新后重试。' }}</p>
    <section v-else class="pool-grid">
      <div class="card table-wrap">
        <table class="data-table">
          <thead><tr><th>客户问题</th><th>问题类型</th><th>分析摘要</th><th>状态</th></tr></thead>
          <tbody>
            <tr v-for="item in results" :key="`${item.feedback_id}-${item.revision}`">
              <td><button class="link-button" type="button" @click="choose(item)">{{ item.question }}</button><small>{{ formatTime(item.created_at) }}</small></td>
              <td><span class="badge">{{ displayStatus(item.feedback_type) }}</span></td>
              <td class="summary-cell">{{ readableSummary(item.analysis) }}</td>
              <td><span class="badge">{{ displayStatus(item.analysis_status) }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <aside v-if="selected" class="card detail">
        <div class="section-title"><div><p class="eyebrow">分析记录</p><h2>问题详情</h2></div><span class="badge">{{ displayStatus(selected.analysis_status) }}</span></div>
        <dl class="content-facts">
          <div><dt>客户问题</dt><dd>{{ selected.question }}</dd></div>
          <div><dt>AI 原回答</dt><dd>{{ selected.ai_answer }}</dd></div>
          <div><dt>人工最终回复</dt><dd>{{ selected.final_answer || '未提供人工最终回复。' }}</dd></div>
          <div><dt>问题类型</dt><dd>{{ displayStatus(selected.feedback_type) }}</dd></div>
          <div><dt>AI 分析摘要</dt><dd>{{ readableSummary(selected.analysis) }}</dd></div>
        </dl>
        <section class="recommendations"><h3>优化建议</h3><ul v-if="readableSuggestions(selected.suggestions).length"><li v-for="item in readableSuggestions(selected.suggestions)" :key="item">{{ item }}</li></ul><p v-else class="muted">分析记录没有提供可直接展示的建议文本；可在技术信息中查看原始结构化记录。</p></section>
        <details class="technical-details"><summary>技术信息与原始结构化记录</summary><dl class="technical-facts"><div><dt>分析任务</dt><dd>{{ selected.analysis_run_id }}</dd></div><div><dt>模型 / Prompt</dt><dd>{{ selected.model_version }} / {{ selected.prompt_version }}</dd></div><div><dt>证据版本</dt><dd>修订 {{ selected.revision }}</dd></div><div><dt>内容校验</dt><dd>{{ selected.content_hash }}</dd></div></dl><pre>{{ formatJson({ analysis: selected.analysis, suggestions: selected.suggestions }) }}</pre></details>
      </aside>
      <aside v-else class="card detail"><h2>问题详情</h2><p>选择一条已分析问题，查看客服反馈、分析摘要和可追溯证据。</p></aside>
    </section>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }.trial-note { margin-bottom: 20px; color: #75570a; background: #fff8df; }.pool-grid { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(320px, 1fr); gap: 20px; }.detail { display: grid; align-content: start; gap: 14px; }.section-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }.detail h2, .recommendations h3 { margin: 0; color: #172554; }.link-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; text-align: left; cursor: pointer; }.summary-cell { min-width: 220px; line-height: 1.55; }.content-facts, .technical-facts { display: grid; gap: 11px; margin: 0; }.content-facts dt, .technical-facts dt { color: #64748b; font-size: 12px; font-weight: 700; }.content-facts dd, .technical-facts dd { margin: 3px 0 0; overflow-wrap: anywhere; line-height: 1.55; white-space: pre-wrap; }.recommendations { padding: 14px; border-radius: 10px; background: #f5f8fc; }.recommendations ul { margin: 9px 0 0; padding-left: 20px; }.recommendations li { margin-bottom: 7px; line-height: 1.55; }.muted, small { color: #64748b; font-size: 12px; line-height: 1.55; }.technical-details { border-top: 1px solid #e6edf5; color: #526279; font-size: 13px; }.technical-details summary { padding-top: 12px; cursor: pointer; }.technical-details pre { max-height: 250px; overflow: auto; padding: 10px; border-radius: 8px; background: #f4f7fb; font-size: 12px; white-space: pre-wrap; }
@media (max-width: 900px) { .pool-grid { grid-template-columns: 1fr; } }
</style>
