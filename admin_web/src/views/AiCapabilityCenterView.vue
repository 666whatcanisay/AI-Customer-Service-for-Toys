<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  apiErrorMessage,
  getAiControlCenterOverview,
  type AiControlCenterOverview,
} from '../api/client'
import { displayPassRate, displayStatus } from '../presentation'

const overview = ref<AiControlCenterOverview | null>(null)
const loading = ref(false)
const error = ref('')

const serviceSummary = computed(() => {
  const value = overview.value
  if (!value) return '暂无法读取'
  if (value.service.ready === true && value.service.modelConfigured === true && value.service.status === 'RUNNING') return '已就绪'
  if (value.service.status === 'PAUSED') return '已暂停'
  if (value.service.status === 'ERROR') return '需要处理'
  return '尚未就绪'
})

const modelSummary = computed(() => {
  const value = overview.value
  if (!value || value.model.configured !== true) return '尚未配置'
  return value.model.name || '已配置，名称暂无法读取'
})

const knowledgeSummary = computed(() => {
  const knowledge = overview.value?.knowledge
  if (!knowledge) return '暂无法读取'
  if (knowledge.status !== 'AVAILABLE') return '当前不可查询'
  if (knowledge.queryableChunkCount === null) return '可查询，数量暂无法读取'
  return `可查询 ${knowledge.queryableChunkCount} 条知识片段`
})

const evaluationSummary = computed(() => {
  const latest = overview.value?.latestEvaluation
  if (!latest || latest.status !== 'AVAILABLE' || !latest.evaluation) return '暂无已保存评测'
  if (latest.evaluation.passRate === null) return '已有评测，结果暂无法读取'
  return `通过率 ${displayPassRate(latest.evaluation.passRate)}`
})

function displayValue(value: string | number | null): string {
  return value === null || value === '' ? '暂无法读取' : String(value)
}

