<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { formatEvidenceTime, summarizeAnalysis, technicalJson } from '../aiPresentation'
import { apiErrorMessage, listAiFeedbackAnalysisResults, type AiFeedbackAnalysisResult } from '../api/client'
import { displayStatus } from '../presentation'

const results = ref<AiFeedbackAnalysisResult[]>([])
const total = ref<number | null>(null)
const selected = ref<AiFeedbackAnalysisResult | null>(null)
const loading = ref(false)
const error = ref('')

const selectedSummary = computed(() => selected.value
  ? summarizeAnalysis(selected.value.analysis, selected.value.suggestions)
  : null)

function summaryFor(item: AiFeedbackAnalysisResult) {
  return summarizeAnalysis(item.analysis, item.suggestions)
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const response = await listAiFeedbackAnalysisResults()
    results.value = response.items
    total.value = response.total
    if (selected.value) {
      selected.value = response.items.find((item) => item.feedback_id === selected.value?.feedback_id) || null
    }
  } catch (reason: unknown) {
    results.value = []
    total.value = null
    selected.value = null
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

function choose(item: AiFeedbackAnalysisResult): void { selected.value = item }

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <h1>AI 问题</h1>
        <p>查看已经完成分析的客服反馈。页面只读展示分析证据，不会修改提示词、发布知识或执行任何业务动作。</p>
      </div>
      <button class="button secondary" type="button" @click="load">刷新数据</button>
    </div>

    <p class="notice trial-note">当前为测试 / 试运行数据观察。未分析的问题不会被显示成已完成的分析结果。</p>
    <p v-if="loading" class="notice" role="status">正在加载已分析问题…</p>
    <div v-else-if="error" class="notice error" role="alert">
      <strong>数据加载失败</strong><br />
      原因：{{ error }}<br />
      建议下一步：检查服务状态后重试；如仍失败，请联系平台管理员。
    </div>
    <p v-else-if="results.length === 0" class="notice">样本不足：{{ total === 0 ? '暂无已完成分析的 AI 问题。请等待分析结果回写。' : '暂无可展示数据。请刷新后重试。' }}</p>

    <section v-else class="pool-grid">
      <div class="card table-wrap">
        <table class="data-table">
          <thead><tr><th>客户问题</th><th>问题类型</th><th>AI 分析结论</th><th>当前状态</th><th>使用模型</th><th>提示词版本</th><th>分析时间</th></tr></thead>
          <tbody>
            <tr v-for="item in results" :key="`${item.feedback_id}-${item.revision}`">
              <td><button class="link-button" type="button" @click="choose(item)">{{ item.question || '未提供' }}</button></td>
              <td><span class="badge">{{ displayStatus(item.feedback_type) }}</span></td>
              <td class="summary-cell">{{ summaryFor(item).overview }}</td>
              <td><span class="badge">{{ displayStatus(item.analysis_status) }}</span></td>
              <td>{{ item.model_version || '未提供' }}</td>
              <td>{{ item.prompt_version || '未提供' }}</td>
              <td>{{ formatEvidenceTime(item.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <aside v-if="selected && selectedSummary" class="card detail">
        <h2>问题详情</h2>
        <p><strong>客户问题</strong><br />{{ selected.question || '未提供' }}</p>
        <p><strong>AI 回答</strong><br />{{ selected.ai_answer || '未提供' }}</p>
        <p><strong>人工回复</strong><br />{{ selected.final_answer || '未提供' }}</p>
        <dl class="business-summary">
          <div><dt>问题概述</dt><dd>{{ selectedSummary.overview }}</dd></div>
          <div><dt>AI 与人工差异</dt><dd>{{ selectedSummary.difference }}</dd></div>
          <div><dt>风险判断</dt><dd>{{ selectedSummary.risk }}</dd></div>
          <div><dt>建议动作</dt><dd>{{ selectedSummary.action }}</dd></div>
        </dl>
        <details class="technical-details">
          <summary>技术详情</summary>
          <dl>
            <div><dt>证据版本</dt><dd>修订版本 {{ selected.revision }}</dd></div>
            <div><dt>内容校验</dt><dd>{{ selected.content_hash || '未提供' }}</dd></div>
            <div><dt>分析任务</dt><dd>{{ selected.analysis_run_id || '未提供' }}</dd></div>
            <div><dt>模型 / 提示词版本</dt><dd>{{ selected.model_version || '未提供' }} / {{ selected.prompt_version || '未提供' }}</dd></div>
          </dl>
          <p class="technical-caption">原始分析证据</p>
          <pre>{{ technicalJson({ analysis: selected.analysis, suggestions: selected.suggestions }) }}</pre>
        </details>
      </aside>
    </section>
  </main>
</template>

<style scoped>
.trial-note { margin-bottom: 20px; color: #75570a; background: #fff8df; }
.pool-grid { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(320px, 1fr); gap: 20px; }
.detail { display: grid; align-content: start; gap: 13px; }
.detail h2, .detail p { margin: 0; }.detail h2 { color: #172554; }
.detail p, dd { line-height: 1.55; overflow-wrap: anywhere; white-space: pre-wrap; }
.link-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; text-align: left; cursor: pointer; }
.summary-cell { min-width: 180px; white-space: normal; }
.business-summary, .technical-details dl { display: grid; gap: 9px; margin: 0; }
.business-summary { padding: 13px; border-radius: 9px; background: #f6f8fc; }
dt { color: #64748b; font-size: 12px; font-weight: 700; } dd { margin: 3px 0 0; }
.technical-details { border-top: 1px solid #e6edf5; color: #526279; font-size: 13px; }
.technical-details summary { padding-top: 13px; cursor: pointer; }
.technical-caption { margin: 12px 0 7px !important; color: #64748b; font-size: 12px; }
pre { max-width: 100%; margin: 0; padding: 10px; overflow: auto; border-radius: 8px; background: #f4f7fb; font-size: 12px; white-space: pre-wrap; }
@media (max-width: 950px) { .pool-grid { grid-template-columns: 1fr; } }
</style>
