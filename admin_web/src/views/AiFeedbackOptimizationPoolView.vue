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
function formatted(value: unknown): string { return JSON.stringify(value, null, 2) }

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header"><div><h1>AI 问题中心</h1><p>查看已完成 AI 分析的客服问题与改进建议。页面只读，不提供提示词修改、知识发布或业务自动执行。</p></div><button class="button secondary" type="button" @click="load">刷新数据</button></div>
    <p class="notice trial-note">当前展示测试/试运行中的已分析问题；未分析的问题不会被错误展示为分析结果。</p>
    <p v-if="loading" class="notice" role="status">正在读取已分析问题…</p>
    <p v-else-if="error" class="notice error" role="alert">暂时无法读取优化建议。{{ error }}</p>
    <p v-else-if="results.length === 0" class="notice">样本不足：{{ total === 0 ? '尚无已完成分析的 AI 问题。请先等待分析结果回写。' : '未读取到可展示的问题。请刷新后重试。' }}</p>
    <section v-else class="pool-grid">
      <div class="card table-wrap"><table class="data-table"><thead><tr><th>客户问题</th><th>问题类型</th><th>分析结论</th><th>状态</th></tr></thead><tbody>
        <tr v-for="item in results" :key="`${item.feedback_id}-${item.revision}`"><td><button class="link-button" type="button" @click="choose(item)">{{ item.question }}</button></td><td><span class="badge">{{ displayStatus(item.feedback_type) }}</span></td><td class="analysis-cell">{{ formatted(item.analysis) }}</td><td><span class="badge">{{ displayStatus(item.analysis_status) }}</span></td></tr>
      </tbody></table></div>
      <aside v-if="selected" class="card detail"><h2>问题详情</h2><p><strong>客户问题</strong><br>{{ selected.question }}</p><p><strong>AI 回答</strong><br>{{ selected.ai_answer }}</p><p><strong>人工回复</strong><br>{{ selected.final_answer || '未提供人工回复' }}</p><p><strong>AI 分析</strong></p><pre>{{ formatted(selected.analysis) }}</pre><p><strong>改进建议</strong></p><pre>{{ formatted(selected.suggestions) }}</pre><details class="technical-details"><summary>技术信息</summary><dl><div><dt>证据版本</dt><dd>修订版本 {{ selected.revision }}</dd></div><div><dt>内容校验</dt><dd>{{ selected.content_hash }}</dd></div><div><dt>分析任务</dt><dd>{{ selected.analysis_run_id }}</dd></div><div><dt>模型 / 提示词版本</dt><dd>{{ selected.model_version }} / {{ selected.prompt_version }}</dd></div><div><dt>写入时间</dt><dd>{{ selected.created_at }}</dd></div></dl></details></aside>
      <aside v-else class="card detail"><h2>问题详情</h2><p>选择一条已分析问题，查看客服反馈与 AI 分析证据。</p></aside>
    </section>
  </main>
</template>

<style scoped>
.trial-note { margin-bottom: 20px; color: #75570a; background: #fff8df; }.pool-grid { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(310px, 1fr); gap: 20px; }.detail { display: grid; align-content: start; gap: 12px; }.detail h2, .detail p { margin: 0; }.detail h2 { color: #172554; }.detail p { line-height: 1.55; overflow-wrap: anywhere; white-space: pre-wrap; }.link-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; text-align: left; cursor: pointer; }.analysis-cell { min-width: 200px; white-space: pre-wrap; }pre { max-width: 100%; margin: 0; padding: 10px; overflow: auto; border-radius: 8px; background: #f4f7fb; font-size: 12px; white-space: pre-wrap; }.technical-details { margin-top: 3px; border-top: 1px solid #e6edf5; color: #526279; font-size: 13px; }.technical-details summary { padding-top: 12px; cursor: pointer; }.technical-details dl { display: grid; gap: 8px; margin: 11px 0 0; }.technical-details dt { color: #64748b; }.technical-details dd { margin: 2px 0 0; overflow-wrap: anywhere; }@media (max-width: 900px) { .pool-grid { grid-template-columns: 1fr; } }
</style>