function formatDate(value: string | null): string {
  if (!value) return '暂无法读取'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

async function load(): Promise<void> {
  if (loading.value) return
  loading.value = true
  error.value = ''
  overview.value = null
  try {
    overview.value = await getAiControlCenterOverview()
  } catch (reason: unknown) {
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

onMounted(() => { void load() })
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">AI 运营 · 只读控制面</p>
        <h1>AI状态</h1>
        <p>查看真实模型、知识和运行状态；本页不提供模型切换、提示词修改、知识发布或客户业务自动化。</p>
      </div>
      <button class="button secondary" type="button" :disabled="loading" @click="load">{{ loading ? '刷新中…' : '刷新状态' }}</button>
    </div>

    <p v-if="loading" class="notice" role="status">正在读取 AI状态…</p>
    <section v-else-if="error" class="card unavailable" role="alert">
      <h2>AI 服务尚未就绪</h2>
      <p>{{ error }}</p>
      <p>请先检查本机 A 服务和模型配置；资料质量、客服运营等 C 端页面仍可独立使用。</p>
    </section>

    <template v-else-if="overview">
      <section class="summary-grid" aria-label="AI 运行摘要">
        <article class="summary-card">
          <span>AI 服务</span>
          <strong>{{ serviceSummary }}</strong>
          <small>当前状态：{{ displayStatus(overview.service.status, '暂无法读取') }}</small>
        </article>
        <article class="summary-card">
          <span>当前模型</span>
          <strong>{{ modelSummary }}</strong>
          <small>提供方：{{ displayValue(overview.model.provider) }}</small>
        </article>
        <article class="summary-card">
          <span>知识状态</span>
          <strong>{{ knowledgeSummary }}</strong>
          <small>仅代表 A 当前可查询集合，不代表资料已自动发布。</small>
        </article>
        <article class="summary-card">
          <span>最近评测</span>
          <strong>{{ evaluationSummary }}</strong>
          <small>只显示已保存评测，不以空结果伪装失败。</small>
        </article>
      </section>

      <section class="content-grid">
        <article class="card runtime-card">
          <div class="section-heading">
            <div>
              <h2>模型观察</h2>
              <p>指标仅从本次服务启动后累计，不是客服绩效或历史运营报表。</p>
            </div>
            <span class="badge">{{ displayValue(overview.runtime.metricsScope) }}</span>
          </div>
          <div v-if="overview.runtime.metricsScope === 'since_start'" class="runtime-metrics">
            <div><span>调用次数</span><strong>{{ displayValue(overview.runtime.callCount) }}</strong></div>
            <div><span>成功次数</span><strong>{{ displayValue(overview.runtime.successCount) }}</strong></div>
            <div><span>异常次数</span><strong>{{ displayValue(overview.runtime.errorCount) }}</strong></div>
            <div><span>平均响应</span><strong>{{ overview.runtime.averageLatencyMs === null ? '暂无法读取' : `${overview.runtime.averageLatencyMs} ms` }}</strong></div>
          </div>
          <p v-else class="notice">当前服务未提供启动后的运行指标。</p>
          <p class="last-called">最近调用：{{ formatDate(overview.runtime.lastCalledAt) }}</p>
        </article>

        <article class="card evaluation-card">
          <h2>评测概览</h2>
          <template v-if="overview.latestEvaluation.status === 'AVAILABLE' && overview.latestEvaluation.evaluation">
            <dl>
              <div><dt>评测时间</dt><dd>{{ formatDate(overview.latestEvaluation.evaluation.executedAt) }}</dd></div>
              <div><dt>覆盖用例</dt><dd>{{ displayValue(overview.latestEvaluation.evaluation.totalCases) }}</dd></div>
              <div><dt>通过用例</dt><dd>{{ displayValue(overview.latestEvaluation.evaluation.passedCases) }}</dd></div>
              <div><dt>通过率</dt><dd>{{ overview.latestEvaluation.evaluation.passRate === null ? '暂无法读取' : displayPassRate(overview.latestEvaluation.evaluation.passRate) }}</dd></div>
            </dl>
          </template>
          <p v-else class="notice">暂无已保存评测。这不代表评测失败，也不会自动触发新的评测。</p>
          <RouterLink class="text-link" to="/ai-optimization-pool">查看已有评测记录</RouterLink>
        </article>
      </section>

      <section class="workbench-links" aria-label="AI 运营工作区">
        <RouterLink to="/knowledge-quality-pool" class="workbench-link"><strong>知识质量中心</strong><span>查看资料完整度、待补充项和人工审核后的分析结果。</span></RouterLink>
        <RouterLink to="/ai-feedback-optimization-pool" class="workbench-link"><strong>AI 问题中心</strong><span>查看客服已确认问题的原因、建议和分析状态。</span></RouterLink>
        <span class="workbench-link planned"><strong>模型策略管理</strong><span>规划中；当前不提供模型切换或提示词修改。</span></span>
      </section>

      <details class="technical-details">
        <summary>技术详情</summary>
        <dl>
          <div><dt>模块标识</dt><dd>{{ overview.moduleId }}</dd></div>
          <div><dt>知识范围</dt><dd>{{ displayValue(overview.knowledge.scope) }}</dd></div>
          <div><dt>提示词版本</dt><dd>{{ displayValue(overview.technical.promptVersion) }}</dd></div>
          <div><dt>提示词校验</dt><dd>{{ displayValue(overview.technical.promptHash) }}</dd></div>
          <div><dt>初始化状态</dt><dd>{{ displayValue(overview.service.initializationError) }}</dd></div>
          <div><dt>最近异常摘要</dt><dd>{{ displayValue(overview.runtime.lastErrorSummary) }}</dd></div>
        </dl>
      </details>
    </template>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.unavailable { border-left: 5px solid #c77a16; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.summary-card { display: grid; gap: 7px; min-height: 145px; padding: 18px; border: 1px solid #d9e4f1; border-radius: 14px; background: linear-gradient(145deg, #fff, #f5f9ff); }
.summary-card span, .summary-card small, .section-heading p, .last-called { color: #617087; font-size: 13px; line-height: 1.55; }
.summary-card strong { color: #172554; font-size: 18px; overflow-wrap: anywhere; }
.content-grid { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(280px, .9fr); gap: 20px; margin-top: 20px; }
.section-heading { display: flex; justify-content: space-between; gap: 12px; align-items: start; }
.section-heading h2, .evaluation-card h2 { margin: 0; color: #172554; }
.section-heading p { margin: 6px 0 0; }
.runtime-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 18px 0; }
.runtime-metrics div { padding: 12px; border-radius: 10px; background: #f5f8fd; }
.runtime-metrics span { display: block; color: #617087; font-size: 12px; }
.runtime-metrics strong { display: block; margin-top: 6px; color: #172554; font-size: 18px; overflow-wrap: anywhere; }
.last-called { margin: 0; }
dl { display: grid; gap: 11px; margin: 18px 0; }
dt { color: #617087; font-size: 13px; }
dd { margin: 3px 0 0; overflow-wrap: anywhere; }
.text-link { color: #285493; font-weight: 700; text-decoration: none; }
.workbench-links { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 20px; }
.workbench-link { display: grid; gap: 8px; min-height: 112px; padding: 16px; border: 1px solid #dbe4ef; border-radius: 12px; color: #25466f; background: #fff; text-decoration: none; }
.workbench-link strong { color: #172554; }
.workbench-link span { color: #617087; font-size: 13px; line-height: 1.55; }
.workbench-link.planned { color: #718096; background: #fafbfc; }
.technical-details { margin-top: 20px; padding: 16px 20px; border: 1px solid #dae5f1; border-radius: 12px; color: #526279; background: #f8fbff; }
.technical-details summary { cursor: pointer; font-weight: 700; }
.technical-details dl { grid-template-columns: repeat(3, minmax(0, 1fr)); margin-bottom: 0; }
.technical-details dd { color: #2d4364; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
@media (max-width: 1040px) { .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .runtime-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 820px) { .content-grid, .workbench-links { grid-template-columns: 1fr; } .technical-details dl { grid-template-columns: 1fr; } }
</style>
